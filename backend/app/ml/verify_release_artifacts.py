from __future__ import annotations

import hashlib
from pathlib import Path

from app.ml.artifact_store import load_model_artifacts, resolve_artifact_dir


def verify_release_artifacts(artifact_dir: Path | None = None) -> dict[str, str]:
    root = resolve_artifact_dir(artifact_dir)
    checksum_file = root / "SHA256SUMS"
    if not checksum_file.is_file():
        raise RuntimeError(f"Checksum artifact tidak ditemukan: {checksum_file}")

    verified = 0
    for line in checksum_file.read_text().splitlines():
        line = line.strip()
        if not line:
            continue
        expected, filename = line.split(maxsplit=1)
        model_path = root / filename
        if not model_path.is_file():
            raise RuntimeError(f"Artifact hilang: {model_path}")
        actual = hashlib.sha256(model_path.read_bytes()).hexdigest()
        if actual != expected:
            raise RuntimeError(
                f"Checksum artifact tidak cocok untuk {filename}: "
                f"expected={expected}, actual={actual}"
            )
        verified += 1

    artifacts = load_model_artifacts(root, force_reload=True)
    if artifacts.manifest.get("oracle_fields_used_as_features"):
        raise RuntimeError("Release artifact mengandung Oracle feature")

    return {
        "version": artifacts.version,
        "training_cutoff": artifacts.training_cutoff,
        "training_data_hash": artifacts.training_data_hash,
        "verified_files": str(verified),
    }


def main() -> None:
    result = verify_release_artifacts()
    print("artifact version:", result["version"])
    print("training cutoff:", result["training_cutoff"])
    print("training hash:", result["training_data_hash"])
    print("verified files:", result["verified_files"])
    print("oracle fields used: []")


if __name__ == "__main__":
    main()
