from fastapi import APIRouter, Depends, File, HTTPException, UploadFile
from sqlalchemy.orm import Session
from sqlalchemy import func, select
from app.db.session import get_db
from app.db.models import DailySales, Product, Store
from app.schemas.dataset import DatasetReadiness
from app.schemas.dataset import DatasetUploadResponse
from app.services.dataset_upload_service import process_sales_upload
from app.services.dataset_scope import DEMO_DATASET_ID, dataset_filter
from app.schemas.dataset import StoreOut

router = APIRouter(prefix="/datasets", tags=["datasets"])



@router.get("/demo/readiness", response_model=DatasetReadiness)
def get_demo_readiness(db: Session = Depends(get_db)):
    demo_filter = dataset_filter(DailySales.dataset_id, DEMO_DATASET_ID)

    store_count = db.scalar(
        select(func.count(func.distinct(DailySales.store_id)))
        .where(demo_filter)
    )
    sku_count = db.scalar(
        select(func.count(func.distinct(DailySales.sku_id)))
        .where(demo_filter)
    )
    supplier_count = db.scalar(
        select(func.count(func.distinct(Product.supplier_id)))
        .select_from(DailySales)
        .join(Product, Product.sku_id == DailySales.sku_id)
        .where(demo_filter)
    )
    transaction_count = db.scalar(
        select(func.count())
        .select_from(DailySales)
        .where(demo_filter)
    )
    days_covered = db.scalar(
        select(func.count(func.distinct(DailySales.date)))
        .where(demo_filter)
    )

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
@router.post("/upload", response_model=DatasetUploadResponse)
async def upload_dataset(file: UploadFile = File(...), db: Session = Depends(get_db)):
    if not file.filename.lower().endswith(".csv"):
        raise HTTPException(status_code=400, detail="File harus berformat .csv")

    content = await file.read()
    return process_sales_upload(db, content, file.filename)
    
@router.get("/{dataset_id}/stores", response_model=list[StoreOut])
def get_dataset_stores(dataset_id: str, db: Session = Depends(get_db)):
    store_ids_query = select(
        func.distinct(DailySales.store_id)
    ).where(
        dataset_filter(DailySales.dataset_id, dataset_id)
    )

    store_ids = {row[0] for row in db.execute(store_ids_query)}
    if not store_ids:
        raise HTTPException(status_code=404, detail="Dataset tidak ditemukan atau tidak memiliki data toko")

    return db.scalars(select(Store).where(Store.store_id.in_(store_ids))).all()