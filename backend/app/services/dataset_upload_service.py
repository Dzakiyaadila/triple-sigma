"""Validate and persist uploaded daily-sales datasets.

Uploads are intentionally limited to stores and SKUs already present in the
shared catalog. Validation failures return a structured readiness report and do
not mutate the database.
"""
from __future__ import annotations

import csv
import hashlib
import io
import uuid
from datetime import date, datetime, timezone

import pandas as pd
from sqlalchemy import func, insert, select
from sqlalchemy.orm import Session

from app.db.models import CalendarDay, DailySales, Dataset, Product, Store
from app.schemas.dataset import DatasetUploadResponse, UploadIssue

REQUIRED_COLUMNS = {
    "date",
    "store_id",
    "sku_id",
    "units_sold",
    "stock_on_hand_start",
    "stock_on_hand_end",
}
NUMERIC_COLUMNS = (
    "units_sold",
    "stock_on_hand_start",
    "stock_on_hand_end",
)
OPTIONAL_BOOLEAN_COLUMNS = (
    "stockout_flag",
    "promo_flag",
)
MIN_DAYS_HARD = 14
MIN_DAYS_SOFT = 30

_TRUE_VALUES = frozenset({"1", "true", "t", "yes", "y", "ya"})
_FALSE_VALUES = frozenset({"0", "false", "f", "no", "n", "tidak", ""})


def _reject(
    *,
    days_covered: int = 0,
    store_count: int = 0,
    sku_count: int = 0,
    supplier_count: int = 0,
    transaction_count: int = 0,
    min_date: date | None = None,
    max_date: date | None = None,
    calendar_min_date: date | None = None,
    calendar_max_date: date | None = None,
    issues: list[UploadIssue],
) -> DatasetUploadResponse:
    return DatasetUploadResponse(
        dataset_id="",
        data_hash=None,
        days_covered=days_covered,
        store_count=store_count,
        sku_count=sku_count,
        supplier_count=supplier_count,
        transaction_count=transaction_count,
        min_date=min_date,
        max_date=max_date,
        calendar_min_date=calendar_min_date,
        calendar_max_date=calendar_max_date,
        is_ready=False,
        issues=issues,
    )


def _row_numbers(mask: pd.Series, *, limit: int = 8) -> str:
    rows = [str(int(index) + 2) for index in mask[mask].index[:limit]]
    suffix = "…" if int(mask.sum()) > limit else ""
    return ", ".join(rows) + suffix


def _parse_boolean_series(
    series: pd.Series,
    *,
    column_name: str,
    filename: str,
) -> tuple[pd.Series | None, UploadIssue | None]:
    normalized = series.fillna("").astype(str).str.strip().str.lower()
    valid = normalized.isin(_TRUE_VALUES | _FALSE_VALUES)

    if not bool(valid.all()):
        invalid_mask = ~valid
        return None, UploadIssue(
            where=f"{filename}:{column_name}",
            message=(
                "Nilai boolean tidak valid pada baris "
                f"{_row_numbers(invalid_mask)}. Gunakan true/false atau 1/0."
            ),
            severity="error",
        )

    parsed = normalized.isin(_TRUE_VALUES)
    return parsed.astype(bool), None


def _canonical_data_hash(df: pd.DataFrame) -> str:
    canonical = (
        df.loc[
            :,
            [
                "date",
                "store_id",
                "sku_id",
                "units_sold",
                "stock_on_hand_start",
                "stock_on_hand_end",
                "stockout_flag",
                "promo_flag",
            ],
        ]
        .sort_values(["date", "store_id", "sku_id"], kind="stable")
        .reset_index(drop=True)
        .copy()
    )

    canonical["date"] = canonical["date"].map(lambda value: value.isoformat())
    for column in NUMERIC_COLUMNS:
        canonical[column] = canonical[column].astype("int64")
    for column in OPTIONAL_BOOLEAN_COLUMNS:
        canonical[column] = canonical[column].astype("int8")

    payload = canonical.to_csv(index=False, lineterminator="\n").encode("utf-8")
    return hashlib.sha256(payload).hexdigest()


