from __future__ import annotations

from dataclasses import dataclass
from math import ceil
from statistics import fmean

import numpy as np

from app.ml.contracts import RetailSnapshot, SupplierDeliveryHistoryRow
from app.ml.oracle_guard import assert_oracle_safe_payload


DEFAULT_PRIOR_STRENGTH = 12.0


@dataclass(frozen=True)
class SupplierRiskEstimate:
    supplier_id: str
    sample_size: int
    on_time_probability: float
    mean_lead_time_days: float
    p90_lead_time_days: float
    delay_probability: float
    horizon_arrival_probability: float
    confidence: str
    warnings: tuple[str, ...]


@dataclass(frozen=True)
class OutstandingArrivalEstimate:
    order_id: str
    sku_id: str
    supplier_id: str
    elapsed_days: int
    horizon_days: int
    arrival_probability: float
    confidence: str
    warnings: tuple[str, ...]


@dataclass(frozen=True)
class SupplierRiskResult:
    horizon_days: int
    suppliers: tuple[SupplierRiskEstimate, ...]
    outstanding_orders: tuple[OutstandingArrivalEstimate, ...]
    warnings: tuple[str, ...]

    def supplier_by_id(self) -> dict[str, SupplierRiskEstimate]:
        return {item.supplier_id: item for item in self.suppliers}

    def arrival_by_order_id(self) -> dict[str, OutstandingArrivalEstimate]:
        return {item.order_id: item for item in self.outstanding_orders}


def _confidence(sample_size: int) -> str:
    if sample_size >= 20:
        return "tinggi"
    if sample_size >= 5:
        return "sedang"
    return "rendah"


def _quantile(values: list[float], q: float) -> float:
    if not values:
        raise ValueError("quantile membutuhkan minimal satu nilai")
    return float(np.quantile(np.asarray(values, dtype=float), q))


def _global_defaults(
    snapshot: RetailSnapshot,
) -> tuple[float, float, float, float, list[float]]:
    history = list(snapshot.supplier_delivery_history)
    promised = [
        float(supplier.promised_lead_time_days)
        for supplier in snapshot.suppliers
    ]

    if history:
        lead_values = [float(row.actual_lead_time_days) for row in history]
        on_time = float(np.mean([row.delay_days <= 0 for row in history]))
        delay_ge2 = float(np.mean([row.delay_days >= 2 for row in history]))
        mean_lead = float(fmean(lead_values))
        p90_lead = _quantile(lead_values, 0.90)
        return on_time, mean_lead, p90_lead, delay_ge2, lead_values

    fallback_lead = float(fmean(promised)) if promised else 1.0
    fallback_values = promised if promised else [fallback_lead]
    return 0.5, fallback_lead, max(fallback_values), 0.5, fallback_values


def _conditional_arrival_probability(
    *,
    local_history: list[SupplierDeliveryHistoryRow],
    global_history: list[SupplierDeliveryHistoryRow],
    elapsed_days: int,
    horizon_days: int,
    prior_strength: float,
) -> tuple[float, tuple[str, ...]]:
    if elapsed_days < 0:
        raise ValueError("elapsed_days tidak boleh negatif")
    if horizon_days < 1:
        raise ValueError("horizon_days harus minimal 1")

    window_end = elapsed_days + horizon_days

    local_at_risk = [
        row
        for row in local_history
        if float(row.actual_lead_time_days) > elapsed_days
    ]
    local_successes = sum(
        elapsed_days < float(row.actual_lead_time_days) <= window_end
        for row in local_history
    )

    global_at_risk = [
        row
        for row in global_history
        if float(row.actual_lead_time_days) > elapsed_days
    ]
    global_successes = sum(
        elapsed_days < float(row.actual_lead_time_days) <= window_end
        for row in global_history
    )

    warnings: list[str] = []
    if global_at_risk:
        prior_mean = global_successes / len(global_at_risk)
    else:
        # Once an outstanding order is older than every completed delivery in
        # the available history, the empirical survival tail has no support.
        # Use an explicit uninformative prior instead of fabricating a tail.
        prior_mean = 0.5
        warnings.append(
            "Usia PO melewati dukungan histori lead time; "
            "probabilitas kedatangan memakai prior netral."
        )

    probability = (
        local_successes + prior_strength * prior_mean
    ) / (len(local_at_risk) + prior_strength)

    return float(np.clip(probability, 0.0, 1.0)), tuple(warnings)


