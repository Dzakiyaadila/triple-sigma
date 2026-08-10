from __future__ import annotations

import json
from dataclasses import asdict
from pathlib import Path

from app.ml.contracts import MLDecisionConstraints
from app.ml.feature_engineering import FORECAST_FEATURES, RECONSTRUCTION_FEATURES
from app.ml.optimizer import (
    OPTIMIZER_ALGORITHM,
    OPTIMIZER_CANDIDATE_SCOPE,
    POLICY_WEIGHTS,
)
from app.ml.oracle_guard import ORACLE_FORBIDDEN_FIELDS
from app.schemas.decision_run import DecisionConstraints, DecisionRunRequest


REPO_ROOT = Path(__file__).resolve().parents[3]
FREEZE_PATH = REPO_ROOT / "docs" / "RC_POLICY_FREEZE.json"
ARTIFACT_MANIFEST_PATH = (
    REPO_ROOT
    / "backend"
    / "artifacts"
    / "restockiq-demand-v1"
    / "manifest.json"
)


def verify_rc_contract() -> dict:
    freeze = json.loads(FREEZE_PATH.read_text(encoding="utf-8"))
    manifest = json.loads(
        ARTIFACT_MANIFEST_PATH.read_text(encoding="utf-8")
    )

    expected_artifact = {
        "version": manifest["version"],
        "training_dataset_id": manifest["training_dataset_id"],
        "training_cutoff": manifest["training_cutoff"],
        "training_data_hash": manifest["training_data_hash"],
        "horizons": manifest["horizons"],
        "quantiles": manifest["quantiles"],
    }
    if freeze.get("demand_artifact") != expected_artifact:
        raise RuntimeError("RC demand-artifact freeze tidak cocok dengan manifest")

    expected_oracle_fields = sorted(ORACLE_FORBIDDEN_FIELDS)
    inference = freeze.get("inference_contract", {})
    if inference.get("oracle_forbidden_fields") != expected_oracle_fields:
        raise RuntimeError("RC Oracle-field freeze tidak cocok dengan firewall")
    if inference.get("calendar_payday_feature") != "is_payday_week":
        raise RuntimeError("RC payday contract harus memakai is_payday_week")
    for features in (RECONSTRUCTION_FEATURES, FORECAST_FEATURES):
        if "is_payday_week" not in features or "is_payday" in features:
            raise RuntimeError("RC payday freeze tidak cocok dengan model features")
    if inference.get("zero_budget_supported") is not True:
        raise RuntimeError("RC zero-budget contract harus aktif")
    MLDecisionConstraints(budget_rp=0)
    DecisionConstraints(budget_rp=0)
    DecisionRunRequest(
        dataset_id="contract-check",
        store_id="contract-check",
        decision_date="2024-05-31",
        budget_rp=0,
    )

    expected_policies = {
        name: asdict(weights)
        for name, weights in sorted(POLICY_WEIGHTS.items())
    }
    optimizer = freeze.get("optimizer", {})
    if optimizer.get("algorithm") != OPTIMIZER_ALGORITHM:
        raise RuntimeError("RC optimizer algorithm freeze tidak dikenal")
    if optimizer.get("candidate_scope") != OPTIMIZER_CANDIDATE_SCOPE:
        raise RuntimeError("RC optimizer candidate scope tidak cocok")
    if optimizer.get("policies") != expected_policies:
        raise RuntimeError("RC policy weights tidak cocok dengan production code")

    backtest = freeze.get("backtest_evidence", {})
    if backtest != {
        "status": "not_available_for_rc",
        "allowed_metric_claims": [],
    }:
        raise RuntimeError("RC backtest claim boundary berubah tanpa evidence")

    return freeze


def main() -> None:
    freeze = verify_rc_contract()
    artifact = freeze["demand_artifact"]
    print("RC CONTRACT: VERIFIED")
    print("artifact version:", artifact["version"])
    print("policy presets:", ", ".join(freeze["optimizer"]["policies"]))
    print("oracle fields used: []")
    print("backtest metric claims: none")


if __name__ == "__main__":
    main()
