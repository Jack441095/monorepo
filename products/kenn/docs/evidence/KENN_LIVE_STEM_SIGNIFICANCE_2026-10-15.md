# Live stem significance — 15 October 2026

This records a bounded E2 publication fix in [KENN_PLAN.md](../../KENN_PLAN.md), based on `ba30ede0`.

## Changed behavior and reuse decision

Per-insert and paired analysis already abstained at or below -80 dBFS RMS, but both built their returned measurement dictionaries before testing activity. The per-insert answer also quoted peak, RMS and relative band values before saying the source was near silence. A caller could therefore consume silent-source metrics despite the abstention.

Both routes now apply their existing activity checks before publishing measurements. Per-insert analysis retains its target and session association but returns an empty `measured` dictionary, no interpretations, recommendations or proposal, and asks for an audible passage. Paired analysis withholds both sources' measurements when either is at or below -80 dBFS RMS or below the existing low-band power floor of 1e-8 in the FFT's linear power units. Both routes return `insufficient_signal`.

The reuse choice is the existing KENN activity gate: this changes output ordering only. There is no new DSP, threshold, measurement, dependency or alternate analyser to benchmark. The -80 dBFS live policy remains separate from the whole-file reference scorer's -60 dBFS policy; neither is a recording-quality target.

## Verification

From `products/kenn/apps/backend/src`, with FakeLive:

```sh
KENN_LIVE_BACKEND=fake ../.venv/bin/python -m pytest -q -p no:randomly kenn/tests/test_live_track_analysis.py kenn/tests/test_live_paired_analysis.py
```

**88 passed, 4 skipped in 1.41 s.** The skips are optional native HTTP/performance profiles requiring a compiled performance binary and explicit opt-in. The tests cover -100 dBFS, the inclusive -80 dBFS boundary, -79.9 dBFS recovery, either quiet source in a pair, and the existing silent low-band case. No Live writes or action proposals occur.

To check that these regressions catch the previous code, each production file was temporarily restored from `HEAD` while retaining the new tests, then restored byte-for-byte with matching SHA-256:

- Track selector `-k quiet_insert_withholds`: **2 failed, 41 deselected in 0.07 s** against the old source.
- Paired selector `-k 'paired_rms_gate or bound_silent_low_end'`: **5 failed, 2 passed, 42 deselected in 0.08 s** against the old source.

An independent read-only review found no actionable gaps in the four code/test changes: empty dictionaries preserve the response keys, activity thresholds are unchanged, and target association remains available on abstention.

Broader backend and mix-review verification:

```sh
KENN_LIVE_BACKEND=fake PYTHONPATH=../../../packages/mix-review/core ../.venv/bin/python -m pytest -q -p no:randomly kenn/tests ../../../packages/mix-review/tests
```

**5479 passed, 55 skipped, 3 failed, 5 warnings in 127.88 s.** These are the same three failures recorded before this slice in the browser-reference receipt:

- `test_mixing_doctor.py::test_low_end_name_and_fader_overlap_is_an_advisory_candidate`: expected advisory missing (`StopIteration`).
- `test_mixing_doctor.py::test_near_ceiling_track_meter_creates_track_specific_headroom_advisory`: expected advisory missing (`StopIteration`).
- `test_session_grounded_advice_evaluation.py::test_fixed_session_grounded_benchmark_qualifies`: benchmark returns `qualified=False`; the local index lacks embeddings and logs BM25-only retrieval.

No additional full-suite failures appeared. `git diff --check` passed.

## Limits and exact changed files

This does not finish the stem-significance gate. Generic chat evidence and `review_from_handoff` still need a silent-source publication audit. Raw plug-in transport remains available to consumers that need source identity and activity information. Meter conformance and listening qualification remain separate work.

- `apps/backend/src/kenn/core/live_track_analysis.py`: move the existing quiet gate before measurement publication and numeric answer construction.
- `apps/backend/src/kenn/core/live_paired_analysis.py`: move the existing activity gate before paired measurement publication.
- `apps/backend/src/kenn/tests/test_live_track_analysis.py`: pin quiet-output withholding and recovery above the floor.
- `apps/backend/src/kenn/tests/test_live_paired_analysis.py`: pin either quiet source, boundary recovery and silent low-band withholding.
- `KENN_PLAN.md`: record this slice while leaving the broader checkbox open.
- `docs/evidence/KENN_LIVE_STEM_SIGNIFICANCE_2026-10-15.md`: this receipt.
