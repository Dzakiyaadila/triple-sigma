# RestockIQ frontend

TanStack Start renders the real RestockIQ decision journey. It consumes the FastAPI `RestockPlan` contract and does not generate local recommendations, synthetic daily forecast trajectories, or placeholder evaluation metrics.

## Runtime

```bash
npm ci
cp .env.example .env
npm run dev
```

`VITE_API_URL` points to the API base. Local development uses `http://localhost:8000/api/v2`; the release image uses the same-origin path `/api/v2` through Caddy.

## Canonical gates

```bash
npx tsc --noEmit
npm run build
npm run test:e2e:list
```

The production build uses Nitro's `node-server` preset and starts with:

```bash
node .output/server/index.mjs
```

## Truthfulness boundaries

- Approve/edit/reject/confirm update UI state only after backend acknowledgement.
- Forecast detail displays direct cumulative H1/H7/H14 Q10/Q50/Q90 values.
- Evaluation displays only actual plan outputs and provenance.
- Manual edits use server-returned cash; the UI discloses that the full risk curve is not recomputed.
- The service-level slider is absent because the exact optimizer does not implement a global minimum-fill-rate constraint.
- Confirmed history is loaded from the backend durability API and survives browser/backend restarts.
- A failed confirmation never creates a local history row. The page exposes backend history-load errors instead of displaying a false empty state.

## Browser acceptance

With the full stack running:

```bash
npx playwright install chromium
PLAYWRIGHT_BASE_URL=http://localhost npm run test:e2e
```

The RC suite covers zero budget, authoritative approval and q=0 rejection, drawer/evaluation truthfulness, a delayed mutation race, forced confirmation failure without fake history, and setup invalidation. The public RC evidence run uses the deployed HTTPS URL instead of localhost.
