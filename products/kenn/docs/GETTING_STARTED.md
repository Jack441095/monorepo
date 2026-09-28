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

## Ableton through MCP

KENN can use a local Ableton Control Deck MCP server for Live inspection
instead of its bundled AbletonOSC client. Install and build Control Deck in a
separate trusted checkout with an ARM64 Node.js 24 runtime, enable its
`Control_Deck` Control Surface in Live, and launch KENN with an explicit stdio
command. Node.js 24 is required by the provider's current `node:sqlite` sample
index even though its upstream README still states Node.js 20+.

Control Deck's setup script installs its Remote Script into Ableton's default
User Library under the home folder. If Live uses a custom User Library, make
sure the stamped `Control_Deck` directory is instead present under that active
library's `Remote Scripts` directory, restart Live, and then select it in
Settings > Tempo & MIDI. Do not copy the unstamped provider source: the
installed script and `data/bridge-token` must contain the same per-install
secret.

```bash
export KENN_LIVE_BACKEND=control-deck-mcp
export KENN_LIVE_MCP_CWD=/absolute/path/to/ableton-control-deck
export KENN_LIVE_MCP_COMMAND="node /absolute/path/to/ableton-control-deck/dist/src/index.js"
python3 run_ux_backend.py
```

The command is parsed into an argument vector and launched directly without a
shell. KENN permits only the Control Deck status and inspection tools. MCP
mutations remain disabled until a disposable Live set has passed KENN's
proposal, confirmation, fresh-state, readback, receipt, and undo qualification.
Selecting `control-deck-mcp` without a command is a startup error; KENN never
silently falls back to OSC after MCP was requested.

Capture backend-specific real-host evidence after the companion and Live are
running:

```bash
PYTHONPATH=apps/backend/src python3 tooling/scripts/qualify_ableton_live.py \
  --mode real \
  --require-backend ableton-control-deck-mcp \
  --output /tmp/kenn-control-deck-qualification.json
```

## Working on KENN as a collaborator

Clone the repository; don't copy someone's working folder. A working folder carries local-only data that must not
travel (see `LOCAL_DATA_POLICY.md`): the owner's typed requests (`data/asked_log.jsonl`), Live action receipts, planner
logs, `.runtime/` logs and demo audio, plus 8 GB of model weights. Two people editing one synced copy of a git
repository also corrupts it; use branches and pull requests instead.

**What git gives you:** all source, tests, evaluation harnesses and docs. Everything below runs from that alone.

### Working together (from 27 Sept 2026)

KENN has its own private repository, `Nite-DSP/kenn-app`, split out of the NITE DSP monorepo with its history so a
collaborator sees only KENN. That repository is where KENN work happens now:

- `main` is protected: nobody pushes to it directly. Make a branch per piece of work (`yourname/what-it-does`), push
  it, and open a pull request; the other person reviews and merges.
- Run the checks below before opening a pull request, and keep pull requests small enough to review in one sitting.
  Two people changing `core/live_intent.py` at once is the usual conflict; pull `main` into your branch often.
- Tests and evaluations use the fake Live backend. Real Live is used only for release soaks, which the owner runs.
- `Nite-DSP/kenn` is the older, frozen pre-monorepo repository; don't work there.
- At each release the owner brings `main` back into the monorepo
  (`git subtree pull --prefix=products/kenn <kenn remote> main`). Don't change `products/kenn` in the monorepo in
  between, or the two drift apart.

**Without Ableton Live**, KENN runs against a recorded copy of the demo set. In the `kenn-app` repository run these from
its root; in the monorepo, from `products/kenn`:

```bash
export KENN_LIVE_BACKEND=fake        # the tests set this themselves; nothing touches a real Live set
PYTHONPATH="apps/backend/src:tooling" python3 -m pytest -q apps/backend/src/kenn/tests
PYTHONPATH="apps/backend/src:tooling" python3 tooling/scripts/score_natural_phrasings.py tooling/data/natural_*.jsonl
PYTHONPATH="apps/backend/src:tooling" python3 tooling/scripts/measure_chat_routing.py
```

The first checks every change, the second scores the command parser on 1,751 labelled phrasings, and the third
starts a private fake-Live KENN and measures where chat messages land (Live or the notes).

**What doesn't come with git, and how to get it:**

| Needed for | Item | How |
|---|---|---|
| Hybrid retrieval | MiniLM embedding model | `python3 tooling/scripts/fetch_embedding_model.py` |
| Knowledge answers | Notes (`Training_Data_Notes/`) and the built index | From the owner after a licensing review: some notes summarise third-party courses and videos |
| Real Live control | Ableton Live 12 and KENN's AbletonOSC in the User Library | The app's **Set up KENN** page, or `tooling/scripts/deploy_abletonosc.py` |

Without the notes and index, knowledge answers abstain and the tests that need them skip. Model weights, the GPU box
and its SSH key stay with the owner.

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
