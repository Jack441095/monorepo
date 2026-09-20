# KENN Mix Review Adapter

This is the first product-owned boundary for KENN Mix Review. The **default
engine is KENN-owned** (`core/local_engine.py`): a deterministic WAV analyzer
with an optional NumPy accelerator and a Python standard-library fallback. It
has no runtime dependency on any external `Audio_Too` checkout and runs
standalone from this repository alone.

Qualified fault families (see `core/local_engine.py` for thresholds and
`docs/KENN_BETA_GAP_MATRIX.md` for qualification status/evidence): clipping,
headroom, silence/truncation, channel imbalance, phase/polarity & mono
compatibility, DC offset, and an approximate (non-LUFS) loudness estimate.
Masking, tonal-balance, arrangement/dynamics, genre-context, calibrated
BS.1770 loudness, and true-peak analysis are explicitly **not evaluated** --
the engine abstains on them rather than guessing, and every report says so.

Current contract:

- input is an explicit local filesystem path, not an HTTP upload;
- audio bytes are read into memory and are not copied into the product tree;
- the returned `kenn.mix_review.local_receipt.v2` includes a source hash, analysis result, and runtime
  boundary metadata;
- runtime state is redirected to an external temporary/configured directory,
  outside the product checkout;
- no public route, report sharing, database workflow, Ableton action, or
  AutoMix invocation is included;
- analysis never mutates, renders, or exports audio.

The adapter is not yet a qualified public Mix Review product. Its measured
fault families have unit-test coverage against synthetic fixtures
(`tests/test_local_engine.py`) but have not been through human listening
review or a real-mix benchmark corpus -- see `docs/KENN_BETA_GAP_MATRIX.md`.

The adapter is wired through `core.MixReviewBoundary`; the analyzer and
validator remain injected, so the engine can be swapped without changing the
receipt contract.

## Local probe

From the repository root:

```sh
python3 mix-review/adapter.py ./path/to/local-mix.wav
```

## Optional legacy engine (not beta-default)

A previous, external-dependency version of this adapter called a preserved
`Audio_Too` checkout's `audio_analysis.mix_review` implementation. That path
still exists as an explicit, non-default opt-in for controlled parity
comparison only: set `KENN_MIX_REVIEW_ENGINE=audio_too_legacy` and
`KENN_AUDIO_TOO_ROOT` to a real external checkout. It is never reached by the
default beta product path, and importing it without both variables set
raises immediately rather than silently falling back.
