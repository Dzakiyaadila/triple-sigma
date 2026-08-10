from __future__ import annotations

from copy import deepcopy
from datetime import date, datetime, timezone

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db.models import DecisionRun, Product, Recommendation, Store
from app.ml.contracts import MLDecisionConstraints
from app.ml.restock_plan import generate_restock_plan
from app.schemas.decision_run import RestockPlan
from app.services.dataset_scope import ensure_dataset_metadata
from app.services.plan_cache import plans_cache
from app.services.reasoning import generate_reasoning
from app.services.retail_snapshot_service import build_retail_snapshot


PLAN_SUMMARY_FIELDS = (
    "budget_allocated_rp",
    "expected_nov_contribution_rp",
    "estimated_lmar_avoided_rp",
    "estimated_wcar_added_rp",
    "estimated_fill_rate",
    "data_quality",
    "warnings",
)


class DecisionRunNotFoundError(LookupError):
    pass


class PersistedPlanError(RuntimeError):
    pass


def _plan_summary(plan: dict) -> dict:
    return {
        field: deepcopy(plan[field])
        for field in PLAN_SUMMARY_FIELDS
    }


def _load_run_records(
    db: Session,
    run_id: str,
    *,
    lock: bool = False,
) -> tuple[DecisionRun, list[Recommendation]]:
    statement = select(DecisionRun).where(DecisionRun.run_id == run_id)
    if lock:
        statement = statement.with_for_update()

    run = db.execute(statement).scalar_one_or_none()
    if run is None:
        raise DecisionRunNotFoundError(f"Run tidak ditemukan: {run_id}")

    recommendations = list(
        db.execute(
            select(Recommendation)
            .where(Recommendation.run_id == run_id)
            .order_by(Recommendation.recommendation_id)
        ).scalars()
    )
    return run, recommendations


def _rebuild_plan(
    run: DecisionRun,
    recommendations: list[Recommendation],
) -> dict:
    constraints = (
        deepcopy(run.constraints_json)
        if isinstance(run.constraints_json, dict)
        else {}
    )
    summary = constraints.get("plan_summary")
    if not isinstance(summary, dict):
        raise PersistedPlanError(
            f"Run {run.run_id} dibuat sebelum kontrak durability R8. "
            "Jalankan ulang plan untuk memperoleh state yang dapat dipulihkan."
        )

    missing_summary = [
        field for field in PLAN_SUMMARY_FIELDS if field not in summary
    ]
    if missing_summary:
        raise PersistedPlanError(
            f"Ringkasan plan run {run.run_id} tidak lengkap: "
            f"{missing_summary}"
        )

    rows: list[dict] = []
    for persisted in recommendations:
        if not isinstance(persisted.before_metrics_json, dict):
            raise PersistedPlanError(
                f"Recommendation {persisted.recommendation_id} tidak memiliki "
                "before_metrics_json yang valid."
            )

        row = deepcopy(persisted.before_metrics_json)
        row["status"] = persisted.status
        row["adjusted_qty"] = persisted.adjusted_qty

        after = (
            persisted.after_metrics_json
            if isinstance(persisted.after_metrics_json, dict)
            else {}
        )
        if "required_cash_rp" in after:
            row["required_cash_rp"] = float(after["required_cash_rp"])
        elif persisted.status == "ditolak":
            row["required_cash_rp"] = 0.0

        rows.append(row)

    rows.sort(
        key=lambda row: (
            int(row.get("priority_rank", 0)),
            str(row.get("sku_id", "")),
        )
    )
    plan = {
        "run_id": run.run_id,
        "model_version": run.model_version,
        "data_hash": run.data_hash,
        **deepcopy(summary),
        "runtime_ms": int(run.runtime_ms or 0),
        "recommendations": rows,
    }
    return RestockPlan.model_validate(plan).model_dump(mode="json") | {
        "recommendations": rows
    }


