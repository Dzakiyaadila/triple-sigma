from datetime import date, timedelta

from sqlalchemy import create_engine, func, select
from sqlalchemy.orm import Session

from app.db.models import (
    Base,
    CalendarDay,
    DailySales,
    Dataset,
    Product,
    Store,
    Supplier,
)
from app.services.dataset_upload_service import process_sales_upload


def _build_db() -> tuple[object, Session]:
    engine = create_engine("sqlite+pysqlite:///:memory:")
    Base.metadata.create_all(engine)
    db = Session(engine)

    db.add_all(
        [
            Store(store_id="S01", store_name="Store 1"),
            Supplier(
                supplier_id="SUP01",
                supplier_name="Supplier 1",
                promised_lead_time_days=2,
            ),
            Product(
                sku_id="SKU001",
                product_name="Produk 1",
                category="Sembako",
                supplier_id="SUP01",
                unit_cost_rp=10_000,
                unit_price_rp=13_000,
            ),
        ]
    )

    start = date(2024, 1, 1)
    for offset in range(90):
        current = start + timedelta(days=offset)
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

    db.commit()
    return engine, db


def _csv(
    *,
    days: int = 14,
    sku_id: str = "SKU001",
    stockout_value: str = "False",
    promo_value: str = "False",
) -> bytes:
    lines = [
        "date,store_id,sku_id,units_sold,stock_on_hand_start,"
        "stock_on_hand_end,stockout_flag,promo_flag"
    ]
    start = date(2024, 1, 1)

    for offset in range(days):
        current = start + timedelta(days=offset)
        lines.append(
            f"{current.isoformat()},S01,{sku_id},2,10,8,"
            f"{stockout_value},{promo_value}"
        )

    return ("\n".join(lines) + "\n").encode("utf-8")


def test_valid_upload_persists_rows_with_hash_and_boolean_values():
    _, db = _build_db()
    try:
        result = process_sales_upload(
            db,
            _csv(stockout_value="False", promo_value="True"),
            "sales.csv",
        )

        assert result.is_ready is True
        assert result.dataset_id.startswith("upload-")
        assert result.data_hash is not None
        assert len(result.data_hash) == 64
        assert result.days_covered == 14
        assert result.store_count == 1
        assert result.sku_count == 1
        assert result.supplier_count == 1
        assert result.transaction_count == 14
        assert result.min_date == date(2024, 1, 1)
        assert result.max_date == date(2024, 1, 14)
        assert result.calendar_min_date == date(2024, 1, 1)
        assert result.calendar_max_date == date(2024, 3, 30)

        dataset = db.get(Dataset, result.dataset_id)
        assert dataset is not None
        assert dataset.data_hash == result.data_hash
        assert dataset.readiness_status == "valid"

        rows = list(
            db.scalars(
                select(DailySales)
                .where(DailySales.dataset_id == result.dataset_id)
                .order_by(DailySales.date)
            )
        )
        assert len(rows) == 14
        assert all(row.stockout_flag is False for row in rows)
        assert all(row.promo_flag is True for row in rows)
    finally:
        db.close()


def test_hash_is_stable_when_upload_row_order_changes():
    _, db = _build_db()
    try:
        original = _csv(days=14).decode("utf-8").splitlines()
        header, rows = original[0], original[1:]
        reversed_csv = ("\n".join([header, *reversed(rows)]) + "\n").encode()

        first = process_sales_upload(db, _csv(days=14), "first.csv")
        second = process_sales_upload(db, reversed_csv, "second.csv")

        assert first.is_ready is True
        assert second.is_ready is True
        assert first.dataset_id != second.dataset_id
        assert first.data_hash == second.data_hash
    finally:
        db.close()


def test_invalid_numeric_value_returns_report_without_database_mutation():
    _, db = _build_db()
    try:
        payload = _csv(days=14).decode("utf-8").replace(
            ",2,10,8,False,False",
            ",not-a-number,10,8,False,False",
            1,
        ).encode("utf-8")

        result = process_sales_upload(db, payload, "invalid.csv")

        assert result.is_ready is False
        assert result.dataset_id == ""
        assert any(issue.severity == "error" for issue in result.issues)
        assert db.scalar(select(func.count()).select_from(Dataset)) == 0
        assert db.scalar(select(func.count()).select_from(DailySales)) == 0
    finally:
        db.close()


