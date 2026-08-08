from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app.db.session import get_db
from app.ml.artifact_store import ArtifactError
from app.ml.optimizer import OptimizationInfeasibleError
from app.schemas.decision_run import DecisionRunRequest, RestockPlan
from app.services.decision_run_service import run_decision
from app.services.plan_cache import plans_cache

router = APIRouter(prefix="/decision-runs", tags=["decision-runs"])


@router.post("", response_model=RestockPlan)
def create_decision_run(payload: DecisionRunRequest, db: Session = Depends(get_db)):
    try:
        plan = run_decision(
            db=db,
            dataset_id=payload.dataset_id,
            store_id=payload.store_id,
            decision_date=payload.decision_date,
            budget_rp=payload.budget_rp,
            policy_preset=payload.policy_preset,
            horizon_days=payload.horizon_days,
            min_fill_rate=payload.min_fill_rate,
            protected_sku_ids=payload.protected_sku_ids,
        )
    except ArtifactError as exc:
        raise HTTPException(
            status_code=503,
            detail=f"Model demand belum tersedia: {exc}",
        ) from exc
    except OptimizationInfeasibleError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc

    plans_cache[plan["run_id"]] = plan
    return plan


@router.get("/{run_id}/plan", response_model=RestockPlan)
def get_plan(run_id: str):
    plan = plans_cache.get(run_id)
    if not plan:
        raise HTTPException(status_code=404, detail="Run tidak ditemukan")
    return plan