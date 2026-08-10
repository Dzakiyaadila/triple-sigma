# RestockIQ

RestockIQ is a cash-allocation decision layer for constrained retail restocking. It reconstructs demand censored by stockouts, forecasts cumulative demand quantiles, estimates supplier and inventory risk, and allocates one shared Rupiah budget with an exact multiple-choice knapsack optimizer.

It is not a POS, inventory CRUD system, or a generic analytics dashboard.

## Release architecture

```text
browser -> Caddy -> TanStack Start frontend
                 -> FastAPI backend -> PostgreSQL
                                    -> frozen LightGBM artifacts
                                    -> exact stochastic MCKP
```

The release image contains the frozen model artifact `restockiq-demand-v1-a067286b7c1e`. Artifact checksums and the Oracle-feature firewall are verified while the backend image is built.

## Fresh-clone start

Requirements: Docker Engine with Docker Compose v2.

```bash
cp .env.example .env
```

Replace `POSTGRES_PASSWORD` in `.env`, then run:

```bash
docker compose config --quiet
docker compose up --build -d
docker compose ps
python scripts/release_smoke.py
```

Local application: <http://localhost>

For public HTTPS, set `SITE_ADDRESS` to the public hostname and set `ALLOWED_ORIGINS` to its `https://` origin before starting Compose. Caddy provisions TLS automatically when DNS points to the host and ports 80/443 are reachable.

## Canonical validation

Backend:

```bash
cd backend
export DATABASE_URL="${RELEASE_TEST_DATABASE_URL:-sqlite+pysqlite:///:memory:}"
python -m pytest tests/ -q
python -m app.ml.verify_release_artifacts
python -m app.ml.verify_rc_contract
python -c "from app.main import app; print('FastAPI import OK')"
```

Frontend:

```bash
cd frontend
npm ci
npx tsc --noEmit
npm run build
npm run test:e2e:list
```

Release stack:

```bash
docker compose config --quiet
docker compose build
docker compose up -d
python scripts/release_smoke.py
cd frontend && npm run test:e2e
```

## Decision journey

`select demo data -> set store/date/budget/policy -> run planner -> inspect Action Cards -> approve/edit/reject -> confirm -> export CSV`

Approve, edit, reject, and confirm are server-authoritative. The UI changes decision state only after the backend accepts the mutation.

R8 decision plans, recommendation mutations, confirmation metadata, CSV export state, and confirmed history are persisted in PostgreSQL. An empty process-local cache or backend restart does not invalidate an R8 run.

## Model provenance

| Field | Frozen value |
|---|---|
| Model version | `restockiq-demand-v1-a067286b7c1e` |
| Training cutoff | `2024-05-31` |
| Training data hash | `a067286b7c1e966de43f3db9e1d24a7f8a440d236d94c24365c6d717ca44399c` |
| Oracle features | none |
| Forecast outputs | direct cumulative H1/H7/H14 × Q10/Q50/Q90 |

The machine-readable policy, artifact, payday, zero-budget, Oracle, and backtest-claim boundary is frozen in [`docs/RC_POLICY_FREEZE.json`](docs/RC_POLICY_FREEZE.json) and checked against production code by `python -m app.ml.verify_rc_contract`.

## Release-candidate evidence

Run the full collector against the public HTTPS deployment from a clean commit:

```bash
python scripts/collect_release_evidence.py \
  --base-url https://restock.example.com
```

The collector runs backend, artifact, policy-freeze, frontend, Compose, real HTTP, and Chromium acceptance gates. It records TLS certificate details plus screenshots and failure traces outside the repository. `--allow-http`, `--skip-docker`, and `--skip-browser` are rehearsal options; a skipped gate is never a passing RC pack.

## Known limitations

- Runs created before the R8 durability contract do not contain a persisted plan summary. They return an explicit 409 after restart and must be rerun; R8-created runs are durable.
- A manual quantity edit recalculates quantity and cash, but does not rerun the full LMAR/WCAR risk curve.
- Uploaded CSVs remain outside the release-candidate demo path; the reproducible release is certified against `demo-retail-v1`.
- A global minimum-fill-rate constraint is not implemented and is not exposed in the UI.
- No WMAPE, coverage, bias, Oracle-gap, savings, or business-uplift number is certified for this RC. Those claims remain prohibited until a separate reproducible backtest artifact exists.
- Public HTTPS is a deployment gate, not a property inferred from source code; it is only passed by an evidence pack collected against the real HTTPS URL.

See [GETTING_STARTED.md](GETTING_STARTED.md) for local development and [docs/RELEASE_RUNBOOK.md](docs/RELEASE_RUNBOOK.md) for release operations.
