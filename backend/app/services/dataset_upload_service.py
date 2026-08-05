"""
Proses upload histori transaksi user (CSV) untuk toko/SKU yang sudah
dikenal sistem. Tidak membuat toko/produk/supplier baru — itu di luar
scope MVP karena dim_stores/dim_products/dim_suppliers adalah katalog
bersama (bukan per-dataset).
"""
import io
import uuid
import pandas as pd
from sqlalchemy import select, insert
from sqlalchemy.orm import Session
from datetime import datetime, timezone
from app.db.models import Store, Product, DailySales, Dataset
from app.schemas.dataset import DatasetUploadResponse, UploadIssue

REQUIRED_COLUMNS = {
    "date", "store_id", "sku_id", "units_sold",
    "stock_on_hand_start", "stock_on_hand_end",
}
MIN_DAYS_HARD = 14   
MIN_DAYS_SOFT = 30   


def _reject(days_covered: int, issues: list[UploadIssue]) -> DatasetUploadResponse:
    return DatasetUploadResponse(
        dataset_id="", days_covered=days_covered, store_count=0, sku_count=0,
        transaction_count=0, is_ready=False, issues=issues,
    )


def process_sales_upload(db: Session, file_bytes: bytes, filename: str) -> DatasetUploadResponse:
    issues: list[UploadIssue] = []

    try:
        df = pd.read_csv(io.BytesIO(file_bytes))
    except Exception as e:
        return _reject(0, [UploadIssue(where=filename, message=f"File tidak bisa dibaca sebagai CSV: {e}", severity="error")])

    df.columns = [c.strip().lower() for c in df.columns]
    missing = REQUIRED_COLUMNS - set(df.columns)
    if missing:
        issues.append(UploadIssue(
            where=filename,
            message=f"Kolom wajib tidak ditemukan: {', '.join(sorted(missing))}",
            severity="error",
        ))
        return _reject(0, issues)

    try:
        df["date"] = pd.to_datetime(df["date"]).dt.date
    except Exception:
        return _reject(0, [UploadIssue(where=filename, message="Kolom 'date' tidak bisa diparsing sebagai tanggal", severity="error")])

    known_store_ids = {row[0] for row in db.execute(select(Store.store_id))}
    known_sku_ids = {row[0] for row in db.execute(select(Product.sku_id))}

    unknown_stores = set(df["store_id"].astype(str).unique()) - known_store_ids
    if unknown_stores:
        issues.append(UploadIssue(
            where=filename,
            message=f"store_id tidak dikenal sistem: {', '.join(sorted(unknown_stores))}",
            severity="error",
        ))
        return _reject(0, issues)

    unknown_skus = set(df["sku_id"].astype(str).unique()) - known_sku_ids
    if unknown_skus:
        issues.append(UploadIssue(
            where=filename,
            message=f"{len(unknown_skus)} sku_id tidak dikenal sistem dan akan diabaikan",
            severity="warning",
        ))
        df = df[df["sku_id"].astype(str).isin(known_sku_ids)]

    days_covered = int(df["date"].nunique())
    if days_covered < MIN_DAYS_HARD:
        issues.append(UploadIssue(
            where=filename,
            message=f"Data hanya mencakup {days_covered} hari, minimal {MIN_DAYS_HARD} hari diperlukan",
            severity="error",
        ))
        return _reject(days_covered, issues)

    if days_covered < MIN_DAYS_SOFT:
        issues.append(UploadIssue(
            where=filename,
            message=f"Data cuma {days_covered} hari, forecast mungkin kurang akurat (disarankan minimal {MIN_DAYS_SOFT} hari)",
            severity="warning",
        ))

    dataset_id = f"upload-{uuid.uuid4().hex[:12]}"

    db.execute(insert(Dataset.__table__), [{
        "dataset_id": dataset_id,
        "source_type": "upload",
        "data_hash": None,
        "readiness_status": "valid",
        "created_at": datetime.now(timezone.utc),
    }])

    if "stockout_flag" not in df.columns:
        df["stockout_flag"] = False
    if "promo_flag" not in df.columns:
        df["promo_flag"] = False

    records = [
        {
            "dataset_id": dataset_id,
            "date": row["date"],
            "store_id": str(row["store_id"]),
            "sku_id": str(row["sku_id"]),
            "units_sold": float(row["units_sold"]),
            "stock_on_hand_start": float(row["stock_on_hand_start"]),
            "stock_on_hand_end": float(row["stock_on_hand_end"]),
            "stockout_flag": bool(row["stockout_flag"]),
            "promo_flag": bool(row["promo_flag"]),
        }
        for _, row in df.iterrows()
    ]

    db.execute(insert(DailySales.__table__), records)
    db.commit()

    return DatasetUploadResponse(
        dataset_id=dataset_id,
        days_covered=days_covered,
        store_count=int(df["store_id"].nunique()),
        sku_count=int(df["sku_id"].nunique()),
        transaction_count=len(records),
        is_ready=True,
        issues=issues,
    )