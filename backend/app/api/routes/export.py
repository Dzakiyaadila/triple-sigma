import csv
import io
from fastapi import APIRouter, HTTPException
from fastapi.responses import StreamingResponse
from app.services.plan_cache import plans_cache

router = APIRouter(prefix="/decision-runs", tags=["export"])


@router.get("/{run_id}/export.csv")
def export_csv(run_id: str):
    plan = plans_cache.get(run_id)
    if not plan:
        raise HTTPException(status_code=404, detail="Run tidak ditemukan")

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