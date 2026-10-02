# Reference input evidence — 2 October 2026

This records the synthetic-reference removal slice of B1 in
[KENN_PLAN.md](../../KENN_PLAN.md). Listening usefulness and audio-analysis
conformance remain open.

## Reproduced behavior

`ReferenceMatcher.compute_spectral_delta([], [])` previously substituted two
invented spectra and returned 40 bands, four EQ suggestions and a 0.26 dB RMS
difference. The JSON reference routes and registered reference tool exposed that
result as a measured comparison. The autonomous reference objective also called
the matcher without supplied measurements and could propose the resulting EQ.
The voice shortcut described extracting a commercial reference it did not have.

## Changed behavior

The matcher accepts exactly 40 finite real values for each ERB spectrum. Missing,
partial, nonnumeric, boolean, nonfinite or numerically overflowing inputs return
`available: false`, a diagnostic, empty curves and recipes, and a null RMS
difference. There is no synthetic fallback.

Both JSON routes and their `/kenn` aliases report HTTP 400 with `ok: false` when
comparison is unavailable. Valid supplied spectra retain the existing 1 kHz
normalization, three-point smoothing, +/- 2.5 dB limit and four-band recipe.
The tool uses the same matcher; the autonomous objective reports unavailable
without proposing an EQ step. The voice reply asks for the required spectra.

This validates supplied numeric inputs. It does not establish that those inputs
came from authorized audio, qualify an audio extractor, or validate an EQ target
in Live.

## Verification

- Before the change, matcher/tool cases produced 26 failures and three passes;
  JSON route cases produced 36 failures and four passes. The voice regression
  also failed.
- The final matcher, tool, HTTP and voice checks passed 73 cases in 1.70 s.
- Existing agent, closed-loop and guardian consumers passed 12 cases in 0.70 s.
  The separate multipart WAV reference path passed five cases in 0.60 s.
- Four valid 40-band fixtures preserved their previous curves, recipes and
  rounded RMS values.
- Seventeen deliberate mutations were caught: ten matcher/autonomous cases,
  one voice case and six HTTP response cases. Shared server code was tested
  through temporary compiled copies; matcher source restoration was verified
  by SHA-256.

These scoped runs precede the combined cancellation, streaming and index
verification. Tests used deterministic supplied spectra, synthetic WAV fixtures
and ephemeral loopback HTTP servers. They loaded no language model and wrote
nothing to a running Live session.

Local verification logs are `/tmp/kenn-reference-after-2026-10-02.log`,
`/tmp/kenn-reference-consumers-2026-10-02.log` and
`/tmp/kenn-reference-multipart-2026-10-02.log`. Mutation receipts are
`/tmp/kenn-reference-mutations-2026-10-02.json` and
`/tmp/kenn-reference-http-mutations-2026-10-02.json`.

## Exact changed files

Paths are relative to `products/kenn`.

- `apps/backend/src/kenn/core/reference_matcher.py`: unavailable input contract
  and finite comparison arithmetic.
- `apps/backend/src/kenn/autonomous_agent.py`: shared tool input handling and
  unavailable reference trajectory.
- `apps/backend/src/kenn/speech/voice_copilot.py`: truthful reference reply.
- `apps/backend/src/kenn/server.py`: reference JSON response blocks only.
- `apps/backend/src/kenn/tests/test_reference_matcher.py`: numeric boundaries
  and valid comparison behavior.
- `apps/backend/src/kenn/tests/test_reference_tool_evidence.py`: actual tool,
  agent and voice bindings.
- `apps/backend/src/kenn/tests/test_reference_request_evidence.py`: both routes
  and aliases, including valid-then-missing request isolation.
- `docs/evidence/KENN_REFERENCE_INPUTS_2026-10-02.md`: this receipt.
- `KENN_PLAN.md`: checks only this input-evidence slice.
