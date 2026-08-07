from __future__ import annotations

import json
import os
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path
from typing import Any

import lightgbm as lgb

ARTIFACT_SCHEMA_VERSION = 1
DEFAULT_ARTIFACT_DIR = (
    Path(__file__).resolve().parents[2] / "artifacts" / "restockiq-demand-v1"
)


class ArtifactError(RuntimeError):
    pass


@dataclass(frozen=True)
class ForecastArtifact:
    horizon_days: int
    feature_columns: tuple[str, ...]
    medians: dict[str, float]
    calibration_adjustment: float
    quantile_models: dict[float, lgb.Booster]


@dataclass(frozen=True)
class ModelArtifacts:
    version: str
    training_dataset_id: str
    training_cutoff: str
    training_data_hash: str
    reconstruction_feature_columns: tuple[str, ...]
    reconstruction_medians: dict[str, float]
    reconstruction_model: lgb.Booster
    forecasts: dict[int, ForecastArtifact]
    manifest: dict[str, Any]
    artifact_dir: Path


def resolve_artifact_dir(path: str | Path | None = None) -> Path:
    if path is not None:
        return Path(path).expanduser().resolve()
    configured = os.getenv("RESTOCKIQ_ARTIFACT_DIR")
    if configured:
        return Path(configured).expanduser().resolve()
    return DEFAULT_ARTIFACT_DIR.resolve()


@lru_cache(maxsize=4)
def _load_cached(path_text: str) -> ModelArtifacts:
    artifact_dir = Path(path_text)
    manifest_path = artifact_dir / "manifest.json"
    if not manifest_path.exists():
        raise ArtifactError(
            f"Demand artifact tidak ditemukan: {manifest_path}. "
            "Jalankan `python -m app.ml.train_demand_artifacts`."
        )

    manifest = json.loads(manifest_path.read_text())
    if int(manifest.get("artifact_schema_version", -1)) != ARTIFACT_SCHEMA_VERSION:
        raise ArtifactError(
            "Versi schema artifact tidak didukung: "
            f"{manifest.get('artifact_schema_version')}"
        )

    if manifest.get("oracle_fields_used_as_features"):
        raise ArtifactError("Manifest demand artifact mengandung Oracle feature")

    reconstruction = manifest["reconstruction"]
    reconstruction_path = artifact_dir / reconstruction["model_file"]
    if not reconstruction_path.exists():
        raise ArtifactError(f"Model reconstruction hilang: {reconstruction_path}")

    forecasts: dict[int, ForecastArtifact] = {}
    for horizon_text, config in manifest["forecasts"].items():
        models: dict[float, lgb.Booster] = {}
        for alpha_text, model_file in config["model_files"].items():
            model_path = artifact_dir / model_file
            if not model_path.exists():
                raise ArtifactError(f"Model forecast hilang: {model_path}")
            models[float(alpha_text)] = lgb.Booster(model_file=str(model_path))

        forecasts[int(horizon_text)] = ForecastArtifact(
            horizon_days=int(horizon_text),
            feature_columns=tuple(config["feature_columns"]),
            medians={key: float(value) for key, value in config["medians"].items()},
            calibration_adjustment=float(config["calibration_adjustment"]),
            quantile_models=models,
        )

    return ModelArtifacts(
        version=str(manifest["version"]),
        training_dataset_id=str(manifest["training_dataset_id"]),
        training_cutoff=str(manifest["training_cutoff"]),
        training_data_hash=str(manifest["training_data_hash"]),
        reconstruction_feature_columns=tuple(reconstruction["feature_columns"]),
        reconstruction_medians={
            key: float(value) for key, value in reconstruction["medians"].items()
        },
        reconstruction_model=lgb.Booster(model_file=str(reconstruction_path)),
        forecasts=forecasts,
        manifest=manifest,
        artifact_dir=artifact_dir,
    )


def load_model_artifacts(
    path: str | Path | None = None,
    *,
    force_reload: bool = False,
) -> ModelArtifacts:
    resolved = resolve_artifact_dir(path)
    if force_reload:
        _load_cached.cache_clear()
    return _load_cached(str(resolved))
