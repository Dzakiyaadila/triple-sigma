from __future__ import annotations

from datetime import date, timedelta

import pytest

from app.ml.contracts import (
    CalendarRow,
    InventoryPosition,
    OutstandingOrder,
    ProductSnapshot,
    RetailSnapshot,
    SalesHistoryRow,
    SupplierSnapshot,
)
from app.ml.demand_engine import (
    DemandForecastResult,
    QuantileForecast,
    SKUForecast,
)
from app.ml.risk_engine import build_risk_profiles
from app.ml.supplier_risk import (
    OutstandingArrivalEstimate,
    SupplierRiskEstimate,
    SupplierRiskResult,
)


def _inputs():
    decision = date(2024, 6, 20)
    start = decision - timedelta(days=30)
    product = ProductSnapshot(
        sku_id="SKU001",
        product_name="Produk",
        category="Sembako",
        supplier_id="SUP01",
        unit_cost_rp=100,
        unit_price_rp=160,
        shelf_life_days=20,
        is_perishable=True,
    )
    snapshot = RetailSnapshot(
        dataset_id="demo-retail-v1",
        store_id="S01",
        decision_date=decision,
        lookback_start_date=start,
        horizon_end_date=decision + timedelta(days=7),
        products=(product,),
        suppliers=(
            SupplierSnapshot(
                supplier_id="SUP01",
                supplier_name="Supplier",
                promised_lead_time_days=3,
            ),
        ),
        sales_history=(
            SalesHistoryRow(
                sku_id="SKU001",
                sales_date=decision,
                units_sold=2,
                stock_on_hand_start=5,
                stock_on_hand_end=2.5,
                stockout_flag=False,
                promo_flag=False,
            ),
        ),
        inventory=(
            InventoryPosition(sku_id="SKU001", on_hand=2.5, as_of_date=decision),
        ),
        outstanding_orders=(
            OutstandingOrder(
                order_id="OPEN-1",
                sku_id="SKU001",
                supplier_id="SUP01",
                order_date=decision - timedelta(days=1),
                order_qty_units=10,
                promised_lead_time_days=3,
                expected_arrival_date=decision + timedelta(days=2),
            ),
        ),
        supplier_delivery_history=(),
        calendar=tuple(
            CalendarRow(
                calendar_date=start + timedelta(days=index),
                is_weekend=False,
                is_holiday=False,
                is_payday=False,
            )
            for index in range((decision + timedelta(days=7) - start).days + 1)
        ),
    )
    forecast = QuantileForecast(horizon_days=7, q10=8, q50=12, q90=18)
    demand = DemandForecastResult(
        model_version="test",
        data_hash=snapshot.data_hash(),
        dataset_id=snapshot.dataset_id,
        store_id=snapshot.store_id,
        decision_date=decision.isoformat(),
        horizon_days=7,
        forecasts=(
            SKUForecast(
                sku_id="SKU001",
                selected_horizon=forecast,
                forecasts={7: forecast},
                history_days=100,
                latest_observation_date=decision.isoformat(),
                confidence="tinggi",
                warnings=(),
            ),
        ),
        warnings=(),
    )
    supplier = SupplierRiskResult(
        horizon_days=7,
        suppliers=(
            SupplierRiskEstimate(
                supplier_id="SUP01",
                sample_size=20,
                on_time_probability=0.8,
                mean_lead_time_days=3,
                p90_lead_time_days=5,
                delay_probability=0.2,
                horizon_arrival_probability=0.6,
                confidence="tinggi",
                warnings=(),
            ),
        ),
        outstanding_orders=(
            OutstandingArrivalEstimate(
                order_id="OPEN-1",
                sku_id="SKU001",
                supplier_id="SUP01",
                elapsed_days=1,
                horizon_days=7,
                arrival_probability=0.5,
                confidence="tinggi",
                warnings=(),
            ),
        ),
        warnings=(),
    )
    return snapshot, demand, supplier


def test_effective_inventory_probability_weights_outstanding_orders():
    snapshot, demand, supplier = _inputs()
    result = build_risk_profiles(
        snapshot,
        demand,
        supplier,
        horizon_days=7,
        max_order_qty=12,
    )
    profile = result.profiles[0]

    assert profile.inventory_on_hand == 2.5
    assert profile.inventory_on_order == 10
    assert profile.effective_inventory == pytest.approx(7.5)
    assert isinstance(profile.effective_inventory, float)


def test_risk_curve_is_rupiah_based_and_contains_zero_candidate():
    snapshot, demand, supplier = _inputs()
    profile = build_risk_profiles(
        snapshot,
        demand,
        supplier,
        horizon_days=7,
        max_order_qty=4,
    ).profiles[0]

    zero = profile.options[0]
    one = profile.options[1]

    assert zero.quantity == 0
    assert zero.cash_required_rp == 0
    assert zero.lmar_after_rp == pytest.approx(profile.baseline.lmar_rp)
    assert zero.wcar_after_rp == pytest.approx(profile.baseline.wcar_rp)
    assert one.cash_required_rp == 100
    assert one.expected_available_inventory == pytest.approx(8.1)
    assert one.incremental_lmar_avoided_rp >= 0
    assert isinstance(one.lmar_after_rp, float)
    assert isinstance(one.wcar_after_rp, float)
