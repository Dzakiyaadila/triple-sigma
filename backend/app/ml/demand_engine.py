from __future__ import annotations

from dataclasses import dataclass

import numpy as np
import pandas as pd

from app.ml.artifact_store import ModelArtifacts
from app.ml.contracts import RetailSnapshot
from app.ml.feature_engineering import (
    add_forecast_features,
    add_reconstruction_features,
    prepare_matrix,
    snapshot_to_frame,
)
from app.ml.oracle_guard import assert_oracle_safe_payload


class DemandInferenceError(ValueError):
    pass


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
    latest_observation_date: str
    confidence: str
    warnings: tuple[str, ...]


@dataclass(frozen=True)
class DemandForecastResult:
    model_version: str
    data_hash: str
    dataset_id: str
    store_id: str
    decision_date: str
    horizon_days: int
    forecasts: tuple[SKUForecast, ...]
    warnings: tuple[str, ...]


def enforce_quantile_order(
    q10: np.ndarray,
    q50: np.ndarray,
    q90: np.ndarray,
) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
    ordered = np.sort(
        np.column_stack(
            [
                np.clip(q10, 0, None),
                np.clip(q50, 0, None),
                np.clip(q90, 0, None),
            ]
        ),
        axis=1,
    )
    return ordered[:, 0], ordered[:, 1], ordered[:, 2]


def _confidence(history_days: int, stale_days: int) -> tuple[str, tuple[str, ...]]:
    warnings: list[str] = []
    if stale_days > 0:
        warnings.append(
            f"Observasi terakhir SKU tertinggal {stale_days} hari dari decision date."
        )

    if history_days >= 90 and stale_days == 0:
        return "tinggi", tuple(warnings)
    if history_days >= 30 and stale_days <= 1:
        warnings.append("Histori SKU kurang dari 90 hari; interval lebih tidak pasti.")
        return "sedang", tuple(warnings)

    warnings.append("Histori SKU terbatas; gunakan rekomendasi dengan kehati-hatian.")
    return "rendah", tuple(warnings)


def generate_demand_forecasts(
    snapshot: RetailSnapshot,
    artifacts: ModelArtifacts,
    *,
    horizon_days: int,
) -> DemandForecastResult:
    assert_oracle_safe_payload(snapshot)
    if horizon_days not in artifacts.forecasts:
        raise DemandInferenceError(
            f"Horizon {horizon_days} tidak didukung; "
            f"supported={sorted(artifacts.forecasts)}"
        )

    raw = snapshot_to_frame(snapshot)
    reconstruction_frame = add_reconstruction_features(raw)
    recon_x, _ = prepare_matrix(
        reconstruction_frame,
        artifacts.reconstruction_feature_columns,
        artifacts.reconstruction_medians,
    )
    recon_prediction = np.clip(
        artifacts.reconstruction_model.predict(recon_x), 0, None
    )

    reconstructed = reconstruction_frame.copy()
    reconstructed["reconstructed_demand"] = np.clip(
        np.where(
            reconstructed["stockout_flag"].astype(bool),
            np.maximum(reconstructed["units_sold"].to_numpy(float), recon_prediction),
            reconstructed["units_sold"].to_numpy(float),
        ),
        0,
        None,
    )
    forecast_frame = add_forecast_features(reconstructed)

    latest_rows = (
        forecast_frame.sort_values(["store_id", "sku_id", "date"], kind="stable")
        .groupby(["store_id", "sku_id"], sort=False, as_index=False)
        .tail(1)
        .sort_values("sku_id")
        .reset_index(drop=True)
    )

    expected_skus = {product.sku_id for product in snapshot.products}
    available_skus = set(latest_rows["sku_id"].astype(str))
    missing_skus = expected_skus - available_skus
    if missing_skus:
        raise DemandInferenceError(
            f"Tidak ada histori inference untuk SKU: {sorted(missing_skus)}"
        )

    horizon_predictions: dict[int, tuple[np.ndarray, np.ndarray, np.ndarray]] = {}
    for horizon, artifact in sorted(artifacts.forecasts.items()):
        matrix, _ = prepare_matrix(
            latest_rows, artifact.feature_columns, artifact.medians
        )
        raw_q10 = np.asarray(artifact.quantile_models[0.10].predict(matrix), dtype=float)
        raw_q50 = np.asarray(artifact.quantile_models[0.50].predict(matrix), dtype=float)
        raw_q90 = np.asarray(artifact.quantile_models[0.90].predict(matrix), dtype=float)
        horizon_predictions[horizon] = enforce_quantile_order(
            np.clip(raw_q10 - artifact.calibration_adjustment, 0, None),
            raw_q50,
            raw_q90 + artifact.calibration_adjustment,
        )

    history_counts = raw.groupby("sku_id")["date"].nunique().to_dict()
    forecasts: list[SKUForecast] = []
    global_warnings = list(snapshot.warnings)

    for row_index, row in latest_rows.iterrows():
        sku_id = str(row["sku_id"])
        latest_date = pd.Timestamp(row["date"]).date()
        stale_days = max(0, (snapshot.decision_date - latest_date).days)
        history_days = int(history_counts.get(sku_id, 0))
        confidence, warnings = _confidence(history_days, stale_days)

        per_horizon: dict[int, QuantileForecast] = {}
        for horizon, values in horizon_predictions.items():
            q10, q50, q90 = values
            per_horizon[horizon] = QuantileForecast(
                horizon_days=horizon,
                q10=float(q10[row_index]),
                q50=float(q50[row_index]),
                q90=float(q90[row_index]),
            )

        forecasts.append(
            SKUForecast(
                sku_id=sku_id,
                selected_horizon=per_horizon[horizon_days],
                forecasts=per_horizon,
                history_days=history_days,
                latest_observation_date=latest_date.isoformat(),
                confidence=confidence,
                warnings=warnings,
            )
        )

    return DemandForecastResult(
        model_version=artifacts.version,
        data_hash=snapshot.data_hash(),
        dataset_id=snapshot.dataset_id,
        store_id=snapshot.store_id,
        decision_date=snapshot.decision_date.isoformat(),
        horizon_days=horizon_days,
        forecasts=tuple(forecasts),
        warnings=tuple(global_warnings),
    )
