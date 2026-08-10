import csv
import io
from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import StreamingResponse
from sqlalchemy.orm import Session

from app.db.session import get_db
from app.services.decision_run_service import (
    DecisionRunNotFoundError,
    PersistedPlanError,
    get_persisted_plan,
)

router = APIRouter(prefix="/decision-runs", tags=["export"])


@router.get("/{run_id}/export.csv")
def export_csv(run_id: str, db: Session = Depends(get_db)):
    try:
        plan = get_persisted_plan(db, run_id)
    except DecisionRunNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except PersistedPlanError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc

    approved = [r for r in plan["recommendations"] if r["status"] == "disetujui"]

    buffer = io.StringIO()
    writer = csv.writer(buffer)
    writer.writerow(["sku_id", "quantity", "required_cash_rp", "status"])
    for r in approved:
        qty = r["adjusted_qty"] if r["adjusted_qty"] is not None else r["recommended_qty"]
        writer.writerow([r["sku_id"], qty, r["required_cash_rp"], r["status"]])
    buffer.seek(0)

    return StreamingResponse(
        buffer, media_type="text/csv",
        headers={"Content-Disposition": f"attachment; filename=purchase_order_{run_id}.csv"},
    )
