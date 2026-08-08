from datetime import date

import pytest
from sqlalchemy import (
    Boolean,
    Column,
    Date,
    Float,
    MetaData,
    String,
    Table,
    create_engine,
)
from sqlalchemy.orm import Session

from app.ml.oracle_guard import (
    OracleFieldError,
    assert_oracle_safe_payload,
)
from app.services.retail_snapshot_service import (
    SnapshotBuildError,
    build_retail_snapshot,
)


@pytest.fixture
def snapshot_db():
    engine = create_engine(
        "sqlite+pysqlite:///:memory:",
    )
    metadata = MetaData()

    stores = Table(
        "dim_stores",
        metadata,
        Column("store_id", String, primary_key=True),
    )

    suppliers = Table(
        "dim_suppliers",
        metadata,
        Column("supplier_id", String, primary_key=True),
        Column("supplier_name", String, nullable=False),
        Column(
            "promised_lead_time_days",
            Float,
            nullable=False,
        ),
    )

    products = Table(
        "dim_products",
        metadata,
        Column("sku_id", String, primary_key=True),
        Column("product_name", String, nullable=False),
        Column("category", String, nullable=False),
        Column("supplier_id", String, nullable=False),
        Column("unit_cost_rp", Float, nullable=False),
        Column("unit_price_rp", Float, nullable=False),
    )

    sales = Table(
        "fact_daily_sales",
        metadata,
        Column("dataset_id", String, nullable=True),
        Column("store_id", String, nullable=False),
        Column("sku_id", String, nullable=False),
        Column("sales_date", Date, nullable=False),
        Column("units_sold", Float, nullable=False),
        Column(
            "stock_on_hand_start",
            Float,
            nullable=False,
        ),
        Column(
            "stock_on_hand_end",
            Float,
            nullable=False,
        ),
        Column("stockout_flag", Boolean, nullable=False),
        Column("promo_flag", Boolean, nullable=False),
        # Evaluation-only field exists in the source table.
        # The builder must never select it.
        Column("units_demanded_est", Float),
    )

    purchase_orders = Table(
        "fact_purchase_orders",
        metadata,
        Column(
            "purchase_order_id",
            String,
            primary_key=True,
        ),
        Column("dataset_id", String, nullable=True),
        Column("store_id", String, nullable=False),
        Column("sku_id", String, nullable=False),
        Column("supplier_id", String, nullable=False),
        Column("order_date", Date, nullable=False),
        Column(
            "order_qty_units",
            Float,
            nullable=False,
        ),
        Column(
            "promised_lead_time_days",
            Float,
            nullable=False,
        ),
        Column(
            "actual_lead_time_days",
            Float,
            nullable=False,
        ),
        Column("delay_days", Float, nullable=False),
    )

    calendar = Table(
        "dim_calendar",
        metadata,
        Column(
            "calendar_date",
            Date,
            primary_key=True,
        ),
        Column("is_weekend", Boolean, nullable=False),
        Column("is_holiday", Boolean, nullable=False),
        Column("is_payday_week", Boolean, nullable=False),
    )

    metadata.create_all(engine)

    with engine.begin() as connection:
        connection.execute(
            stores.insert(),
            [{"store_id": "S01"}],
        )

        connection.execute(
            suppliers.insert(),
            [
                {
                    "supplier_id": "SUP01",
                    "supplier_name": "Supplier Satu",
                    "promised_lead_time_days": 2,
                }
            ],
        )

        connection.execute(
            products.insert(),
            [
                {
                    "sku_id": "SKU001",
                    "product_name": "Produk Satu",
                    "category": "Sembako",
                    "supplier_id": "SUP01",
                    "unit_cost_rp": 10_000,
                    "unit_price_rp": 13_000,
                },
                {
                    "sku_id": "SKU002",
                    "product_name": "Produk Dua",
                    "category": "Sembako",
                    "supplier_id": "SUP01",
                    "unit_cost_rp": 20_000,
                    "unit_price_rp": 25_000,
                },
            ],
        )

        connection.execute(
            sales.insert(),
            [
                {
                    "store_id": "S01",
                    "sku_id": "SKU001",
                    "sales_date": date(2026, 1, 3),
                    "units_sold": 5,
                    "stock_on_hand_start": 10,
                    "stock_on_hand_end": 5,
                    "stockout_flag": False,
                    "promo_flag": False,
                    "units_demanded_est": 999,
                },
                {
                    "store_id": "S01",
                    "sku_id": "SKU001",
                    "sales_date": date(2026, 1, 5),
                    "units_sold": 5,
                    "stock_on_hand_start": 5,
                    "stock_on_hand_end": 0,
                    "stockout_flag": True,
                    "promo_flag": False,
                    "units_demanded_est": 999,
                },
                {
                    "store_id": "S01",
                    "sku_id": "SKU001",
                    "sales_date": date(2026, 1, 6),
                    "units_sold": 99,
                    "stock_on_hand_start": 99,
                    "stock_on_hand_end": 0,
                    "stockout_flag": True,
                    "promo_flag": True,
                    "units_demanded_est": 999,
                },
            ],
        )

        connection.execute(
            purchase_orders.insert(),
            [
                {
                    "purchase_order_id": "PO-COMPLETE",
                    "store_id": "S01",
                    "sku_id": "SKU001",
                    "supplier_id": "SUP01",
                    "order_date": date(2026, 1, 1),
                    "order_qty_units": 10,
                    "promised_lead_time_days": 2,
                    "actual_lead_time_days": 2,
                    "delay_days": 0,
                },
                {
                    "purchase_order_id": "PO-OPEN",
                    "store_id": "S01",
                    "sku_id": "SKU001",
                    "supplier_id": "SUP01",
                    "order_date": date(2026, 1, 4),
                    "order_qty_units": 20,
                    "promised_lead_time_days": 2,
                    "actual_lead_time_days": 5,
                    "delay_days": 3,
                },
            ],
        )

        connection.execute(
            calendar.insert(),
            [
                {
                    "calendar_date": date(2026, 1, day),
                    "is_weekend": False,
                    "is_holiday": False,
                    "is_payday_week": day in {5, 6, 7},
                }
                for day in range(1, 13)
            ],
        )

    with Session(engine) as session:
        yield session


