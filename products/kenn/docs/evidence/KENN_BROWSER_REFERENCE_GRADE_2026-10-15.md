# Browser upload reference grades — 15 October 2026

This records a bounded E2 change in [KENN_PLAN.md](../../KENN_PLAN.md), based on
`c977ee8b520b45a0d0bf42c43665eb765080154a`. Source, tests and this receipt are
committed together on `feature/reference-review-grade`.

## Changed behavior

The browser already uploaded an optional `reference`, but the ordinary review
handler selected the first WAV and discarded the other. It now selects the mix
and reference by multipart field role, independent of attachment order. The
ordinary review keeps its goal-specific metrics, findings, action plan and
project association. Its grade also receives the existing reference score.
The browser uses `/api/admin/mix-review`, an alias of `/api/mix-review`.

The saved review includes the reference filename and SHA-256, comparison and
combined grade. Status, JSON export and service restart preserve them. Storage
remains metadata only; neither WAV is retained. Clearing the reference produces
an ordinary review without a reference part or reference metadata.

Empty, corrupt, unsupported, oversized or ambiguous attachments reject the pair
before any review is saved. Nameless `file` and `reference` fields are rejected,
including malformed duplicates. A reference-only request cannot substitute
the reference for the mix. Legacy single-file field names remain accepted. The
request budget admits two WAVs plus a 2 MiB multipart envelope; the existing
150 MiB limit still applies to each WAV. If optional matching fails after valid
audio analysis, measured technical points remain available and the grade says
why the supplied reference could not be graded.

This reuses the existing comparison and ordinary analysis paths. It introduces
no DSP algorithm or dependency. The existing reuse decision is recorded in
[the analysis review](../research/audio_analysis_reuse_2026-10-14.md).

## Verification

Backend commands ran from `products/kenn/apps/backend/src` with the existing
virtual environment and FakeLive. The initial attached-reference regression
failed twice before the fix because the reference part was missing.

```sh
KENN_LIVE_BACKEND=fake ../.venv/bin/python -m pytest -q -p no:randomly kenn/tests/test_grade.py kenn/tests/test_local_mix_review_service.py kenn/tests/test_server_smoke.py -k 'browser or legacy_single or local_service or reference or oversized_mix_upload or grade'
```

**43 passed, 48 deselected in 4.11 s.** Generated PCM checks cover both attachment
orders, ordinary findings and project identity, metadata-only persistence,
status/export, invalid pairs, per-file size limits, unavailable matching,
repeated-input equality, changed references and isolation of the next ordinary
review. The HTTP test shrinks the file budget so the real multipart body exceeds
one WAV's limit and still succeeds.

Nine deliberate mutations were caught: dropping the reference-grade handoff,
using the reference as the mix, losing persisted reference identity, losing the
optional failure reason, saving a mix-only review after an invalid reference,
bypassing the reference byte limit, ignoring nameless references, ignoring a
nameless explicit mix field and restoring the single-WAV request limit. Every
mutation ran in a fresh test process. Both production files were restored and
their SHA-256 checksums matched before the full run.

Frontend commands ran from `products/kenn/apps/frontend`:

```sh
./node_modules/.bin/vitest run src/utils/mixReviewNormalize.test.ts
./node_modules/.bin/vue-tsc -b
VITE_MIX_REVIEW_MOCK=0 ./node_modules/.bin/vite build --outDir /tmp/kenn-browser-reference-grade-2026-10-15
KENN_E2E_PORT=18937 ./node_modules/.bin/playwright test e2e/mix_review_grade.e2e.ts
```

**7 unit tests passed; type checking and the production build passed. One
Chromium test passed in 23.9 s.** The browser test uploads generated one-second
mono tones at 8 kHz. Matching tones display `Reference match 30 / 30`; changing
the reference from 100 Hz to 3 kHz lowers the grade; clearing it removes the
reference part. The displayed total and meaning match each actual HTTP result.
A screenshot was visually checked and remains outside tracked source.

