from __future__ import annotations

from datetime import date
from time import perf_counter
import uuid

from app.ml.artifact_store import ModelArtifacts, load_model_artifacts
from app.ml.contracts import MLDecisionConstraints, RetailSnapshot
from app.ml.demand_engine import DemandForecastResult, generate_demand_forecasts
from app.ml.optimizer import OptimizationResult, optimize_exact_mckp
from app.ml.risk_engine import RiskEngineResult, build_risk_profiles
from app.ml.supplier_risk import SupplierRiskResult, estimate_supplier_risk


DECISION_ENGINE_VERSION = "restockiq-planner-v1"
VALID_REASON_CODES = frozenset(
    {
        "risiko_stockout_tinggi",
        "supplier_andal",
        "supplier_kurang_andal",
        "data_historis_kurang",
    }
)


class PlannerCompatibilityError(ValueError):
    """Raised when a valid request cannot safely use the loaded artifact."""


def _validate_inputs(
    snapshot: RetailSnapshot,
    artifacts: ModelArtifacts,
    constraints: MLDecisionConstraints,
) -> None:
    snapshot_horizon = (snapshot.horizon_end_date - snapshot.decision_date).days
    if snapshot_horizon != constraints.horizon_days:
        raise ValueError(
            "Horizon snapshot tidak cocok dengan decision constraints: "
            f"snapshot={snapshot_horizon}, constraints={constraints.horizon_days}"
        )

    if constraints.horizon_days not in artifacts.forecasts:
        raise PlannerCompatibilityError(
            f"Artifact tidak mendukung horizon {constraints.horizon_days}; "
            f"supported={sorted(artifacts.forecasts)}"
        )

    training_cutoff = date.fromisoformat(artifacts.training_cutoff)
    if training_cutoff >= snapshot.decision_date:
        raise PlannerCompatibilityError(
            "Artifact demand harus dilatih sebelum decision_date untuk replay causal. "
            f"training_cutoff={training_cutoff.isoformat()}, "
            f"decision_date={snapshot.decision_date.isoformat()}"
        )

    if constraints.min_fill_rate is not None:
        raise ValueError(
            "min_fill_rate belum didukung sebagai exact optimizer constraint. "
            "Jangan kirim constraint ini sampai service-level control diaktifkan."
        )


def _combine_confidence(demand_confidence: str, supplier_confidence: str) -> str:
    levels = {"rendah": 0, "sedang": 1, "tinggi": 2}
    if demand_confidence not in levels or supplier_confidence not in levels:
        raise ValueError("Confidence level tidak dikenal")

    level = min(levels[demand_confidence], levels[supplier_confidence])
    return {0: "rendah", 1: "sedang", 2: "tinggi"}[level]


def _reason_codes(
    *,
    stockout_probability: float,
    supplier_on_time_probability: float,
    confidence: str,
) -> list[str]:
    codes: list[str] = []

    if stockout_probability >= 0.30:
        codes.append("risiko_stockout_tinggi")

    if supplier_on_time_probability >= 0.85:
        codes.append("supplier_andal")
    else:
        codes.append("supplier_kurang_andal")

    if confidence == "rendah":
        codes.append("data_historis_kurang")

    if not set(codes).issubset(VALID_REASON_CODES):
        raise AssertionError("Planner menghasilkan reason code di luar contract")
    return codes


def _data_quality(recommendations: list[dict]) -> str:
    confidences = [item["confidence"] for item in recommendations]
    if any(value == "rendah" for value in confidences):
        return "terbatas"
    if any(value == "sedang" for value in confidences):
        return "cukup"
    return "baik"


def _estimated_fill_rate(recommendations: list[dict]) -> float:
    if not recommendations:
        return 1.0

    weights = [max(0.0, float(item["forecast_q50"])) for item in recommendations]
    total_weight = sum(weights)
    if total_weight <= 1e-12:
        return float(
            sum(float(item["_expected_fill_rate_after"]) for item in recommendations)
            / len(recommendations)
        )

    return float(
        sum(
            float(item["_expected_fill_rate_after"]) * weight
            for item, weight in zip(recommendations, weights, strict=True)
        )
        / total_weight
    )


