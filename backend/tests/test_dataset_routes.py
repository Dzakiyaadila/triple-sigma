from datetime import date

import pytest
from fastapi import HTTPException
from sqlalchemy import create_engine
from sqlalchemy.orm import Session

from app.api.routes.datasets import get_dataset_stores
from app.db.models import Base, DailySales, Product, Store, Supplier


def test_get_dataset_stores_returns_only_selected_dataset_stores():
    engine = create_engine("sqlite+pysqlite:///:memory:")
    Base.metadata.create_all(engine)

    with Session(engine) as db:
        db.add_all(
            [
                Store(store_id="S01", store_name="Store 1"),
                Store(store_id="S02", store_name="Store 2"),
                Supplier(supplier_id="SUP01", supplier_name="Supplier 1"),
                Product(
                    sku_id="SKU001",
                    product_name="Produk 1",
                    supplier_id="SUP01",
                ),
                DailySales(
                    dataset_id=None,
                    date=date(2024, 1, 1),
                    store_id="S01",
                    sku_id="SKU001",
                    units_sold=1,
                ),
                DailySales(
                    dataset_id="upload-a",
                    date=date(2024, 1, 1),
                    store_id="S02",
                    sku_id="SKU001",
                    units_sold=1,
                ),
            ]
        )
        db.commit()

        demo_stores = get_dataset_stores("demo-retail-v1", db)
        upload_stores = get_dataset_stores("upload-a", db)

        assert [store.store_id for store in demo_stores] == ["S01"]
        assert [store.store_id for store in upload_stores] == ["S02"]


def test_get_dataset_stores_returns_404_for_missing_dataset():
    engine = create_engine("sqlite+pysqlite:///:memory:")
    Base.metadata.create_all(engine)

    with Session(engine) as db:
        with pytest.raises(HTTPException) as exc_info:
            get_dataset_stores("missing", db)

        assert exc_info.value.status_code == 404
