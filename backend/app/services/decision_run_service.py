from datetime import datetime, timezone, date
from sqlalchemy.orm import Session
from sqlalchemy import select, func
from app.db.models import Store, Product, Supplier, DailySales, DecisionRun, Recommendation
from app.ml.restock_plan import generate_restock_plan
from app.services.reasoning import generate_reasoning
from app.core.constants import DEMO_DATASET_ID

def run_decision(db: Session, store_id: str, decision_date: str, budget_rp: float,
                  policy_preset: str = "seimbang", horizon_days: int = 7,
                  dataset_id: str | None = None) -> dict:
    store = db.get(Store, store_id)
    if not store:
        raise ValueError(f"Toko {store_id} tidak ditemukan")

    if dataset_id in (None, DEMO_DATASET_ID):
        dataset_filter = DailySales.dataset_id.is_(None)
    else:
        dataset_filter = DailySales.dataset_id == dataset_id

    sku_ids_query = select(func.distinct(DailySales.sku_id)).where(
        DailySales.store_id == store_id, dataset_filter,
    )
    scoped_sku_ids = {row[0] for row in db.execute(sku_ids_query)}
    if not scoped_sku_ids:
        raise ValueError(
            f"Tidak ada data transaksi untuk toko {store_id} pada dataset ini"
        )

    products = db.scalars(
        select(Product).where(Product.sku_id.in_(scoped_sku_ids))
    ).all()
    product_dicts = [
        {"sku_id": p.sku_id, "unit_cost_rp": p.unit_cost_rp} for p in products
    ]

    product_by_id = {p.sku_id: p for p in products}
    suppliers = {s.supplier_id: s for s in db.scalars(select(Supplier)).all()}

    plan = generate_restock_plan(
        products=product_dicts, store_id=store_id, decision_date=decision_date,
        budget_rp=budget_rp, policy_preset=policy_preset, horizon_days=horizon_days,
    )

    for r in plan["recommendations"]:
        product = product_by_id.get(r["sku_id"])
        supplier = suppliers.get(product.supplier_id) if product and product.supplier_id else None

        r["sku_name"] = product.product_name if product else r["sku_id"]
        r["category"] = product.category if product else "Lainnya"
        r["supplier_name"] = supplier.supplier_name if supplier else "Supplier tidak diketahui"
        r["supplier_note"] = (
            f"Kemungkinan tepat waktu {round(r['supplier_on_time_probability'] * 100)}%, "
            f"estimasi kedatangan sampai {r['supplier_p90_lead_time_days']} hari."
        )
        r.update(generate_reasoning(r))

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