def _build_recommendations(
    *,
    snapshot: RetailSnapshot,
    demand: DemandForecastResult,
    suppliers: SupplierRiskResult,
    risk: RiskEngineResult,
    optimization: OptimizationResult,
) -> list[dict]:
    demand_by_sku = {item.sku_id: item for item in demand.forecasts}
    supplier_by_id = suppliers.supplier_by_id()
    profile_by_sku = risk.profile_by_sku()
    allocation_by_sku = optimization.allocation_by_sku()

    rows: list[dict] = []
    for product in snapshot.products:
        sku_id = product.sku_id
        demand_item = demand_by_sku[sku_id]
        profile = profile_by_sku[sku_id]
        allocation = allocation_by_sku[sku_id]
        option = allocation.option
        supplier = supplier_by_id[product.supplier_id]

        confidence = _combine_confidence(
            demand_item.confidence,
            supplier.confidence,
        )
        warnings = tuple(
            dict.fromkeys(
                [
                    *demand_item.warnings,
                    *supplier.warnings,
                    *profile.warnings,
                ]
            )
        )
        # NOV at the product boundary is the exact policy-adjusted Rupiah
        # utility used by the optimizer. Keeping one definition prevents the UI
        # from showing a "NOV" number that disagrees with the allocation objective.
        expected_nov = float(allocation.objective_increment_rp)

        rows.append(
            {
                "sku_id": sku_id,
                "recommended_qty": int(allocation.quantity),
                "required_cash_rp": float(allocation.cash_required_rp),
                "inventory_on_hand": float(profile.inventory_on_hand),
                "inventory_on_order": float(profile.inventory_on_order),
                "effective_inventory": float(profile.effective_inventory),
                "forecast_q10": float(profile.forecast_q10),
                "forecast_q50": float(profile.forecast_q50),
                "forecast_q90": float(profile.forecast_q90),
                # The production model is direct cumulative H1/H7/H14. Do not
                # fabricate a daily path by dividing cumulative quantiles.
                "forecast_daily_series": [],
                "stockout_risk_before": float(profile.baseline.stockout_probability),
                "stockout_risk_after": float(option.stockout_risk_after),
                "lmar_before_rp": float(profile.baseline.lmar_rp),
                "lmar_after_rp": float(option.lmar_after_rp),
                "incremental_lmar_avoided_rp": float(
                    option.incremental_lmar_avoided_rp
                ),
                "wcar_before_rp": float(profile.baseline.wcar_rp),
                "wcar_after_rp": float(option.wcar_after_rp),
                "incremental_wcar_added_rp": float(option.incremental_wcar_added_rp),
                "supplier_on_time_probability": float(supplier.on_time_probability),
                "supplier_p90_lead_time_days": float(supplier.p90_lead_time_days),
                "expected_nov_contribution_rp": expected_nov,
                "confidence": confidence,
                "reason_codes": _reason_codes(
                    stockout_probability=profile.baseline.stockout_probability,
                    supplier_on_time_probability=supplier.on_time_probability,
                    confidence=confidence,
                ),
                "warnings": list(warnings),
                "status": "belum_diputuskan",
                "_priority_score": float(allocation.objective_increment_rp),
                "_expected_fill_rate_after": float(option.expected_fill_rate_after),
            }
        )

    rows.sort(
        key=lambda item: (
            item["recommended_qty"] <= 0,
            -item["_priority_score"],
            -item["stockout_risk_before"],
            -item["lmar_before_rp"],
            item["sku_id"],
        )
    )

    for rank, item in enumerate(rows, start=1):
        item["priority_rank"] = rank

    return rows


def generate_restock_plan(
    *,
    snapshot: RetailSnapshot,
    constraints: MLDecisionConstraints,
    artifacts: ModelArtifacts | None = None,
) -> dict:
    """Run the production predictive-to-prescriptive decision pipeline."""

    started = perf_counter()
    loaded_artifacts = artifacts if artifacts is not None else load_model_artifacts()
    _validate_inputs(snapshot, loaded_artifacts, constraints)

    demand = generate_demand_forecasts(
        snapshot,
        loaded_artifacts,
        horizon_days=constraints.horizon_days,
    )
    supplier_risk = estimate_supplier_risk(
        snapshot,
        horizon_days=constraints.horizon_days,
    )
    risk = build_risk_profiles(
        snapshot,
        demand,
        supplier_risk,
        horizon_days=constraints.horizon_days,
    )
    optimization = optimize_exact_mckp(
        risk,
        budget_rp=constraints.budget_rp,
        policy_preset=constraints.policy_preset,
        protected_sku_ids=constraints.protected_sku_ids,
    )

    recommendations = _build_recommendations(
        snapshot=snapshot,
        demand=demand,
        suppliers=supplier_risk,
        risk=risk,
        optimization=optimization,
    )
    estimated_fill_rate = _estimated_fill_rate(recommendations)

    total_lmar_avoided = float(
        sum(item["incremental_lmar_avoided_rp"] for item in recommendations)
    )
    total_wcar_added = float(
        sum(max(0.0, item["incremental_wcar_added_rp"]) for item in recommendations)
    )
    total_nov = float(
        sum(item["expected_nov_contribution_rp"] for item in recommendations)
    )

    top_warnings: list[str] = [
        *snapshot.warnings,
        *demand.warnings,
        *supplier_risk.warnings,
        *risk.warnings,
    ]
    if loaded_artifacts.training_dataset_id != snapshot.dataset_id:
        top_warnings.append(
            "Demand artifact dilatih pada dataset "
            f"{loaded_artifacts.training_dataset_id}; inference dataset saat ini "
            f"adalah {snapshot.dataset_id}."
        )
    low_confidence_count = sum(
        item["confidence"] == "rendah" for item in recommendations
    )
    if low_confidence_count:
        top_warnings.append(
            f"{low_confidence_count} SKU memiliki confidence rendah."
        )

    if abs(total_nov - float(optimization.objective_increment_rp)) > 1e-6:
        raise AssertionError("NOV summary harus sama dengan objective exact optimizer")

    for item in recommendations:
        item.pop("_priority_score", None)
        item.pop("_expected_fill_rate_after", None)

    runtime_ms = max(0, int(round((perf_counter() - started) * 1000)))
    return {
        "run_id": f"run_{uuid.uuid4().hex[:12]}",
        "model_version": (
            f"{DECISION_ENGINE_VERSION}+{loaded_artifacts.version}"
        ),
        "data_hash": snapshot.data_hash(),
        "budget_allocated_rp": float(optimization.cash_used_rp),
        "expected_nov_contribution_rp": total_nov,
        "estimated_lmar_avoided_rp": total_lmar_avoided,
        "estimated_wcar_added_rp": total_wcar_added,
        "estimated_fill_rate": estimated_fill_rate,
        "data_quality": _data_quality(recommendations),
        "warnings": list(dict.fromkeys(top_warnings)),
        "runtime_ms": runtime_ms,
        "recommendations": recommendations,
    }
