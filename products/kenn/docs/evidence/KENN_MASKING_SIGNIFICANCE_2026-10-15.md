# Offline stem masking significance

Recorded 15 October 2026 on `feature/reference-review-grade`, after `3fbebf7e`.

## Publication contract

The offline analyser now records each source's active frame count and every unordered pair's simultaneously active frame count. A source is active when any existing measured band is strictly above the existing -50 dBFS floor. Exactly -50 dBFS is inactive. No additional FFT or audio measurement is introduced.

Without a simultaneously active pair, the result retains capture dimensions and explicit limitations but withholds the candidate count. This distinguishes silence and one playing stem from an active pair with no flagged competition. Two playing stems in separate frequency ranges can still report a measured zero. Positive candidate detection retains its existing per-band activity, 6 dB competition and 20% frame-fraction thresholds.

The typed evidence adapter validates the versioned activity envelope, complete source/pair grid, integer count bounds and logical overlap bounds. Each candidate must name an active pair, a known band and a finite fraction supported by that pair's frame count, allowing the producer's three-decimal rounding. Invalid provenance abstains rather than becoming zero. Signal facts are rebuilt from the findings; cached scalar candidate facts are ignored.

Chat history retains only selected activity fields and normalized candidate fields, limited to the analyser's 12 sources, 66 pairs and seven bands per pair. It retains source identities to recheck the same pair on replay; displayed pair names remain limited to 96 characters per source. It carries no FFT arrays or candidate advice prose. History reads re-enter the adapter. Legacy scalar-only packets retain valid capture metadata and an abstention reason. Input objects and returned payloads remain independent.

## Reuse decision

The standing reuse screen compared the existing NumPy frame arrays with upstream librosa silence detection. [NumPy's axis reduction](https://numpy.org/doc/stable/reference/generated/numpy.any.html) supplies the required per-frame logical OR directly; NumPy uses the [BSD 3-Clause licence](https://raw.githubusercontent.com/numpy/numpy/main/LICENSE.txt). The existing array comparisons, logical AND and reductions are sufficient.

Upstream librosa [`_signal_to_frame_nonsilent` and `split`](https://raw.githubusercontent.com/librosa/librosa/main/librosa/effects.py) calculate broadband RMS and apply a dB threshold relative to a reference (the default is the signal maximum). That differs from this analyser's absolute per-band activity policy and would add another analysis pass and integration work. Librosa's [ISC licence](https://raw.githubusercontent.com/librosa/librosa/main/LICENSE.md) is permissive, but this helper was not shortlisted for an equivalent-DSP benchmark. No dependency was added or changed. Sources were inspected on 15 October 2026.

The existing `tooling/scripts/profile_masking_analysis.py` harness compared the previous producer loaded from git with this producer in process, using three generated 3-second PCM16 sine stems and three repeats at each rate:

| Sample rate | Previous cumulative time | Current cumulative time | Findings, previous/current |
| --- | ---: | ---: | ---: |
| 44.1 kHz | 30.730 ms | 28.363 ms | 1 / 1 |
| 48 kHz | 31.884 ms | 31.558 ms | 1 / 1 |
| 96 kHz | 89.873 ms | 60.802 ms | 2 / 2 |

These are cProfile totals across three calls, with order/warmup variability; they establish neither a speedup nor a latency guarantee. Finding counts stayed unchanged on these fixtures. The added work is boolean reduction over existing frames, with a per-source active mask and temporary per-pair intersection; memory was not measured. No private audio was used or retained.

## Changed files

Paths are relative to `products/kenn`.

- `packages/mix-review/core/masking_analysis.py`: source/pair activity envelope and inactive-pair publication gate.
- `apps/backend/src/kenn/core/evidence.py`: qualified fact reconstruction and history requalification.
- `packages/mix-review/tests/test_masking_analysis.py`: boundary, quiet, recovery and multi-source isolation regressions.
- `apps/backend/src/kenn/tests/test_evidence.py`: malformed/legacy provenance, positive/zero controls and history isolation.
- `apps/backend/src/kenn/tests/test_server_evidence_context.py` and `test_specialist_figures_in_prompt.py`: qualified active fixtures and quiet evidence handling.
- `apps/backend/src/kenn/tests/test_server_smoke.py`: generated multipart uploads through producer, adapter and history for competition, active zero and an inactive pair.
- `KENN_PLAN.md` and this receipt: progress and remaining qualification work.

## Verification

Commands run from `apps/backend/src`, using the fake Live backend:

```sh
KENN_LIVE_BACKEND=fake PYTHONPATH=../../../packages/mix-review/core \
  ../.venv/bin/python -m pytest -q -p no:randomly \
  kenn/tests/test_evidence.py kenn/tests/test_server_evidence_context.py \
  kenn/tests/test_specialist_figures_in_prompt.py kenn/tests/test_server_smoke.py \
  kenn/tests/test_stem_masking_chat_tool.py \
  ../../../packages/mix-review/tests/test_masking_analysis.py
```

Result: **236 passed** in 5.08 seconds.

Replacing the adapter with its previous implementation in memory caused **66 failures, 3 passes, 65 deselections** in the masking evidence subset. Tracked source files were untouched.

Forcing the producer's `has_qualified_pair` predicate true in memory caused **4 failures, 12 passes**: quiet, one-active-source, exact-floor and quiet-to-active recovery assertions caught the bypass. The producer's SHA-256 was unchanged before and after the mutation run.

```sh
KENN_LIVE_BACKEND=fake PYTHONPATH=../../../packages/mix-review/core \
  ../.venv/bin/python -m pytest -q -p no:randomly \
  kenn/tests ../../../packages/mix-review/tests
```

Full-suite result: **5851 passed, 55 skipped, 3 failed** in 133.97 seconds. The failures match the baseline recorded in the preceding saved-comparison receipt:

- `test_mixing_doctor.py::test_low_end_name_and_fader_overlap_is_an_advisory_candidate`: expected advisory absent (`StopIteration`).
- `test_mixing_doctor.py::test_near_ceiling_track_meter_creates_track_specific_headroom_advisory`: expected advisory absent (`StopIteration`).
- `test_session_grounded_advice_evaluation.py::test_fixed_session_grounded_benchmark_qualifies`: missing embedding index leaves retrieval BM25-only and the benchmark does not qualify.

No new failures appeared. `git diff --check` passed.

## Still open

E2 and the significance checkbox remain open. These checks do not establish audible masking, listening usefulness or release qualification. Optional transient and separately supplied stem evidence still need absolute activity provenance for each contributing source; active enclosing-mix RMS cannot qualify an independent stem or render. Active Session Doctor scope and sample-peak wording remain a separate correction. No running Ableton session was changed.
