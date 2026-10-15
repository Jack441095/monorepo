# Canonical context and Session Doctor significance — 15 October 2026

This continues E2 in [KENN_PLAN.md](../../KENN_PLAN.md), based on `da87496a`.

Canonical plug-in frames now pass through the existing advice-publication sanitizer. Missing, invalid, non-finite, overflowing or at/below -80 dBFS RMS withholds signal metrics, spectra and pink-reference shape. Capture identity, measurement window, freshness and window structure remain available, with an explicit signal limitation. The intelligence brief independently checks older canonical contexts so retained quiet meters and pink observations cannot become advice. Active frames above the floor retain their existing signal evidence.

Session Doctor now requires the same active RMS policy before publishing peak or phase findings, and validates each of those meters as finite numeric values. Missing measurements no longer acquire invented defaults. Structural track/fader findings and their proposed remediation remain available even when audio is quiet. GET and POST audit routes inherit this boundary.

This reuses `plugin_context_for_advice` and `live_context_has_activity`, including the existing -80 dBFS floor. It introduces no DSP, numerical threshold, measurement or dependency; the standing measurement-reuse check does not require a new external analyser comparison for this publication change.

The E2 significance checkbox remains open. Ordinary uploaded-review findings, grades and typed evidence, plus captured-WAV session advice, still need publication gates. Raw handoff reads remain transport for bound consumers. Session Doctor's existing active finding text also assumes master scope and overstates what sample peak proves; that wording needs a separate scope review.

## Verification

From `products/kenn/apps/backend/src`, using FakeLive:

```sh
KENN_LIVE_BACKEND=fake ../.venv/bin/python -m pytest -q -p no:randomly kenn/tests/test_session_context.py kenn/tests/test_session_intelligence.py kenn/tests/test_session_doctor.py kenn/tests/test_doctor_handler.py kenn/tests/test_mcp_facade.py kenn/tests/test_diagnostic_loop.py kenn/tests/test_masking_doctor_closed_loop.py
```

**198 passed in 1.16 s.** Coverage includes quiet/exact-floor/above-floor RMS, invalid and missing RMS, invalid individual meters, capture metadata, source isolation, stored canonical contexts, structural observations and remediation. MCP tests exercise context and intelligence tools through read-only dispatch; HTTP handler tests cover cached GET and explicit POST inputs.

The context and doctor implementations were developed in parallel with separate file ownership. Independent read-only reviews found no actionable issues in Session Doctor, handler coverage, the intelligence gate or MCP coverage.

The first broad run found two active-audio fixtures without RMS. They now explicitly supply -18 dBFS, preserving their clipping-diagnosis and phase-remediation expectations under the new contract. The scoped command above includes both callers.

Regression proof: temporarily restoring the three previous production implementations while retaining the new tests produced **35 failed, 4 passed in 0.38 s** across canonical context, older-context intelligence, doctor findings, GET/POST and MCP. This also checks the newly retained measurement-window metadata. All three production files were restored byte-for-byte with SHA-256 checks after the subprocess.

Broader backend and mix-review verification:

```sh
KENN_LIVE_BACKEND=fake PYTHONPATH=../../../packages/mix-review/core ../.venv/bin/python -m pytest -q -p no:randomly kenn/tests ../../../packages/mix-review/tests
```

**5,616 passed, 55 skipped, 3 failed, 5 warnings in 127.09 s.** The remaining failures match the prior baseline:

- `test_mixing_doctor.py::test_low_end_name_and_fader_overlap_is_an_advisory_candidate`: expected advisory absent (`StopIteration`).
- `test_mixing_doctor.py::test_near_ceiling_track_meter_creates_track_specific_headroom_advisory`: expected advisory absent (`StopIteration`).
- `test_session_grounded_advice_evaluation.py::test_fixed_session_grounded_benchmark_qualifies`: the existing BM25-only index lacks embeddings and does not qualify.

`git diff --check` passed. No real Live writes, remote GPU jobs, dependencies, CI or permissions changed.

## Exact changed files

- `apps/backend/src/kenn/core/session_context.py`: sanitize canonical plug-in signal publication while retaining capture metadata.
- `apps/backend/src/kenn/core/session_doctor.py`: gate meter findings and validate their individual values.
- `apps/backend/src/kenn/core/session_intelligence.py`: gate signal evidence from older canonical contexts.
- `apps/backend/src/kenn/tests/test_session_context.py`: quiet/invalid/boundary/active capture and isolation examples.
- `apps/backend/src/kenn/tests/test_session_doctor.py`: activity and individual meter boundaries with structural remediation preserved.
- `apps/backend/src/kenn/tests/test_session_intelligence.py`: older-context withholding and active recovery.
- `apps/backend/src/kenn/tests/test_doctor_handler.py`: GET/POST meter boundary coverage.
- `apps/backend/src/kenn/tests/test_mcp_facade.py`: context and intelligence dispatch coverage.
- `apps/backend/src/kenn/tests/test_diagnostic_loop.py`: explicit active RMS for the measured clipping example.
- `apps/backend/src/kenn/tests/test_masking_doctor_closed_loop.py`: explicit active RMS for the phase-remediation example.
- `KENN_PLAN.md`: delivered slice and remaining publication gaps.
- `docs/evidence/KENN_CONTEXT_SIGNIFICANCE_2026-10-15.md`: this receipt.