def process_sales_upload(
    db: Session,
    file_bytes: bytes,
    filename: str,
) -> DatasetUploadResponse:
    issues: list[UploadIssue] = []

    try:
        csv_text = file_bytes.decode("utf-8-sig")
    except UnicodeDecodeError:
        return _reject(
            issues=[
                UploadIssue(
                    where=filename,
                    message="File CSV harus menggunakan encoding UTF-8.",
                    severity="error",
                )
            ]
        )

    try:
        raw_headers = next(csv.reader(io.StringIO(csv_text)), [])
    except csv.Error as exc:
        return _reject(
            issues=[
                UploadIssue(
                    where=filename,
                    message=f"Header CSV tidak valid: {exc}",
                    severity="error",
                )
            ]
        )

    normalized_headers = [str(column).strip().lower() for column in raw_headers]
    duplicate_headers = sorted(
        {
            column
            for column in normalized_headers
            if normalized_headers.count(column) > 1
        }
    )
    if duplicate_headers:
        return _reject(
            issues=[
                UploadIssue(
                    where=filename,
                    message=(
                        "Nama kolom duplikat: "
                        + ", ".join(duplicate_headers)
                    ),
                    severity="error",
                )
            ]
        )

    try:
        df = pd.read_csv(io.StringIO(csv_text))
    except Exception as exc:
        return _reject(
            issues=[
                UploadIssue(
                    where=filename,
                    message=f"File tidak bisa dibaca sebagai CSV: {exc}",
                    severity="error",
                )
            ]
        )

    if df.empty:
        return _reject(
            issues=[
                UploadIssue(
                    where=filename,
                    message="CSV tidak memiliki baris data.",
                    severity="error",
                )
            ]
        )

    df.columns = [str(column).strip().lower() for column in df.columns]

    missing = REQUIRED_COLUMNS - set(df.columns)
    if missing:
        return _reject(
            issues=[
                UploadIssue(
                    where=filename,
                    message=(
                        "Kolom wajib tidak ditemukan: "
                        + ", ".join(sorted(missing))
                    ),
                    severity="error",
                )
            ]
        )

    parsed_dates = pd.to_datetime(df["date"], errors="coerce")
    invalid_dates = parsed_dates.isna()
    if bool(invalid_dates.any()):
        return _reject(
            issues=[
                UploadIssue(
                    where=f"{filename}:date",
                    message=(
                        "Tanggal tidak valid pada baris "
                        f"{_row_numbers(invalid_dates)}."
                    ),
                    severity="error",
                )
            ]
        )
    df["date"] = parsed_dates.dt.date

    df["store_id"] = df["store_id"].fillna("").astype(str).str.strip()
    df["sku_id"] = df["sku_id"].fillna("").astype(str).str.strip()

    blank_store = df["store_id"].eq("")
    blank_sku = df["sku_id"].eq("")
    if bool(blank_store.any() or blank_sku.any()):
        invalid = blank_store | blank_sku
        return _reject(
            issues=[
                UploadIssue(
                    where=filename,
                    message=(
                        "store_id dan sku_id wajib terisi. Baris bermasalah: "
                        f"{_row_numbers(invalid)}."
                    ),
                    severity="error",
                )
            ]
        )

    for column in NUMERIC_COLUMNS:
        numeric = pd.to_numeric(df[column], errors="coerce")
        invalid_numeric = numeric.isna()
        if bool(invalid_numeric.any()):
            return _reject(
                issues=[
                    UploadIssue(
                        where=f"{filename}:{column}",
                        message=(
                            "Nilai numerik tidak valid pada baris "
                            f"{_row_numbers(invalid_numeric)}."
                        ),
                        severity="error",
                    )
                ]
            )

        non_finite = ~numeric.map(
            lambda value: (
                pd.notna(value)
                and float("-inf") < float(value) < float("inf")
            )
        )
        if bool(non_finite.any()):
            return _reject(
                issues=[
                    UploadIssue(
                        where=f"{filename}:{column}",
                        message=(
                            "Nilai harus finite pada baris "
                            f"{_row_numbers(non_finite)}."
                        ),
                        severity="error",
                    )
                ]
            )

        non_integer = (numeric % 1).abs() > 1e-9
        if bool(non_integer.any()):
            return _reject(
                issues=[
                    UploadIssue(
                        where=f"{filename}:{column}",
                        message=(
                            "Nilai unit/stok harus bilangan bulat pada baris "
                            f"{_row_numbers(non_integer)}."
                        ),
                        severity="error",
                    )
                ]
            )

        negative = numeric < 0
        if bool(negative.any()):
            return _reject(
                issues=[
                    UploadIssue(
                        where=f"{filename}:{column}",
                        message=(
                            "Nilai tidak boleh negatif pada baris "
                            f"{_row_numbers(negative)}."
                        ),
                        severity="error",
                    )
                ]
            )

        df[column] = numeric.astype("int64")

    for column in OPTIONAL_BOOLEAN_COLUMNS:
        if column not in df.columns:
            df[column] = False
            continue

        parsed, issue = _parse_boolean_series(
            df[column],
            column_name=column,
            filename=filename,
        )
        if issue is not None:
            return _reject(issues=[issue])
        assert parsed is not None
        df[column] = parsed

    duplicate_keys = df.duplicated(
        subset=["date", "store_id", "sku_id"],
        keep=False,
    )
    if bool(duplicate_keys.any()):
        return _reject(
            issues=[
                UploadIssue(
                    where=filename,
                    message=(
                        "Kombinasi date + store_id + sku_id harus unik. "
                        "Duplikat ditemukan pada baris "
                        f"{_row_numbers(duplicate_keys)}."
                    ),
                    severity="error",
                )
            ]
        )

    known_store_ids = {
        str(row[0])
        for row in db.execute(select(Store.store_id))
    }
    known_sku_ids = {
        str(row[0])
        for row in db.execute(select(Product.sku_id))
    }

    unknown_stores = set(df["store_id"].unique()) - known_store_ids
    if unknown_stores:
        return _reject(
            issues=[
                UploadIssue(
                    where=filename,
                    message=(
                        "store_id tidak dikenal sistem: "
                        + ", ".join(sorted(unknown_stores))
                    ),
                    severity="error",
                )
            ]
        )

    unknown_skus = set(df["sku_id"].unique()) - known_sku_ids
    if unknown_skus:
        issues.append(
            UploadIssue(
                where=filename,
                message=(
                    f"{len(unknown_skus)} sku_id tidak dikenal sistem dan "
                    "diabaikan: "
                    + ", ".join(sorted(unknown_skus)[:8])
                    + ("…" if len(unknown_skus) > 8 else "")
                ),
                severity="warning",
            )
        )
        df = df[df["sku_id"].isin(known_sku_ids)].copy()

    if df.empty:
        return _reject(
            issues=[
                *issues,
                UploadIssue(
                    where=filename,
                    message="Tidak ada SKU valid yang tersisa setelah validasi.",
                    severity="error",
                ),
            ]
        )

    days_covered = int(df["date"].nunique())
    min_date = min(df["date"])
    max_date = max(df["date"])
    store_count = int(df["store_id"].nunique())
    sku_count = int(df["sku_id"].nunique())
    transaction_count = int(len(df))

    store_days = df.groupby("store_id")["date"].nunique().sort_index()
    short_store_days = store_days[store_days < MIN_DAYS_HARD]
    if not short_store_days.empty:
        details = ", ".join(
            f"{store_id}={int(day_count)} hari"
            for store_id, day_count in short_store_days.items()
        )
        return _reject(
            days_covered=days_covered,
            store_count=store_count,
            sku_count=sku_count,
            transaction_count=transaction_count,
            min_date=min_date,
            max_date=max_date,
            issues=[
                *issues,
                UploadIssue(
                    where=filename,
                    message=(
                        "Setiap toko membutuhkan minimal "
                        f"{MIN_DAYS_HARD} hari histori. Kurang: {details}."
                    ),
                    severity="error",
                ),
            ],
        )

    calendar_min_date, calendar_max_date = db.execute(
        select(
            func.min(CalendarDay.date),
            func.max(CalendarDay.date),
        )
    ).one()

    if calendar_min_date is None or calendar_max_date is None:
        return _reject(
            days_covered=days_covered,
            store_count=store_count,
            sku_count=sku_count,
            transaction_count=transaction_count,
            min_date=min_date,
            max_date=max_date,
            issues=[
                *issues,
                UploadIssue(
                    where="dim_calendar",
                    message="Kalender sistem belum tersedia; dataset belum dapat digunakan.",
                    severity="error",
                ),
            ],
        )

    if min_date < calendar_min_date or max_date > calendar_max_date:
        return _reject(
            days_covered=days_covered,
            store_count=store_count,
            sku_count=sku_count,
            transaction_count=transaction_count,
            min_date=min_date,
            max_date=max_date,
            calendar_min_date=calendar_min_date,
            calendar_max_date=calendar_max_date,
            issues=[
                *issues,
                UploadIssue(
                    where=f"{filename}:date",
                    message=(
                        "Rentang tanggal upload berada di luar kalender yang didukung "
                        f"sistem ({calendar_min_date.isoformat()} s.d. "
                        f"{calendar_max_date.isoformat()})."
                    ),
                    severity="error",
                ),
            ],
        )

    retained_sku_ids = sorted(set(df["sku_id"]))
    supplier_ids = {
        str(row[0])
        for row in db.execute(
            select(Product.supplier_id)
            .where(Product.sku_id.in_(retained_sku_ids))
            .where(Product.supplier_id.is_not(None))
            .distinct()
        )
    }
    supplier_count = len(supplier_ids)

    if days_covered < MIN_DAYS_HARD:
        return _reject(
            days_covered=days_covered,
            store_count=store_count,
            sku_count=sku_count,
            supplier_count=supplier_count,
            transaction_count=transaction_count,
            min_date=min_date,
            max_date=max_date,
            calendar_min_date=calendar_min_date,
            calendar_max_date=calendar_max_date,
            issues=[
                *issues,
                UploadIssue(
                    where=filename,
                    message=(
                        f"Data hanya mencakup {days_covered} hari; minimal "
                        f"{MIN_DAYS_HARD} hari diperlukan."
                    ),
                    severity="error",
                ),
            ],
        )

    if days_covered < MIN_DAYS_SOFT:
        issues.append(
            UploadIssue(
                where=filename,
                message=(
                    f"Data hanya {days_covered} hari; forecast dapat lebih "
                    f"tidak pasti (disarankan minimal {MIN_DAYS_SOFT} hari)."
                ),
                severity="warning",
            )
        )

    data_hash = _canonical_data_hash(df)
    dataset_id = f"upload-{uuid.uuid4().hex[:12]}"

    records = [
        {
            "dataset_id": dataset_id,
            "date": row.date,
            "store_id": row.store_id,
            "sku_id": row.sku_id,
            "units_sold": int(row.units_sold),
            "stock_on_hand_start": int(row.stock_on_hand_start),
            "stock_on_hand_end": int(row.stock_on_hand_end),
            "stockout_flag": bool(row.stockout_flag),
            "promo_flag": bool(row.promo_flag),
        }
        for row in df.itertuples(index=False)
    ]

    try:
        db.execute(
            insert(Dataset.__table__),
            [
                {
                    "dataset_id": dataset_id,
                    "source_type": "upload",
                    "data_hash": data_hash,
                    "readiness_status": "valid",
                    "created_at": datetime.now(timezone.utc),
                }
            ],
        )
        db.execute(insert(DailySales.__table__), records)
        db.commit()
    except Exception:
        db.rollback()
        raise

    return DatasetUploadResponse(
        dataset_id=dataset_id,
        data_hash=data_hash,
        days_covered=days_covered,
        store_count=store_count,
        sku_count=sku_count,
        supplier_count=supplier_count,
        transaction_count=transaction_count,
        min_date=min_date,
        max_date=max_date,
        calendar_min_date=calendar_min_date,
        calendar_max_date=calendar_max_date,
        is_ready=True,
        issues=issues,
    )