def test_duplicate_daily_key_is_rejected():
    _, db = _build_db()
    try:
        original = _csv(days=14).decode("utf-8").splitlines()
        payload = ("\n".join([*original, original[1]]) + "\n").encode()

        result = process_sales_upload(db, payload, "duplicate.csv")

        assert result.is_ready is False
        assert any("harus unik" in issue.message for issue in result.issues)
        assert db.scalar(select(func.count()).select_from(Dataset)) == 0
    finally:
        db.close()


def test_unknown_sku_rows_are_filtered_but_valid_rows_remain_usable():
    _, db = _build_db()
    try:
        known = _csv(days=14).decode("utf-8").splitlines()
        header, known_rows = known[0], known[1:]
        unknown_rows = [row.replace("SKU001", "SKU404") for row in known_rows]
        payload = ("\n".join([header, *known_rows, *unknown_rows]) + "\n").encode()

        result = process_sales_upload(db, payload, "mixed.csv")

        assert result.is_ready is True
        assert result.sku_count == 1
        assert result.transaction_count == 14
        assert result.supplier_count == 1
        assert any(
            issue.severity == "warning" and "sku_id tidak dikenal" in issue.message
            for issue in result.issues
        )
        persisted = db.scalar(
            select(func.count())
            .select_from(DailySales)
            .where(DailySales.dataset_id == result.dataset_id)
        )
        assert persisted == 14
    finally:
        db.close()


def test_upload_outside_supported_calendar_is_rejected():
    _, db = _build_db()
    try:
        payload = _csv(days=14).decode("utf-8").replace("2024-01-", "2026-01-").encode()
        result = process_sales_upload(db, payload, "future.csv")

        assert result.is_ready is False
        assert result.calendar_max_date == date(2024, 3, 30)
        assert any("di luar kalender" in issue.message for issue in result.issues)
        assert db.scalar(select(func.count()).select_from(Dataset)) == 0
    finally:
        db.close()


def test_duplicate_header_is_rejected_before_pandas_mangles_names():
    _, db = _build_db()
    try:
        original = _csv(days=14).decode("utf-8").splitlines()
        header, rows = original[0], original[1:]
        duplicate_header = header.replace(
            "units_sold,stock_on_hand_start",
            "units_sold,units_sold,stock_on_hand_start",
            1,
        )
        duplicate_rows = [
            row.replace(",2,10,8,", ",2,999,10,8,", 1)
            for row in rows
        ]
        payload = ("\n".join([duplicate_header, *duplicate_rows]) + "\n").encode()

        result = process_sales_upload(db, payload, "duplicate-header.csv")

        assert result.is_ready is False
        assert any("Nama kolom duplikat" in issue.message for issue in result.issues)
        assert db.scalar(select(func.count()).select_from(Dataset)) == 0
    finally:
        db.close()


def test_invalid_boolean_value_is_rejected():
    _, db = _build_db()
    try:
        result = process_sales_upload(
            db,
            _csv(days=14, stockout_value="maybe"),
            "invalid-boolean.csv",
        )

        assert result.is_ready is False
        assert any("boolean tidak valid" in issue.message for issue in result.issues)
        assert db.scalar(select(func.count()).select_from(Dataset)) == 0
    finally:
        db.close()


def test_each_store_must_have_minimum_history():
    engine, db = _build_db()
    try:
        db.add(Store(store_id="S02", store_name="Store 2"))
        db.commit()

        original = _csv(days=14).decode("utf-8").splitlines()
        header, rows = original[0], original[1:]
        short_store_rows = [row.replace(",S01,", ",S02,", 1) for row in rows[:3]]
        payload = ("\n".join([header, *rows, *short_store_rows]) + "\n").encode()

        result = process_sales_upload(db, payload, "short-store.csv")

        assert result.is_ready is False
        assert any("S02=3 hari" in issue.message for issue in result.issues)
        assert db.scalar(select(func.count()).select_from(Dataset)) == 0
    finally:
        db.close()
        engine.dispose()
