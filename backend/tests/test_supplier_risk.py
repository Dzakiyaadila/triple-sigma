from __future__ import annotations

from datetime import date, timedelta

from app.ml.contracts import (
    CalendarRow,
    InventoryPosition,
    OutstandingOrder,
    ProductSnapshot,
    RetailSnapshot,
    SalesHistoryRow,
    SupplierDeliveryHistoryRow,
    SupplierSnapshot,
)
from app.ml.supplier_risk import estimate_supplier_risk


def _snapshot() -> RetailSnapshot:
    decision = date(2024, 6, 20)
    start = decision - timedelta(days=30)
    suppliers = (
        SupplierSnapshot(
            supplier_id="SUP01",
            supplier_name="Supplier One",
            promised_lead_time_days=3,
        ),
        SupplierSnapshot(
            supplier_id="SUP02",
            supplier_name="Supplier Sparse",
            promised_lead_time_days=4,
        ),
    )
    products = (
        ProductSnapshot(
            sku_id="SKU001",
            product_name="Produk",
            category="Sembako",
            supplier_id="SUP01",
            unit_cost_rp=100,
            unit_price_rp=160,
        ),
        ProductSnapshot(
            sku_id="SKU002",
            product_name="Produk Dua",
            category="Sembako",
            supplier_id="SUP02",
            unit_cost_rp=120,
            unit_price_rp=180,
        ),
    )
    leads = [2, 3, 4, 2, 5]
    history = tuple(
        SupplierDeliveryHistoryRow(
            order_id=f"DONE-{index}",
            supplier_id="SUP01",
            order_date=decision - timedelta(days=20 - index),
            delivery_date=decision - timedelta(days=20 - index - lead),
            promised_lead_time_days=3,
            actual_lead_time_days=lead,
            delay_days=lead - 3,
        )
        for index, lead in enumerate(leads)
    )
    outstanding = (
        OutstandingOrder(
            order_id="OPEN-NORMAL",
            sku_id="SKU001",
            supplier_id="SUP01",
            order_date=decision - timedelta(days=2),
            order_qty_units=10,
            promised_lead_time_days=3,
            expected_arrival_date=decision + timedelta(days=1),
        ),
        OutstandingOrder(
            order_id="OPEN-OVERDUE",
            sku_id="SKU001",
            supplier_id="SUP01",
            order_date=decision - timedelta(days=10),
            order_qty_units=4,
            promised_lead_time_days=3,
            expected_arrival_date=decision - timedelta(days=7),
        ),
    )
    calendar = tuple(
        CalendarRow(
            calendar_date=start + timedelta(days=index),
            is_weekend=False,
            is_holiday=False,
            is_payday=False,
        )
        for index in range((decision + timedelta(days=7) - start).days + 1)
    )
    return RetailSnapshot(
        dataset_id="demo-retail-v1",
        store_id="S01",
        decision_date=decision,
        lookback_start_date=start,
        horizon_end_date=decision + timedelta(days=7),
        products=products,
        suppliers=suppliers,
        sales_history=(
            SalesHistoryRow(
                sku_id="SKU001",
                sales_date=decision,
                units_sold=2,
                stock_on_hand_start=5,
                stock_on_hand_end=3,
                stockout_flag=False,
                promo_flag=False,
            ),
            SalesHistoryRow(
                sku_id="SKU002",
                sales_date=decision,
                units_sold=1,
                stock_on_hand_start=5,
                stock_on_hand_end=4,
                stockout_flag=False,
                promo_flag=False,
            ),
        ),
        inventory=(
            InventoryPosition(sku_id="SKU001", on_hand=3, as_of_date=decision),
            InventoryPosition(sku_id="SKU002", on_hand=4, as_of_date=decision),
        ),
        outstanding_orders=outstanding,
        supplier_delivery_history=history,
        calendar=calendar,
    )


def test_supplier_risk_is_causal_deterministic_and_bounded():
    snapshot = _snapshot()
    first = estimate_supplier_risk(snapshot, horizon_days=7)
    second = estimate_supplier_risk(snapshot, horizon_days=7)

    assert first == second
    assert all(0 <= item.on_time_probability <= 1 for item in first.suppliers)
    assert all(0 <= item.delay_probability <= 1 for item in first.suppliers)
    assert all(0 <= item.horizon_arrival_probability <= 1 for item in first.suppliers)
    assert all(0 <= item.arrival_probability <= 1 for item in first.outstanding_orders)

    # Outstanding-order contract exposes no future realized delivery outcome.
    order = snapshot.outstanding_orders[0]
    assert not hasattr(order, "actual_lead_time_days")
    assert not hasattr(order, "delivery_date")


def test_sparse_supplier_shrinks_to_global_history():
    result = estimate_supplier_risk(_snapshot(), horizon_days=7)
    supplier = result.supplier_by_id()["SUP02"]

    assert supplier.sample_size == 0
    assert supplier.confidence == "rendah"
    assert supplier.mean_lead_time_days > 0
    assert supplier.p90_lead_time_days > 0
    assert supplier.warnings


def test_outstanding_arrival_conditions_on_elapsed_age():
    result = estimate_supplier_risk(_snapshot(), horizon_days=7)
    arrivals = result.arrival_by_order_id()

    normal = arrivals["OPEN-NORMAL"]
    overdue = arrivals["OPEN-OVERDUE"]

    assert normal.elapsed_days == 2
    assert normal.arrival_probability > 0.5
    assert overdue.elapsed_days == 10
    assert overdue.arrival_probability == 0.5
    assert any("dukungan histori" in warning for warning in overdue.warnings)
