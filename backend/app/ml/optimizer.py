from __future__ import annotations

from dataclasses import dataclass
import math
from time import perf_counter

from app.ml.contracts import PolicyPreset
from app.ml.risk_engine import RiskEngineResult, SKURiskProfile, SKUQuantityOption


OPTIMIZER_ALGORITHM = "exact_sparse_mckp_dynamic_programming"
OPTIMIZER_CANDIDATE_SCOPE = (
    "exactly one selected option per SKU from generated quantity candidates; "
    "q=0 is available unless a protected-SKU floor applies"
)


@dataclass(frozen=True)
class PolicyWeights:
    lmar_avoided: float
    wcar_added: float
    cash_used: float


POLICY_WEIGHTS: dict[PolicyPreset, PolicyWeights] = {
    "lindungi_kas": PolicyWeights(
        lmar_avoided=0.85,
        wcar_added=1.25,
        cash_used=0.08,
    ),
    "seimbang": PolicyWeights(
        lmar_avoided=1.00,
        wcar_added=0.75,
        cash_used=0.02,
    ),
    "lindungi_ketersediaan": PolicyWeights(
        lmar_avoided=1.25,
        wcar_added=0.35,
        cash_used=0.00,
    ),
}


class OptimizationInfeasibleError(ValueError):
    pass


@dataclass(frozen=True)
class AllocationDecision:
    sku_id: str
    quantity: int
    cash_required_rp: float
    objective_increment_rp: float
    option: SKUQuantityOption


@dataclass(frozen=True)
class OptimizationResult:
    policy_preset: PolicyPreset
    budget_rp: float
    cash_used_rp: float
    budget_remaining_rp: float
    objective_increment_rp: float
    runtime_ms: int
    allocations: tuple[AllocationDecision, ...]

    def allocation_by_sku(self) -> dict[str, AllocationDecision]:
        return {item.sku_id: item for item in self.allocations}


def score_option(
    option: SKUQuantityOption,
    policy_preset: PolicyPreset,
) -> float:
    weights = POLICY_WEIGHTS[policy_preset]
    added_wcar = max(0.0, float(option.incremental_wcar_added_rp))
    return float(
        weights.lmar_avoided * float(option.incremental_lmar_avoided_rp)
        - weights.wcar_added * added_wcar
        - weights.cash_used * float(option.cash_required_rp)
    )


def _integer_rupiah(value: float) -> int:
    if value < -1e-9:
        raise ValueError("Nilai Rupiah tidak boleh negatif")
    # Procurement costs are expected to be integral Rupiah. `ceil` keeps the
    # solver conservative if an upstream source nevertheless supplies cents.
    return int(math.ceil(max(0.0, float(value)) - 1e-9))


def _protected_floor(profile: SKURiskProfile, protected: bool) -> int:
    if not protected:
        return 0
    if profile.baseline.stockout_probability <= 0:
        return 0
    if not any(option.quantity >= 1 for option in profile.options):
        return 0
    return 1


def _allowed_options(
    profile: SKURiskProfile,
    *,
    protected: bool,
) -> tuple[SKUQuantityOption, ...]:
    if not profile.options:
        raise OptimizationInfeasibleError(
            f"SKU {profile.sku_id} tidak memiliki candidate quantity"
        )
    if profile.options[0].quantity != 0:
        raise ValueError(
            f"Candidate q=0 wajib tersedia untuk SKU {profile.sku_id}"
        )

    floor = _protected_floor(profile, protected)
    return tuple(option for option in profile.options if option.quantity >= floor)


def _pareto_prune(
    states: dict[int, tuple[float, tuple[int, ...]]],
) -> dict[int, tuple[float, tuple[int, ...]]]:
    """Remove states dominated by a cheaper state with >= utility.

    Under a single cash constraint, such states can never be part of an
    optimal continuation. This keeps the sparse exact DP tractable without
    discretizing Rupiah costs.
    """

    pruned: dict[int, tuple[float, tuple[int, ...]]] = {}
    best_utility = -math.inf
    tolerance = 1e-9

    for cost in sorted(states):
        utility, path = states[cost]
        if utility > best_utility + tolerance:
            pruned[cost] = (utility, path)
            best_utility = utility
    return pruned


