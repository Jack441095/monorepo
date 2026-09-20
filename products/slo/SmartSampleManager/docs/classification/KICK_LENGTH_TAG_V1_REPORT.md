# SLO Kick Length Tag (Short / Long) V1 Report

**Generated for:** Fine-Grained Subcategorization V1, Phase 10.

## Method and honest framing

Unlike the bass timbre tag (Phase 9), this is **not** a discovered natural category. Real kick one-shot durations from this session's own cross-vendor corpus (n=51, excluding clear ground-truth outliers >3s that are almost certainly mislabeled non-kick content) are continuous from 0.07s to 2.09s with no natural cluster boundary — median 0.74s, mean 0.79s.

**Threshold chosen: 0.7s** (just below the median, a round, explainable number) — a stated, practical split over a continuous distribution, not a discovered category. This is presented to users as such; it is not marketed as more precise than it is.

## Implementation

Added directly in `SampleManagerEngine::prepareFile()` (not `AbletonTaxonomy::classify()`, to avoid restructuring that function's several early-return paths for a simple, additive, duration-only check): gated on `subcategory == "Kick"`, appends `"Short"` (< 0.7s) or `"Long"` (>= 0.7s) to `secondaryTags`. No embedding dependency — duration is already computed before this point, so this runs synchronously, not waiting on the async ONNX inference batch (unlike the Bass timbre tag).

## Verification

Real-corpus re-scan (620-file B-006 corpus, 60 ground-truth Kick entries): **22 Short, 35 Long**, matching the expected split at the 0.7s threshold exactly. New regression test `TestKickLength` (real engine, real fixture audio — `test_kick.wav` at 1.0s expects Long, a new synthetic `test_kick_short.wav` at 0.3s expects Short, since no existing fixture was under the threshold) — all checks pass.

## Bonus finding (not a bug): more corpus ground-truth noise

Two files in the "Kick" ground-truth group picked up an `"808"` bass-timbre tag during verification: `LFM2_808 Clean #1 (G).wav` and `LFM2_808 Clean #2 (BASS ONLY) (G).wav` (the second literally has "BASS ONLY" in its filename). Checked their actual predicted subcategory: both are `Bass One-Shot`, not `Kick` — the engine is correct, this session's own B-006 corpus-sampling script mislabeled them as Kick ground truth (same class of issue already documented in `FX_FOLEY_RISER_FORENSIC_AUDIT_V1.md` for FX/Foley). No code changed for this — it's a corpus-labeling note, not a classifier defect.

## Scope limitations

- Threshold not validated against producer perception (no listening test) — it's a statistical median, not a psychoacoustic boundary. If "short vs long" needs to mean something more specific to producers (e.g. "trap-style tight kick" vs "808-style boomy kick"), that's a different, richer distinction than raw duration and would need its own separability study, likely combining duration with decay-time and low-frequency content the way the existing DSP feature set partially supports.
- Applies only to `subcategory == "Kick"` (one-shots) — kick-drum loops (`"Drum Loop"` subcategory) are untouched.
