from __future__ import annotations

import csv
import io
import json
import os
from urllib.error import HTTPError
from urllib.request import Request, urlopen


SITE_URL = os.getenv("RESTOCKIQ_BASE_URL", "http://localhost").rstrip("/")
API_URL = f"{SITE_URL}/api/v2"


def request_json(path: str, method: str = "GET", payload: dict | None = None):
    body = json.dumps(payload).encode() if payload is not None else None
    request = Request(
        f"{API_URL}{path}",
        data=body,
        method=method,
        headers={"Content-Type": "application/json"},
    )
    try:
        with urlopen(request, timeout=30) as response:
            return json.load(response)
    except HTTPError as exc:
        detail = exc.read().decode(errors="replace")
        raise RuntimeError(f"{method} {path} failed: {exc.code} {detail}") from exc


def main() -> None:
    with urlopen(f"{SITE_URL}/health/ready", timeout=10) as response:
        readiness = json.load(response)
    assert readiness["status"] == "ready"

    dataset = request_json("/datasets/demo/readiness")
    assert dataset["is_ready"] is True
    assert dataset["transaction_count"] == 28_210

    plan = request_json(
        "/decision-runs",
        method="POST",
        payload={
            "dataset_id": "demo-retail-v1",
            "store_id": "S01",
            "decision_date": "2024-06-23",
            "budget_rp": 10_000_000,
            "horizon_days": 7,
            "policy_preset": "seimbang",
            "protected_sku_ids": [],
        },
    )
    assert len(plan["recommendations"]) == 31
    assert plan["budget_allocated_rp"] <= 10_000_000

    recommendation = next(
        item for item in plan["recommendations"] if item["recommended_qty"] > 0
    )
    mutation = request_json(
        f"/decision-runs/{plan['run_id']}/recommendations/{recommendation['sku_id']}",
        method="PATCH",
        payload={
            "status": "disetujui",
            "adjusted_qty": recommendation["recommended_qty"],
        },
    )
    assert mutation["status"] == "disetujui"
    assert mutation["required_cash_rp"] > 0

    confirmation = request_json(
        f"/decision-runs/{plan['run_id']}/confirm",
        method="POST",
    )
    assert confirmation["confirmed_count"] == 1

    with urlopen(
        f"{API_URL}/decision-runs/{plan['run_id']}/export.csv",
        timeout=10,
    ) as response:
        rows = list(csv.DictReader(io.StringIO(response.read().decode())))
    assert len(rows) == 1
    assert rows[0]["sku_id"] == recommendation["sku_id"]

    print("RELEASE SMOKE: PASSED")
    print("run_id:", plan["run_id"])
    print("model_version:", plan["model_version"])
    print("runtime_ms:", plan["runtime_ms"])
    print("exported_rows:", len(rows))


if __name__ == "__main__":
    main()
