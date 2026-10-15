# Reference comparison grades — 15 October 2026

This records a bounded E2 change in [KENN_PLAN.md](../../KENN_PLAN.md), based on
`9a7a04454e9789bd2b38ea41b039f1609d4869fc`. The source and tests are committed
with this receipt on `feature/reference-review-grade`.

## Changed behavior

The existing reference comparison calculated `reference_match_score` but omitted
it from the backend response and combined grade. `compare_reference_audio` now
returns both the detailed reference score and a combined `grade`. The separate
`/api/mix-review/reference` and `/api/mix-review/reference-match` handlers retain
that grade in their metadata-only review receipts, including after a service
restart. The comparison's source filenames and hashes remain attached to it.

Reference scoring no longer awards points for unavailable readings:

- Either source's RMS missing, non-finite or at/below -60 dBFS withholds the entire
  reference part. This is a house significance gate using the existing silence
  level, not an EBU requirement.
- Missing, non-finite or boolean component readings leave those components out.
- A mono file has neither stereo component to compare. Undefined correlation
  stays missing when either channel lacks variance or bass energy. Width stays
  missing when mid or side power reaches the existing numerical floor.
- Without NumPy, the legacy comparison's uniform spectrum earns no points.
- If optional reference matching fails, measured technical points remain
  available and the grade explains the reference failure instead of claiming
  that no reference was supplied.

The 20/10/5/5 reference weights and scoring tolerances are unchanged. Missing
components reduce points available; the score is never rescaled to 40 or 100.
No new DSP algorithm, dependency, native meter or Live write was introduced.
The reuse decision remains the one recorded in
[the 14 October analysis review](../research/audio_analysis_reuse_2026-10-14.md).

## Verification

Commands ran from `products/kenn/apps/backend/src` using the existing backend
virtual environment, FakeLive and generated PCM fixtures. No private audio,
model run, index rebuild or real Live session was used.

```sh
KENN_LIVE_BACKEND=fake PYTHONPATH=../../../packages/mix-review/core ../.venv/bin/python -m pytest -q -p no:randomly kenn/tests/test_grade.py kenn/tests/test_local_mix_review_service.py ../../../packages/mix-review/tests/test_reference_matching.py
```

**54 passed in 1.49 s.** The checks cover combined totals, persistence, optional
engine failures with technical points retained, silent sources, non-finite
readings, the -60 dBFS boundary, mono files, bass-free stereo, absent side energy,
the NumPy fallback, repeated-input equality, a changed reference changing the
grade, and a later ordinary review remaining reference-free.

Ten deliberate mutations were caught: dropping the reference handoff, replacing
its failure reason, scoring silent sources, accepting non-finite/boolean values,
scoring mono placeholders, inventing perfect bass correlation, scoring the width
floor, grading the NumPy fallback, assigning reference points to a later ordinary
upload, and discarding measured technical readings. Each mutation ran in a fresh
test process. All three edited source files were restored and their SHA-256
checksums matched before the final full run.

```sh
KENN_LIVE_BACKEND=fake PYTHONPATH=../../../packages/mix-review/core ../.venv/bin/python -m pytest -q -p no:randomly kenn/tests ../../../packages/mix-review/tests
```

**5,446 passed, 55 skipped, 3 failed, 5 warnings in 128.05 s.** All three failures
also reproduced with the three changed production files temporarily restored to
`9a7a0445`, followed by byte-for-byte restoration of the working files:

- `test_mixing_doctor.py::test_low_end_name_and_fader_overlap_is_an_advisory_candidate`
- `test_mixing_doctor.py::test_near_ceiling_track_meter_creates_track_specific_headroom_advisory`
- `test_session_grounded_advice_evaluation.py::test_fixed_session_grounded_benchmark_qualifies`

The first two raise `StopIteration` looking for their expected advisories. The
benchmark returns `qualified=False`; the run also reports missing embeddings for
the local index and explicitly uses BM25-only retrieval. These failures were
left unchanged. The baseline reproduction command was:

```sh
KENN_LIVE_BACKEND=fake PYTHONPATH=../../../packages/mix-review/core ../.venv/bin/python -m pytest -q -p no:randomly kenn/tests/test_mixing_doctor.py::test_low_end_name_and_fader_overlap_is_an_advisory_candidate kenn/tests/test_mixing_doctor.py::test_near_ceiling_track_meter_creates_track_specific_headroom_advisory kenn/tests/test_session_grounded_advice_evaluation.py::test_fixed_session_grounded_benchmark_qualifies
```

An independent read-only reviewer found the bass-free stereo placeholder defect.
After the correction, it signed off after checking mono, silence, bass-free
stereo, a silent right channel, measured stereo, optional matching failure and
the NumPy fallback. `git diff --check` passed.

## Material limits

E2 remains open. These checks establish score delivery and missing-evidence
behavior; they do not qualify measurement accuracy or listening usefulness.
The existing Python analysis remains pending its qualified C++ replacement.
No native conformance or performance result is added by this change.

The ordinary browser upload posts `file` plus optional `reference` to
`/api/mix-review`, whose existing handler takes only the first WAV. Connecting
that reference to the ordinary review and browser Grade card remains pending.
Chat and plug-in audits also lack an associated reference comparison. The
broader stem-significance, source-tier and deterministic-grade gates remain open.

## Exact changed files

Paths are relative to `products/kenn`.

- `apps/backend/src/kenn/core/grade.py`: retain a supplied unavailable part's reason.
- `apps/backend/src/kenn/core/local_mix_review_service.py`: return the reference
  score and combine it with this upload's measured technical grade.
- `packages/mix-review/core/reference_matching.py`: withhold unsupported reference
  components, preserve undefined stereo readings and handle unavailable coaching.
- `apps/backend/src/kenn/tests/test_grade.py`.
- `apps/backend/src/kenn/tests/test_local_mix_review_service.py`.
- `packages/mix-review/tests/test_reference_matching.py`.
- `KENN_PLAN.md`: record this delivery and the remaining E2 boundaries.
- `docs/evidence/KENN_REFERENCE_GRADE_2026-10-15.md`: this receipt.
