# PRODUCT REVIEW — PLATFORM (backend+website), AUDIO_TOO, THURSDAY, AUDIOGEN/AUTOMIX, LAYER-ALIGNMENT, CLIENT — 2026-09-17

## Platform backend · HARDEN · 29/50 (Alpha)
FastAPI (0.141.1) + Alembic + Paddle commerce + licensing/downloads/waitlist; Railway deploy + staging rehearsal gate. Verified: `ruff check backend/app` clean; `pytest collect` BLOCKED (no nacl in env — TOOL_MISSING); commerce.py Paddle httpx calls read поверхностно (deep auth/webhook review outstanding, F-18). Diverges from platform/backend copy (4 files). No auto CI (manual dispatch only).

## Platform website · HARDEN · 28/50 (Alpha)
Next 16.3.0/React 19.2.8/Tailwind 4/TS5/Playwright; `build:production` gated by config check; copy-audit script; staging Basic-Auth (`proxy.ts`). README is generic create-next-app (truth gap). Diverges from platform/website (16.3.5 + routes). Not built here (TOOL_MISSING: npm ci skipped per cost).

## Audio_Too · CONSOLIDATE · 24/50 (internal Alpha)
Python 3.12 workspace (server/studio/thursday/audiogen/...); 145 test entries; ~1,330 CI tests claimed (UNVERIFIED); live `data/audio_too.db` gitignored; dual remote risk (F-09). Decision Q6 pending: product vs private tooling.

## Thursday · CONTINUE RESEARCH · 22/50 (Prototype)
106 modules + 44 test files; stdlib-only core + lazy extras; extraction coupling documented (typed-command/LLM still coupled; 819+ tests remain in Audio_Too). No commercial path; security review referenced (not read).

## AudioGen / AutoMix (Audio_Too) · CONTINUE RESEARCH · 18/50
Code present (kokoro-onnx Darwin, numba Intel → Apple-Silicon-only full gate per README); no quality metric (R-08 blocks any sale). KENN automix: intentionally disabled (grade A for honesty).

## Layer-alignment · research asset, no verdict
Isolated R&D git (Nite-DSP/layer-alignment); frozen engine JSON + eval pipeline; recent real-audio qualification commits; no package manifest. Keep as research input to SLO (R-01).

## kenn-evaluation · test harness, no verdict
Black-box golden benchmark (`run_golden_benchmark.py`); own repo; supports R-03.

## Design-system · shared component, adopt (FT3-04)
v2.1.0 dual-theme tokens; adoption across products UNVERIFIED.

## Client-Work · out of scope (hygiene only)
Branch-per-client; spot check found no secret patterns; per-client stacks. No findings.
