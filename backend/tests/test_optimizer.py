from __future__ import annotations

import pytest

from app.ml.optimizer import (
    OptimizationInfeasibleError,
    optimize_exact_mckp,
    score_option,
)
from app.ml.risk_engine import (
    RiskEngineResult,
    RiskMetrics,
    SKURiskProfile,
    SKUQuantityOption,
)


def _profile(
    sku_id: str,
    options: list[tuple[int, float, float, float]],
    *,
    stockout_probability: float = 0.5,
) -> SKURiskProfile:
    built = tuple(
        SKUQuantityOption(
            sku_id=sku_id,
            quantity=quantity,
            cash_required_rp=cash,
            expected_available_inventory=float(quantity),
            stockout_risk_after=max(0.0, stockout_probability - 0.1 * quantity),
            lmar_after_rp=max(0.0, 500 - lmar_avoided),
            wcar_after_rp=max(0.0, wcar_added),
            expected_fill_rate_after=min(1.0, 0.5 + 0.1 * quantity),
            incremental_lmar_avoided_rp=lmar_avoided,
            incremental_wcar_added_rp=wcar_added,
        )
        for quantity, cash, lmar_avoided, wcar_added in options
    )
    return SKURiskProfile(
        sku_id=sku_id,
        supplier_id="SUP01",
        inventory_on_hand=0,
        inventory_on_order=0,
        effective_inventory=0,
        new_order_arrival_probability=1.0,
        forecast_q10=1,
        forecast_q50=2,
        forecast_q90=3,
        baseline=RiskMetrics(
            stockout_probability=stockout_probability,
            lmar_rp=500,
            wcar_rp=0,
            expected_fill_rate=0,
        ),
        options=built,
        warnings=(),
    )


def _risk(*profiles: SKURiskProfile) -> RiskEngineResult:
    return RiskEngineResult(horizon_days=7, profiles=profiles, warnings=())


def test_exact_allocator_respects_budget_and_selects_one_option_per_sku():
    result = optimize_exact_mckp(
        _risk(
            _profile("A", [(0, 0, 0, 0), (1, 60, 100, 0)]),
            _profile("B", [(0, 0, 0, 0), (1, 40, 64, 0)]),
        ),
        budget_rp=100,
        policy_preset="seimbang",
    )

    assert result.cash_used_rp <= 100
    assert len(result.allocations) == 2
    assert {item.sku_id for item in result.allocations} == {"A", "B"}
    for item in result.allocations:
        assert item.cash_required_rp == item.quantity * (
            60 if item.sku_id == "A" else 40
        )


def test_zero_budget_selects_zero_quantity_for_every_sku():
    risk = _risk(
        _profile("A", [(0, 0, 0, 0), (1, 60, 100, 0)]),
        _profile("B", [(0, 0, 0, 0), (1, 40, 64, 0)]),
    )

    result = optimize_exact_mckp(
        risk,
        budget_rp=0,
        policy_preset="seimbang",
    )

    assert result.cash_used_rp == 0
    assert result.budget_remaining_rp == 0
    assert result.objective_increment_rp == 0
    assert all(item.quantity == 0 for item in result.allocations)


def test_exact_dp_beats_ratio_greedy_crafted_case():
    risk = _risk(
        _profile("A", [(0, 0, 0, 0), (1, 60, 101.2, 0)]),
        _profile("B", [(0, 0, 0, 0), (1, 40, 65.8, 0)]),
        _profile("C", [(0, 0, 0, 0), (1, 40, 65.8, 0)]),
    )
    exact = optimize_exact_mckp(
        risk,
        budget_rp=80,
        policy_preset="seimbang",
    )

    candidates = []
    for profile in risk.profiles:
        option = profile.options[1]
        utility = score_option(option, "seimbang")
        candidates.append((utility / option.cash_required_rp, profile.sku_id, option))
    remaining = 80.0
    greedy_utility = 0.0
    for _, _, option in sorted(candidates, reverse=True):
        if option.cash_required_rp <= remaining:
            remaining -= option.cash_required_rp
            greedy_utility += score_option(option, "seimbang")

    allocation = exact.allocation_by_sku()
    assert allocation["A"].quantity == 0
    assert allocation["B"].quantity == 1
    assert allocation["C"].quantity == 1
    assert exact.objective_increment_rp > greedy_utility


def test_policy_preset_changes_real_allocation():
    risk = _risk(
        _profile(
            "A",
            [
                (0, 0, 0, 0),
                (1, 100, 120, 80),
                (2, 200, 200, 220),
            ],
        )
    )

    cash = optimize_exact_mckp(
        risk, budget_rp=200, policy_preset="lindungi_kas"
    )
    balanced = optimize_exact_mckp(
        risk, budget_rp=200, policy_preset="seimbang"
    )
    availability = optimize_exact_mckp(
        risk, budget_rp=200, policy_preset="lindungi_ketersediaan"
    )

    quantities = [
        cash.allocations[0].quantity,
        balanced.allocations[0].quantity,
        availability.allocations[0].quantity,
    ]
    assert quantities == [0, 1, 2]


def test_protected_sku_floor_is_honored_or_reported_infeasible():
    risk = _risk(
        _profile(
            "PROTECTED",
            [(0, 0, 0, 0), (1, 100, 10, 50)],
            stockout_probability=0.5,
        )
    )
    result = optimize_exact_mckp(
        risk,
        budget_rp=100,
        policy_preset="lindungi_kas",
        protected_sku_ids=("PROTECTED",),
    )
    assert result.allocations[0].quantity == 1

    with pytest.raises(OptimizationInfeasibleError):
        optimize_exact_mckp(
            risk,
            budget_rp=99,
            policy_preset="lindungi_kas",
            protected_sku_ids=("PROTECTED",),
        )


def test_optimizer_is_deterministic():
    risk = _risk(
        _profile("A", [(0, 0, 0, 0), (1, 100, 150, 10)]),
        _profile("B", [(0, 0, 0, 0), (1, 100, 140, 10)]),
    )
    first = optimize_exact_mckp(risk, budget_rp=100, policy_preset="seimbang")
    second = optimize_exact_mckp(risk, budget_rp=100, policy_preset="seimbang")

    assert [(x.sku_id, x.quantity) for x in first.allocations] == [
        (x.sku_id, x.quantity) for x in second.allocations
    ]
    assert first.cash_used_rp == second.cash_used_rp
    assert first.objective_increment_rp == second.objective_increment_rp
