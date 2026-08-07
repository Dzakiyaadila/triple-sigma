from __future__ import annotations

from datetime import date, timedelta

import numpy as np
import pandas as pd

from app.ml.artifact_store import load_model_artifacts
from app.ml.contracts import (
    CalendarRow,
    InventoryPosition,
    ProductSnapshot,
    RetailSnapshot,
    SalesHistoryRow,
    SupplierSnapshot,
)
from app.ml.demand_engine import enforce_quantile_order, generate_demand_forecasts
from app.ml.demand_training import TrainingConfig, train_demand_artifacts
from app.ml.feature_engineering import (
    RECONSTRUCTION_FEATURES,
    add_forward_target,
    add_reconstruction_features,
    snapshot_to_frame,
)
from app.ml.oracle_guard import ORACLE_FORBIDDEN_FIELDS


def _snapshot(days: int = 120) -> RetailSnapshot:
    start = date(2026, 1, 1)
    decision = start + timedelta(days=days - 1)
    products = (
        ProductSnapshot(
            sku_id="SKU001",
            product_name="Produk Satu",
            category="Sembako",
            supplier_id="SUP01",
            unit_cost_rp=10_000,
            unit_price_rp=13_000,
            shelf_life_days=60,
            is_perishable=False,
            lead_time_days_default=2,
        ),
    )
    suppliers = (
        SupplierSnapshot(
            supplier_id="SUP01",
            supplier_name="Supplier Satu",
            promised_lead_time_days=2,
        ),
    )

    sales = []
    for index in range(days):
        current = start + timedelta(days=index)
        base = 7 + (index % 7) + (2 if index % 15 == 0 else 0)
        stockout = index > 28 and index % 17 == 0
        sold = min(base, 5) if stockout else base
        sales.append(
            SalesHistoryRow(
                sku_id="SKU001",
                sales_date=current,
                units_sold=sold,
                stock_on_hand_start=20,
                stock_on_hand_end=max(0, 20 - sold),
                stockout_flag=stockout,
                promo_flag=index % 15 == 0,
            )
        )

    calendar = tuple(
        CalendarRow(
            calendar_date=start + timedelta(days=index),
            is_weekend=(start + timedelta(days=index)).weekday() >= 5,
            is_holiday=False,
            is_payday=(start + timedelta(days=index)).day >= 25,
        )
        for index in range(days + 15)
    )
    return RetailSnapshot(
        dataset_id="demo-retail-v1",
        store_id="S01",
        decision_date=decision,
        lookback_start_date=start,
        horizon_end_date=decision + timedelta(days=14),
        products=products,
        suppliers=suppliers,
        sales_history=tuple(sales),
        inventory=(
            InventoryPosition(sku_id="SKU001", on_hand=8, as_of_date=decision),
        ),
        outstanding_orders=(),
        supplier_delivery_history=(),
        calendar=calendar,
    )


def test_forward_target_is_strictly_future():
    frame = pd.DataFrame(
        {
            "store_id": ["S01"] * 5,
            "sku_id": ["SKU001"] * 5,
            "reconstructed_demand": [1.0, 2.0, 3.0, 4.0, 5.0],
        }
    )
    result = add_forward_target(
        frame,
        signal_col="reconstructed_demand",
        horizon_days=2,
        target_col="target_h2",
    )
    assert result.loc[0, "target_h2"] == 5.0
    assert result.loc[1, "target_h2"] == 7.0
    assert result.loc[2, "target_h2"] == 9.0
    assert pd.isna(result.loc[3, "target_h2"])


def test_reconstruction_feature_contract_is_oracle_free_and_causal():
    frame = snapshot_to_frame(_snapshot(45))
    featured = add_reconstruction_features(frame)
    assert ORACLE_FORBIDDEN_FIELDS.isdisjoint(RECONSTRUCTION_FEATURES)
    assert ORACLE_FORBIDDEN_FIELDS.isdisjoint(featured.columns)

    row = featured.iloc[-1]
    original = float(row["past_stockout_rate_28"])
    changed = frame.copy()
    changed.loc[changed.index[-1], "stockout_flag"] = not bool(
        changed.loc[changed.index[-1], "stockout_flag"]
    )
    changed_featured = add_reconstruction_features(changed)
    assert float(changed_featured.iloc[-1]["past_stockout_rate_28"]) == original


def test_quantile_crossing_is_repaired():
    q10, q50, q90 = enforce_quantile_order(
        np.array([10.0]), np.array([5.0]), np.array([8.0])
    )
    assert 0 <= q10[0] <= q50[0] <= q90[0]


def test_artifact_roundtrip_and_real_inference(tmp_path):
    snapshot = _snapshot()
    manifest = train_demand_artifacts(
        [snapshot],
        artifact_dir=tmp_path,
        training_dataset_id="demo-retail-v1",
        config=TrainingConfig(
            n_estimators=24,
            num_leaves=9,
            calibration_days=14,
            min_training_rows=35,
        ),
    )
    assert manifest["oracle_fields_used_as_features"] == []
    assert manifest["forecast_target"] == (
        "t+1_through_t+H_cumulative_reconstructed_demand"
    )
    assert manifest["forecast_signal"] == "rolling_origin_reconstructed_demand"

    artifacts = load_model_artifacts(tmp_path, force_reload=True)
    result = generate_demand_forecasts(snapshot, artifacts, horizon_days=7)
    assert result.model_version == manifest["version"]
    assert result.data_hash == snapshot.data_hash()
    assert len(result.forecasts) == 1
    selected = result.forecasts[0].selected_horizon
    assert 0 <= selected.q10 <= selected.q50 <= selected.q90
    assert set(result.forecasts[0].forecasts) == {1, 7, 14}
