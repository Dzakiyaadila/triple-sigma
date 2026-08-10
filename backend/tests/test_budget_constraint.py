from __future__ import annotations

from datetime import date, datetime, timezone

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import Session
from sqlalchemy.pool import StaticPool

from app.db.models import (
    Base,
    Dataset,
    DecisionRun,
    Product,
    Recommendation,
    Store,
    Supplier,
)
from app.services.decision_run_service import (
    confirm_run,
    get_persisted_plan,
    list_confirmed_runs,
    update_recommendation,
)
from app.services.plan_cache import plans_cache


@pytest.fixture
def decision_db():
    engine = create_engine(
        "sqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(engine)

    with Session(engine) as db:
        db.add(
            Dataset(
                dataset_id="demo-retail-v1",
                source_type="demo",
                readiness_status="valid",
                created_at=datetime.now(timezone.utc),
            )
        )
        db.add(Store(store_id="S01", store_name="Toko Satu"))
        db.add(
            Supplier(
                supplier_id="SUP01",
                supplier_name="Supplier Satu",
                promised_lead_time_days=2,
            )
        )
        for sku_id in ("SKU001", "SKU002", "SKU003"):
            db.add(
                Product(
                    sku_id=sku_id,
                    product_name=f"Produk {sku_id}",
                    category="Sembako",
                    unit_cost_rp=10_000,
                    unit_price_rp=13_000,
                    shelf_life_days=60,
                    is_perishable=False,
                    lead_time_days_default=2,
                    supplier_id="SUP01",
                )
            )
        db.commit()
        yield db

    plans_cache.clear()


def _recommendation(
    sku_id: str,
    quantity: int,
    *,
    status: str = "belum_diputuskan",
) -> dict:
    cash = quantity * 10_000
    return {
        "sku_id": sku_id,
        "sku_name": f"Produk {sku_id}",
        "category": "Sembako",
        "priority_rank": int(sku_id[-1]),
        "recommended_qty": quantity,
        "required_cash_rp": cash,
        "inventory_on_hand": 0,
        "inventory_on_order": 0,
        "effective_inventory": 0,
        "forecast_q10": 1,
        "forecast_q50": 2,
        "forecast_q90": 3,
        "forecast_daily_series": [],
        "stockout_risk_before": 0.5,
        "stockout_risk_after": 0.2 if quantity else 0.5,
        "lmar_before_rp": 50_000,
        "lmar_after_rp": 20_000 if quantity else 50_000,
        "incremental_lmar_avoided_rp": 30_000 if quantity else 0,
        "wcar_before_rp": 0,
        "wcar_after_rp": cash,
        "incremental_wcar_added_rp": cash,
        "supplier_name": "Supplier Satu",
        "supplier_note": "Data uji",
        "supplier_on_time_probability": 0.9,
        "supplier_p90_lead_time_days": 2,
        "expected_nov_contribution_rp": 20_000 if quantity else 0,
        "confidence": "tinggi",
        "reason_codes": ["risiko_stockout_tinggi"],
        "reasoning_short": "Alasan uji",
        "reason_more": "Alasan jumlah",
        "reason_not_more": "Alasan batas",
        "warnings": [],
        "status": status,
    }


def _seed_run(
    db: Session,
    *,
    budget_rp: float = 200_000,
    rows: list[dict] | None = None,
) -> str:
    recommendations = rows or [_recommendation("SKU001", 10)]
    run_id = "run_test"
    db.add(
        DecisionRun(
            run_id=run_id,
            dataset_id="demo-retail-v1",
            store_id="S01",
            decision_date=date(2024, 6, 23),
            budget_rp=budget_rp,
            policy_preset="seimbang",
            constraints_json={
                "horizon_days": 7,
                "min_fill_rate": None,
                "protected_sku_ids": [],
                "plan_summary": {
                    "budget_allocated_rp": sum(
                        row["required_cash_rp"] for row in recommendations
                    ),
                    "expected_nov_contribution_rp": sum(
                        row["expected_nov_contribution_rp"]
                        for row in recommendations
                    ),
                    "estimated_lmar_avoided_rp": sum(
                        row["incremental_lmar_avoided_rp"]
                        for row in recommendations
                    ),
                    "estimated_wcar_added_rp": sum(
                        row["incremental_wcar_added_rp"]
                        for row in recommendations
                    ),
                    "estimated_fill_rate": 0.8,
                    "data_quality": "baik",
                    "warnings": [],
                },
            },
            model_version="decision-v1+artifact-v1",
            data_hash="hash-test",
            status="completed",
            runtime_ms=10,
            created_at=datetime.now(timezone.utc),
        )
    )
    for row in recommendations:
        db.add(
            Recommendation(
                run_id=run_id,
                sku_id=row["sku_id"],
                original_qty=row["recommended_qty"],
                adjusted_qty=None,
                status=row["status"],
                before_metrics_json=row,
                after_metrics_json=None,
                explanation_json={},
            )
        )
    db.commit()
    return run_id


def test_approve_within_budget_survives_cache_loss(decision_db):
    run_id = _seed_run(decision_db)

    result = update_recommendation(
        decision_db,
        run_id,
        "SKU001",
        "disetujui",
        adjusted_qty=10,
    )
    plans_cache.clear()
    recovered = get_persisted_plan(decision_db, run_id)
    row = recovered["recommendations"][0]

    assert result["budget_allocated_rp"] == 100_000
    assert result["budget_remaining_rp"] == 100_000
    assert row["status"] == "disetujui"
    assert row["adjusted_qty"] == 10
    assert row["required_cash_rp"] == 100_000


def test_approve_exceeding_budget_raises_error(decision_db):
    run_id = _seed_run(decision_db, budget_rp=200_000)

    with pytest.raises(ValueError, match="melebihi budget"):
        update_recommendation(
            decision_db,
            run_id,
            "SKU001",
            "disetujui",
            adjusted_qty=100,
        )


def test_approve_zero_quantity_raises_error(decision_db):
    run_id = _seed_run(
        decision_db,
        rows=[_recommendation("SKU001", 0)],
    )

    with pytest.raises(ValueError, match="harus lebih dari 0 unit"):
        update_recommendation(
            decision_db,
            run_id,
            "SKU001",
            "disetujui",
            adjusted_qty=0,
        )


def test_confirm_ignores_approved_zero_quantity(decision_db):
    rows = [
        _recommendation("SKU001", 0, status="disetujui"),
        _recommendation("SKU002", 2, status="disetujui"),
        _recommendation("SKU003", 5, status="ditolak"),
    ]
    run_id = _seed_run(decision_db, rows=rows)

    result = confirm_run(decision_db, run_id)

    assert result["confirmed_count"] == 1
    assert result["total_cost_rp"] == 20_000


def test_confirmation_and_history_are_durable_and_idempotent(decision_db):
    run_id = _seed_run(decision_db)
    update_recommendation(
        decision_db,
        run_id,
        "SKU001",
        "disetujui",
        adjusted_qty=7,
    )

    first = confirm_run(decision_db, run_id)
    plans_cache.clear()
    second = confirm_run(decision_db, run_id)
    recovered = get_persisted_plan(decision_db, run_id)
    history = list_confirmed_runs(decision_db)

    assert second == first
    assert recovered["recommendations"][0]["status"] == "disetujui"
    assert history == [
        {
            "id": run_id,
            "date": "2024-06-23",
            "store_id": "S01",
            "store_name": "Toko Satu",
            "budget": 200_000,
            "approved_count": 1,
            "total": 70_000,
            "status": "Selesai",
            "items": [
                {
                    "sku_id": "SKU001",
                    "sku_name": "Produk SKU001",
                    "qty": 7,
                    "subtotal": 70_000,
                }
            ],
        }
    ]

    with pytest.raises(ValueError, match="sudah dikonfirmasi"):
        update_recommendation(
            decision_db,
            run_id,
            "SKU001",
            "ditolak",
            adjusted_qty=0,
        )


def test_unconfirmed_run_is_not_exposed_as_history(decision_db):
    _seed_run(decision_db)

    assert list_confirmed_runs(decision_db) == []
