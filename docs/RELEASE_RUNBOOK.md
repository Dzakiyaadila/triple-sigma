# RestockIQ release runbook

## 1. Preflight

```bash
git status --short --branch
git diff --check
test -z "$(git status --porcelain)"
test -f .env || cp .env.example .env
```

Run release evidence only from the exact clean commit that will be tagged. Do
not collect certifying evidence from a working tree with staged, unstaged, or
untracked changes.

Set a strong `POSTGRES_PASSWORD`. For public deployment, set:

```env
SITE_ADDRESS=restock.example.com
ALLOWED_ORIGINS=https://restock.example.com
VITE_API_URL=/api/v2
```

DNS must resolve to the host and inbound ports 80/443 must be open.

## 2. Validate source

Create the pinned backend environment once. The collector auto-detects this
environment even when the collector itself is launched with another system
Python:

```bash
cd backend
test -x .venv/bin/python || python3.12 -m venv .venv
.venv/bin/python -m pip install -r requirements.txt
cd ..
```

The collector rejects Python versions other than 3.12 and environments missing
the pinned backend dependencies. `RELEASE_BACKEND_PYTHON` may point to an
equivalent Python 3.12 environment.

```bash
cd backend
export DATABASE_URL="${RELEASE_TEST_DATABASE_URL:-sqlite+pysqlite:///:memory:}"
.venv/bin/python -m pytest tests/ -q
.venv/bin/python -m app.ml.verify_release_artifacts
.venv/bin/python -m app.ml.verify_rc_contract
.venv/bin/python -c "from app.main import app; print('FastAPI import OK')"

cd ../frontend
npm ci
npm run lint
npx tsc --noEmit
npm run build
npx playwright install chromium
npm run test:e2e:list

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

Expected smoke output starts with `RELEASE SMOKE: PASSED` and reports the
frozen model version. It also certifies zero-budget behavior, persisted plan
retrieval, idempotent confirmation, post-confirm immutability, durable history,
and CSV export.

## 4. Deploy

```bash
docker compose up --build -d
docker compose ps
docker compose logs backend-bootstrap
python scripts/release_smoke.py
```

`backend-bootstrap` must exit with code 0. On an existing complete database it
prints that seeding was skipped; on a fresh database it reports the six frozen
source-table row counts.

After deployment, run the browser suite against the same URL:

```bash
cd frontend
PLAYWRIGHT_BASE_URL=https://restock.example.com npm run test:e2e
```

The Chromium binary must install and the two browser scenarios must pass. A
listed test, a downloaded package, or source review alone is not browser
acceptance evidence.

## 5. Roll-forward and rollback

Application images are immutable by Git commit/tag. Database data is held in
the named Postgres volume. Before changing a production schema or dataset, take
a database backup outside this stack.

To roll back application code, check out the previous release tag and rebuild.
Do not delete the Postgres volume during an application rollback.

## 6. Collect release evidence

From the repository root, collect the complete pack against the public HTTPS
deployment:

```bash
python scripts/collect_release_evidence.py \
  --base-url https://restock.example.com
```

For a local rehearsal, HTTP may be allowed explicitly. The resulting pack is
non-certifying:

```bash
python scripts/collect_release_evidence.py \
  --base-url http://localhost \
  --allow-http
```

The default evidence directory is outside the repository. It contains commit
metadata, command logs, a machine-readable summary, TLS/certificate and
readiness evidence, plus Playwright screenshots/traces/videos and its HTML
report. Keep the entire directory unchanged with the release record.

The collector stops at preflight before expensive gates when the worktree is
dirty or no valid backend Python 3.12 environment is available. Generated patch
files must be moved outside the repository before evidence collection.

`--skip-docker` and `--skip-browser` exist for diagnosis only. Either flag
forces the pack status to `failed`, as does a dirty worktree. `--allow-http`
only permits an explicitly non-certifying local rehearsal; it never proves
public HTTPS.

The evidence pack captures:

- Git commit and branch metadata;
- backend tests plus artifact and RC-contract verifier output;
- frontend install, lint, TypeScript, and production-build output;
- `docker compose config` and `docker compose ps`;
- release-smoke output;
- public URL, certificate, and HTTPS readiness status;
- browser acceptance report and artifacts.

## 7. Tag the evidenced commit

Only after both release PRs are merged into the intended release branch, check
out the resulting merge commit, deploy that exact commit, and collect a passing
certifying evidence pack. Then tag the commit recorded in `metadata.json`:

```bash
git rev-parse HEAD
git tag -a <release-tag> -m "RestockIQ release candidate"
git push origin <release-tag>
```

The first command must equal the evidence pack's `git_commit`. Never tag an
earlier feature-branch head or a commit that was modified after evidence was
collected.

## 8. Known stop conditions

Do not tag a release when:

- artifact checksums or Oracle guard fail;
- the RC policy/claim freeze differs from production code;
- bootstrap reports a partially populated database;
- backend readiness is not 200;
- the real planner returns 503;
- zero-budget, persistence, idempotency, immutability, history, or export smoke
  fails;
- lint, TypeScript, production build, or backend tests exit non-zero;
- Chromium cannot install or either browser scenario fails;
- the public URL or its TLS/readiness check fails;
- Docker validation or browser validation was skipped;
- the evidence worktree is dirty;
- any WMAPE, coverage, bias, Oracle-gap, savings, uplift, or business-outcome
  claim is proposed without a separate reproducible evidence artifact;
- `summary.json` is not exactly `passed` for the commit and public URL to tag.
