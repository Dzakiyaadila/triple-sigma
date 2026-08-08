# RestockIQ local development

## Prerequisites

- Python 3.12
- Node.js 20 and npm
- PostgreSQL 15+

## Backend

```bash
cd backend
python3.12 -m venv .venv
source .venv/bin/activate
python -m pip install -r requirements.txt
cp .env.example .env
```

Create the database, set `DATABASE_URL` in `backend/.env`, then bootstrap:

```bash
python -m app.db.seed
python -m app.ml.verify_release_artifacts
python -m uvicorn app.main:app --reload --port 8000
```

The bootstrap is idempotent. It inserts the frozen demo dataset only when all six source tables are empty, skips when all are already populated, and stops on a partially populated database.

Readiness:

```bash
curl -fsS http://localhost:8000/health/ready
```

## Frontend

In a second terminal:

```bash
cd frontend
npm ci
cp .env.example .env
npm run dev
```

The default development API URL is `http://localhost:8000/api/v2`.

## Tests and build

```bash
cd backend
python -m pytest tests/ -q
python -c "from app.main import app; print('FastAPI import OK')"

cd ../frontend
npx tsc --noEmit
npm run build
```

## Local end-to-end smoke

With backend and frontend reachable through the Compose/Caddy stack:

```bash
python scripts/release_smoke.py
```

For another environment:

```bash
RESTOCKIQ_BASE_URL=https://restock.example.com python scripts/release_smoke.py
```

The smoke test verifies readiness, demo dataset counts, a real 31-SKU plan, one authoritative approval, confirmation, and CSV export.
