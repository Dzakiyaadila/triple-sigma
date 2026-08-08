# RestockIQ backend

FastAPI orchestrates the production decision path:

```text
RetailSnapshot
  -> frozen probabilistic demand inference
  -> causal supplier risk
  -> LMAR/WCAR risk profiles
  -> exact cash-constrained MCKP
  -> RestockPlan
```

The ML layer receives a typed snapshot and does not query the database directly.

## Runtime configuration

| Variable | Purpose |
|---|---|
| `DATABASE_URL` | SQLAlchemy PostgreSQL URL using the `psycopg` driver |
| `ALLOWED_ORIGINS` | comma-separated CORS origins |
| `RESTOCKIQ_ARTIFACT_DIR` | frozen demand-artifact directory |

## Bootstrap

```bash
python -m app.db.seed
python -m app.ml.verify_release_artifacts
```

`app.db.seed` is transactional and idempotent. It refuses a partially populated source schema instead of mixing data snapshots.

## API

Base path: `/api/v2`

- `GET /datasets/demo/readiness`
- `GET /datasets/{dataset_id}/stores`
- `GET /datasets/{dataset_id}/products`
- `POST /decision-runs`
- `GET /decision-runs/history`
- `GET /decision-runs/{run_id}/plan`
- `PATCH /decision-runs/{run_id}/recommendations/{sku_id}`
- `POST /decision-runs/{run_id}/confirm`
- `GET /decision-runs/{run_id}/export.csv`

Operational endpoints:

- `GET /health` — compatibility liveness response
- `GET /health/live` — process liveness
- `GET /health/ready` — database plus frozen-artifact readiness

Planner errors are mapped explicitly: missing/invalid artifacts to 503, infeasible optimization to 422, and invalid decision inputs to 400.

Decision runs are durable for R8-created records. PostgreSQL stores the original plan payload, plan summary, authoritative recommendation mutations, and idempotent confirmation metadata. Retrieval, mutation, confirmation, history, and CSV export rebuild from those rows rather than depending on process memory. Confirmed runs reject further mutation.

## Validation

```bash
python -m pytest tests/ -q
python -m app.ml.verify_release_artifacts
python -m app.ml.verify_rc_contract
python -c "from app.main import app; print('FastAPI import OK')"
```

The model directory contains one reconstruction model, nine quantile models, the manifest, and `SHA256SUMS`. Individual files must not be replaced independently.
