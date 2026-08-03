"""
Load dataset sintetis Della ke database. Jalankan sekali:
    python -m app.db.seed
"""
import pandas as pd
from sqlalchemy import create_engine, insert
from app.core.config import DATABASE_URL
from app.db.models import Base, Store, Supplier, Product, CalendarDay, DailySales, PurchaseOrder

EXCEL_PATH = "data/synthetic/RestockIQ_Dataset_Sintetis.xlsx"

SHEET_MODEL_MAP = {
    "Dim_Stores": Store,
    "Dim_Suppliers": Supplier,
    "Dim_Products": Product,
    "Dim_Calendar": CalendarDay,
    "Fact_Daily_Sales": DailySales,
    "Fact_Purchase_Orders": PurchaseOrder,
}


def seed():
    engine = create_engine(DATABASE_URL)
    Base.metadata.create_all(engine)

    for sheet_name, model in SHEET_MODEL_MAP.items():
        df = pd.read_excel(EXCEL_PATH, sheet_name=sheet_name)

        for col in df.columns:
            if col == "date" or "date" in col.lower():
                df[col] = pd.to_datetime(df[col], errors="coerce").dt.date

        df = df.where(pd.notnull(df), None)  # NaN -> None, biar cocok jadi NULL di database

        table_columns = {c.name for c in model.__table__.columns}
        records = [
            {k: v for k, v in row.items() if k in table_columns}
            for row in df.to_dict(orient="records")
        ]

        with engine.begin() as conn:
            conn.execute(insert(model.__table__), records)

        print(f"{sheet_name} -> {model.__tablename__}: {len(records)} baris")


if __name__ == "__main__":
    seed()