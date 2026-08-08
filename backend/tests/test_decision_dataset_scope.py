from datetime import date, timedelta

from sqlalchemy import create_engine, select
from sqlalchemy.orm import Session

from app.db.models import (
    Base,
    CalendarDay,
    DailySales,
    Dataset,
    DecisionRun,
    Product,
    Store,
    Supplier,
)
from app.services.decision_run_service import run_decision


def test_run_decision_persists_selected_dataset_id(monkeypatch):
    engine = create_engine("sqlite+pysqlite:///:memory:")
    Base.metadata.create_all(engine)

    decision_date = date(2026, 1, 5)

    captured = {}

    def fake_generate_restock_plan(*, snapshot, constraints):
        captured["dataset_id"] = snapshot.dataset_id
        captured["protected_sku_ids"] = constraints.protected_sku_ids
        return {
            "run_id": "run_dataset_scope",
            "model_version": "restockiq-planner-test",
            "data_hash": snapshot.data_hash(),
            "budget_allocated_rp": 10_000.0,
            "expected_nov_contribution_rp": 1_000.0,
            "estimated_lmar_avoided_rp": 2_000.0,
            "estimated_wcar_added_rp": 1_000.0,
            "estimated_fill_rate": 0.9,
            "data_quality": "baik",
            "warnings": [],
            "runtime_ms": 1,
            "recommendations": [
                {
                    "sku_id": "SKU001",
                    "priority_rank": 1,
                    "recommended_qty": 1,
                    "required_cash_rp": 10_000.0,
                    "inventory_on_hand": 8.0,
                    "inventory_on_order": 0.0,
                    "effective_inventory": 8.0,
                    "forecast_q10": 5.0,
                    "forecast_q50": 7.0,
                    "forecast_q90": 10.0,
                    "forecast_daily_series": [],
                    "stockout_risk_before": 0.4,
                    "stockout_risk_after": 0.2,
                    "lmar_before_rp": 4_000.0,
                    "lmar_after_rp": 2_000.0,
                    "incremental_lmar_avoided_rp": 2_000.0,
                    "wcar_before_rp": 1_000.0,
                    "wcar_after_rp": 2_000.0,
                    "incremental_wcar_added_rp": 1_000.0,
                    "supplier_on_time_probability": 0.8,
                    "supplier_p90_lead_time_days": 3.0,
                    "expected_nov_contribution_rp": 1_000.0,
                    "confidence": "sedang",
                    "reason_codes": [
                        "risiko_stockout_tinggi",
                        "supplier_kurang_andal",
                    ],
                    "warnings": [],
                    "status": "belum_diputuskan",
                }
            ],
        }

    monkeypatch.setattr(
        "app.services.decision_run_service.generate_restock_plan",
        fake_generate_restock_plan,
    )

    with Session(engine) as db:
        db.add(Store(store_id="S01", store_name="Store 1"))
        db.add(
            Supplier(
                supplier_id="SUP01",
                supplier_name="Supplier 1",
                promised_lead_time_days=2,
            )
        )
        db.add(
            Product(
                sku_id="SKU001",
                product_name="Produk 1",
                category="Sembako",
                supplier_id="SUP01",
                unit_cost_rp=10_000,
                unit_price_rp=13_000,
            )
        )

        for offset in range(-4, 8):
            current = decision_date + timedelta(days=offset)
            db.add(
                CalendarDay(
                    date=current,
                    day_of_week=current.strftime("%A"),
                    is_weekend=current.weekday() >= 5,
                    is_holiday=False,
                    day_of_month=current.day,
                    is_payday_week=False,
                    month=current.month,
                )
            )

        db.add_all(
            [
                DailySales(
                    dataset_id=None,
                    date=decision_date - timedelta(days=1),
                    store_id="S01",
                    sku_id="SKU001",
                    stock_on_hand_start=10,
                    units_sold=2,
                    stock_on_hand_end=8,
                    promo_flag=False,
                    stockout_flag=False,
                ),
                DailySales(
                    dataset_id="upload-other",
                    date=decision_date - timedelta(days=1),
                    store_id="S01",
                    sku_id="SKU001",
                    stock_on_hand_start=999,
                    units_sold=999,
                    stock_on_hand_end=999,
                    promo_flag=True,
                    stockout_flag=False,
                ),
            ]
        )
        db.add(
            Dataset(
                dataset_id="upload-other",
                source_type="upload",
                readiness_status="valid",
            )
        )
        db.commit()

        plan = run_decision(
            db=db,
            dataset_id="demo-retail-v1",
            store_id="S01",
            decision_date=decision_date.isoformat(),
            budget_rp=100_000,
            policy_preset="seimbang",
            horizon_days=7,
            protected_sku_ids=["SKU001"],
        )

        run = db.scalar(
            select(DecisionRun).where(
                DecisionRun.run_id == plan["run_id"]
            )
        )

        assert run is not None
        assert run.dataset_id == "demo-retail-v1"
        assert db.get(Dataset, "demo-retail-v1") is not None
        assert run.data_hash == plan["data_hash"]
        assert run.data_hash != "dummy-hash"
        assert captured["dataset_id"] == "demo-retail-v1"
        assert captured["protected_sku_ids"] == ("SKU001",)
        assert run.constraints_json["protected_sku_ids"] == ["SKU001"]
