from __future__ import annotations

import argparse
import hashlib
import json
from datetime import date, datetime, timezone
from pathlib import Path
from typing import Any

import lightgbm as lgb
import numpy as np
import pandas as pd
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db.models import Store
from app.db.session import engine
from app.ml.artifact_store import DEFAULT_ARTIFACT_DIR
from app.ml.feature_engineering import (
    FORECAST_FEATURES,
    RECONSTRUCTION_FEATURES,
    add_forward_target,
    fit_category_maps,
    prepare_forecast_frame,
    prepare_matrix,
    prepare_reconstruction_frame,
    snapshots_to_frame,
)
from app.services.retail_snapshot_service import (
    build_retail_snapshot,
)


SEED = 20260723
HORIZONS = (1, 7, 14)
QUANTILES = (0.10, 0.50, 0.90)


def _model_parameters(
    *,
    objective: str,
    alpha: float | None = None,
    n_estimators: int = 220,
) -> dict[str, Any]:
    parameters: dict[str, Any] = {
        "objective": objective,
        "n_estimators": n_estimators,
        "learning_rate": 0.035,
        "num_leaves": 23,
        "min_child_samples": 40,
        "subsample": 0.90,
        "subsample_freq": 1,
        "colsample_bytree": 0.90,
        "reg_alpha": 0.50,
        "reg_lambda": 5.00,
        "random_state": SEED,
        "n_jobs": -1,
        "verbosity": -1,
    }

    if alpha is not None:
        parameters["alpha"] = alpha

    return parameters


