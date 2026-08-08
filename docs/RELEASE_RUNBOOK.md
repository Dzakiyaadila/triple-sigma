# RestockIQ release runbook

## 1. Preflight

```bash
git status --short --branch
git diff --check
cp .env.example .env
```

Set a strong `POSTGRES_PASSWORD`. For public deployment, set:

```env
SITE_ADDRESS=restock.example.com
ALLOWED_ORIGINS=https://restock.example.com
VITE_API_URL=/api/v2
```

DNS must resolve to the host and inbound ports 80/443 must be open.

## 2. Validate source

```bash
cd backend
python -m pytest tests/ -q
python -m app.ml.verify_release_artifacts
python -c "from app.main import app; print('FastAPI import OK')"

cd ../frontend
npm ci
npx tsc --noEmit
npm run build

cd ..
docker compose config --quiet
```

## 3. Fresh-volume rehearsal

Use a disposable Compose project name so existing project data is untouched:

```bash
docker compose -p restockiq-rc build
docker compose -p restockiq-rc up -d
docker compose -p restockiq-rc ps
python scripts/release_smoke.py
```

Expected smoke output starts with `RELEASE SMOKE: PASSED` and reports the frozen model version.

## 4. Deploy

```bash
docker compose up --build -d
docker compose ps
docker compose logs backend-bootstrap
python scripts/release_smoke.py
```

`backend-bootstrap` must exit with code 0. On an existing complete database it prints that seeding was skipped; on a fresh database it reports the six frozen source-table row counts.

## 5. Roll-forward and rollback

Application images are immutable by Git commit/tag. Database data is held in the named Postgres volume. Before changing a production schema or dataset, take a database backup outside this stack.

To roll back application code, check out the previous release tag and rebuild. Do not delete the Postgres volume during an application rollback.

## 6. Release evidence

Capture:

- Git commit and tag;
- backend test output;
- TypeScript and production-build output;
- artifact verifier output;
- `docker compose ps`;
- bootstrap log;
- release-smoke output;
- public URL and HTTPS status;
- browser acceptance screenshots.

## 7. Known stop conditions

Do not tag a release when:

- artifact checksums or Oracle guard fail;
- bootstrap reports a partially populated database;
- backend readiness is not 200;
- the real planner returns 503;
- authoritative mutation/confirm/export smoke fails;
- TypeScript or production build exits non-zero.
