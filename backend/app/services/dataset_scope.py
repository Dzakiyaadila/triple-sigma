from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

from sqlalchemy.orm import Session

from app.db.models import Dataset


DEMO_DATASET_ID = "demo-retail-v1"


class DatasetScopeError(ValueError):
    """Raised when a decision references an unavailable dataset."""


def dataset_filter(column: Any, dataset_id: str):
    """Return the SQL predicate for a public dataset identifier."""
    if dataset_id == DEMO_DATASET_ID:
        return column.is_(None)
    return column == dataset_id


def ensure_dataset_metadata(
    db: Session,
    *,
    dataset_id: str,
) -> Dataset:
    """Ensure DecisionRun can persist the selected dataset identity."""
    dataset = db.get(Dataset, dataset_id)

    if dataset_id == DEMO_DATASET_ID:
        if dataset is None:
            dataset = Dataset(
                dataset_id=DEMO_DATASET_ID,
                source_type="demo",
                data_hash=None,
                readiness_status="valid",
                created_at=datetime.now(timezone.utc),
            )
            db.add(dataset)
            db.flush()
        return dataset

    if dataset is None:
        raise DatasetScopeError(
            f"Dataset {dataset_id} tidak ditemukan"
        )

    if dataset.readiness_status != "valid":
        raise DatasetScopeError(
            f"Dataset {dataset_id} belum siap digunakan "
            f"(status={dataset.readiness_status})"
        )

    return dataset