def test_snapshot_applies_temporal_cutoff(snapshot_db):
    snapshot = build_retail_snapshot(
        snapshot_db,
        dataset_id="demo-retail-v1",
        store_id="S01",
        decision_date=date(2026, 1, 5),
        horizon_days=7,
        lookback_days=5,
    )

    assert snapshot.dataset_id == "demo-retail-v1"
    assert snapshot.store_id == "S01"
    assert snapshot.decision_date == date(2026, 1, 5)
    assert snapshot.horizon_end_date == date(2026, 1, 12)

    assert any(
        "histori lebih pendek" in warning.lower()
        for warning in snapshot.warnings
    )
    assert all(
        row.sales_date <= snapshot.decision_date
        for row in snapshot.sales_history
    )

    # Future sales on 6 January must be excluded.
    assert {
        row.sales_date for row in snapshot.sales_history
    } == {
        date(2026, 1, 3),
        date(2026, 1, 5),
    }

    inventory = {
        row.sku_id: row
        for row in snapshot.inventory
    }

    assert inventory["SKU001"].on_hand == 0
    assert inventory["SKU001"].as_of_date == date(
        2026,
        1,
        5,
    )

    # SKU without history receives an explicit zero position.
    assert inventory["SKU002"].on_hand == 0

    assert {
        order.order_id
        for order in snapshot.outstanding_orders
    } == {"PO-OPEN"}

    open_order = next(
        order
        for order in snapshot.outstanding_orders
        if order.order_id == "PO-OPEN"
    )

    assert not hasattr(open_order, "actual_lead_time_days")
    assert not hasattr(open_order, "delay_days")

    assert all(
        delivery.delivery_date <= snapshot.decision_date
        for delivery in snapshot.supplier_delivery_history
    )

    assert {
        delivery.order_id
        for delivery in snapshot.supplier_delivery_history
    } == {"PO-COMPLETE"}


def test_snapshot_contains_future_known_calendar(snapshot_db):
    snapshot = build_retail_snapshot(
        snapshot_db,
        dataset_id="demo-retail-v1",
        store_id="S01",
        decision_date=date(2026, 1, 5),
        horizon_days=7,
        lookback_days=5,
    )

    calendar_dates = {
        row.calendar_date for row in snapshot.calendar
    }

    assert date(2026, 1, 5) in calendar_dates
    assert date(2026, 1, 12) in calendar_dates
    calendar_by_date = {
        row.calendar_date: row for row in snapshot.calendar
    }
    assert calendar_by_date[date(2026, 1, 5)].is_payday_week is True
    assert calendar_by_date[date(2026, 1, 8)].is_payday_week is False


