# Realtime signal significance — 15 October 2026

This continues the E2 stem-significance work in [KENN_PLAN.md](../../KENN_PLAN.md), based on `faac48f5`.

## Behavior and policy reuse

Both realtime recommendation helpers previously checked freshness alone. They now require finite, non-boolean numeric RMS strictly above the existing -80 dBFS floor before publishing peak, clipping, stereo or pink-reference advice. Missing, invalid, non-finite and unrepresentable RMS abstain. Active advice and its existing freshness policy remain unchanged.

Withholding the advice list alone left the raw `live_context` attached to HTTP and MCP recommendation responses. The shared `plugin_context_for_advice` now retains only source identity, capture timing/counts, controls, freshness and window structure on quiet contexts. It omits all signal fields, including FFTs, paired windows and pink-reference details, and rebuilds typed evidence from the retained provenance instead of trusting a cached packet. The response reports why signal publication is withheld. Active context is copied unchanged; the source context is not mutated.

The composed realtime session review independently gates its plug-in-bus metrics, pink-reference/shape and supplied recommendations. Fresh source/window metadata remains current even when signal activity is insufficient. Structural Live track observations remain available. The existing unavailable/stale path is unchanged.

`live_context_has_activity` extracts the already-shipped policy from `from_plugin_context`; all new gates reuse it. No DSP, analyser, numerical threshold, dependency or new measurement is introduced. The roadmap's measurement-reuse check therefore requires no new external measurement candidate or benchmark for this publication change.

Raw `live_context_summary` and `/api/plugin-live-review` remain transport reads for bound consumers; this slice does not globally qualify them. `SessionDoctor.audit`, canonical session-context/intelligence publication, ordinary uploaded-review findings/grades/evidence and captured-WAV session advice remain open in the roadmap. The E2 significance checkbox remains unchecked.

## Verification

From `products/kenn/apps/backend/src`, using FakeLive:

```sh
KENN_LIVE_BACKEND=fake ../.venv/bin/python -m pytest -q -p no:randomly kenn/tests/test_evidence.py kenn/tests/test_server_smoke.py kenn/tests/test_mcp_facade.py kenn/tests/test_realtime_session_review.py
```

**207 passed in 4.21 s.** Tests cover quiet and exact-floor RMS, missing/bool/non-finite/overflow inputs, misleading hot peaks and stereo/pink warnings, active recovery at -79.9 dBFS, retained capture provenance, nested signal removal, cached-evidence replacement and source-context isolation. HTTP tests ingest validated fake handoffs and fetch the real recommendation endpoint. MCP tests exercise dispatch through an injected read-only client; composed-review tests retain structural Live observations beside the quiet plug-in output.

Implementation ran in parallel with separate ownership of the recommendation and composed-review modules; the parent owned the shared policy and response boundary. Active fixtures that previously omitted RMS now explicitly supply an active -18 dBFS reading.

Broader backend and mix-review verification:

```sh
KENN_LIVE_BACKEND=fake PYTHONPATH=../../../packages/mix-review/core ../.venv/bin/python -m pytest -q -p no:randomly kenn/tests ../../../packages/mix-review/tests
```

**5,564 passed, 55 skipped, 3 failed, 5 warnings in 128.51 s.** Remaining failures match the prior baseline:

- `test_mixing_doctor.py::test_low_end_name_and_fader_overlap_is_an_advisory_candidate`: expected advisory absent (`StopIteration`).
- `test_mixing_doctor.py::test_near_ceiling_track_meter_creates_track_specific_headroom_advisory`: expected advisory absent (`StopIteration`).
- `test_session_grounded_advice_evaluation.py::test_fixed_session_grounded_benchmark_qualifies`: the existing BM25-only index lacks embeddings and does not qualify.

Regression check: temporarily restoring the four previous production implementations (`realtime.py`, `mcp/session_review.py`, `realtime_session_review.py` and `server.py`) while retaining the shared helper and new tests gives **22 failed, 1 passed in 2.20 s**. This covers the direct recommendation, MCP response, composed-review and HTTP boundary regressions; the active HTTP control still passes. All four files were restored byte-for-byte with SHA-256 checks after the subprocess.

Independent read-only review found no remaining quiet signal leak in these bounded publication paths. The composed report retains its existing scope/freshness/window schema; insert identity and capture sample metadata remain in the recommendation context. `git diff --check` passed. No real Live writes, remote GPU job, dependency, CI or permission change was made.

## Exact changed files

- `apps/backend/src/kenn/core/evidence.py`: share the activity predicate and filter quiet published context; keep typed-evidence behavior.
- `apps/backend/src/kenn/core/mcp/realtime.py`: gate both recommendation helpers on source activity.
- `apps/backend/src/kenn/core/mcp/session_review.py`: filter the context attached to MCP recommendation responses.
- `apps/backend/src/kenn/core/realtime_session_review.py`: gate quiet signal facts while retaining structural Live observations and capture provenance.
- `apps/backend/src/kenn/server.py`: filter context attached to HTTP recommendation responses.
- `apps/backend/src/kenn/tests/test_evidence.py`: nested signal removal, cached-evidence replacement and input isolation.
- `apps/backend/src/kenn/tests/test_mcp_facade.py`: quiet recommendation and MCP response regressions; explicit active fixture RMS.
- `apps/backend/src/kenn/tests/test_realtime_session_review.py`: quiet/invalid boundaries, retained structure and active recovery.
- `apps/backend/src/kenn/tests/test_server_smoke.py`: HTTP handoff-to-recommendation boundaries and raw transport isolation.
- `KENN_PLAN.md`: record the delivered gates and retain the remaining work.
- `docs/evidence/KENN_REALTIME_SIGNIFICANCE_2026-10-15.md`: this receipt.
