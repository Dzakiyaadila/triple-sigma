from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from app.db.session import get_db
from app.schemas.decision_run import (
    RecommendationUpdateRequest, RecommendationUpdateResponse, ConfirmResponse,
)
from app.services.decision_run_service import update_recommendation, confirm_run
from app.services.plan_cache import plans_cache

router = APIRouter(prefix="/decision-runs", tags=["recommendations"])


@router.patch("/{run_id}/recommendations/{sku_id}", response_model=RecommendationUpdateResponse)
def update_sku_decision(run_id: str, sku_id: str, payload: RecommendationUpdateRequest,
                         db: Session = Depends(get_db)):
    plan = plans_cache.get(run_id)
    if not plan:
        raise HTTPException(status_code=404, detail="Run tidak ditemukan")

    try:
        result = update_recommendation(db, plan, sku_id, payload.status, payload.adjusted_qty)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))

    return result


@router.post("/{run_id}/confirm", response_model=ConfirmResponse)
def confirm_decision_run(run_id: str):
    plan = plans_cache.get(run_id)
    if not plan:
        raise HTTPException(status_code=404, detail="Run tidak ditemukan")
    return confirm_run(plan)