def _fit_final_model(
    *,
    features: pd.DataFrame,
    target: pd.Series,
    dates: pd.Series,
    objective: str,
    alpha: float | None = None,
) -> lgb.LGBMRegressor:
    unique_dates = sorted(
        pd.to_datetime(dates).dropna().unique()
    )

    if len(unique_dates) < 28:
        raise ValueError(
            "Training data membutuhkan minimal 28 tanggal"
        )

    validation_start = pd.Timestamp(
        unique_dates[-min(21, len(unique_dates) // 4)]
    )

    train_mask = pd.to_datetime(dates) < validation_start
    valid_mask = ~train_mask

    provisional = lgb.LGBMRegressor(
        **_model_parameters(
            objective=objective,
            alpha=alpha,
        )
    )

    provisional.fit(
        features.loc[train_mask],
        target.loc[train_mask],
        eval_set=[
            (
                features.loc[valid_mask],
                target.loc[valid_mask],
            )
        ],
        callbacks=[
            lgb.early_stopping(
                stopping_rounds=30,
                verbose=False,
            ),
            lgb.log_evaluation(period=0),
        ],
    )

    best_iteration = int(
        provisional.best_iteration_
        or provisional.n_estimators
    )

    final_model = lgb.LGBMRegressor(
        **_model_parameters(
            objective=objective,
            alpha=alpha,
            n_estimators=best_iteration,
        )
    )

    final_model.fit(features, target)

    return final_model


def _calibration_radius(
    y_true: np.ndarray,
    q10: np.ndarray,
    q90: np.ndarray,
) -> float:
    q_low = np.minimum(q10, q90)
    q_high = np.maximum(q10, q90)

    nonconformity = np.maximum.reduce(
        [
            q_low - y_true,
            y_true - q_high,
            np.zeros_like(y_true),
        ]
    )

    return float(
        np.quantile(nonconformity, 0.80)
    )


def _training_hash(
    *,
    snapshot_hashes: dict[str, str],
    decision_date_value: date,
) -> str:
    payload = json.dumps(
        {
            "snapshot_hashes": snapshot_hashes,
            "decision_date": (
                decision_date_value.isoformat()
            ),
            "seed": SEED,
            "horizons": HORIZONS,
            "quantiles": QUANTILES,
        },
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")

    return hashlib.sha256(payload).hexdigest()


def train_artifacts(
    *,
    decision_date_value: date,
    lookback_days: int,
    artifact_dir: Path,
) -> dict[str, Any]:
    artifact_dir.mkdir(
        parents=True,
        exist_ok=True,
    )

    with Session(engine) as db:
        store_ids = list(
            db.scalars(
                select(Store.store_id)
                .order_by(Store.store_id)
            )
        )

        if not store_ids:
            raise ValueError(
                "Tidak ada toko pada database"
            )

        snapshots = [
            build_retail_snapshot(
                db,
                store_id=store_id,
                decision_date=decision_date_value,
                horizon_days=7,
                lookback_days=lookback_days,
            )
            for store_id in store_ids
        ]

    snapshot_hashes = {
        snapshot.store_id: snapshot.data_hash()
        for snapshot in snapshots
    }

    training_data_hash = _training_hash(
        snapshot_hashes=snapshot_hashes,
        decision_date_value=decision_date_value,
    )

    raw_frame = snapshots_to_frame(snapshots)
    category_maps = fit_category_maps(raw_frame)

    reconstruction_frame = (
        prepare_reconstruction_frame(
            raw_frame,
            category_maps,
        )
    )

    reconstruction_training = (
        reconstruction_frame.loc[
            ~reconstruction_frame[
                "historical_stockout_flag"
            ]
        ]
        .copy()
    )

    reconstruction_matrix, reconstruction_medians = (
        prepare_matrix(
            reconstruction_training,
            RECONSTRUCTION_FEATURES,
        )
    )

    reconstruction_target = (
        reconstruction_training["units_sold"]
        .clip(lower=0)
        .astype(float)
    )

    reconstruction_model = _fit_final_model(
        features=reconstruction_matrix,
        target=reconstruction_target,
        dates=reconstruction_training["date"],
        objective="poisson",
    )

    reconstruction_file = "reconstruction_poisson.txt"

    reconstruction_model.booster_.save_model(
        str(artifact_dir / reconstruction_file)
    )

    all_reconstruction_matrix, _ = prepare_matrix(
        reconstruction_frame,
        RECONSTRUCTION_FEATURES,
        reconstruction_medians,
    )

    reconstructed_prediction = np.clip(
        reconstruction_model.predict(
            all_reconstruction_matrix
        ),
        0,
        None,
    )

    reconstructed_frame = (
        reconstruction_frame.copy()
    )

    reconstructed_frame["reconstructed_demand"] = (
        np.where(
            reconstructed_frame[
                "historical_stockout_flag"
            ],
            np.maximum(
                reconstructed_frame["units_sold"],
                reconstructed_prediction,
            ),
            reconstructed_frame["units_sold"],
        )
    ).clip(lower=0)

    forecast_frame = prepare_forecast_frame(
        reconstructed_frame,
        category_maps,
    )

    forecast_manifest: dict[str, Any] = {}

    for horizon in HORIZONS:
        target_column = f"target_h{horizon}"

        horizon_frame = add_forward_target(
            forecast_frame,
            signal_column="reconstructed_demand",
            horizon_days=horizon,
            target_column=target_column,
        )

        mature = (
            horizon_frame
            .dropna(
                subset=[
                    target_column,
                    *FORECAST_FEATURES,
                ]
            )
            .copy()
        )

        if mature.empty:
            raise ValueError(
                f"Training frame H{horizon} kosong"
            )

        matrix, medians = prepare_matrix(
            mature,
            FORECAST_FEATURES,
        )

        target = (
            mature[target_column]
            .clip(lower=0)
            .astype(float)
        )

        unique_dates = sorted(
            mature["date"].unique()
        )

        calibration_start = pd.Timestamp(
            unique_dates[
                -min(21, max(7, len(unique_dates) // 5))
            ]
        )

        fit_mask = mature["date"] < calibration_start
        calibration_mask = ~fit_mask

        if fit_mask.sum() < 100:
            raise ValueError(
                f"Training rows H{horizon} tidak cukup"
            )

        provisional_predictions: dict[
            float,
            np.ndarray,
        ] = {}

        final_models: dict[
            float,
            lgb.LGBMRegressor,
        ] = {}

        model_files: dict[str, str] = {}

        for alpha in QUANTILES:
            provisional = lgb.LGBMRegressor(
                **_model_parameters(
                    objective="quantile",
                    alpha=alpha,
                )
            )

            provisional.fit(
                matrix.loc[fit_mask],
                target.loc[fit_mask],
                eval_set=[
                    (
                        matrix.loc[calibration_mask],
                        target.loc[calibration_mask],
                    )
                ],
                callbacks=[
                    lgb.early_stopping(
                        stopping_rounds=30,
                        verbose=False,
                    ),
                    lgb.log_evaluation(period=0),
                ],
            )

            provisional_predictions[alpha] = (
                np.clip(
                    provisional.predict(
                        matrix.loc[calibration_mask]
                    ),
                    0,
                    None,
                )
            )

            best_iteration = int(
                provisional.best_iteration_
                or provisional.n_estimators
            )

            final_model = lgb.LGBMRegressor(
                **_model_parameters(
                    objective="quantile",
                    alpha=alpha,
                    n_estimators=best_iteration,
                )
            )

            final_model.fit(matrix, target)
            final_models[alpha] = final_model

            alpha_label = int(round(alpha * 100))
            model_file = (
                f"forecast_h{horizon}_q"
                f"{alpha_label:02d}.txt"
            )

            final_model.booster_.save_model(
                str(artifact_dir / model_file)
            )

            model_files[f"{alpha:.2f}"] = model_file

        calibration_y = (
            target.loc[calibration_mask]
            .to_numpy(float)
        )

        calibration_radius = _calibration_radius(
            calibration_y,
            provisional_predictions[0.10],
            provisional_predictions[0.90],
        )

        forecast_manifest[str(horizon)] = {
            "feature_columns": list(
                FORECAST_FEATURES
            ),
            "medians": medians,
            "calibration_radius": (
                calibration_radius
            ),
            "model_files": model_files,
            "training_rows": int(len(mature)),
            "training_date_min": str(
                mature["date"].min().date()
            ),
            "training_date_max": str(
                mature["date"].max().date()
            ),
        }

        print(
            f"H{horizon}:",
            len(mature),
            "rows | calibration radius:",
            round(calibration_radius, 4),
        )

    version = (
        "restockiq-lgbm-"
        f"{decision_date_value.isoformat()}-"
        f"{training_data_hash[:10]}"
    )

    manifest = {
        "version": version,
        "created_at": (
            datetime.now(timezone.utc).isoformat()
        ),
        "training_cutoff": (
            decision_date_value.isoformat()
        ),
        "training_data_hash": training_data_hash,
        "store_ids": store_ids,
        "snapshot_hashes": snapshot_hashes,
        "category_maps": category_maps,
        "reconstruction": {
            "model_file": reconstruction_file,
            "feature_columns": list(
                RECONSTRUCTION_FEATURES
            ),
            "medians": reconstruction_medians,
            "training_rows": int(
                len(reconstruction_training)
            ),
        },
        "forecasts": forecast_manifest,
        "oracle_fields_used_as_features": [],
        "seed": SEED,
    }

    manifest_path = artifact_dir / "manifest.json"

    manifest_path.write_text(
        json.dumps(
            manifest,
            indent=2,
            sort_keys=True,
        )
    )

    print()
    print("Artifact version:", version)
    print("Artifact directory:", artifact_dir)
    print("Manifest:", manifest_path)

    return manifest


def main() -> None:
    parser = argparse.ArgumentParser(
        description=(
            "Train versioned RestockIQ production artifacts"
        )
    )

    parser.add_argument(
        "--decision-date",
        default="2024-06-23",
    )

    parser.add_argument(
        "--lookback-days",
        type=int,
        default=182,
    )

    parser.add_argument(
        "--artifact-dir",
        default=str(DEFAULT_ARTIFACT_DIR),
    )

    args = parser.parse_args()

    train_artifacts(
        decision_date_value=date.fromisoformat(
            args.decision_date
        ),
        lookback_days=args.lookback_days,
        artifact_dir=Path(args.artifact_dir),
    )


if __name__ == "__main__":
    main()
