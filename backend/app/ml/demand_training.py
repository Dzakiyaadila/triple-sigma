from __future__ import annotations

import hashlib
import inspect
import json
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import lightgbm as lgb
import numpy as np
import pandas as pd

from app.ml.artifact_store import ARTIFACT_SCHEMA_VERSION
from app.ml.contracts import RetailSnapshot
from app.ml.feature_engineering import (
    FORECAST_FEATURES,
    RECONSTRUCTION_FEATURES,
    add_forecast_features,
    add_forward_target,
    add_reconstruction_features,
    prepare_matrix,
    snapshots_to_frame,
)
from app.ml.oracle_guard import ORACLE_FORBIDDEN_FIELDS

SEED = 20260723
HORIZONS = (1, 7, 14)
QUANTILES = (0.10, 0.50, 0.90)


class DemandTrainingError(ValueError):
    pass


@dataclass(frozen=True)
class TrainingConfig:
    n_estimators: int = 180
    num_leaves: int = 23
    calibration_days: int = 21
    min_training_rows: int = 60
    reconstruction_warmup_days: int = 42
    reconstruction_oof_block_days: int = 21


def _params(
    config: TrainingConfig,
    *,
    objective: str,
    alpha: float | None = None,
    n_estimators: int | None = None,
) -> dict[str, Any]:
    result: dict[str, Any] = {
        "objective": objective,
        "n_estimators": n_estimators or config.n_estimators,
        "learning_rate": 0.035,
        "num_leaves": config.num_leaves,
        "min_child_samples": 45,
        "subsample": 0.85,
        "subsample_freq": 1,
        "colsample_bytree": 0.85,
        "reg_alpha": 0.5,
        "reg_lambda": 5.0,
        "random_state": SEED,
        "n_jobs": -1,
        "verbosity": -1,
    }
    if alpha is not None:
        result["alpha"] = alpha
    return result


def _fit_with_early_stopping(
    model: lgb.LGBMRegressor,
    x_train: pd.DataFrame,
    y_train: pd.Series,
    x_valid: pd.DataFrame,
    y_valid: pd.Series,
) -> lgb.LGBMRegressor:
    kwargs: dict[str, Any] = {
        "callbacks": [
            lgb.early_stopping(30, verbose=False),
            lgb.log_evaluation(0),
        ]
    }
    parameters = inspect.signature(model.fit).parameters
    if "eval_X" in parameters:
        kwargs["eval_X"] = x_valid
        kwargs["eval_y"] = y_valid
    else:
        kwargs["eval_set"] = [(x_valid, y_valid)]
    model.fit(x_train, y_train, **kwargs)
    return model


