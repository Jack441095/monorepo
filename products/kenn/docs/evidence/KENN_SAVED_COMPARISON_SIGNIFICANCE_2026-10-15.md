# Saved comparison and canonical upload significance

Recorded 15 October 2026 on `feature/reference-review-grade`, after `519b26d5`.

## Publication contract

Uploaded comparison measurements, reference grade points, presets and listening guidance require finite numeric RMS strictly above -60 dBFS for both sources. Missing legacy provenance, booleans, strings, non-finite numbers, overflowing integers and exactly -60 dBFS abstain. This reuses the existing upload floor and matcher RMS; it adds no audio analysis or dependencies.

Canonical context also qualifies ordinary own-source metrics, findings and actions. Active comparisons retain bounded per-source RMS so downstream intelligence can requalify them. Identity and explicit limitations remain available. Older stored contexts and explicit comparison inputs receive the same checks.

Saved standalone and attached comparisons are sanitized on status, list and export without rewriting stored receipts. Removing the comparison also removes its downloadable preset. An independently active mix retains its own grade only when saved grade parts permit an exact recomputation; an inseparable aggregate abstains. New standalone comparisons retain qualified mix metrics when the reference is unavailable so this behavior survives reload.

Typed evidence and cached handoff prose withhold unqualified paired measurements and advice. Cached prose is rebuilt from active own metrics and explicit intent because its sentences cannot reliably be separated into own-source and reference claims. Direct coaching calls also abstain for unqualified pairs. Realtime comparison availability retains its existing contract.

## Changed files

Paths below are relative to `products/kenn`.

- `apps/backend/src/kenn/core/evidence.py`: shared two-source predicate and typed reference fact gate.
- `apps/backend/src/kenn/core/session_context.py`: canonical upload projection and bounded pair provenance.
- `apps/backend/src/kenn/core/session_intelligence.py`: older uploaded contexts, explicit comparison evidence and coaching qualification.
- `apps/backend/src/kenn/core/local_mix_review_service.py`: saved comparison publication and exact mix-only grade recomputation.
- `apps/backend/src/kenn/core/mixdown_coach.py`: direct listening-guidance abstention.
- `apps/backend/src/kenn/server_payloads.py`: rebuild unqualified reference handoff history from qualified own measurements.
- `apps/backend/src/kenn/tests/test_evidence.py`, `test_session_context.py`, `test_session_intelligence.py`, `test_local_mix_review_service.py`, `test_mixdown_coach.py`, `test_server_payloads.py`, `test_server_smoke.py`, `test_mcp_facade.py`: boundaries, active controls, isolation and publication regressions.
- `tooling/scripts/evaluate_mixdown_coach.py`: explicit active pair fixtures and quiet-source abstention case.
- `KENN_PLAN.md` and this receipt: progress and remaining qualification work.

## Verification

Backend commands run from `apps/backend/src` with `KENN_LIVE_BACKEND=fake`.

```sh
../.venv/bin/python -m pytest -q -p no:randomly \
  kenn/tests/test_session_context.py kenn/tests/test_session_intelligence.py \
  kenn/tests/test_evidence.py kenn/tests/test_server_payloads.py \
  kenn/tests/test_server_smoke.py kenn/tests/test_local_mix_review_service.py \
  kenn/tests/test_grade.py kenn/tests/test_reference_request_evidence.py \
  kenn/tests/test_reference_tool_evidence.py kenn/tests/test_mix_review_route.py \
  kenn/tests/test_realtime_session_review.py kenn/tests/test_knowledge_request_context.py \
  kenn/tests/test_mixdown_coach.py
```

Result: **415 passed**. The MCP facade module separately passed **109 tests**, including quiet reference behavior through both intelligence and direct recommendations. HTTP tests cover missing RMS, exactly -60 dBFS and an active -59.9 dBFS control across status, JSON export and preset download. Legacy source files remain unchanged. The actual mixdown-coach evaluator passed all **6 cases**.

Mutation checks used process-local substitutions, leaving source files untouched. Forcing the shared pair predicate true produced **70 failed, 235 passed** across publication regressions. Replacing canonical projection with its previous implementation caused all **35 new canonical regressions** to fail.

```sh
PYTHONPATH=../../../packages/mix-review/core ../.venv/bin/python -m pytest \
  -q -p no:randomly kenn/tests ../../../packages/mix-review/tests
```

The initial full run reported **5772 passed, 55 skipped, 5 failed** in 131.89 seconds. Two MCP tests used an intended-active fixture without pair RMS. That fixture was corrected and the whole MCP module then passed. The three other failures match the recorded baseline:

- `test_mixing_doctor.py::test_low_end_name_and_fader_overlap_is_an_advisory_candidate`: expected advisory absent (`StopIteration`).
- `test_mixing_doctor.py::test_near_ceiling_track_meter_creates_track_specific_headroom_advisory`: expected advisory absent (`StopIteration`).
- `test_session_grounded_advice_evaluation.py::test_fixed_session_grounded_benchmark_qualifies`: missing embedding index leaves retrieval BM25-only and the benchmark does not qualify.

Final full-suite result after the fixture correction: **5775 passed, 55 skipped, 3 failed** in 130.44 seconds. Only the three baseline failures above remain. `git diff --check` passed.

## Still open

E2 and its significance checkbox remain open. Offline masking already requires both per-frame band levels above -50 dBFS for positive findings, but zero candidates does not distinguish inactive pairs from active pairs without competition. Its evidence adapter also trusts older scalar facts without source activity provenance.

Optional transient, stem masking and low-end stem evidence still need activity provenance for each contributing source. An enclosing active mix cannot qualify an independently supplied stem or render. KENN has no local transient producer to establish that provenance; external normalized onset measurements alone do not prove absolute source activity.

Active Session Doctor scope and sample-peak wording require a separate correction. These checks do not establish audible usefulness or release qualification.
