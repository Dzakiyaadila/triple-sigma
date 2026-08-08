from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from app.db.session import get_db
from app.schemas.decision_run import DecisionRunRequest, RestockPlan
from app.services.decision_run_service import run_decision

router = APIRouter(prefix="/decision-runs", tags=["decision-runs"])

from app.services.plan_cache import plans_cache


@router.post("", response_model=RestockPlan)
def create_decision_run(payload: DecisionRunRequest, db: Session = Depends(get_db)):
    try:
        plan = run_decision(
            db=db, dataset_id=payload.dataset_id, store_id=payload.store_id,
            decision_date=payload.decision_date,
            budget_rp=payload.budget_rp, policy_preset=payload.policy_preset,
            horizon_days=payload.horizon_days,
            min_fill_rate=payload.min_fill_rate, protected_sku_ids=payload.protected_sku_ids,
        )
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))

    plans_cache[plan["run_id"]] = plan
    return plan


@router.get("/{run_id}/plan", response_model=RestockPlan)
def get_plan(run_id: str):
    plan = plans_cache.get(run_id)
    if not plan:
        raise HTTPException(status_code=404, detail="Run tidak ditemukan")
    return plan