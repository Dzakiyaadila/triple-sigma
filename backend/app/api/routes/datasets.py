from fastapi import APIRouter, Depends, File, HTTPException, UploadFile
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.db.models import CalendarDay, DailySales, Product, Store
from app.db.session import get_db
from app.schemas.dataset import (
    DatasetReadiness,
    DatasetUploadResponse,
    SkuOption,
    StoreOut,
)
from app.services.dataset_scope import DEMO_DATASET_ID, dataset_filter
from app.services.dataset_upload_service import process_sales_upload

router = APIRouter(prefix="/datasets", tags=["datasets"])


@router.get("/demo/readiness", response_model=DatasetReadiness)
def get_demo_readiness(db: Session = Depends(get_db)):
    demo_filter = dataset_filter(DailySales.dataset_id, DEMO_DATASET_ID)

    store_count = db.scalar(
        select(func.count(func.distinct(DailySales.store_id))).where(demo_filter)
    ) or 0
    sku_count = db.scalar(
        select(func.count(func.distinct(DailySales.sku_id))).where(demo_filter)
    ) or 0
    supplier_count = db.scalar(
        select(func.count(func.distinct(Product.supplier_id)))
        .select_from(DailySales)
        .join(Product, Product.sku_id == DailySales.sku_id)
        .where(demo_filter)
    ) or 0
    transaction_count = db.scalar(
        select(func.count()).select_from(DailySales).where(demo_filter)
    ) or 0
    days_covered = db.scalar(
        select(func.count(func.distinct(DailySales.date))).where(demo_filter)
    ) or 0
    min_date, max_date = db.execute(
        select(
            func.min(DailySales.date),
            func.max(DailySales.date),
        ).where(demo_filter)
    ).one()
    calendar_min_date, calendar_max_date = db.execute(
        select(
            func.min(CalendarDay.date),
            func.max(CalendarDay.date),
        )
    ).one()

    is_ready = bool(
        transaction_count
        and store_count
        and sku_count
        and days_covered >= 14
        and min_date is not None
        and max_date is not None
        and calendar_min_date is not None
        and calendar_max_date is not None
    )

    warnings: list[str] = []
    if transaction_count and days_covered < 30:
        warnings.append(
            "Histori demo kurang dari 30 hari; ketidakpastian forecast dapat meningkat."
        )

    return DatasetReadiness(
        dataset_id=DEMO_DATASET_ID,
        source_type="demo",
        days_covered=int(days_covered),
        store_count=int(store_count),
        sku_count=int(sku_count),
        supplier_count=int(supplier_count),
        transaction_count=int(transaction_count),
        min_date=min_date,
        max_date=max_date,
        calendar_min_date=calendar_min_date,
        calendar_max_date=calendar_max_date,
        is_ready=is_ready,
        warnings=warnings,
    )


@router.post("/upload", response_model=DatasetUploadResponse)
async def upload_dataset(
    file: UploadFile = File(...),
    db: Session = Depends(get_db),
):
    filename = (file.filename or "").strip()
    if not filename:
        raise HTTPException(status_code=400, detail="Nama file tidak tersedia")
    if not filename.lower().endswith(".csv"):
        raise HTTPException(status_code=400, detail="File harus berformat .csv")

    content = await file.read()
    if not content:
        raise HTTPException(status_code=400, detail="File CSV kosong")

    return process_sales_upload(db, content, filename)


@router.get("/{dataset_id}/stores", response_model=list[StoreOut])
def get_dataset_stores(
    dataset_id: str,
    db: Session = Depends(get_db),
):
    store_ids_query = select(
        func.distinct(DailySales.store_id)
    ).where(
        dataset_filter(DailySales.dataset_id, dataset_id)
    )

    store_ids = {row[0] for row in db.execute(store_ids_query) if row[0] is not None}
    if not store_ids:
        raise HTTPException(
            status_code=404,
            detail="Dataset tidak ditemukan atau tidak memiliki data toko",
        )

    return list(
        db.scalars(
            select(Store)
            .where(Store.store_id.in_(store_ids))
            .order_by(Store.store_id)
        )
    )


@router.get("/{dataset_id}/skus", response_model=list[SkuOption])
def get_dataset_skus(dataset_id: str, store_id: str, db: Session = Depends(get_db)):
    sku_ids_query = select(func.distinct(DailySales.sku_id)).where(
        DailySales.store_id == store_id,
        dataset_filter(DailySales.dataset_id, dataset_id),
    )
    sku_ids = {row[0] for row in db.execute(sku_ids_query) if row[0] is not None}
    if not sku_ids:
        return []

    return list(
        db.scalars(
            select(Product)
            .where(Product.sku_id.in_(sku_ids))
            .order_by(Product.sku_id)
        )
    )