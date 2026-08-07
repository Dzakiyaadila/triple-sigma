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


def test_run_decision_persists_selected_dataset_id():
    engine = create_engine("sqlite+pysqlite:///:memory:")
    Base.metadata.create_all(engine)

    decision_date = date(2026, 1, 5)

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
