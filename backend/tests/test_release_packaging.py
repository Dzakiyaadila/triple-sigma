import json
from pathlib import Path

import pytest
from sqlalchemy import create_engine

from app.db.models import Base, Store
from app.db.seed import seed
from app.ml.verify_release_artifacts import verify_release_artifacts


def test_frozen_release_artifacts_are_complete_and_oracle_safe():
    result = verify_release_artifacts()

    assert result["version"] == "restockiq-demand-v1-a067286b7c1e"
    assert result["training_cutoff"] == "2024-05-31"
    assert result["training_data_hash"] == (
        "a067286b7c1e966de43f3db9e1d24a7f8a440d236d94c24365c6d717ca44399c"
    )
    assert result["verified_files"] == "11"


def test_demo_seed_is_idempotent(tmp_path):
    database_url = f"sqlite+pysqlite:///{tmp_path / 'restockiq.db'}"

    assert seed(database_url=database_url) == "seeded"
    assert seed(database_url=database_url) == "unchanged"


def test_demo_seed_refuses_partially_populated_database(tmp_path):
    database_url = f"sqlite+pysqlite:///{tmp_path / 'partial.db'}"
    engine = create_engine(database_url)
    Base.metadata.create_all(engine)
    with engine.begin() as connection:
        connection.execute(
            Store.__table__.insert(),
            [{"store_id": "S01", "store_name": "Partial"}],
        )

    with pytest.raises(RuntimeError, match="terisi sebagian"):
        seed(database_url=database_url)


def test_manifest_does_not_list_oracle_features():
    manifest_path = (
        Path(__file__).resolve().parents[1]
        / "artifacts"
        / "restockiq-demand-v1"
        / "manifest.json"
    )
    manifest = json.loads(manifest_path.read_text())

    assert manifest["oracle_fields_used_as_features"] == []
