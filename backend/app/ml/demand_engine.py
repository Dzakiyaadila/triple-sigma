from __future__ import annotations

from dataclasses import dataclass

import numpy as np
import pandas as pd

from app.ml.artifact_store import ModelArtifacts
from app.ml.contracts import RetailSnapshot
from app.ml.feature_engineering import (
    prepare_forecast_frame,
    prepare_matrix,
    prepare_reconstruction_frame,
    snapshot_to_frame,
)


@dataclass(frozen=True)
class QuantileForecast:
    horizon_days: int
    q10: float
    q50: float
    q90: float


@dataclass(frozen=True)
class SKUForecast:
    sku_id: str
    selected_horizon: QuantileForecast
    forecasts: dict[int, QuantileForecast]
    history_days: int
    reconstructed_units: float
    confidence: str
    warnings: tuple[str, ...]


@dataclass(frozen=True)
class DemandForecastResult:
    model_version: str
    data_hash: str
    store_id: str
    decision_date: str
    horizon_days: int
    forecasts: tuple[SKUForecast, ...]


def enforce_quantile_order(
    q10: np.ndarray,
    q50: np.ndarray,
    q90: np.ndarray,
) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
    stacked = np.column_stack(
        [
            np.clip(q10, 0, None),
            np.clip(q50, 0, None),
            np.clip(q90, 0, None),
        ]
    )

    ordered = np.sort(stacked, axis=1)

    return (
        ordered[:, 0],
        ordered[:, 1],
        ordered[:, 2],
    )


def _confidence(
    history_days: int,
) -> tuple[str, tuple[str, ...]]:
    if history_days >= 90:
        return "tinggi", ()

    if history_days >= 30:
        return (
            "sedang",
            (
                "Histori SKU kurang dari 90 hari; "
                "ketidakpastian lebih tinggi.",
            ),
        )

    return (
        "rendah",
        (
            "Histori SKU kurang dari 30 hari; "
            "gunakan rekomendasi dengan kehati-hatian.",
        ),
    )


def generate_demand_forecasts(
    snapshot: RetailSnapshot,
    artifacts: ModelArtifacts,
    *,
    horizon_days: int,
) -> DemandForecastResult:
    if horizon_days not in artifacts.forecast_artifacts:
        supported = sorted(
            artifacts.forecast_artifacts
        )

        raise ValueError(
            f"Horizon {horizon_days} belum didukung. "
            f"Supported={supported}"
        )

    raw_frame = snapshot_to_frame(snapshot)

    reconstruction_frame = (
        prepare_reconstruction_frame(
            raw_frame,
            artifacts.category_maps,
        )
    )

    reconstruction_matrix, _ = prepare_matrix(
        reconstruction_frame,
        artifacts.reconstruction_feature_columns,
        artifacts.reconstruction_medians,
    )

    reconstructed_prediction = np.clip(
        artifacts.reconstruction_model.predict(
            reconstruction_matrix
        ),
        0,
        None,
    )

    reconstruction_frame["reconstructed_demand"] = (
        np.where(
            reconstruction_frame[
                "historical_stockout_flag"
            ],
            np.maximum(
                reconstruction_frame["units_sold"],
                reconstructed_prediction,
            ),
            reconstruction_frame["units_sold"],
        )
    )

    forecast_frame = prepare_forecast_frame(
        reconstruction_frame,
        artifacts.category_maps,
    )

    latest_rows = (
        forecast_frame
        .sort_values(
            ["store_id", "sku_id", "date"],
            kind="stable",
        )
        .groupby(
            ["store_id", "sku_id"],
            as_index=False,
            sort=False,
        )
        .tail(1)
        .sort_values("sku_id")
        .reset_index(drop=True)
    )

    product_ids = {
        product.sku_id
        for product in snapshot.products
    }

    available_ids = set(
        latest_rows["sku_id"].astype(str)
    )

    missing_ids = product_ids - available_ids

    if missing_ids:
        raise ValueError(
            "Tidak ada inference row untuk SKU: "
            f"{sorted(missing_ids)}"
        )

    horizon_predictions: dict[
        int,
        tuple[np.ndarray, np.ndarray, np.ndarray],
    ] = {}

    for horizon, artifact in sorted(
        artifacts.forecast_artifacts.items()
    ):
        matrix, _ = prepare_matrix(
            latest_rows,
            artifact.feature_columns,
            artifact.medians,
        )

        raw_q10 = np.asarray(
            artifact.quantile_models[0.10].predict(
                matrix
            ),
            dtype=float,
        )

        raw_q50 = np.asarray(
            artifact.quantile_models[0.50].predict(
                matrix
            ),
            dtype=float,
        )

        raw_q90 = np.asarray(
            artifact.quantile_models[0.90].predict(
                matrix
            ),
            dtype=float,
        )

        calibrated_q10 = np.clip(
            raw_q10 - artifact.calibration_radius,
            0,
            None,
        )

        calibrated_q90 = (
            raw_q90 + artifact.calibration_radius
        )

        horizon_predictions[horizon] = (
            enforce_quantile_order(
                calibrated_q10,
                raw_q50,
                calibrated_q90,
            )
        )

    history_counts = (
        raw_frame.groupby("sku_id")["date"]
        .nunique()
        .to_dict()
    )

    sku_forecasts: list[SKUForecast] = []

    for row_index, row in latest_rows.iterrows():
        sku_id = str(row["sku_id"])
        all_horizons: dict[int, QuantileForecast] = {}

        for horizon, predictions in (
            horizon_predictions.items()
        ):
            q10, q50, q90 = predictions

            all_horizons[horizon] = (
                QuantileForecast(
                    horizon_days=horizon,
                    q10=float(q10[row_index]),
                    q50=float(q50[row_index]),
                    q90=float(q90[row_index]),
                )
            )

        history_days = int(
            history_counts.get(sku_id, 0)
        )

        confidence, warnings = _confidence(
            history_days
        )

        sku_forecasts.append(
            SKUForecast(
                sku_id=sku_id,
                selected_horizon=all_horizons[
                    horizon_days
                ],
                forecasts=all_horizons,
                history_days=history_days,
                reconstructed_units=float(
                    row["reconstructed_demand"]
                ),
                confidence=confidence,
                warnings=warnings,
            )
        )

    return DemandForecastResult(
        model_version=artifacts.version,
        data_hash=snapshot.data_hash(),
        store_id=snapshot.store_id,
        decision_date=(
            snapshot.decision_date.isoformat()
        ),
        horizon_days=horizon_days,
        forecasts=tuple(sku_forecasts),
    )
