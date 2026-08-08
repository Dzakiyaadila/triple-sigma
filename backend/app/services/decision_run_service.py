from datetime import datetime, timezone, date
from sqlalchemy.orm import Session
from app.db.models import Product, DecisionRun, Recommendation
from app.ml.contracts import MLDecisionConstraints
from app.ml.restock_plan import generate_restock_plan
from app.schemas.decision_run import RestockPlan
from app.services.reasoning import generate_reasoning
from app.services.dataset_scope import ensure_dataset_metadata
from app.services.retail_snapshot_service import build_retail_snapshot


def run_decision(
    db: Session,
    dataset_id: str,
    store_id: str,
    decision_date: str,
    budget_rp: float,
    policy_preset: str = "seimbang",
    horizon_days: int = 7,
    min_fill_rate: float | None = None,
    protected_sku_ids: list[str] | tuple[str, ...] = (),
) -> dict:
    decision_day = date.fromisoformat(decision_date)
    constraints = MLDecisionConstraints(
        budget_rp=budget_rp,
        horizon_days=horizon_days,
        policy_preset=policy_preset,
        min_fill_rate=min_fill_rate,
        protected_sku_ids=tuple(protected_sku_ids),
    )

    snapshot = build_retail_snapshot(
        db,
        dataset_id=dataset_id,
        store_id=store_id,
        decision_date=decision_day,
        horizon_days=horizon_days,
    )

    ensure_dataset_metadata(
        db,
        dataset_id=dataset_id,
    )

    product_by_id = {
        product.sku_id: product
        for product in snapshot.products
    }
    suppliers = {
        supplier.supplier_id: supplier
        for supplier in snapshot.suppliers
    }

    plan = generate_restock_plan(
        snapshot=snapshot,
        constraints=constraints,
    )

    for recommendation in plan["recommendations"]:
        product = product_by_id.get(recommendation["sku_id"])
        supplier = (
            suppliers.get(product.supplier_id)
            if product and product.supplier_id
            else None
        )

        recommendation["sku_name"] = (
            product.product_name if product else recommendation["sku_id"]
        )
        recommendation["category"] = product.category if product else "Lainnya"
        recommendation["supplier_name"] = (
            supplier.supplier_name if supplier else "Supplier tidak diketahui"
        )
        recommendation["supplier_note"] = (
            "Estimasi historis: "
            f"{round(recommendation['supplier_on_time_probability'] * 100)}% "
            "tepat waktu, dengan P90 lead time "
            f"{recommendation['supplier_p90_lead_time_days']:.1f} hari."
        )
        recommendation.update(generate_reasoning(recommendation))

    # Validate the full public contract before any recommendation is persisted.
    plan = RestockPlan.model_validate(plan).model_dump(mode="json")

    run = DecisionRun(
        run_id=plan["run_id"],
        dataset_id=dataset_id,
        store_id=store_id,
        decision_date=decision_day,
        budget_rp=budget_rp,
        policy_preset=policy_preset,
        constraints_json={
            "horizon_days": horizon_days,
            "min_fill_rate": min_fill_rate,
            "protected_sku_ids": list(protected_sku_ids),
        },
        model_version=plan["model_version"],
        data_hash=plan["data_hash"],
        status="completed",
        runtime_ms=plan["runtime_ms"],
        created_at=datetime.now(timezone.utc),
    )
    db.add(run)

    for recommendation in plan["recommendations"]:
        db.add(
            Recommendation(
                run_id=plan["run_id"],
                sku_id=recommendation["sku_id"],
                original_qty=recommendation["recommended_qty"],
                adjusted_qty=None,
                status="belum_diputuskan",
                before_metrics_json=recommendation,
                after_metrics_json=None,
                explanation_json={
                    "reason_codes": recommendation["reason_codes"],
                    "warnings": recommendation["warnings"],
                },
            )
        )

    db.commit()
    return plan


def update_recommendation(db: Session, plan: dict, sku_id: str, status: str,
                           adjusted_qty: int | None) -> dict:
    rec = next((r for r in plan["recommendations"] if r["sku_id"] == sku_id), None)
    if not rec:
        raise ValueError(f"SKU {sku_id} tidak ditemukan di run ini")

    product = db.get(Product, sku_id)
    unit_cost = product.unit_cost_rp if product else 0

    new_qty = (
        0
        if status == "ditolak"
        else (
            adjusted_qty
            if adjusted_qty is not None
            else rec["recommended_qty"]
        )
    )

    if status == "disetujui" and new_qty <= 0:
        raise ValueError(
            "Jumlah SKU yang disetujui harus lebih dari 0 unit."
        )

    new_cost = new_qty * unit_cost

    hypothetical_total = sum(
        (new_cost if r["sku_id"] == sku_id else r["required_cash_rp"])
        for r in plan["recommendations"]
        if (r["sku_id"] == sku_id and status == "disetujui")
        or (r["sku_id"] != sku_id and r["status"] == "disetujui")
    )

    run = db.get(DecisionRun, plan["run_id"])
    if status == "disetujui" and hypothetical_total > run.budget_rp:
        raise ValueError(
            f"Total biaya (Rp{hypothetical_total:,.0f}) melebihi budget "
            f"(Rp{run.budget_rp:,.0f}). Kurangi jumlah atau tolak SKU lain dulu."
        )

    rec["status"] = status
    rec["adjusted_qty"] = adjusted_qty
    rec["required_cash_rp"] = new_cost

    db_rec = db.query(Recommendation).filter_by(run_id=plan["run_id"], sku_id=sku_id).first()
    if db_rec:
        db_rec.status = status
        db_rec.adjusted_qty = adjusted_qty
        db.commit()

    budget_allocated = sum(r["required_cash_rp"] for r in plan["recommendations"] if r["status"] == "disetujui")

    return {
        "sku_id": sku_id, "status": status, "adjusted_qty": adjusted_qty,
        "required_cash_rp": new_cost, "budget_allocated_rp": budget_allocated,
        "budget_remaining_rp": run.budget_rp - budget_allocated,
    }


def confirm_run(plan: dict) -> dict:
    approved = [
        recommendation
        for recommendation in plan["recommendations"]
        if recommendation["status"] == "disetujui"
        and (
            recommendation["adjusted_qty"]
            if recommendation.get("adjusted_qty") is not None
            else recommendation["recommended_qty"]
        ) > 0
    ]

    total_cost = sum(
        recommendation["required_cash_rp"]
        for recommendation in approved
    )

    return {
        "confirmed_count": len(approved),
        "confirmed_at": datetime.now(timezone.utc).isoformat(),
        "total_cost_rp": total_cost,
    }