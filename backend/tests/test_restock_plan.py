from __future__ import annotations

from datetime import date, timedelta

import pytest

from app.ml.artifact_store import load_model_artifacts
from app.ml.contracts import (
    CalendarRow,
    InventoryPosition,
    MLDecisionConstraints,
    ProductSnapshot,
    RetailSnapshot,
    SalesHistoryRow,
    SupplierSnapshot,
)
from app.ml.demand_training import TrainingConfig, train_demand_artifacts
from app.ml.restock_plan import (
    PlannerCompatibilityError,
    VALID_REASON_CODES,
    generate_restock_plan,
)


def _snapshot(days: int) -> RetailSnapshot:
    start = date(2026, 1, 1)
    decision = start + timedelta(days=days - 1)

    sales = []
    for index in range(days):
        current = start + timedelta(days=index)
        base = 7 + (index % 7) + (3 if index % 19 == 0 else 0)
        stockout = index > 30 and index % 23 == 0
        sold = min(base, 5) if stockout else base
        sales.append(
            SalesHistoryRow(
                sku_id="SKU001",
                sales_date=current,
                units_sold=sold,
                stock_on_hand_start=25,
                stock_on_hand_end=max(0, 25 - sold),
                stockout_flag=stockout,
                promo_flag=index % 19 == 0,
            )
        )

    calendar = tuple(
        CalendarRow(
            calendar_date=start + timedelta(days=index),
            is_weekend=(start + timedelta(days=index)).weekday() >= 5,
            is_holiday=False,
            is_payday_week=(start + timedelta(days=index)).day >= 25,
        )
        for index in range(days + 15)
    )

    return RetailSnapshot(
        dataset_id="demo-retail-v1",
        store_id="S01",
        decision_date=decision,
        lookback_start_date=start,
        horizon_end_date=decision + timedelta(days=7),
        products=(
            ProductSnapshot(
                sku_id="SKU001",
                product_name="Produk Satu",
                category="Sembako",
                supplier_id="SUP01",
                unit_cost_rp=10_000,
                unit_price_rp=14_000,
                shelf_life_days=90,
                is_perishable=False,
                lead_time_days_default=2,
            ),
        ),
        suppliers=(
            SupplierSnapshot(
                supplier_id="SUP01",
                supplier_name="Supplier Satu",
                promised_lead_time_days=2,
            ),
        ),
        sales_history=tuple(sales),
        inventory=(
            InventoryPosition(
                sku_id="SKU001",
                on_hand=4,
                as_of_date=decision,
            ),
        ),
        outstanding_orders=(),
        supplier_delivery_history=(),
        calendar=calendar,
    )


def _artifacts(tmp_path):
    training = _snapshot(120)
    train_demand_artifacts(
        [training],
        artifact_dir=tmp_path,
        training_dataset_id="demo-retail-v1",
        config=TrainingConfig(
            n_estimators=24,
            num_leaves=9,
            calibration_days=14,
            min_training_rows=35,
        ),
    )
    return load_model_artifacts(tmp_path, force_reload=True)


def test_real_planner_maps_forecast_risk_and_optimizer_to_contract(tmp_path):
    artifacts = _artifacts(tmp_path)
    snapshot = _snapshot(140)
    constraints = MLDecisionConstraints(
        budget_rp=500_000,
        horizon_days=7,
        policy_preset="seimbang",
    )

    plan = generate_restock_plan(
        snapshot=snapshot,
        constraints=constraints,
        artifacts=artifacts,
    )

    assert plan["model_version"].startswith("restockiq-planner-v1+")
    assert "mock" not in plan["model_version"]
    assert plan["data_hash"] == snapshot.data_hash()
    assert plan["budget_allocated_rp"] <= constraints.budget_rp
    assert plan["expected_nov_contribution_rp"] == pytest.approx(
        sum(
            item["expected_nov_contribution_rp"]
            for item in plan["recommendations"]
        )
    )
    assert 0 <= plan["estimated_fill_rate"] <= 1
    assert len(plan["recommendations"]) == 1

    recommendation = plan["recommendations"][0]
    assert recommendation["sku_id"] == "SKU001"
    assert recommendation["priority_rank"] == 1
    assert recommendation["required_cash_rp"] == (
        recommendation["recommended_qty"] * 10_000
    )
    assert recommendation["forecast_daily_series"] == []
    assert 0 <= recommendation["forecast_q10"] <= recommendation["forecast_q50"]
    assert recommendation["forecast_q50"] <= recommendation["forecast_q90"]
    assert set(recommendation["reason_codes"]).issubset(VALID_REASON_CODES)
    assert recommendation["status"] == "belum_diputuskan"


def test_planner_rejects_artifact_that_is_not_strictly_historical(tmp_path):
    artifacts = _artifacts(tmp_path)
    same_day_snapshot = _snapshot(120)

    with pytest.raises(PlannerCompatibilityError, match="dilatih sebelum"):
        generate_restock_plan(
            snapshot=same_day_snapshot,
            constraints=MLDecisionConstraints(
                budget_rp=500_000,
                horizon_days=7,
            ),
            artifacts=artifacts,
        )


def test_planner_rejects_unimplemented_min_fill_constraint(tmp_path):
    artifacts = _artifacts(tmp_path)

    with pytest.raises(ValueError, match="min_fill_rate belum didukung"):
        generate_restock_plan(
            snapshot=_snapshot(140),
            constraints=MLDecisionConstraints(
                budget_rp=500_000,
                horizon_days=7,
                min_fill_rate=0.90,
            ),
            artifacts=artifacts,
        )