def estimate_supplier_risk(
    snapshot: RetailSnapshot,
    *,
    horizon_days: int,
    prior_strength: float = DEFAULT_PRIOR_STRENGTH,
) -> SupplierRiskResult:
    """Estimate supplier reliability using only outcomes known by the cutoff.

    `RetailSnapshot` already enforces that completed delivery history does not
    extend beyond `decision_date`, and outstanding orders contain no realized
    future lead-time field. This function deliberately consumes only those two
    prediction-time-safe collections.
    """

    assert_oracle_safe_payload(snapshot)
    if horizon_days < 1:
        raise ValueError("horizon_days harus minimal 1")
    if prior_strength <= 0:
        raise ValueError("prior_strength harus positif")

    history = list(snapshot.supplier_delivery_history)
    global_on_time, global_mean, global_p90, global_delay, _ = _global_defaults(
        snapshot
    )

    history_by_supplier: dict[str, list[SupplierDeliveryHistoryRow]] = {}
    for row in history:
        history_by_supplier.setdefault(row.supplier_id, []).append(row)

    supplier_estimates: list[SupplierRiskEstimate] = []
    result_warnings: list[str] = []

    for supplier in sorted(snapshot.suppliers, key=lambda item: item.supplier_id):
        local = history_by_supplier.get(supplier.supplier_id, [])
        n = len(local)
        warnings: list[str] = []

        on_time_successes = sum(row.delay_days <= 0 for row in local)
        delay_successes = sum(row.delay_days >= 2 for row in local)
        local_leads = [float(row.actual_lead_time_days) for row in local]

        on_time_probability = (
            on_time_successes + prior_strength * global_on_time
        ) / (n + prior_strength)
        delay_probability = (
            delay_successes + prior_strength * global_delay
        ) / (n + prior_strength)
        mean_lead = (
            sum(local_leads) + prior_strength * global_mean
        ) / (n + prior_strength)

        if n >= 10:
            p90_lead = _quantile(local_leads, 0.90)
        elif n:
            p90_lead = 0.5 * _quantile(local_leads, 0.90) + 0.5 * global_p90
            warnings.append(
                "Histori supplier terbatas; P90 di-shrink ke distribusi global."
            )
        else:
            p90_lead = global_p90
            warnings.append(
                "Belum ada delivery selesai untuk supplier; estimasi memakai prior global."
            )

        horizon_arrival_probability, arrival_warnings = (
            _conditional_arrival_probability(
                local_history=local,
                global_history=history,
                elapsed_days=0,
                horizon_days=horizon_days,
                prior_strength=prior_strength,
            )
        )
        warnings.extend(arrival_warnings)

        supplier_estimates.append(
            SupplierRiskEstimate(
                supplier_id=supplier.supplier_id,
                sample_size=n,
                on_time_probability=float(np.clip(on_time_probability, 0.0, 1.0)),
                mean_lead_time_days=max(1.0, float(mean_lead)),
                p90_lead_time_days=max(1.0, float(p90_lead)),
                delay_probability=float(np.clip(delay_probability, 0.0, 1.0)),
                horizon_arrival_probability=horizon_arrival_probability,
                confidence=_confidence(n),
                warnings=tuple(warnings),
            )
        )

    arrival_estimates: list[OutstandingArrivalEstimate] = []
    estimate_by_supplier = {
        item.supplier_id: item for item in supplier_estimates
    }

    for order in sorted(snapshot.outstanding_orders, key=lambda item: item.order_id):
        local = history_by_supplier.get(order.supplier_id, [])
        elapsed_days = max(0, (snapshot.decision_date - order.order_date).days)
        probability, warnings = _conditional_arrival_probability(
            local_history=local,
            global_history=history,
            elapsed_days=elapsed_days,
            horizon_days=horizon_days,
            prior_strength=prior_strength,
        )

        supplier_estimate = estimate_by_supplier[order.supplier_id]
        order_warnings = list(warnings)
        if elapsed_days > ceil(supplier_estimate.p90_lead_time_days):
            order_warnings.append(
                "PO outstanding sudah melewati estimasi P90 lead time supplier."
            )

        arrival_estimates.append(
            OutstandingArrivalEstimate(
                order_id=order.order_id,
                sku_id=order.sku_id,
                supplier_id=order.supplier_id,
                elapsed_days=elapsed_days,
                horizon_days=horizon_days,
                arrival_probability=probability,
                confidence=supplier_estimate.confidence,
                warnings=tuple(order_warnings),
            )
        )

    if not history:
        result_warnings.append(
            "Supplier delivery history kosong; seluruh reliability memakai prior/fallback."
        )

    return SupplierRiskResult(
        horizon_days=horizon_days,
        suppliers=tuple(supplier_estimates),
        outstanding_orders=tuple(arrival_estimates),
        warnings=tuple(result_warnings),
    )
