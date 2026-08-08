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
python -m pytest tests/ -q
python -m app.ml.verify_release_artifacts
python -c "from app.main import app; print('FastAPI import OK')"
```

Frontend:

```bash
cd frontend
npm ci
npx tsc --noEmit
npm run build
```

Release stack:

```bash
docker compose config --quiet
docker compose build
docker compose up -d
python scripts/release_smoke.py
```

## Decision journey

`select demo data -> set store/date/budget/policy -> run planner -> inspect Action Cards -> approve/edit/reject -> confirm -> export CSV`

Approve, edit, reject, and confirm are server-authoritative. The UI changes decision state only after the backend accepts the mutation.

## Model provenance

| Field | Frozen value |
|---|---|
| Model version | `restockiq-demand-v1-a067286b7c1e` |
| Training cutoff | `2024-05-31` |
| Training data hash | `a067286b7c1e966de43f3db9e1d24a7f8a440d236d94c24365c6d717ca44399c` |
| Oracle features | none |
| Forecast outputs | direct cumulative H1/H7/H14 × Q10/Q50/Q90 |

## Known limitations

- Decision plans are cached in backend memory; a backend restart invalidates plan retrieval and mutation for runs created before the restart.
- The browser history view is session-local and is not durable server-side history.
- A manual quantity edit recalculates quantity and cash, but does not rerun the full LMAR/WCAR risk curve.
- Uploaded CSVs remain outside the release-candidate demo path; the reproducible release is certified against `demo-retail-v1`.
- A global minimum-fill-rate constraint is not implemented and is not exposed in the UI.
- Zero-budget and payday-feature certification remain explicit R8 gates; this R7 release does not alter frozen analytical behavior.

See [GETTING_STARTED.md](GETTING_STARTED.md) for local development and [docs/RELEASE_RUNBOOK.md](docs/RELEASE_RUNBOOK.md) for release operations.
