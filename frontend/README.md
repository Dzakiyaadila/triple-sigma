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
- Browser history is session-local until durable history APIs are implemented.
