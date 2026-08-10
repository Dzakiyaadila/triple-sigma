"""Idempotently bootstrap the frozen RestockIQ demo dataset."""

from __future__ import annotations

import hashlib
from datetime import datetime, timezone
from pathlib import Path

import pandas as pd
from sqlalchemy import create_engine, func, insert, select, update

from app.core.config import DATABASE_URL
from app.db.models import (
    Base,
    CalendarDay,
    DailySales,
    Dataset,
    Product,
    PurchaseOrder,
    Store,
    Supplier,
)
from app.services.dataset_scope import DEMO_DATASET_ID

EXCEL_PATH = (
    Path(__file__).resolve().parents[2]
    / "data"
    / "synthetic"
    / "RestockIQ_Dataset_Sintetis.xlsx"
)

SHEET_MODEL_MAP = {
    "Dim_Stores": Store,
    "Dim_Suppliers": Supplier,
    "Dim_Products": Product,
    "Dim_Calendar": CalendarDay,
    "Fact_Daily_Sales": DailySales,
    "Fact_Purchase_Orders": PurchaseOrder,
}

EXPECTED_DEMO_COUNTS = {
    "dim_stores": 5,
    "dim_suppliers": 6,
    "dim_products": 31,
    "dim_calendar": 182,
    "fact_daily_sales": 28_210,
    "fact_purchase_orders": 549,
}


def _records_for_sheet(
    workbook_path: Path,
    sheet_name: str,
    model: type,
) -> list[dict]:
    frame = pd.read_excel(workbook_path, sheet_name=sheet_name)

    for column in frame.columns:
        if column == "date" or "date" in column.lower():
            frame[column] = pd.to_datetime(
                frame[column],
                errors="coerce",
            ).dt.date

    frame = frame.where(pd.notnull(frame), None)
    table_columns = {column.name for column in model.__table__.columns}
    return [
        {
            key: value
            for key, value in row.items()
            if key in table_columns
        }
        for row in frame.to_dict(orient="records")
    ]


def _source_counts(connection) -> dict[str, int]:
    counts: dict[str, int] = {}
    for model in SHEET_MODEL_MAP.values():
        statement = select(func.count()).select_from(model.__table__)
        if model in (DailySales, PurchaseOrder):
            statement = statement.where(model.dataset_id.is_(None))
        counts[model.__tablename__] = int(
            connection.scalar(statement) or 0
        )
    return counts


def _upsert_demo_metadata(connection, data_hash: str) -> None:
    exists = connection.scalar(
        select(Dataset.dataset_id).where(
            Dataset.dataset_id == DEMO_DATASET_ID
        )
    )
    values = {
        "source_type": "demo",
        "data_hash": data_hash,
        "readiness_status": "valid",
    }
    if exists:
        connection.execute(
            update(Dataset)
            .where(Dataset.dataset_id == DEMO_DATASET_ID)
            .values(**values)
        )
        return

    connection.execute(
        insert(Dataset).values(
            dataset_id=DEMO_DATASET_ID,
            created_at=datetime.now(timezone.utc),
            **values,
        )
    )


def seed(
    database_url: str = DATABASE_URL,
    workbook_path: Path = EXCEL_PATH,
) -> str:
    if not database_url:
        raise ValueError("DATABASE_URL wajib diisi sebelum bootstrap")
    if not workbook_path.is_file():
        raise FileNotFoundError(
            f"Dataset demo tidak ditemukan: {workbook_path}"
        )

    engine = create_engine(database_url)
    Base.metadata.create_all(engine)
    data_hash = hashlib.sha256(workbook_path.read_bytes()).hexdigest()

    with engine.begin() as connection:
        counts = _source_counts(connection)
        if counts == EXPECTED_DEMO_COUNTS:
            _upsert_demo_metadata(connection, data_hash)
            print("Demo dataset already seeded; bootstrap skipped.")
            return "unchanged"

        if any(counts.values()):
            detail = ", ".join(
                f"{table}={count}"
                for table, count in sorted(counts.items())
            )
            raise RuntimeError(
                "Database demo terisi sebagian; bootstrap dihentikan agar "
                f"tidak mencampur snapshot. Counts: {detail}"
            )

        for sheet_name, model in SHEET_MODEL_MAP.items():
            records = _records_for_sheet(
                workbook_path,
                sheet_name,
                model,
            )
            connection.execute(insert(model.__table__), records)
            print(
                f"{sheet_name} -> {model.__tablename__}: "
                f"{len(records)} baris"
            )

        _upsert_demo_metadata(connection, data_hash)

    return "seeded"


if __name__ == "__main__":
    seed()
