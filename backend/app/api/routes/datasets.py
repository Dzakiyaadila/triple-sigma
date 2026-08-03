from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session
from sqlalchemy import func, select
from app.db.session import get_db
from app.db.models import Store, Product, Supplier, DailySales
from app.schemas.dataset import DatasetReadiness

router = APIRouter(prefix="/datasets", tags=["datasets"])

DEMO_DATASET_ID = "demo-retail-v1"


@router.get("/demo/readiness", response_model=DatasetReadiness)
def get_demo_readiness(db: Session = Depends(get_db)):
    store_count = db.scalar(select(func.count()).select_from(Store))
    sku_count = db.scalar(select(func.count()).select_from(Product))
    supplier_count = db.scalar(select(func.count()).select_from(Supplier))
    transaction_count = db.scalar(select(func.count()).select_from(DailySales))
    days_covered = db.scalar(select(func.count(func.distinct(DailySales.date))))

    return DatasetReadiness(
        dataset_id=DEMO_DATASET_ID,
        source_type="demo",
        days_covered=days_covered or 0,
        store_count=store_count or 0,
        sku_count=sku_count or 0,
        supplier_count=supplier_count or 0,
        transaction_count=transaction_count or 0,
        is_ready=True,
        warnings=[],
    )