def _split_tail(
    frame: pd.DataFrame,
    *,
    calibration_days: int,
    min_training_rows: int,
) -> tuple[pd.Series, pd.Series]:
    dates = pd.to_datetime(frame["date"])
    unique_dates = sorted(dates.dropna().unique())
    if len(unique_dates) < 14:
        raise DemandTrainingError("Training membutuhkan minimal 14 tanggal")

    tail_days = min(calibration_days, max(7, len(unique_dates) // 5))
    cutoff = pd.Timestamp(unique_dates[-tail_days])
    train_mask = dates < cutoff
    valid_mask = ~train_mask
    if int(train_mask.sum()) < min_training_rows or int(valid_mask.sum()) == 0:
        raise DemandTrainingError(
            "Training rows tidak cukup untuk temporal train/calibration split"
        )
    return train_mask, valid_mask


def _best_iteration(model: lgb.LGBMRegressor, fallback: int) -> int:
    return max(1, int(getattr(model, "best_iteration_", None) or fallback))


def _calibration_adjustment(
    y_true: np.ndarray,
    q10: np.ndarray,
    q90: np.ndarray,
) -> float:
    nonconformity = np.maximum(q10 - y_true, y_true - q90)
    return float(np.quantile(np.maximum(nonconformity, 0.0), 0.80))


def _causal_rule(frame: pd.DataFrame) -> np.ndarray:
    prediction = (
        frame["roll_mean_28"]
        .fillna(frame["roll_mean_14"])
        .fillna(frame["roll_mean_7"])
        .fillna(frame["units_sold"])
        .clip(lower=0)
    )
    return prediction.to_numpy(float)


def _rolling_origin_reconstructed_signal(
    reconstruction_frame: pd.DataFrame,
    *,
    config: TrainingConfig,
) -> np.ndarray:
    """Create forecast-training signal without fitting on future rows.

    Uncensored rows always retain observed sales. Censored rows are predicted
    by an expanding model fitted strictly before each temporal block; the early
    warm-up period uses a causal rolling-rule fallback.
    """
    frame = reconstruction_frame.sort_values(
        ["date", "store_id", "sku_id"], kind="stable"
    ).copy()
    result = frame["units_sold"].to_numpy(float).copy()
    stockout = frame["stockout_flag"].astype(bool).to_numpy()
    result[stockout] = np.maximum(
        result[stockout],
        _causal_rule(frame)[stockout],
    )

    unique_dates = sorted(pd.to_datetime(frame["date"]).dropna().unique())
    if len(unique_dates) <= config.reconstruction_warmup_days:
        return np.clip(result, 0, None)

    warmup_end_index = config.reconstruction_warmup_days
    block_days = max(1, config.reconstruction_oof_block_days)

    for start_index in range(warmup_end_index, len(unique_dates), block_days):
        block_start = pd.Timestamp(unique_dates[start_index])
        block_end = pd.Timestamp(
            unique_dates[min(start_index + block_days - 1, len(unique_dates) - 1)]
        )
        train = frame.loc[
            (pd.to_datetime(frame["date"]) < block_start)
            & (~frame["stockout_flag"].astype(bool))
        ].copy()
        block_mask = pd.to_datetime(frame["date"]).between(block_start, block_end)
        block = frame.loc[block_mask].copy()
        if len(train) < config.min_training_rows or block.empty:
            continue

        train_x, medians = prepare_matrix(train, RECONSTRUCTION_FEATURES)
        block_x, _ = prepare_matrix(block, RECONSTRUCTION_FEATURES, medians)
        model = lgb.LGBMRegressor(
            **_params(config, objective="regression")
        )
        model.fit(train_x, train["units_sold"].clip(lower=0).astype(float))
        predictions = np.clip(model.predict(block_x), 0, None)
        block_stockout = block["stockout_flag"].astype(bool).to_numpy()
        block_indices = np.flatnonzero(block_mask.to_numpy())
        target_indices = block_indices[block_stockout]
        result[target_indices] = np.maximum(
            frame.loc[block_mask, "units_sold"].to_numpy(float)[block_stockout],
            predictions[block_stockout],
        )

    return np.clip(result, 0, None)


def _combined_hash(snapshots: list[RetailSnapshot]) -> str:
    payload = [
        {
            "dataset_id": snapshot.dataset_id,
            "store_id": snapshot.store_id,
            "data_hash": snapshot.data_hash(),
        }
        for snapshot in sorted(snapshots, key=lambda item: item.store_id)
    ]
    encoded = json.dumps(payload, sort_keys=True, separators=(",", ":")).encode()
    return hashlib.sha256(encoded).hexdigest()


def train_demand_artifacts(
    snapshots: list[RetailSnapshot],
    *,
    artifact_dir: Path,
    training_dataset_id: str,
    config: TrainingConfig = TrainingConfig(),
) -> dict[str, Any]:
    if not snapshots:
        raise DemandTrainingError("Tidak ada snapshot untuk training")
    if {snapshot.dataset_id for snapshot in snapshots} != {training_dataset_id}:
        raise DemandTrainingError("Semua snapshot training harus berasal dari satu dataset")

    artifact_dir.mkdir(parents=True, exist_ok=True)
    raw = snapshots_to_frame(snapshots)
    reconstruction_frame = add_reconstruction_features(raw)

    # Production reconstruction labels are only uncensored observed sales.
    reconstruction_train = reconstruction_frame.loc[
        ~reconstruction_frame["stockout_flag"].astype(bool)
    ].copy()
    if len(reconstruction_train) < config.min_training_rows:
        raise DemandTrainingError("Uncensored reconstruction rows tidak cukup")

    recon_x, recon_medians = prepare_matrix(
        reconstruction_train, RECONSTRUCTION_FEATURES
    )
    recon_y = reconstruction_train["units_sold"].clip(lower=0).astype(float)
    recon_train_mask, recon_valid_mask = _split_tail(
        reconstruction_train,
        calibration_days=config.calibration_days,
        min_training_rows=config.min_training_rows,
    )

    provisional_recon = lgb.LGBMRegressor(
        **_params(config, objective="regression")
    )
    provisional_recon = _fit_with_early_stopping(
        provisional_recon,
        recon_x.loc[recon_train_mask],
        recon_y.loc[recon_train_mask],
        recon_x.loc[recon_valid_mask],
        recon_y.loc[recon_valid_mask],
    )
    recon_iterations = _best_iteration(provisional_recon, config.n_estimators)
    final_recon = lgb.LGBMRegressor(
        **_params(
            config,
            objective="regression",
            n_estimators=recon_iterations,
        )
    )
    final_recon.fit(recon_x, recon_y)
    recon_file = "reconstruction_censor_no_inventory.txt"
    final_recon.booster_.save_model(str(artifact_dir / recon_file))

    # Forecast training uses rolling-origin reconstruction rather than
    # predictions from the final reconstruction model fitted on later rows.
    reconstructed = reconstruction_frame.sort_values(
        ["date", "store_id", "sku_id"], kind="stable"
    ).copy()
    reconstructed["reconstructed_demand"] = (
        _rolling_origin_reconstructed_signal(
            reconstructed,
            config=config,
        )
    )

    forecast_base = add_forecast_features(reconstructed)
    forecast_manifest: dict[str, Any] = {}

    for horizon in HORIZONS:
        target_col = f"target_h{horizon}"
        frame = add_forward_target(
            forecast_base,
            signal_col="reconstructed_demand",
            horizon_days=horizon,
            target_col=target_col,
        ).dropna(subset=[target_col]).copy()

        if len(frame) < config.min_training_rows:
            raise DemandTrainingError(f"Training rows H{horizon} tidak cukup")

        matrix, medians = prepare_matrix(frame, FORECAST_FEATURES)
        target = frame[target_col].clip(lower=0).astype(float)
        train_mask, calibration_mask = _split_tail(
            frame,
            calibration_days=config.calibration_days,
            min_training_rows=config.min_training_rows,
        )

        # Split-conformal discipline: calibration rows never enter model fitting.
        # We intentionally use the fixed, pre-declared model complexity here
        # instead of selecting iterations on the calibration tail.
        quantile_models: dict[float, lgb.LGBMRegressor] = {}
        calibration_predictions: dict[float, np.ndarray] = {}
        for alpha in QUANTILES:
            model = lgb.LGBMRegressor(
                **_params(config, objective="quantile", alpha=alpha)
            )
            model.fit(matrix.loc[train_mask], target.loc[train_mask])
            quantile_models[alpha] = model
            calibration_predictions[alpha] = np.clip(
                model.predict(matrix.loc[calibration_mask]), 0, None
            )

        adjustment = _calibration_adjustment(
            target.loc[calibration_mask].to_numpy(float),
            calibration_predictions[0.10],
            calibration_predictions[0.90],
        )

        model_files: dict[str, str] = {}
        for alpha in QUANTILES:
            file_name = f"forecast_h{horizon}_q{int(alpha * 100):02d}.txt"
            quantile_models[alpha].booster_.save_model(
                str(artifact_dir / file_name)
            )
            model_files[f"{alpha:.2f}"] = file_name

        calibration_dates = pd.to_datetime(frame.loc[calibration_mask, "date"])
        fit_dates = pd.to_datetime(frame.loc[train_mask, "date"])
        forecast_manifest[str(horizon)] = {
            "feature_columns": list(FORECAST_FEATURES),
            "medians": medians,
            "calibration_adjustment": adjustment,
            "calibration_target": "future_cumulative_reconstructed_demand",
            "model_files": model_files,
            "training_rows": int(len(frame)),
            "training_date_min": str(pd.Timestamp(frame["date"].min()).date()),
            "training_date_max": str(pd.Timestamp(frame["date"].max()).date()),
            "model_fit_date_max": str(fit_dates.max().date()),
            "calibration_date_min": str(calibration_dates.min().date()),
            "calibration_date_max": str(calibration_dates.max().date()),
        }

    training_hash = _combined_hash(snapshots)
    training_cutoff = max(snapshot.decision_date for snapshot in snapshots).isoformat()
    version = f"restockiq-demand-v1-{training_hash[:12]}"
    manifest = {
        "artifact_schema_version": ARTIFACT_SCHEMA_VERSION,
        "version": version,
        "created_at": datetime.now(timezone.utc).isoformat(),
        "training_dataset_id": training_dataset_id,
        "training_cutoff": training_cutoff,
        "training_data_hash": training_hash,
        "seed": SEED,
        "reconstruction_variant": "censor_no_inventory",
        "reconstruction_label": "uncensored_observed_units_sold",
        "forecast_signal": "rolling_origin_reconstructed_demand",
        "forecast_target": "t+1_through_t+H_cumulative_reconstructed_demand",
        "horizons": list(HORIZONS),
        "quantiles": list(QUANTILES),
        "oracle_fields_used_as_features": [],
        "oracle_forbidden_fields": sorted(ORACLE_FORBIDDEN_FIELDS),
        "reconstruction": {
            "model_file": recon_file,
            "feature_columns": list(RECONSTRUCTION_FEATURES),
            "medians": recon_medians,
            "training_rows": int(len(reconstruction_train)),
        },
        "forecasts": forecast_manifest,
        "library_versions": {
            "lightgbm": lgb.__version__,
            "numpy": np.__version__,
            "pandas": pd.__version__,
        },
    }
    (artifact_dir / "manifest.json").write_text(
        json.dumps(manifest, indent=2, sort_keys=True)
    )
    return manifest
