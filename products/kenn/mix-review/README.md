# KENN Mix Review Adapter

This is the first product-owned boundary for KENN Mix Review. It is a local,
read-only adapter around the preserved Audio_Too decoder, running only the
three fault detectors that carry real qualification evidence.

## Contract (schema `kenn.mix_review.local_receipt.v2`)

- Input is an explicit local filesystem path, not an HTTP upload.
- Audio bytes are read into memory and are not copied into the product tree.
- Audio is decoded through the real product decoder
  (`audio_analysis.utils.audio_io_api.decode_audio_bytes`), then analysed with
  `qualified_detectors.py` — a frozen, promoted copy of the detector and gate
  logic that was actually evaluated in V2-D (see that file's docstring for
  full provenance). **The older, broader flag set from
  `audio_analysis.mix_review.mix_review.analyze_wav` (`review_flags`) is
  deliberately not used here** — those heuristics have never been evaluated
  with precision/recall numbers and must not be presented as findings.
- Every completed receipt always returns exactly 3 findings — clipping,
  headroom, lr_imbalance — each with an explicit `status`:
  - `finding` — a real, actionable, qualified result (evidence-backed).
  - `observed_not_actionable` — measured but not a finding (near a threshold,
    or gated by scope/persistence — see below).
  - `no_issue_detected` — measured and clearly below the qualified threshold.
  - `insufficient_evidence` / `context_required` may also appear via
    `recommendation_state` for edge cases (mono audio, non-persistent
    imbalance).
- Each finding carries: `measured_value`/`unit`/`evidence` (raw measurement),
  `severity`, `confidence_bucket`/`confidence_kind`, `score`, `explanation`,
  `suggested_next_step` (only populated for real findings), `limitations`,
  and `gate_reason`.
- The receipt's `unqualified_scope_note` states explicitly that no other
  fault type was checked.
- Runtime state is redirected to `.runtime/` outside the Audio_Too checkout.
- No public route, report sharing, database workflow, Ableton action, or
  AutoMix invocation is included.

## The `scope` parameter — read this before interpreting headroom results

Headroom is only ever reported as a `finding` when you explicitly pass
`scope="mix_in_progress"`. With the default (`"unknown"`) or `"master"`, a
headroom result is always `observed_not_actionable` regardless of how much
margin the peak actually has — this mirrors the exact frozen gate behaviour
that was qualified in V2-D (headroom significance depends on knowing whether
the file is still being mixed), not a beta-only restriction.

The adapter is not yet a qualified public Mix Review product: no human/blind
review has been completed. See `../BETA_SCOPE.md` and `../BETA_BLOCKERS.md`.

## Local probe

From the repository root:

```sh
python3 products/kenn/mix-review/adapter.py ./path/to/local-mix.wav --scope mix_in_progress
```

The engine source remains at `Audio_Too/studio/audio_analysis`; do not modify
that checkout. The optional `KENN_AUDIO_TOO_ROOT` variable can point to another
read-only checkout for a controlled local test.

## Supported audio

Formats: `.wav`, `.aif`, `.aiff`, `.flac`, `.m4a`, `.mp3` (subject to the
underlying decoder being available for non-WAV formats). Max size: 150 MB.
Native WAV files are decoded directly; 8/16/24-bit PCM are supported, 32-bit
(int or float) WAV is rejected explicitly rather than risking a silent
misinterpretation. Mono files are analysed as duplicated L=R stereo.
