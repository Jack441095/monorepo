# Comparison and proposal significance — 15 October 2026

This continues the E2 significance work in [KENN_PLAN.md](../../KENN_PLAN.md), based on `a7f81c0e`.

## Changed behavior and reuse decision

Live-versus-uploaded comparison previously checked freshness but admitted level rows and pink-reference deltas regardless of source activity. `build_realtime_mix_comparison` now requires finite, non-boolean live RMS above -80 dBFS and uploaded report RMS above -60 dBFS before publishing any peak/RMS/crest rows or paired pink-reference shape. If either side is quiet or unqualified, both sides' signal-derived outputs are withheld, `comparison_available` is false, and a limitation identifies the unavailable side. IDs, schema, scope, advisory/control flags and current capture-window provenance remain available.

`proposals_from_live_context` previously used peak alone. It now requires finite, non-boolean RMS above the shared live -80 dBFS activity floor and finite peak before constructing its existing delivery-target proposal. Quiet or unqualified context returns no proposal. Active proposal fields, confirmation and undo remain unchanged; this changes no audio or Live state.

The numerical policy reuses existing KENN boundaries: `core.evidence.LIVE_ACTIVITY_FLOOR_DBFS` for the live input and `reference_matching.REFERENCE_MIN_RMS_DBFS` for whole-file publication. The latter is mirrored locally because the optional matching engine is loaded from a file; comparing existing report metrics must not require importing that engine. No measurement, DSP, dependency or alternate analyser is introduced, so no external measurement candidate or new benchmark is required for this publication change.

The RMS meanings remain explicit. `local_engine.analyze_wav` reports the arithmetic mean of channel RMS amplitudes; the reference scorer's profile uses mono-downmixed RMS. This comparison uses the existing report value and does not substitute it for the reference scorer's anti-phase-sensitive measurement. The earlier plug-in receipt's description of the report as per-channel power is corrected to the actual arithmetic mean of channel RMS amplitudes.

## Verification

From `products/kenn/apps/backend/src`, using FakeLive:

```sh
KENN_LIVE_BACKEND=fake ../.venv/bin/python -m pytest -q -p no:randomly kenn/tests/test_realtime_mix_comparison.py kenn/tests/test_evidence.py kenn/tests/test_plugin_actions.py kenn/tests/test_plugin_handoff.py kenn/tests/test_server_smoke.py
```

**181 passed in 3.21 s.** The comparison tests exercise missing/invalid/non-finite/unrepresentable RMS, quiet sources, exact boundaries and recovery just above the floor for either source, including populated pink-reference details. They verify quiet comparisons cannot become chat evidence. HTTP tests ingest a validated live frame and fetch the comparison endpoint for either quiet side. Proposal tests cover invalid RMS and peak plus real handoff ingestion at -80 and -79.9 dBFS.

Baseline checks temporarily restored each production file from `HEAD` while retaining the new tests, then restored the working source byte-for-byte with matching SHA-256:

- Comparison selector `-k requires_activity`: **16 failed, 2 passed, 5 deselected in 0.08 s** against the old source.
- Proposal test file: **13 failed, 5 passed in 0.09 s** against the old source.

The expanded scoped command also includes `kenn/tests/test_mcp_facade.py`: **272 passed in 4.10 s**. The first broad run exposed four old MCP comparison fixtures without uploaded RMS; the active uploaded fixture now declares -18 dBFS, and two new MCP tests prove either quiet source still withholds shape details. The production gate was retained.

Implementation and review ran in parallel with disjoint file ownership. Read-only comparison review confirmed that the gate covers both rows and pink shape while retaining provenance. Its policy-source concern is addressed by naming the mirrored canonical constant and the optional engine boundary in code.

Broader backend and mix-review command:

```sh
KENN_LIVE_BACKEND=fake PYTHONPATH=../../../packages/mix-review/core ../.venv/bin/python -m pytest -q -p no:randomly kenn/tests ../../../packages/mix-review/tests
```

**5,531 passed, 55 skipped, 3 failed, 5 warnings in 130.48 s.** The remaining failures match the prior baseline:

- `test_mixing_doctor.py::test_low_end_name_and_fader_overlap_is_an_advisory_candidate`: expected advisory absent (`StopIteration`).
- `test_mixing_doctor.py::test_near_ceiling_track_meter_creates_track_specific_headroom_advisory`: expected advisory absent (`StopIteration`).
- `test_session_grounded_advice_evaluation.py::test_fixed_session_grounded_benchmark_qualifies`: benchmark does not qualify with the existing BM25-only index and missing embeddings.

`git diff --check` passed. No actual Live session, remote GPU, dependency, CI setting or permission was changed.

## Remaining scope and exact changed files

The E2 significance checkbox remains open. A parallel read-only audit, confirmed against the current source, found these remaining bypasses:

- `SessionDoctor.audit` checks plug-in peak and correlation without source RMS; its HTTP and MCP callers pass raw live context.
- `session_context` copies plug-in metrics and shape details into canonical context; the intelligence brief's `_audio_evidence` separately republishes numeric metrics.
- Realtime recommendations (`core/mcp/realtime.py`) and composed session reviews (`core/realtime_session_review.py`) check freshness but still publish raw quiet plug-in signal details.
- Ordinary uploaded-review findings, `_grade_from_report` and `from_mix_review_context` lack a source-activity publication gate. The earlier reference-comparison gate does not cover them. Captured-WAV `live_session_advice` is a separate audio path with the same missing activity policy; its arrangement-only fallback is structural metadata and should remain available.

Raw handoff transport still carries measurements so activity, identity and capture clocks can be checked by bound consumers. This slice does not qualify meters, listening usefulness or all uploaded diagnostics.

- `apps/backend/src/kenn/core/realtime_mix_comparison.py`: gate signal comparisons on activity from both sources; keep provenance and explain abstention.
- `apps/backend/src/kenn/plugin_actions.py`: gate peak-derived proposals on active RMS and finite peak.
- `apps/backend/src/kenn/tests/test_realtime_mix_comparison.py`: either-source boundaries, invalid evidence and chat-evidence isolation.
- `apps/backend/src/kenn/tests/test_plugin_actions.py`: proposal boundaries, invalid evidence, payload preservation and handoff integration.
- `apps/backend/src/kenn/tests/test_server_smoke.py`: HTTP comparison abstention with either quiet source.
- `apps/backend/src/kenn/tests/test_mcp_facade.py`: qualify the active uploaded fixture and verify either-source quiet abstention through MCP.
- `docs/evidence/KENN_PLUGIN_SIGNIFICANCE_2026-10-15.md`: correct the reported RMS semantics.
- `KENN_PLAN.md`: record progress without closing the wider gate.
- `docs/evidence/KENN_COMPARISON_SIGNIFICANCE_2026-10-15.md`: this receipt.
