"""
STUB — akan digantikan implementasi team ML. Untuk sekarang, fungsi ini
menghasilkan data dummy yang PERSIS mengikuti skema RestockPlan/SKURecommendation
di app/schemas/decision_run.py, supaya backend+frontend bisa terus jalan.
"""
import random
import uuid
from datetime import date, timedelta


def generate_restock_plan(products: list[dict], store_id: str, decision_date: str,
                           budget_rp: float, policy_preset: str = "seimbang",
                           horizon_days: int = 7,
                           protected_sku_ids: list[str] | None = None,
                           min_fill_rate: float | None = None) -> dict:
    rng = random.Random(f"{store_id}-{decision_date}-{budget_rp}")
    protected_set = set(protected_sku_ids or [])

    candidates = []
    for p in products:
        q50 = rng.randint(15, 60)
        q10 = max(1, int(q50 * rng.uniform(0.5, 0.75)))
        q90 = int(q50 * rng.uniform(1.25, 1.6))

        inventory_on_hand = rng.randint(0, 20)
        inventory_on_order = rng.choice([0, 0, 0, 10, 15])
        effective_inventory = inventory_on_hand + inventory_on_order

        stockout_risk_before = round(rng.uniform(0.1, 0.5), 2)
        unit_cost = p["unit_cost_rp"] or 1000

        lmar_before = round(q50 * unit_cost * rng.uniform(0.8, 2.2), -3)
        wcar_before = round(inventory_on_hand * unit_cost * rng.uniform(0.3, 1.0), -3)

        candidates.append({
            "sku_id": p["sku_id"], "unit_cost": unit_cost,
            "q10": q10, "q50": q50, "q90": q90,
            "inventory_on_hand": inventory_on_hand,
            "inventory_on_order": inventory_on_order,
            "effective_inventory": effective_inventory,
            "stockout_risk_before": stockout_risk_before,
            "lmar_before": lmar_before, "wcar_before": wcar_before,
            "supplier_on_time_probability": round(rng.uniform(0.65, 0.97), 2),
            "supplier_p90_lead_time_days": rng.randint(2, 7),
        })

    # SKU yang dilindungi dapat prioritas alokasi budget paling awal,
    # sisanya diurutkan seperti biasa (risiko x LMAR, makin tinggi makin prioritas).
    protected_candidates = [c for c in candidates if c["sku_id"] in protected_set]
    other_candidates = [c for c in candidates if c["sku_id"] not in protected_set]
    other_candidates.sort(key=lambda c: c["stockout_risk_before"] * c["lmar_before"], reverse=True)
    candidates = protected_candidates + other_candidates

    recommendations = []
    running_cost = 0.0
    for rank, c in enumerate(candidates, start=1):
        qty = max(0, c["q50"] - c["effective_inventory"])
        cost = qty * c["unit_cost"]

        if running_cost + cost > budget_rp:
            qty = max(0, int((budget_rp - running_cost) / c["unit_cost"])) if c["unit_cost"] > 0 else 0
            cost = qty * c["unit_cost"]
        running_cost += cost

        risk_reduction = 0.65 if qty > 0 else 0.0
        stockout_risk_after = round(c["stockout_risk_before"] * (1 - risk_reduction), 2)
        lmar_after = round(c["lmar_before"] * (1 - risk_reduction), -3)
        wcar_after = round(c["wcar_before"] + cost * 0.4, -3)

        confidence = "tinggi" if c["supplier_on_time_probability"] > 0.85 else (
            "sedang" if c["supplier_on_time_probability"] > 0.7 else "rendah")

        reason_codes = []
        if c["stockout_risk_before"] > 0.3:
            reason_codes.append("risiko_stockout_tinggi")
        reason_codes.append("supplier_andal" if c["supplier_on_time_probability"] > 0.85 else "supplier_kurang_andal")
        if c["sku_id"] in protected_set:
            reason_codes.append("sku_dilindungi")

        start = date.fromisoformat(decision_date)
        daily_series = [
            {
                "date": (start + timedelta(days=i + 1)).isoformat(),
                "q10": round(c["q10"] / horizon_days, 1),
                "q50": round(c["q50"] / horizon_days, 1),
                "q90": round(c["q90"] / horizon_days, 1),
            }
            for i in range(min(horizon_days, 7))
        ]

        nov = (c["lmar_before"] - lmar_after) - (wcar_after - c["wcar_before"]) * 0.1

        item_warnings = [] if confidence != "rendah" else ["Data historis SKU ini terbatas"]

        recommendations.append({
            "sku_id": c["sku_id"], "priority_rank": rank, "recommended_qty": qty,
            "required_cash_rp": cost,
            "inventory_on_hand": c["inventory_on_hand"],
            "inventory_on_order": c["inventory_on_order"],
            "effective_inventory": c["effective_inventory"],
            "forecast_q10": c["q10"], "forecast_q50": c["q50"], "forecast_q90": c["q90"],
            "forecast_daily_series": daily_series,
            "stockout_risk_before": c["stockout_risk_before"],
            "stockout_risk_after": stockout_risk_after,
            "lmar_before_rp": c["lmar_before"], "lmar_after_rp": lmar_after,
            "incremental_lmar_avoided_rp": c["lmar_before"] - lmar_after,
            "wcar_before_rp": c["wcar_before"], "wcar_after_rp": wcar_after,
            "incremental_wcar_added_rp": wcar_after - c["wcar_before"],
            "supplier_on_time_probability": c["supplier_on_time_probability"],
            "supplier_p90_lead_time_days": c["supplier_p90_lead_time_days"],
            "expected_nov_contribution_rp": nov,
            "confidence": confidence, "reason_codes": reason_codes,
            "warnings": item_warnings,
            "status": "belum_diputuskan",
        })

    total_lmar = sum(r["incremental_lmar_avoided_rp"] for r in recommendations)
    total_wcar = sum(r["incremental_wcar_added_rp"] for r in recommendations)
    total_nov = sum(r["expected_nov_contribution_rp"] for r in recommendations)
    fill_rate = round(sum(1 for r in recommendations if r["recommended_qty"] > 0) / max(len(recommendations), 1), 2)

    plan_warnings = []
    if min_fill_rate is not None and fill_rate < min_fill_rate:
        plan_warnings.append(
            f"Fill rate hasil optimisasi ({round(fill_rate * 100)}%) belum mencapai target "
            f"minimum ({round(min_fill_rate * 100)}%). Pertimbangkan menambah modal restock."
        )

    return {
        "run_id": f"run_{uuid.uuid4().hex[:12]}",
        "model_version": "mock-v0.1", "data_hash": "dummy-hash",
        "budget_allocated_rp": running_cost,
        "expected_nov_contribution_rp": total_nov,
        "estimated_lmar_avoided_rp": total_lmar,
        "estimated_wcar_added_rp": total_wcar,
        "estimated_fill_rate": fill_rate,
        "data_quality": "baik (data simulasi)", "warnings": plan_warnings,
        "runtime_ms": rng.randint(300, 900),
        "recommendations": recommendations,
    }