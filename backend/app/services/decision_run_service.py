from datetime import datetime, timezone, date
from sqlalchemy.orm import Session
from sqlalchemy import select
from app.db.models import Store, Product, DecisionRun, Recommendation
from app.ml.restock_plan import generate_restock_plan


def run_decision(db: Session, store_id: str, decision_date: str, budget_rp: float,
                  policy_preset: str = "balanced", horizon_days: int = 7) -> dict:
    store = db.get(Store, store_id)
    if not store:
        raise ValueError(f"Toko {store_id} tidak ditemukan")

    products = db.scalars(select(Product)).all()
    product_dicts = [
        {"sku_id": p.sku_id, "unit_cost_rp": p.unit_cost_rp} for p in products
    ]

    plan = generate_restock_plan(
        products=product_dicts, store_id=store_id, decision_date=decision_date,
        budget_rp=budget_rp, policy_preset=policy_preset, horizon_days=horizon_days,
    )

    run = DecisionRun(
        run_id=plan["run_id"], dataset_id=None, store_id=store_id,
        decision_date=date.fromisoformat(decision_date), budget_rp=budget_rp,
        policy_preset=policy_preset, constraints_json={"horizon_days": horizon_days},
        model_version=plan["model_version"], data_hash=plan["data_hash"],
        status="completed", runtime_ms=plan["runtime_ms"],
        created_at=datetime.now(timezone.utc),
    )
    db.add(run)

    for r in plan["recommendations"]:
        db.add(Recommendation(
            run_id=plan["run_id"], sku_id=r["sku_id"],
            original_qty=r["recommended_qty"], adjusted_qty=None,
            status="belum_diputuskan", before_metrics_json=r,
            after_metrics_json=None,
            explanation_json={"reason_codes": r["reason_codes"], "warnings": r["warnings"]},
        ))

    db.commit()
    return plan