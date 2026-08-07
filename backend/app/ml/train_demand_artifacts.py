from __future__ import annotations

import argparse
from datetime import date
from pathlib import Path

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db.models import DailySales
from app.db.session import engine
from app.ml.artifact_store import DEFAULT_ARTIFACT_DIR
from app.ml.demand_training import TrainingConfig, train_demand_artifacts
from app.services.dataset_scope import DEMO_DATASET_ID, dataset_filter
from app.services.retail_snapshot_service import build_retail_snapshot

DEFAULT_TRAINING_CUTOFF = date(2024, 5, 31)


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Train production-safe RestockIQ demand artifacts"
    )
    parser.add_argument("--dataset-id", default=DEMO_DATASET_ID)
    parser.add_argument(
        "--decision-date",
        default=DEFAULT_TRAINING_CUTOFF.isoformat(),
        help=(
            "Artifact training cutoff. Default is frozen before the June "
            "demo/evaluation window to preserve temporal causality."
        ),
    )
    parser.add_argument("--lookback-days", type=int, default=182)
    parser.add_argument("--artifact-dir", default=str(DEFAULT_ARTIFACT_DIR))
    args = parser.parse_args()

    training_date = date.fromisoformat(args.decision_date)
    with Session(engine) as db:
        store_ids = list(
            db.scalars(
                select(DailySales.store_id)
                .where(dataset_filter(DailySales.dataset_id, args.dataset_id))
                .where(DailySales.date <= training_date)
                .distinct()
                .order_by(DailySales.store_id)
            )
        )
        if not store_ids:
            raise ValueError(
                f"Dataset {args.dataset_id} tidak memiliki toko training "
                f"sampai {training_date.isoformat()}"
            )

        snapshots = [
            build_retail_snapshot(
                db,
                dataset_id=args.dataset_id,
                store_id=store_id,
                decision_date=training_date,
                horizon_days=1,
                lookback_days=args.lookback_days,
            )
            for store_id in store_ids
        ]

    manifest = train_demand_artifacts(
        snapshots,
        artifact_dir=Path(args.artifact_dir),
        training_dataset_id=args.dataset_id,
        config=TrainingConfig(),
    )
    print("version:", manifest["version"])
    print("training cutoff:", manifest["training_cutoff"])
    print("training hash:", manifest["training_data_hash"])
    print("artifact dir:", Path(args.artifact_dir).resolve())
    print("oracle fields used:", manifest["oracle_fields_used_as_features"])


if __name__ == "__main__":
    main()
