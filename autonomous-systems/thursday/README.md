# Thursday

Thursday is NITE DSP's business AI orchestrator. It's a proactive,
context-aware assistant that:

- remembers conversation context across turns,
- classifies intents and extracts entities,
- routes requests to the right module (KENN, AudioGen, audio analysis,
  business agents, and more),
- monitors business health and raises alerts proactively,
- presents one unified conversational interface across HTTP, CLI, SSE, and
  voice.

Thursday's live deployment runs inside the `Audio_Too` Flask app
(`Audio_Too/thursday`). This repository is the in-progress **standalone
extraction** of that same codebase, tracked as the
`autonomous-systems/thursday` submodule of the NITE DSP monorepo.

## Extraction status

**`import thursday` succeeds standalone** — verified with no `audio_too`,
`nite_ai`, or other Audio_Too code on `sys.path`. But a meaningful slice of
Thursday's actual behavior (building/executing typed commands, LLM-backed
decisions, and most of the live service bridges — Ableton, AudioGen,
creative-lab, portfolio publishing) is genuine, documented coupling to the
`Audio_Too` process, not yet cut over to an explicit cross-repo contract.

Read **[`docs/EXTRACTION_COUPLING.md`](docs/EXTRACTION_COUPLING.md)** before
assuming any feature works outside that process — it lists exactly what's
vendored, what's deferred behind a lazy import with a typed error, and what
still requires the real `Audio_Too` app to function, plus a real
clean-checkout receipt (commands run, actual output, not a claimed pass
count).

## Install

```
pip install -e .
```

`pyproject.toml` declares no hard dependencies: the core `import thursday`
path (`session_manager`, `intent`, `resolver`, `formatter`, `errors`) is
pure standard library. Individual features pull in extras lazily at call
time (`numpy`, `onnxruntime`, `httpx`, `PyYAML`, `faster-whisper`,
`kokoro-onnx`, `sounddevice`, `soundfile`, `psutil`) or need the real
`audio_too`/`nite_ai` packages installed alongside this one for the
integration points documented in `docs/EXTRACTION_COUPLING.md`.

## Company operations (Ops upgrade, phases 1–11 + follow-on work)

As of 2026-09-02, this repo also has the full "Thursday Autonomous Company
Operations Upgrade" work migrated in from `Audio_Too/thursday`, organised
under `thursday/ops/`: a persistent, founder-facing task ledger; daily-
status and weekly-report composers; Marketing, Advertising, Funding/
Investment, Engineering, Infrastructure, Finance/Admin, Support,
Documentation, and QA/Beta-Readiness modules; an agent-briefing command
for handing off work to another AI agent; and beta-invite email drafting.
All of it follows the same non-fabrication discipline established during
the extraction: every number is either a live query (the real Admin CRM, a
live-parsed checklist file) or explicitly labelled "Not specified"/
"Evidence missing" rather than guessed. See
`docs/NITE_DSP_THURSDAY_AUDIT_AND_UPGRADE_PLAN_V1.md` in the parent
NITE_DSP repo for the full build history, and `docs/EXTRACTION_COUPLING.md`
for what each migration pass changed about the extraction's own coupling
(`scheduler.py`/`scheduling.py` got the same lazy-import treatment as
Category B; `finance_ops.py` gained an extra path candidate to reach
Audio_Too's business data from this repo's sibling — not nested — location).

## Tests

This repository has a real, standalone-runnable test suite: the original
V2-D/V2-E coverage (`thursday._compat`, `thursday.shadow_adapters`,
`thursday.lease_policy`, `thursday.evals.orchestration_benchmark`) plus
all `thursday/ops/` modules above and their trigger-dispatch machinery
(`thursday.ops.structured_commands`). 242 tests, run with:

```bash
pip install -e . --no-deps
python3 -m pytest -q
```

Its one prior file, `test_thursday_routes.py`, tested Audio_Too's Flask
route glue rather than Thursday itself and was removed (byte-identical to
the real copy already in `Audio_Too/tests/`) — see
`docs/EXTRACTION_COUPLING.md` for why.

The much larger, already-qualified regression suite for Thursday's
day-to-day behavior (819+ tests, intent classification, brain routing,
company state, macros, and the V2-C through V2-I autonomy qualification)
lives in `Audio_Too/tests/thursday` and runs against the live copy
(`Audio_Too/thursday`), not this extraction — that machinery is
deliberately out of scope here (see `docs/EXTRACTION_COUPLING.md`). This
repo's test suite covers what's genuinely standalone; it is not a
replacement for that suite.

The `THURSDAY_V2*` qualification receipts and `thursday/evals/v2*` modules
in this repo are a separate, already-qualified body of work and are out of
scope for this extraction effort — see `docs/EXTRACTION_COUPLING.md` for
what was and wasn't touched.

## Repository layout

- `thursday/` — the package itself (~100 modules: session management,
  intent/entity resolution, the service registry, orchestration, brain
  (LLM-backed decisions), company-state reads, voice output, and the
  `evals/` benchmark suite).
- `thursday/_compat.py` — small, stable primitives vendored from
  `audio_too` so this package doesn't need it at import time (see
  `docs/EXTRACTION_COUPLING.md`).
- `docs/` — design docs, backlog, and the extraction coupling contract.