The browser used a disposable FakeLive companion serving that build. Project
folder discovery was stubbed to an empty generated-test project so the final
regression would not auto-load a producer bounce. Upload, analysis, grading and
the Grade card used the real application path. LLM generation was disabled.
The companion was stopped after the test. On this Mac it was started explicitly
as arm64 to match the existing NumPy environment:

```sh
KENN_STATIC_ROOT=/tmp/kenn-browser-reference-grade-2026-10-15 KENN_MIX_REVIEW_RUNTIME_DIR=/tmp/kenn-browser-reference-grade-runtime-2026-10-15 KENN_LLM_ENABLED=0 AUDIO_TOO_LLM_ENABLED=0 KENN_LIVE_LLM_ENABLED=0 KENN_LLM_BACKGROUND=0 /usr/bin/arch -arm64 ../backend/.venv/bin/python ../../tooling/scripts/run_fake_live_companion.py --port 18937
```

Full backend and mix-review package suite, from the backend source directory:

```sh
KENN_LIVE_BACKEND=fake PYTHONPATH=../../../packages/mix-review/core ../.venv/bin/python -m pytest -q -p no:randomly kenn/tests ../../../packages/mix-review/tests
```

**5,466 passed, 55 skipped, 3 failed, 5 warnings in 128.17 s.** The three failures
match the pre-existing set recorded and reproduced before this slice in
[the preceding reference-grade receipt](KENN_REFERENCE_GRADE_2026-10-15.md):

- `test_mixing_doctor.py::test_low_end_name_and_fader_overlap_is_an_advisory_candidate`
- `test_mixing_doctor.py::test_near_ceiling_track_meter_creates_track_specific_headroom_advisory`
- `test_session_grounded_advice_evaluation.py::test_fixed_session_grounded_benchmark_qualifies`

The first two raise `StopIteration` looking for advisories; the benchmark returns
`qualified=False`. The local index still lacks embeddings and explicitly uses
BM25-only retrieval. Those failures and the index were left unchanged.

An independent read-only reviewer found that nameless reserved fields could be
silently ignored, allowing an invalid reference to become a mix-only review.
After the fix, it exercised seven multipart boundary cases and signed off the
restored production diff against `c977ee8b`. It found no further actionable
defects in this bounded slice. `git diff --check` passed.

## Material limits

E2 remains open. This proves browser delivery and persistence on synthetic
uploads; it does not qualify meter accuracy, listening usefulness or native
performance. Missing optional loudness readings still leave their points
unavailable. Uploaded spectral health remains unscored because the analyser's
bands differ from the Doctor's bands. Chat and plug-in audits still lack an
associated reference comparison, and the plug-in has no grade display.

The ordinary report and reference comparison currently analyze the mix
separately to preserve the ordinary report's goal-specific findings. No
large-upload latency or memory claim follows from the short generated fixtures.
No real Live write, model run, index rebuild or dependency change was made.

## Exact changed files

Paths are relative to `products/kenn`.

- `apps/backend/src/kenn/core/local_mix_review_service.py`: select attachment
  roles, validate the pair, combine the grade and retain reference metadata.
- `apps/backend/src/kenn/routes/audio_handler.py`: admit two bounded WAVs in
  the ordinary upload request.
- `apps/backend/src/kenn/tests/test_local_mix_review_service.py`: generated
  multipart, grade, persistence, failure and isolation regressions.
- `apps/backend/src/kenn/tests/test_server_smoke.py`: real HTTP upload,
  status/export and oversized-request checks.
- `apps/frontend/src/utils/mixReviewNormalize.test.ts`: preserve reference,
  grade and ordinary metrics together.
- `apps/frontend/e2e/mix_review_grade.e2e.ts`: actual browser upload and Grade
  card checks with generated audio.
- `KENN_PLAN.md`: record this delivery and the remaining E2 work.
- `docs/evidence/KENN_BROWSER_REFERENCE_GRADE_2026-10-15.md`: this receipt.
