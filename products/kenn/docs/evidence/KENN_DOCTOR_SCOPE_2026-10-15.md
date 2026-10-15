# Session Doctor capture scope

Recorded 15 October 2026 on `feature/reference-review-grade`, after `edaacfcb`.

## Behavior

Session Doctor receives per-insert telemetry from `live_context_summary`, not an authenticated master-bus meter or a verified binding to a Live track. A host label such as `Master` cannot establish that binding.

Active sample peaks above the existing -0.5 dBFS threshold now produce the advisory `CAPTURE_SAMPLE_PEAK_RISK`. The finding identifies the captured insert, reports sample peak in dBFS and states that true peak and master-bus clipping have not been established. It asks the producer to inspect capture gain/routing and measure true peak separately before choosing an output ceiling.

Negative correlation now produces the advisory `CAPTURE_NEGATIVE_CORRELATION`, recommending a mono audition and inspection of stereo processing. It does not diagnose audible severity, identify affected frequencies or prescribe a sub-bass change. Both observations have `track_index=-1`, `track_name="Captured insert"`, no target parameter and no proposed value. These codes replace `MASTER_OVERLOAD_RISK` and `STEREO_PHASE_CANCELLATION`; no in-repository consumer outside the migrated tests depended on the old identifiers.

The former phase-remediation rule inserted Utility at 90 Hz on track 0 when the meter had no track identity. That rule is removed. Capture-only observations contribute no repair steps, repairable-conflict count or predicted improvement. Existing track-specific structural proposals retain their behavior. No real Live session was modified.

The finite-value checks, -80 dBFS source-activity floor, -0.5 dBFS peak threshold and negative-correlation threshold remain unchanged. This slice changes interpretation and proposal generation, adding no DSP, dependencies or permissions.

## Exact files

Paths are relative to `products/kenn`.

- `apps/backend/src/kenn/core/session_doctor.py`: advisory capture wording/codes, removal of the unbound Utility rule and exclusion of informational observations from repair estimates.
- `apps/backend/src/kenn/tests/test_session_doctor.py`: active/quiet and malformed-meter expectations, exact thresholds, host-label isolation and capture-only proposal behavior.
- `apps/backend/src/kenn/tests/test_doctor_handler.py`: GET/POST route projection, active capture meaning and structural-advice preservation.
- `apps/backend/src/kenn/tests/test_masking_doctor_closed_loop.py`: structural volume/pan repairs survive without an unbound phase insertion.
- `apps/backend/src/kenn/tests/test_server_smoke.py`: real GET/POST HTTP requests preserve informational capture scope.
- `KENN_PLAN.md` and this receipt: progress and remaining qualification work.

## Verification

Commands run from `apps/backend/src` with fake Live:

```sh
KENN_LIVE_BACKEND=fake ../.venv/bin/python -m pytest -q -p no:randomly \
  kenn/tests/test_session_doctor.py kenn/tests/test_doctor_handler.py \
  kenn/tests/test_masking_doctor_closed_loop.py \
  kenn/tests/test_doctor_remediate_disabled.py kenn/tests/test_mcp_new_tools.py \
  kenn/tests/test_natural_language_coproducer.py \
  kenn/tests/test_orchestrator_session_ownership.py kenn/tests/test_server_smoke.py
```

Result: **170 passed** in 4.65 seconds.

Mutation checks used process-local substitutions without editing tracked files. Loading the preceding committed `SessionDoctor.audit` made both new GET/POST route cases fail (**2 failed**). Removing the informational filter from the recipe's conflict count made all three host-label isolation cases fail (**3 failed, 30 deselected**). A SHA-256 comparison confirmed the production file remained unchanged after the latter substitution.

```sh
KENN_LIVE_BACKEND=fake PYTHONPATH=../../../packages/mix-review/core \
  ../.venv/bin/python -m pytest -q -p no:randomly \
  kenn/tests ../../../packages/mix-review/tests
```

Full-suite result: **5861 passed, 55 skipped, 3 failed** in 132.37 seconds. The failures match the preceding masking receipt:

- `test_mixing_doctor.py::test_low_end_name_and_fader_overlap_is_an_advisory_candidate`: expected advisory absent (`StopIteration`).
- `test_mixing_doctor.py::test_near_ceiling_track_meter_creates_track_specific_headroom_advisory`: expected advisory absent (`StopIteration`).
- `test_session_grounded_advice_evaluation.py::test_fixed_session_grounded_benchmark_qualifies`: missing embedding index leaves retrieval BM25-only and the benchmark does not qualify.

No new failures appeared. Independent read-only review identified a stale module description; it was corrected to match capture scope. The reviewer found no remaining capture-only path to the removed Utility action or recipe estimates. `git diff --check` passed.

## Remaining work

E2 and the significance checkbox remain open. Optional transient pre/post renders, legacy ERB masking previews and low-end stem rankings still lack raw activity provenance for their separate contributing sources through handoff, typed evidence and history. Peak-normalized scores and an active enclosing upload cannot establish those sources' significance.

The remaining structural heuristics and recipe estimates are not listening qualification or measured post-repair results. This correction does not prove track-associated diagnosis, actionable capture binding, the native true-peak meter or release readiness.
