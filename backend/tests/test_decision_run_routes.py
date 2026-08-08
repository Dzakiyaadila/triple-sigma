import pytest
from fastapi import HTTPException

from app.api.routes import decision_runs
from app.ml.artifact_store import ArtifactError
from app.schemas.decision_run import DecisionRunRequest


def test_artifact_failure_is_exposed_as_service_unavailable(monkeypatch):
    def fail_run(**kwargs):
        raise ArtifactError("manifest hilang")

    monkeypatch.setattr(decision_runs, "run_decision", fail_run)

    payload = DecisionRunRequest(
        dataset_id="demo-retail-v1",
        store_id="S01",
        decision_date="2024-06-19",
        budget_rp=1_000_000,
        horizon_days=7,
        policy_preset="seimbang",
    )

    with pytest.raises(HTTPException) as exc_info:
        decision_runs.create_decision_run(payload, db=object())

    assert exc_info.value.status_code == 503
    assert "Model demand belum tersedia" in exc_info.value.detail
