from datetime import date

import pytest
from fastapi import HTTPException
from sqlalchemy import create_engine
from sqlalchemy.orm import Session

from app.api.routes.datasets import get_dataset_products, get_dataset_stores
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

def test_get_dataset_products_returns_only_selected_dataset_products():
    engine = create_engine("sqlite+pysqlite:///:memory:")
    Base.metadata.create_all(engine)

    with Session(engine) as db:
        db.add_all(
            [
                Store(store_id="S01", store_name="Store 1"),
                Supplier(supplier_id="SUP01", supplier_name="Supplier 1"),
                Product(
                    sku_id="SKU001",
                    product_name="Produk 1",
                    category="Sembako",
                    supplier_id="SUP01",
                ),
                Product(
                    sku_id="SKU002",
                    product_name="Produk 2",
                    category="Minuman",
                    supplier_id="SUP01",
                ),
                Product(
                    sku_id="SKU003",
                    product_name="Produk Masa Depan",
                    category="Minuman",
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
                    store_id="S01",
                    sku_id="SKU002",
                    units_sold=1,
                ),
                DailySales(
                    dataset_id=None,
                    date=date(2024, 1, 2),
                    store_id="S01",
                    sku_id="SKU003",
                    units_sold=1,
                ),
            ]
        )
        db.commit()

        demo_products = get_dataset_products("demo-retail-v1", "S01", date(2024, 1, 1), db)
        upload_products = get_dataset_products("upload-a", "S01", date(2024, 1, 1), db)

        assert [product.sku_id for product in demo_products] == ["SKU001"]
        assert [product.sku_id for product in upload_products] == ["SKU002"]


def test_get_dataset_products_returns_404_for_missing_dataset():
    engine = create_engine("sqlite+pysqlite:///:memory:")
    Base.metadata.create_all(engine)

    with Session(engine) as db:
        with pytest.raises(HTTPException) as exc_info:
            get_dataset_products("missing", "S01", date(2024, 1, 1), db)

        assert exc_info.value.status_code == 404