def get_persisted_plan(db: Session, run_id: str) -> dict:
    run, recommendations = _load_run_records(db, run_id)
    plan = _rebuild_plan(run, recommendations)
    plans_cache[run_id] = plan
    return plan


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
        recommendation["category"] = (
            product.category if product else "Lainnya"
        )
        recommendation["supplier_name"] = (
            supplier.supplier_name
            if supplier
            else "Supplier tidak diketahui"
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
            "plan_summary": _plan_summary(plan),
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
    plans_cache[plan["run_id"]] = plan
    return plan


def update_recommendation(
    db: Session,
    run_id: str,
    sku_id: str,
    status: str,
    adjusted_qty: int | None,
) -> dict:
    run, persisted_rows = _load_run_records(db, run_id, lock=True)
    if run.status == "confirmed":
        raise ValueError("Run sudah dikonfirmasi dan tidak dapat diubah.")

    plan = _rebuild_plan(run, persisted_rows)
    rec = next(
        (
            row
            for row in plan["recommendations"]
            if row["sku_id"] == sku_id
        ),
        None,
    )
    if rec is None:
        raise ValueError(f"SKU {sku_id} tidak ditemukan di run ini")

    persisted = next(
        row for row in persisted_rows if row.sku_id == sku_id
    )
    product = db.get(Product, sku_id)
    if product is None or product.unit_cost_rp is None:
        raise ValueError(f"Harga pokok SKU {sku_id} tidak tersedia")
    unit_cost = float(product.unit_cost_rp)

    new_qty = (
        0
        if status == "ditolak"
        else (
            adjusted_qty
            if adjusted_qty is not None
            else int(rec["recommended_qty"])
        )
    )
    if new_qty < 0:
        raise ValueError("Jumlah SKU tidak boleh negatif.")
    if status == "disetujui" and new_qty <= 0:
        raise ValueError(
            "Jumlah SKU yang disetujui harus lebih dari 0 unit."
        )

    new_cost = float(new_qty * unit_cost)
    hypothetical_total = sum(
        (
            new_cost
            if row["sku_id"] == sku_id
            else float(row["required_cash_rp"])
        )
        for row in plan["recommendations"]
        if (
            row["sku_id"] == sku_id
            and status == "disetujui"
        )
        or (
            row["sku_id"] != sku_id
            and row["status"] == "disetujui"
        )
    )

    if status == "disetujui" and hypothetical_total > run.budget_rp:
        raise ValueError(
            f"Total biaya (Rp{hypothetical_total:,.0f}) melebihi budget "
            f"(Rp{run.budget_rp:,.0f}). Kurangi jumlah atau tolak SKU lain dulu."
        )

    persisted.status = status
    persisted.adjusted_qty = adjusted_qty
    persisted.after_metrics_json = {
        "effective_qty": new_qty,
        "required_cash_rp": new_cost,
    }
    db.commit()

    rec["status"] = status
    rec["adjusted_qty"] = adjusted_qty
    rec["required_cash_rp"] = new_cost
    plans_cache[run_id] = plan

    budget_allocated = sum(
        float(row["required_cash_rp"])
        for row in plan["recommendations"]
        if row["status"] == "disetujui"
    )
    return {
        "sku_id": sku_id,
        "status": status,
        "adjusted_qty": adjusted_qty,
        "required_cash_rp": new_cost,
        "budget_allocated_rp": budget_allocated,
        "budget_remaining_rp": float(run.budget_rp - budget_allocated),
    }


def confirm_run(db: Session, run_id: str) -> dict:
    run, persisted_rows = _load_run_records(db, run_id, lock=True)
    constraints = (
        deepcopy(run.constraints_json)
        if isinstance(run.constraints_json, dict)
        else {}
    )
    existing = constraints.get("confirmation")
    if isinstance(existing, dict):
        return deepcopy(existing)

    plan = _rebuild_plan(run, persisted_rows)
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
        float(recommendation["required_cash_rp"])
        for recommendation in approved
    )
    result = {
        "confirmed_count": len(approved),
        "confirmed_at": datetime.now(timezone.utc).isoformat(),
        "total_cost_rp": total_cost,
    }

    run.status = "confirmed"
    constraints["confirmation"] = result
    run.constraints_json = constraints
    db.commit()
    plans_cache[run_id] = plan
    return result


def list_confirmed_runs(db: Session) -> list[dict]:
    runs = list(
        db.execute(
            select(DecisionRun)
            .where(DecisionRun.status == "confirmed")
            .order_by(DecisionRun.created_at.desc(), DecisionRun.run_id.desc())
        ).scalars()
    )

    history: list[dict] = []
    for run in runs:
        constraints = (
            run.constraints_json
            if isinstance(run.constraints_json, dict)
            else {}
        )
        confirmation = constraints.get("confirmation")
        if not isinstance(confirmation, dict):
            continue

        persisted_rows = list(
            db.execute(
                select(Recommendation)
                .where(Recommendation.run_id == run.run_id)
                .order_by(Recommendation.recommendation_id)
            ).scalars()
        )
        items: list[dict] = []
        for persisted in persisted_rows:
            if persisted.status != "disetujui":
                continue

            before = (
                persisted.before_metrics_json
                if isinstance(persisted.before_metrics_json, dict)
                else {}
            )
            after = (
                persisted.after_metrics_json
                if isinstance(persisted.after_metrics_json, dict)
                else {}
            )
            qty = int(
                after.get(
                    "effective_qty",
                    persisted.adjusted_qty
                    if persisted.adjusted_qty is not None
                    else persisted.original_qty or 0,
                )
            )
            if qty <= 0:
                continue

            items.append(
                {
                    "sku_id": persisted.sku_id,
                    "sku_name": before.get("sku_name", persisted.sku_id),
                    "qty": qty,
                    "subtotal": float(
                        after.get(
                            "required_cash_rp",
                            before.get("required_cash_rp", 0),
                        )
                    ),
                }
            )

        store = db.get(Store, run.store_id)
        history.append(
            {
                "id": run.run_id,
                "date": run.decision_date.isoformat(),
                "store_id": run.store_id,
                "store_name": (
                    store.store_name if store is not None else run.store_id
                ),
                "budget": float(run.budget_rp),
                "approved_count": int(confirmation["confirmed_count"]),
                "total": float(confirmation["total_cost_rp"]),
                "status": "Selesai",
                "items": items,
            }
        )

    return history
