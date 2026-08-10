from __future__ import annotations

from dataclasses import dataclass
import math

import numpy as np

from app.ml.contracts import ProductSnapshot, RetailSnapshot
from app.ml.demand_engine import DemandForecastResult, QuantileForecast
from app.ml.supplier_risk import SupplierRiskResult


DEFAULT_SCENARIO_COUNT = 61
DEFAULT_MAX_ORDER_QTY = 120


@dataclass(frozen=True)
class RiskMetrics:
    stockout_probability: float
    lmar_rp: float
    wcar_rp: float
    expected_fill_rate: float


@dataclass(frozen=True)
class SKUQuantityOption:
    sku_id: str
    quantity: int
    cash_required_rp: float
    expected_available_inventory: float
    stockout_risk_after: float
    lmar_after_rp: float
    wcar_after_rp: float
    expected_fill_rate_after: float
    incremental_lmar_avoided_rp: float
    incremental_wcar_added_rp: float


@dataclass(frozen=True)
class SKURiskProfile:
    sku_id: str
    supplier_id: str
    inventory_on_hand: float
    inventory_on_order: float
    effective_inventory: float
    new_order_arrival_probability: float
    forecast_q10: float
    forecast_q50: float
    forecast_q90: float
    baseline: RiskMetrics
    options: tuple[SKUQuantityOption, ...]
    warnings: tuple[str, ...]


@dataclass(frozen=True)
class RiskEngineResult:
    horizon_days: int
    profiles: tuple[SKURiskProfile, ...]
    warnings: tuple[str, ...]

    def profile_by_sku(self) -> dict[str, SKURiskProfile]:
        return {profile.sku_id: profile for profile in self.profiles}


def quantile_scenarios(
    q10: float,
    q50: float,
    q90: float,
    *,
    scenario_count: int = DEFAULT_SCENARIO_COUNT,
) -> np.ndarray:
    if scenario_count < 5:
        raise ValueError("scenario_count harus minimal 5")

    low = max(0.0, float(q10))
    median = max(low, float(q50))
    high = max(median, float(q90))

    u = (np.arange(scenario_count, dtype=float) + 0.5) / scenario_count
    scenarios = np.empty(scenario_count, dtype=float)

    lower = u < 0.10
    mid_low = (u >= 0.10) & (u < 0.50)
    mid_high = (u >= 0.50) & (u < 0.90)
    upper = u >= 0.90

    scenarios[lower] = low * (u[lower] / 0.10)
    scenarios[mid_low] = low + (median - low) * (u[mid_low] - 0.10) / 0.40
    scenarios[mid_high] = median + (high - median) * (u[mid_high] - 0.50) / 0.40
    tail_slope = max(high - median, 1.0)
    scenarios[upper] = high + tail_slope * (u[upper] - 0.90) / 0.10

    return np.clip(scenarios, 0.0, None)


def _shelf_multiplier(product: ProductSnapshot, horizon_days: int) -> float:
    if not product.is_perishable:
        return 1.0
    return 1.0 + min(
        1.5,
        horizon_days / max(float(product.shelf_life_days), 1.0),
    )


def evaluate_inventory_risk(
    *,
    scenarios: np.ndarray,
    available_inventory: float,
    product: ProductSnapshot,
    horizon_days: int,
) -> RiskMetrics:
    available = max(0.0, float(available_inventory))
    demand = np.asarray(scenarios, dtype=float)
    if demand.ndim != 1 or len(demand) == 0:
        raise ValueError("scenarios harus array satu dimensi yang tidak kosong")

    margin = max(0.0, float(product.unit_price_rp - product.unit_cost_rp))
    shortage = np.maximum(demand - available, 0.0)

    stockout_probability = float(np.mean(demand > available))
    lmar = float(shortage.mean() * margin)

    slow_probability = float(np.mean(demand < available))
    wcar = float(
        available
        * float(product.unit_cost_rp)
        * slow_probability
        * _shelf_multiplier(product, horizon_days)
    )

    mean_demand = float(demand.mean())
    if mean_demand <= 1e-12:
        expected_fill_rate = 1.0
    else:
        expected_sales = float(np.minimum(demand, available).mean())
        expected_fill_rate = float(np.clip(expected_sales / mean_demand, 0.0, 1.0))

    return RiskMetrics(
        stockout_probability=stockout_probability,
        lmar_rp=lmar,
        wcar_rp=wcar,
        expected_fill_rate=expected_fill_rate,
    )


def _max_candidate_quantity(
    *,
    scenarios: np.ndarray,
    effective_inventory: float,
    arrival_probability: float,
    max_order_qty: int,
) -> int:
    if max_order_qty < 0:
        raise ValueError("max_order_qty tidak boleh negatif")
    if max_order_qty == 0:
        return 0

    target = float(np.max(scenarios))
    gap = max(0.0, target - effective_inventory)
    probability = max(float(arrival_probability), 0.05)
    required = int(math.ceil(gap / probability)) + 5
    return min(max_order_qty, max(1, required))


