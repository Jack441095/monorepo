# Uploaded and captured-audio publication qualification — 15 October 2026

Scope: follow-up to E2's source-significance gate, based on `49d0ccd6`.

Ordinary uploaded reviews, typed uploaded chat evidence, cached handoff prose and captured-WAV advice now require finite numeric, non-boolean reported RMS strictly above -60 dBFS before publishing signal-derived claims. Missing, malformed, overflowing and non-finite values abstain. The exact -60 dBFS boundary abstains; -59.9 dBFS qualifies for publication, but does not guarantee enough measurements for a grade.

This reuses the existing uploaded activity threshold from realtime comparisons and the reference scorer. No DSP, analysis dependency, meter, permission or CI change was introduced. The standing reuse check therefore resolves to the existing implementation; no new analyser or external benchmark was needed. Uploaded reports use their existing mean-channel RMS; reference matching retains its separate downmixed-RMS qualification. These are activity floors, not mix-quality targets.

## Behavior and files

- `apps/backend/src/kenn/core/evidence.py`: shared uploaded activity policy; unqualified handoffs produce a limitation-only evidence packet, withholding numeric and nested transient, stem, reference and pink-shape facts.
- `apps/backend/src/kenn/core/realtime_mix_comparison.py`: consumes that policy while preserving the existing threshold import for callers.
- `apps/backend/src/kenn/core/local_mix_review_service.py`: withholds ordinary quiet review metrics, evidence, findings, flags, actions, technical rating and grade points. Status, list and exports sanitize older ordinary receipts on a deep copy without rewriting the saved registry. Source/reference hashes, project identity and input context survive. Attached unavailable references retain their explicit scorer reason in review limitations.
- `apps/backend/src/kenn/core/live_session_advice.py`: successful but unqualified captures use structural arrangement advice with an explicit activity limitation and retained filename, hash and cache provenance. Captured signal findings, loudness and pink-shape advice are withheld.
- `apps/backend/src/kenn/server_payloads.py`: unqualified structured handoffs rebuild chat history from bounded title and explicit producer goals, excluding cached signal prose and nested repair/revision/reference claims.
- Tests changed: `test_evidence.py`, `test_grade.py`, `test_live_session_advice.py`, `test_local_mix_review_service.py`, `test_server_payloads.py` (new), `test_server_smoke.py`, and `test_knowledge_request_context.py`, all under `apps/backend/src/kenn/tests/`. The routing fixture now supplies active RMS explicitly.
- `KENN_PLAN.md` records the delivered slice and remaining publication gaps.

## Verification

All commands ran from `apps/backend/src` with `KENN_LIVE_BACKEND=fake`; no real Live session or GPU was used.

Scoped command, including real HTTP upload/chat and MCP-to-HTTP routing:

```sh
KENN_LIVE_BACKEND=fake ../.venv/bin/python -m pytest -q -p no:randomly \
  kenn/tests/test_knowledge_request_context.py kenn/tests/test_evidence.py \
  kenn/tests/test_realtime_mix_comparison.py kenn/tests/test_live_session_advice.py \
  kenn/tests/test_grade.py kenn/tests/test_local_mix_review_service.py \
  kenn/tests/test_server_payloads.py kenn/tests/test_server_smoke.py
```

Result: **252 passed**. Generated mono 16-bit PCM uploads use amplitudes 1, 32 and 33 at 8 kHz; adjacent amplitudes 32 and 33 straddle -60 dBFS. Quiet upload output and subsequent chat evidence abstain; the active control publishes measured evidence. Saved legacy ordinary receipts abstain on status/list/JSON export while their source file remains unchanged.

Mutation check: temporarily forced the shared uploaded activity predicate to return true. The evidence, grade, ordinary review, captured-WAV and handoff tests reported **53 failed, 96 passed**. The source was restored byte-for-byte before the final scoped run.

Full backend plus mix-review command:

```sh
KENN_LIVE_BACKEND=fake PYTHONPATH=../../../packages/mix-review/core \
  ../.venv/bin/python -m pytest -q -p no:randomly \
  kenn/tests ../../../packages/mix-review/tests
```

Result before correcting the active routing fixture: **5680 passed, 55 skipped, 4 failed** in 128.34 s. The new routing-fixture failure was corrected and its whole test module passed in the scoped run above. The other three failures match the previously recorded baseline:

- `test_mixing_doctor.py::test_low_end_name_and_fader_overlap_is_an_advisory_candidate`: expected advisory absent (`StopIteration`).
- `test_mixing_doctor.py::test_near_ceiling_track_meter_creates_track_specific_headroom_advisory`: expected advisory absent (`StopIteration`).
- `test_session_grounded_advice_evaluation.py::test_fixed_session_grounded_benchmark_qualifies`: benchmark does not qualify with the missing embedding index and BM25-only retrieval.

The full suite was not repeated after the fixture-only correction. `git diff --check` passed.

## Still open

E2 and its significance checkbox remain open. Parallel read-only review found these remaining paths:

- `session_context._safe_mix_review` accepts raw/older uploaded metrics and advice without source qualification. Its comparison projection drops `dynamics`, including the per-source RMS needed to qualify both mix and reference.
- `session_intelligence._audio_evidence` gates plug-in frames but still accepts older uploaded metrics and explicit comparison LTAS/pink evidence. Completed-comparison coaching also needs qualification.
- Stored standalone reference-comparison receipts bypass ordinary-review read sanitization. Status, export and preset download need requalification of both sources, including missing legacy provenance. New comparisons already gate both sources during generation.

Active Session Doctor scope/sample-peak wording and the other E2 meter, reference and listening qualifications remain separate unfinished work. This receipt claims no release qualification or listening usefulness.
