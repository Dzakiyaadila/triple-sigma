from datetime import date, timedelta

import numpy as np
import pandas as pd

from app.ml.contracts import (
    CalendarRow,
    InventoryPosition,
    ProductSnapshot,
    RetailSnapshot,
    SalesHistoryRow,
    SupplierSnapshot,
)
from app.ml.demand_engine import (
    enforce_quantile_order,
)
from app.ml.feature_engineering import (
    add_forward_target,
    fit_category_maps,
    prepare_reconstruction_frame,
    snapshot_to_frame,
)


def _snapshot() -> RetailSnapshot:
    start = date(2026, 1, 1)
    decision_date = date(2026, 2, 10)
    horizon_end = decision_date + timedelta(days=7)

    sales = []

    current = start

    while current <= decision_date:
        units = float((current.day % 5) + 1)

        sales.append(
            SalesHistoryRow(
                sku_id="SKU001",
                sales_date=current,
                units_sold=units,
                stock_on_hand_start=20,
                stock_on_hand_end=max(0, 20 - units),
                stockout_flag=False,
                promo_flag=False,
            )
        )

        current += timedelta(days=1)

    calendar = []
    current = start

    while current <= horizon_end:
        calendar.append(
            CalendarRow(
                calendar_date=current,
                is_weekend=current.weekday() >= 5,
                is_holiday=False,
                is_payday=False,
            )
        )

        current += timedelta(days=1)

    return RetailSnapshot(
        store_id="S01",
        decision_date=decision_date,
        lookback_start_date=start,
        horizon_end_date=horizon_end,
        products=(
            ProductSnapshot(
                sku_id="SKU001",
                product_name="Produk Satu",
                category="Sembako",
                supplier_id="SUP01",
                unit_cost_rp=10_000,
                unit_price_rp=13_000,
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
                on_hand=10,
                as_of_date=decision_date,
            ),
        ),
        outstanding_orders=(),
        supplier_delivery_history=(),
        calendar=tuple(calendar),
    )


def test_feature_frame_contains_no_oracle_fields():
    snapshot = _snapshot()
    frame = snapshot_to_frame(snapshot)

    forbidden = {
        "units_demanded_est",
        "demand_profile",
        "avg_daily_demand_per_store",
        "cash_locked_in_stock_rp",
    }

    assert forbidden.isdisjoint(frame.columns)

    mappings = fit_category_maps(frame)
    featured = prepare_reconstruction_frame(
        frame,
        mappings,
    )

    assert forbidden.isdisjoint(featured.columns)


def test_forward_target_uses_future_days_only():
    frame = pd.DataFrame(
        {
            "store_id": ["S01"] * 5,
            "sku_id": ["SKU001"] * 5,
            "reconstructed_demand": [
                1.0,
                2.0,
                3.0,
                4.0,
                5.0,
            ],
        }
    )

    result = add_forward_target(
        frame,
        signal_column="reconstructed_demand",
        horizon_days=2,
        target_column="target_h2",
    )

    assert result.loc[0, "target_h2"] == 5.0
    assert result.loc[1, "target_h2"] == 7.0
    assert result.loc[2, "target_h2"] == 9.0
    assert pd.isna(result.loc[3, "target_h2"])
    assert pd.isna(result.loc[4, "target_h2"])


def test_quantile_crossing_is_repaired():
    q10, q50, q90 = enforce_quantile_order(
        np.array([10.0, 2.0]),
        np.array([5.0, 3.0]),
        np.array([8.0, 1.0]),
    )

    assert np.all(q10 <= q50)
    assert np.all(q50 <= q90)
    assert np.all(q10 >= 0)