def _selected_forecast(
    forecasts: DemandForecastResult,
    sku_id: str,
) -> QuantileForecast:
    by_sku = {item.sku_id: item for item in forecasts.forecasts}
    if sku_id not in by_sku:
        raise ValueError(f"Demand forecast tidak ditemukan untuk {sku_id}")
    return by_sku[sku_id].selected_horizon


def build_risk_profiles(
    snapshot: RetailSnapshot,
    demand_forecasts: DemandForecastResult,
    supplier_risk: SupplierRiskResult,
    *,
    horizon_days: int,
    scenario_count: int = DEFAULT_SCENARIO_COUNT,
    max_order_qty: int = DEFAULT_MAX_ORDER_QTY,
) -> RiskEngineResult:
    if demand_forecasts.dataset_id != snapshot.dataset_id:
        raise ValueError("Demand forecast berasal dari dataset berbeda")
    if demand_forecasts.store_id != snapshot.store_id:
        raise ValueError("Demand forecast berasal dari store berbeda")
    if demand_forecasts.horizon_days != horizon_days:
        raise ValueError("Horizon demand forecast tidak cocok")
    if supplier_risk.horizon_days != horizon_days:
        raise ValueError("Horizon supplier risk tidak cocok")

    products = {product.sku_id: product for product in snapshot.products}
    inventory = {position.sku_id: position for position in snapshot.inventory}
    supplier_by_id = supplier_risk.supplier_by_id()
    arrival_by_order = supplier_risk.arrival_by_order_id()

    outstanding_by_sku: dict[str, list] = {}
    for order in snapshot.outstanding_orders:
        outstanding_by_sku.setdefault(order.sku_id, []).append(order)

    profiles: list[SKURiskProfile] = []

    for sku_id in sorted(products):
        product = products[sku_id]
        forecast = _selected_forecast(demand_forecasts, sku_id)
        scenarios = quantile_scenarios(
            forecast.q10,
            forecast.q50,
            forecast.q90,
            scenario_count=scenario_count,
        )

        on_hand = float(inventory[sku_id].on_hand)
        orders = outstanding_by_sku.get(sku_id, [])
        on_order = float(sum(order.order_qty_units for order in orders))
        weighted_on_order = 0.0
        warnings: list[str] = []

        for order in orders:
            estimate = arrival_by_order.get(order.order_id)
            if estimate is None:
                raise ValueError(
                    f"Arrival estimate tidak ditemukan untuk PO {order.order_id}"
                )
            weighted_on_order += (
                float(order.order_qty_units) * estimate.arrival_probability
            )
            warnings.extend(estimate.warnings)

        effective_inventory = on_hand + weighted_on_order
        baseline = evaluate_inventory_risk(
            scenarios=scenarios,
            available_inventory=effective_inventory,
            product=product,
            horizon_days=horizon_days,
        )

        supplier_estimate = supplier_by_id.get(product.supplier_id)
        if supplier_estimate is None:
            raise ValueError(
                f"Supplier risk tidak ditemukan untuk {product.supplier_id}"
            )
        new_order_arrival_probability = supplier_estimate.horizon_arrival_probability
        warnings.extend(supplier_estimate.warnings)

        max_quantity = _max_candidate_quantity(
            scenarios=scenarios,
            effective_inventory=effective_inventory,
            arrival_probability=new_order_arrival_probability,
            max_order_qty=max_order_qty,
        )

        options: list[SKUQuantityOption] = []
        for quantity in range(max_quantity + 1):
            expected_available = (
                effective_inventory
                + quantity * new_order_arrival_probability
            )
            after = evaluate_inventory_risk(
                scenarios=scenarios,
                available_inventory=expected_available,
                product=product,
                horizon_days=horizon_days,
            )
            options.append(
                SKUQuantityOption(
                    sku_id=sku_id,
                    quantity=quantity,
                    cash_required_rp=float(quantity * product.unit_cost_rp),
                    expected_available_inventory=float(expected_available),
                    stockout_risk_after=after.stockout_probability,
                    lmar_after_rp=after.lmar_rp,
                    wcar_after_rp=after.wcar_rp,
                    expected_fill_rate_after=after.expected_fill_rate,
                    incremental_lmar_avoided_rp=max(
                        0.0,
                        baseline.lmar_rp - after.lmar_rp,
                    ),
                    incremental_wcar_added_rp=(
                        after.wcar_rp - baseline.wcar_rp
                    ),
                )
            )

        profiles.append(
            SKURiskProfile(
                sku_id=sku_id,
                supplier_id=product.supplier_id,
                inventory_on_hand=on_hand,
                inventory_on_order=on_order,
                effective_inventory=float(effective_inventory),
                new_order_arrival_probability=float(new_order_arrival_probability),
                forecast_q10=float(forecast.q10),
                forecast_q50=float(forecast.q50),
                forecast_q90=float(forecast.q90),
                baseline=baseline,
                options=tuple(options),
                warnings=tuple(dict.fromkeys(warnings)),
            )
        )

    return RiskEngineResult(
        horizon_days=horizon_days,
        profiles=tuple(profiles),
        warnings=tuple(supplier_risk.warnings),
    )