def optimize_exact_mckp(
    risk: RiskEngineResult,
    *,
    budget_rp: float,
    policy_preset: PolicyPreset = "seimbang",
    protected_sku_ids: tuple[str, ...] | list[str] = (),
) -> OptimizationResult:
    """Solve the cash-constrained quantity allocation exactly in Rupiah.

    Each SKU is one MCKP group and contributes exactly one quantity option.
    The sparse dynamic program keeps a Pareto frontier of exact integer-Rupiah
    spend states; SciPy MILP is intentionally not used by the production
    allocator.
    """

    started = perf_counter()
    if budget_rp < 0:
        raise ValueError("budget_rp tidak boleh negatif")
    if policy_preset not in POLICY_WEIGHTS:
        raise ValueError(f"Policy preset tidak dikenal: {policy_preset}")

    budget = _integer_rupiah(budget_rp)
    protected = set(protected_sku_ids)
    profiles = sorted(risk.profiles, key=lambda profile: profile.sku_id)
    known_skus = {profile.sku_id for profile in profiles}
    unknown_protected = protected - known_skus
    if unknown_protected:
        raise ValueError(
            f"Protected SKU tidak ditemukan: {sorted(unknown_protected)}"
        )

    # cost -> (objective, path of option indices in each allowed group)
    states: dict[int, tuple[float, tuple[int, ...]]] = {0: (0.0, ())}
    allowed_by_profile: list[tuple[SKUQuantityOption, ...]] = []

    for profile in profiles:
        options = _allowed_options(
            profile,
            protected=profile.sku_id in protected,
        )
        allowed_by_profile.append(options)
        next_states: dict[int, tuple[float, tuple[int, ...]]] = {}

        for spent_before in sorted(states):
            utility_before, path_before = states[spent_before]
            for option_index, option in enumerate(options):
                option_cost = _integer_rupiah(option.cash_required_rp)
                spent_after = spent_before + option_cost
                if spent_after > budget:
                    continue

                candidate_utility = utility_before + score_option(
                    option,
                    policy_preset,
                )
                candidate_path = path_before + (option_index,)
                existing = next_states.get(spent_after)
                if existing is None or candidate_utility > existing[0] + 1e-9:
                    next_states[spent_after] = (
                        candidate_utility,
                        candidate_path,
                    )

        if not next_states:
            if profile.sku_id in protected:
                raise OptimizationInfeasibleError(
                    "Budget tidak cukup untuk memenuhi protected SKU floor: "
                    f"{profile.sku_id}"
                )
            raise OptimizationInfeasibleError(
                f"Tidak ada allocation state feasible setelah SKU {profile.sku_id}"
            )

        states = _pareto_prune(next_states)

    if not profiles:
        return OptimizationResult(
            policy_preset=policy_preset,
            budget_rp=float(budget_rp),
            cash_used_rp=0.0,
            budget_remaining_rp=float(budget_rp),
            objective_increment_rp=0.0,
            runtime_ms=max(0, int(round((perf_counter() - started) * 1000))),
            allocations=(),
        )

    best_cost, (best_utility, best_path) = max(
        states.items(),
        key=lambda item: (item[1][0], -item[0]),
    )

    allocations: list[AllocationDecision] = []
    actual_cash = 0.0
    for profile, options, option_index in zip(
        profiles,
        allowed_by_profile,
        best_path,
        strict=True,
    ):
        option = options[option_index]
        option_score = score_option(option, policy_preset)
        actual_cash += float(option.cash_required_rp)
        allocations.append(
            AllocationDecision(
                sku_id=profile.sku_id,
                quantity=option.quantity,
                cash_required_rp=float(option.cash_required_rp),
                objective_increment_rp=option_score,
                option=option,
            )
        )

    if actual_cash > budget_rp + 1e-6:
        raise AssertionError(
            "Exact allocator menghasilkan cash usage di atas budget"
        )
    if len(allocations) != len(profiles):
        raise AssertionError("Setiap SKU harus memiliki tepat satu allocation")

    runtime_ms = max(0, int(round((perf_counter() - started) * 1000)))
    return OptimizationResult(
        policy_preset=policy_preset,
        budget_rp=float(budget_rp),
        cash_used_rp=float(actual_cash),
        budget_remaining_rp=float(max(0.0, budget_rp - actual_cash)),
        objective_increment_rp=float(best_utility),
        runtime_ms=runtime_ms,
        allocations=tuple(allocations),
    )
