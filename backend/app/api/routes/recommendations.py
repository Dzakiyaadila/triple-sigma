from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from app.db.session import get_db
from app.schemas.decision_run import (
    RecommendationUpdateRequest, RecommendationUpdateResponse, ConfirmResponse,
)
from app.services.decision_run_service import (
    DecisionRunNotFoundError,
    PersistedPlanError,
    confirm_run,
    update_recommendation,
)

router = APIRouter(prefix="/decision-runs", tags=["recommendations"])


@router.patch("/{run_id}/recommendations/{sku_id}", response_model=RecommendationUpdateResponse)
def update_sku_decision(run_id: str, sku_id: str, payload: RecommendationUpdateRequest,
                         db: Session = Depends(get_db)):
    try:
        result = update_recommendation(
            db,
            run_id,
            sku_id,
            payload.status,
            payload.adjusted_qty,
        )
    except DecisionRunNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except PersistedPlanError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc

    return result


@router.post("/{run_id}/confirm", response_model=ConfirmResponse)
def confirm_decision_run(run_id: str, db: Session = Depends(get_db)):
    try:
        return confirm_run(db, run_id)
    except DecisionRunNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except PersistedPlanError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