def test_snapshot_is_oracle_safe(snapshot_db):
    snapshot = build_retail_snapshot(
        snapshot_db,
        dataset_id="demo-retail-v1",
        store_id="S01",
        decision_date=date(2026, 1, 5),
        horizon_days=7,
        lookback_days=5,
    )

    dumped = snapshot.model_dump(mode="python")

    assert "units_demanded_est" not in str(dumped)
    assert_oracle_safe_payload(snapshot)


def test_oracle_guard_rejects_nested_forbidden_field():
    payload = {
        "store_id": "S01",
        "rows": [
            {
                "sku_id": "SKU001",
                "units_demanded_est": 100,
            }
        ],
    }

    with pytest.raises(
        OracleFieldError,
        match="units_demanded_est",
    ):
        assert_oracle_safe_payload(payload)


def test_snapshot_hash_is_deterministic(snapshot_db):
    first = build_retail_snapshot(
        snapshot_db,
        dataset_id="demo-retail-v1",
        store_id="S01",
        decision_date=date(2026, 1, 5),
        horizon_days=7,
        lookback_days=5,
    )

    second = build_retail_snapshot(
        snapshot_db,
        dataset_id="demo-retail-v1",
        store_id="S01",
        decision_date=date(2026, 1, 5),
        horizon_days=7,
        lookback_days=5,
    )

    assert first.data_hash() == second.data_hash()


def test_snapshot_rejects_non_positive_lookback(snapshot_db):
    with pytest.raises(
        SnapshotBuildError,
        match="lookback_days harus minimal 1",
    ):
        build_retail_snapshot(
            snapshot_db,
            dataset_id="demo-retail-v1",
            store_id="S01",
            decision_date=date(2026, 1, 5),
            horizon_days=7,
            lookback_days=0,
        )


def test_snapshot_rejects_decision_date_outside_calendar_range(
    snapshot_db,
):
    with pytest.raises(
        SnapshotBuildError,
        match="di luar rentang valid",
    ):
        build_retail_snapshot(
            snapshot_db,
            dataset_id="demo-retail-v1",
            store_id="S01",
            decision_date=date(2026, 7, 28),
            horizon_days=7,
            lookback_days=5,
        )


def test_snapshot_isolates_datasets_with_same_store_and_sku(snapshot_db):
    metadata = MetaData()
    sales = Table(
        "fact_daily_sales",
        metadata,
        autoload_with=snapshot_db.get_bind(),
    )
    purchase_orders = Table(
        "fact_purchase_orders",
        metadata,
        autoload_with=snapshot_db.get_bind(),
    )

    snapshot_db.execute(
        sales.insert(),
        [
            {
                "dataset_id": "upload-b",
                "store_id": "S01",
                "sku_id": "SKU001",
                "sales_date": date(2026, 1, 5),
                "units_sold": 999,
                "stock_on_hand_start": 999,
                "stock_on_hand_end": 888,
                "stockout_flag": False,
                "promo_flag": True,
                "units_demanded_est": 999,
            }
        ],
    )
    snapshot_db.execute(
        purchase_orders.insert(),
        [
            {
                "purchase_order_id": "PO-UPLOAD",
                "dataset_id": "upload-b",
                "store_id": "S01",
                "sku_id": "SKU001",
                "supplier_id": "SUP01",
                "order_date": date(2026, 1, 2),
                "order_qty_units": 777,
                "promised_lead_time_days": 1,
                "actual_lead_time_days": 1,
                "delay_days": 0,
            }
        ],
    )
    snapshot_db.commit()

    demo = build_retail_snapshot(
        snapshot_db,
        dataset_id="demo-retail-v1",
        store_id="S01",
        decision_date=date(2026, 1, 5),
        horizon_days=7,
        lookback_days=5,
    )
    uploaded = build_retail_snapshot(
        snapshot_db,
        dataset_id="upload-b",
        store_id="S01",
        decision_date=date(2026, 1, 5),
        horizon_days=7,
        lookback_days=5,
    )

    assert 999.0 not in {row.units_sold for row in demo.sales_history}
    assert {row.units_sold for row in uploaded.sales_history} == {999.0}
    assert {product.sku_id for product in demo.products} == {"SKU001", "SKU002"}
    assert {product.sku_id for product in uploaded.products} == {"SKU001"}
    assert "PO-UPLOAD" not in {
        delivery.order_id
        for delivery in demo.supplier_delivery_history
    }
    assert {
        delivery.order_id
        for delivery in uploaded.supplier_delivery_history
    } == {"PO-UPLOAD"}
