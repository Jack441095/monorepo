# Plug-in evidence significance — 15 October 2026

This continues the E2 stem-significance publication work in [KENN_PLAN.md](../../KENN_PLAN.md), based on `7a3f592a`.

## Changed behavior and reuse decision

`from_plugin_context` admitted meter, dynamics, stereo, band-energy and instantaneous/rolling pink-reference facts to generic chat even when its source RMS was near silence. It now requires finite numeric RMS above the existing live-analysis -80 dBFS floor before admitting those facts. Missing, boolean, non-finite or unrepresentable RMS does not establish activity. Capture sample rate/count, audio age, measurement-window positions/generation/drop counts, live-window status and packet freshness survive the abstention, with an explicit limitation saying signal-derived measurements were withheld.

`review_from_handoff` now applies the same inclusive quiet boundary after the full handoff validation and before constructing signal-derived observations. A quiet source receives only an insufficient-signal observation asking for an audible passage. The review schema, unavailable AutoMix state and general limitations remain. Active-source observations are unchanged.

Ingestion still accepts valid quiet frames and retains raw transport metrics, conversation/insert identity, host track name and capture clocks. Bound consumers need that information to decide whether their next capture is active. An integration regression passes the same quiet cached frame into chat history and verifies it cannot restore signal facts or tonal/stereo observations.

This reuses KENN's existing live activity policy. There is no new measurement, DSP, threshold or dependency; no alternate measurement implementation is introduced to benchmark. The whole-file reference policy remains separate at -60 dBFS.

## Verification

From `products/kenn/apps/backend/src`, using FakeLive:

```sh
KENN_LIVE_BACKEND=fake ../.venv/bin/python -m pytest -q -p no:randomly kenn/tests/test_evidence.py kenn/tests/test_plugin_handoff.py
```

**86 passed in 0.66 s.** Tests include -100 dBFS, the exact -80 dBFS boundary, -79.9 dBFS recovery, unqualified RMS, misleadingly strong peak/stereo fields, nonzero spectra and instantaneous/rolling pink-reference details.

Baseline checks temporarily restored each production file from `HEAD` while retaining the new tests, then restored the working source byte-for-byte with matching SHA-256:

- Evidence selector `-k quiet_or_unqualified_plugin_context`: **7 failed, 16 deselected in 0.08 s** against the old source.
- Review selector `-k review_withholds_signal_observations`: **2 failed, 1 passed, 60 deselected in 0.07 s** against the old source.

The evidence change and handoff review were split between parallel workers with disjoint file ownership. Independent read-only review found no actionable issue in the handoff gate, validation ordering, boundary controls or source-identity preservation.

Broader backend and mix-review verification:

```sh
KENN_LIVE_BACKEND=fake PYTHONPATH=../../../packages/mix-review/core ../.venv/bin/python -m pytest -q -p no:randomly kenn/tests ../../../packages/mix-review/tests
```

**5491 passed, 55 skipped, 3 failed, 5 warnings in 127.66 s.** The same three failures were present before this slice and are recorded in the live-stem and browser-reference receipts:

- `test_mixing_doctor.py::test_low_end_name_and_fader_overlap_is_an_advisory_candidate`: expected advisory missing (`StopIteration`).
- `test_mixing_doctor.py::test_near_ceiling_track_meter_creates_track_specific_headroom_advisory`: expected advisory missing (`StopIteration`).
- `test_session_grounded_advice_evaluation.py::test_fixed_session_grounded_benchmark_qualifies`: benchmark returns `qualified=False`; the index lacks embeddings and logs BM25-only retrieval.

No additional full-suite failures appeared. `git diff --check` passed.

## Remaining scope and exact changed files

The E2 checkbox remains open. `build_realtime_mix_comparison` still derives live-versus-uploaded deltas and pink-shape details from raw context, and `proposals_from_live_context` still derives delivery-target proposals from peak alone. Those consumers need separate significance gates. The comparison must check both sides; uploaded `metrics.rms_dbfs` uses per-channel power whereas the reference scorer uses mono-downmixed RMS, so reusing one as the other would silently change the anti-phase policy. This slice does not qualify meter accuracy, listening usefulness, uploaded non-reference health or all raw transport consumers.

- `apps/backend/src/kenn/core/evidence.py`: gate signal facts while retaining capture provenance.
- `apps/backend/src/kenn/plugin_handoff.py`: gate plug-in review observations after validation.
- `apps/backend/src/kenn/tests/test_evidence.py`: quiet/unqualified RMS and active boundary controls.
- `apps/backend/src/kenn/tests/test_plugin_handoff.py`: review boundaries and ingest-to-chat integration.
- `KENN_PLAN.md`: record the delivered scope and remaining consumers.
- `docs/evidence/KENN_PLUGIN_SIGNIFICANCE_2026-10-15.md`: this receipt.
