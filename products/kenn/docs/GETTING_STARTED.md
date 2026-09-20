# Getting started with KENN

This repository contains the complete collaborative KENN product source, including the SLO classification integration. Each product area has one canonical home.

It includes:

- KENN Python backend and tests;
- the current Vue/TypeScript UX source;
- the served/legacy web UI code;
- SLO classification adapter, routes, frontend contract, mock states and UX;
- VST3/AU plugin source;
- Ableton Remote Script and OSC integration source;
- desktop companion source;
- chat, Mix Review and AutoMix source;
- scripts, evaluation harnesses, documentation and third-party source notices.

Git deliberately excludes private or generated material: real environment files, dependencies, compiled builds, models, unreviewed training corpora, generated knowledge indexes, chat databases, logs, audio and caches.

## UX-only start

```bash
cd "apps/frontend"
cp .env.example .env.local
npm ci
npm run dev
```

The default example enables mock classification data. Select **SLO Library** in the workspace.

## Full backend + frontend start

From the product root:

```bash
python3 tooling/scripts/create_demo_slo_cache.py
export SLO_CLASSIFICATION_DB="$PWD/.runtime/demo_slo.sqlite3"
python3 run_ux_backend.py
```

Then set the frontend's `.env.local` to:

```env
VITE_SLO_CLASSIFICATION_MOCK=false
API_URL=http://127.0.0.1:8090
```

Run the frontend with `npm run dev`. The development runner exposes KENN's full HTTP handler but skips model/index startup warm-up so UX work does not require excluded assets.

## Focused verification

```bash
PYTHONPATH=apps/backend/src python3 -m pytest -q \
  apps/backend/src/kenn/tests/test_slo_classification_adapter.py \
  apps/backend/src/kenn/tests/test_slo_classification_routes.py

cd "apps/frontend"
npm test
npm run build
```

See `PRODUCT_MAP.md`, `SLO_INTEGRATION.md`, and `CONTRIBUTING.md` before making structural changes.
