from __future__ import annotations

import json
import os
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path
from typing import Any

import lightgbm as lgb


DEFAULT_ARTIFACT_DIR = (
    Path(__file__).resolve().parents[2]
    / "artifacts"
    / "restockiq-lgbm-v1"
)


class ArtifactNotFoundError(FileNotFoundError):
    """Raised when trained RestockIQ artifacts are unavailable."""


@dataclass(frozen=True)
class ForecastArtifact:
    horizon_days: int
    feature_columns: tuple[str, ...]
    medians: dict[str, float]
    calibration_radius: float
    quantile_models: dict[float, lgb.Booster]


@dataclass(frozen=True)
class ModelArtifacts:
    version: str
    training_cutoff: str
    training_data_hash: str
    category_maps: dict[str, dict[str, int]]

    reconstruction_feature_columns: tuple[str, ...]
    reconstruction_medians: dict[str, float]
    reconstruction_model: lgb.Booster

    forecast_artifacts: dict[int, ForecastArtifact]
    manifest: dict[str, Any]
    artifact_dir: Path


def resolve_artifact_dir(
    artifact_dir: str | Path | None = None,
) -> Path:
    if artifact_dir is not None:
        return Path(artifact_dir).expanduser().resolve()

    configured = os.getenv("RESTOCKIQ_ARTIFACT_DIR")

    if configured:
        return Path(configured).expanduser().resolve()

    return DEFAULT_ARTIFACT_DIR.resolve()


@lru_cache(maxsize=4)
def _load_cached(
    artifact_dir_string: str,
) -> ModelArtifacts:
    artifact_dir = Path(artifact_dir_string)
    manifest_path = artifact_dir / "manifest.json"

    if not manifest_path.exists():
        raise ArtifactNotFoundError(
            f"Model manifest tidak ditemukan: {manifest_path}. "
            "Jalankan `python -m app.ml.train_artifacts`."
        )

    manifest = json.loads(
        manifest_path.read_text()
    )

    reconstruction_config = manifest["reconstruction"]
    reconstruction_path = (
        artifact_dir
        / reconstruction_config["model_file"]
    )

    if not reconstruction_path.exists():
        raise ArtifactNotFoundError(
            f"Reconstruction model tidak ditemukan: "
            f"{reconstruction_path}"
        )

    reconstruction_model = lgb.Booster(
        model_file=str(reconstruction_path)
    )

    forecast_artifacts: dict[int, ForecastArtifact] = {}

    for horizon_text, config in manifest[
        "forecasts"
    ].items():
        horizon = int(horizon_text)
        models: dict[float, lgb.Booster] = {}

        for alpha_text, model_file in config[
            "model_files"
        ].items():
            model_path = artifact_dir / model_file

            if not model_path.exists():
                raise ArtifactNotFoundError(
                    f"Forecast model tidak ditemukan: "
                    f"{model_path}"
                )

            models[float(alpha_text)] = lgb.Booster(
                model_file=str(model_path)
            )

        forecast_artifacts[horizon] = (
            ForecastArtifact(
                horizon_days=horizon,
                feature_columns=tuple(
                    config["feature_columns"]
                ),
                medians={
                    key: float(value)
                    for key, value
                    in config["medians"].items()
                },
                calibration_radius=float(
                    config["calibration_radius"]
                ),
                quantile_models=models,
            )
        )

    return ModelArtifacts(
        version=str(manifest["version"]),
        training_cutoff=str(
            manifest["training_cutoff"]
        ),
        training_data_hash=str(
            manifest["training_data_hash"]
        ),
        category_maps={
            column: {
                str(key): int(value)
                for key, value in mapping.items()
            }
            for column, mapping
            in manifest["category_maps"].items()
        },
        reconstruction_feature_columns=tuple(
            reconstruction_config["feature_columns"]
        ),
        reconstruction_medians={
            key: float(value)
            for key, value
            in reconstruction_config["medians"].items()
        },
        reconstruction_model=reconstruction_model,
        forecast_artifacts=forecast_artifacts,
        manifest=manifest,
        artifact_dir=artifact_dir,
    )


def load_model_artifacts(
    artifact_dir: str | Path | None = None,
    *,
    force_reload: bool = False,
) -> ModelArtifacts:
    resolved = resolve_artifact_dir(artifact_dir)

    if force_reload:
        _load_cached.cache_clear()

    return _load_cached(str(resolved))
