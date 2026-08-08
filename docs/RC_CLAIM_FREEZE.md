# RestockIQ release-candidate claim freeze

This document defines what the RestockIQ RC may and may not claim. The machine-readable companion is `RC_POLICY_FREEZE.json`; `python -m app.ml.verify_rc_contract` fails when the frozen artifact, policy weights, payday field, zero-budget flag, or Oracle firewall drifts from production code.

## Evidence-backed statements

- The packaged demand artifact is `restockiq-demand-v1-a067286b7c1e`, trained through `2024-05-31` with training hash `a067286b7c1e966de43f3db9e1d24a7f8a440d236d94c24365c6d717ca44399c`.
- The demand layer contains one censor-aware reconstruction model and direct cumulative H1/H7/H14 Q10/Q50/Q90 models.
- `units_demanded_est`, `demand_profile`, `avg_daily_demand_per_store`, and `cash_locked_in_stock_rp` are forbidden inference fields. The frozen artifact manifest reports no Oracle field used as a feature.
- The production allocator is an exact sparse dynamic program for the defined multiple-choice knapsack candidate set and policy objective. “Exact” is scoped to those generated quantity options; it is not a claim of globally optimal retail operations outside that set.
- A budget of Rp0 is valid when no protected-SKU floor requires positive spend. It produces one q=0 allocation per SKU, zero cash allocation, and zero NOV contribution. An infeasible protected floor remains an explicit 422.
- The calendar covariate is semantically `is_payday_week`. Legacy aliases may be read, but the typed snapshot and model feature retain the week-level name.
- Approve, edit, reject, confirm, and history are server-authoritative. R8-created plans and confirmed history recover from PostgreSQL after a backend restart; confirmed runs are immutable through the recommendation API.

## Frozen policy objective

| Preset | LMAR avoided | WCAR added penalty | Cash-used penalty |
|---|---:|---:|---:|
| `lindungi_kas` | 0.85 | 1.25 | 0.08 |
| `seimbang` | 1.00 | 0.75 | 0.02 |
| `lindungi_ketersediaan` | 1.25 | 0.35 | 0.00 |

Changing any weight, candidate construction, protected floor, or optimizer algorithm requires a new freeze file, tests, and claim review. It is not an RC documentation-only change.

## Prohibited claims for this RC

- No WMAPE, quantile coverage, bias, Oracle-gap, accuracy-uplift, savings, revenue-uplift, or business-outcome number is certified. The RC contains no reproducible backtest evidence artifact for those metrics.
- Newsvendor is not the production policy and may only be described as a future/evaluation baseline when evidence exists.
- Manual quantity edits do not recompute the full LMAR/WCAR curve; only authoritative quantity and cash are recalculated.
- A global minimum-fill-rate constraint is not implemented.
- Uploaded CSVs are not part of the certified `demo-retail-v1` release path.
- Public HTTPS, Docker health, and browser acceptance may only be claimed for the exact commit and URL recorded by a passing evidence pack. Source configuration alone is not proof of deployment.

## Tag condition

Do not create an RC tag until both stacked PRs are merged into the intended release branch, the resulting commit is clean, and `scripts/collect_release_evidence.py` passes without `--allow-http`, `--skip-docker`, or `--skip-browser` against the public HTTPS URL. The tag must point to that evidenced commit, not to an earlier branch head.
