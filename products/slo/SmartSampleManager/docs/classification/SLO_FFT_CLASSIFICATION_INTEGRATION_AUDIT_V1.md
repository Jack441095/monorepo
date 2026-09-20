# SLO FFT Classification Integration Audit V1

**Date:** 2026-09-15  
**Status:** evidence sidecar V1 shipped; no production classifier weights changed

## Executive decision

FFT analysis should remain a first-class *evidence and specialist-model*
signal, but generic spectral descriptors should not simply be concatenated onto
the current PANNs/CLAP-style embedding. The existing encoder already captures
most stationary spectral shape. The measured gain from a broad waveform block
is only +0.12 percentage points on the 1,022-row grouped benchmark and +0.23
points on the later 1,493-row breadth benchmark. That is below the promotion
gate and is not enough to justify a production model/schema change.

The useful FFT route is narrower:

1. **Form specialist:** full-file, windowed spectra for loop-vs-one-shot and
   loop-family decisions.
2. **Mechanism specialist:** attack-window spectrum for drum f0/salience and
   low-end onset structure.
3. **Evidence layer:** retain unit-bearing spectral facts (band energy, flux,
   harmonicity, purity, modulation) that can explain or veto a low-confidence
   class without pretending they are universal truth.

## What SLO already computes

The production C++ path is not FFT-free:

- `analyzeAudioProperties()` uses a 2048-point Hann FFT with a 512-sample hop
  for frame-averaged spectral centroid, 85% rolloff, and a spectral-flux onset
  proxy.
- `computeMelSpectrogram()` uses the same 2048/512 protocol before the PANNs
  embedding model. This is the main reason generic centroid/rolloff features
  overlap the embedding.
- `detectKeyFromAudio()` uses a 4096-point FFT and multi-frame chroma to
  choose a conservative root/mode result.
- The offline `physics_v1_1` extractor computes 32 interpretable descriptors,
  including band energy, spectral flux, harmonic structure, pitch glide,
  modulation, and stereo width.

The current 520-D acoustic head receives 512 PANNs dimensions plus eight DSP
dimensions. Dimensions 6 and 7 are complementary encodings of the *same*
rolloff scalar (`1 - r` and `r`), so replacing one requires retraining the head;
it must not be changed ad hoc at inference time.

## Measured evidence

### Broad FFT/waveform concatenation

The frozen grouped benchmark (`results_waveform_feature_eval_v1.json`) reports:

| Arm | Accuracy | Macro F1 | Coverage at 90% precision |
|---|---:|---:|---:|
| incumbent audio | 56.40% | 46.90% | 27.1% |
| waveform only | 36.80% | 29.70% | 0.1% |
| audio + waveform | 56.52% | 47.13% | 27.3% |

The later breadth receipt reports 54.762% for audio and 54.990% for
audio+waveform (+0.228 pp). Both are research evidence, not a reason to alter
the shipped head.

### Production-sidecar ablation

The new sidecar was evaluated on 519 successfully decoded by-ear rows (520
candidates) with
collection-grouped five-fold CV (five seeds), mirroring the native 2048/512
FFT protocol. Duration+sustain reached **92.563%** accuracy; sidecar-only
reached **84.817%** (macro-F1 **47.980%** under the loop/one-shot imbalance),
and the fused probe reached **92.254%**. This is a **-0.309 pp** global result,
so the sidecar is intentionally not a universal loop gate. The full receipt is
`tools/classification_benchmark/receipts/fft_sidecar_benchmark_v1.json`.

A targeted loop-family ablation on the four viable families (92 rows across 23
collections) reached **65.652%** with the existing full-file loop spectrum,
**56.739%** with the sidecar alone, and **61.956%** when fused. The sidecar is
therefore not promoted into that specialist yet; the sample is too small and
the added dimensions are currently redundant/noisy. Receipt:
`tools/classification_benchmark/receipts/fft_loop_family_benchmark_v1.json`.

The complementary drum one-shot ablation (387 successfully decoded rows, 388
candidates, seven mechanism classes,
collection-grouped five-fold CV) reached **66.718%** with the existing attack
features, **48.992%** with the sidecar alone, and **67.183%** when fused. The
small **+0.465 pp** gain is below the +2 pp promotion gate, so FFT remains a
conditional evidence/tie-breaker rather than a production class override.
Receipt: `tools/classification_benchmark/receipts/fft_drum_oneshot_benchmark_v1.json`.

A follow-up temporal specialist combined the cached autocorrelation/recurrence
features with the FFT sidecar on the deduplicated corpus (568 fully finite rows
after two undecodable files were excluded; 106 loops across 128 two-level
collection groups). Under ten-seed collection-held-out CV, duration+sustain
scored **85.651%** accuracy, the periodicity block **86.426%**, and
duration+sustain+periodicity **86.620%**. Adding the FFT dimensions reached
**87.518%** (**+0.898 pp** over the full periodicity arm; **+1.092 pp** over
periodicity alone). This is directionally useful but below the +2 pp promotion
gate, so it remains an evidence/specialist candidate rather than an automatic
loop override. The benchmark loader also now deduplicates six repeated paths
and fails closed on conflicting duplicate labels. Receipt:
`tools/classification_benchmark/receipts/periodicity_fft_loop_benchmark_v2.json`.

The existing multi-window physics cache was tested as a separate block (568
aligned rows after cache intersection, ten seeds). Periodicity alone scored
**86.620%**; periodicity+FFT scored **87.518%**; periodicity+physics reached
**89.560%** (**+2.940 pp**); and the naïve all-features fusion reached
**88.926%** (**+1.408 pp** over periodicity+FFT). Physics therefore clears the
+2 pp research gate by itself, but concatenating every FFT block is not
monotonic and must not be promoted without a specialist-specific review.
Receipt:
`tools/classification_benchmark/receipts/periodicity_fft_physics_benchmark_v4.json`.

The nested selective follow-up calibrates an auto-accept threshold inside each
training fold using a Wilson lower bound, then evaluates only on unseen
collections. The strict 95%-precision target produced **zero** safely accepted
rows for the baseline and fewer than one row per fold on average for the fused
arm, so neither met the target. The nominal 90% target under-delivered at about
**83.27–89.32%** held-out precision across the ten-seed arms, exposing
collection shift rather than hiding it. Fixed
operating points are more useful for triage: at confidence **0.98**, the
periodicity arm accepted **19.056%** of rows at **91.645%** precision, while
periodicity+FFT accepted **25.968%** at **94.192%** (+2.547 pp precision and
+6.912 pp coverage). Repeating the outer split over ten seeds kept the pattern
but still missed a 95% precision requirement, so this supports a high-
confidence review queue, not an always-correct auto-rename gate. Receipt:
`tools/classification_benchmark/receipts/periodicity_fft_loop_selective_benchmark_v3.json`.

The ten-seed selective run with physics confirms the trade-off: at fixed
confidence **0.98**, the all-features arm reached **93.333%** precision at
**34.923%** coverage versus **94.192%** at **25.968%** for periodicity+FFT.
Physics increases review throughput, but reduces accepted precision; it is
therefore a review-prioritization feature, not a new auto-accept gate. Receipt:
`tools/classification_benchmark/receipts/periodicity_fft_physics_selective_benchmark_v2.json`.

Finally, the specialist was tested against the frozen full-taxonomy incumbent
on 1,023 eligible physics-aligned corpus rows across ten grouped seeds. The incumbent
scored **56.589%** accuracy. Binary loop overrides at 0.70/0.80/0.90
probability changed only 0.54%/0.28%/0.03% of rows and reached just
22.036%/35.000%/5.000% override precision, with no meaningful overall gain.
This rejects direct loop overrides at the taxonomy level; the specialist may
only contribute evidence or review priority until a class-conditional family
model is trained and calibrated. Receipt:
`tools/classification_benchmark/receipts/full_taxonomy_loop_specialist_fusion_v1.json`.

A supported-class loop-family model was then evaluated on the same corpus. At
the 0.70 specialist-confidence gate it improved overall accuracy only from
**56.589%** to **56.919%** (+0.330 pp); at 0.80 it reached **57.104%**
(+0.515 pp). Override precision was **72.557%** and **57.800%** respectively,
far below an automatic-action standard. This is a useful specialist probe, but
not a production override. Receipt:
`tools/classification_benchmark/receipts/full_taxonomy_loop_family_specialist_v1.json`.

Adding the full-file loop-spectrum block to the family specialist was tested
on the broader aligned taxonomy (235 supported loop rows across 58
collections). Loop-spectrum alone scored **53.362%**, physics alone **54.042%**,
and the combined block **56.213%** (+2.851 pp over loop-spectrum). This is the
best current feature stack for a loop-family specialist, but the support is too
small for automatic action; it needs a larger, independently reviewed loop
batch and calibrated per-class abstention. Receipt:
`tools/classification_benchmark/receipts/full_taxonomy_loop_family_feature_fusion_v1.json`.

The research model was then applied to the existing 500-row label-free FFT
queue. It resolved periodicity evidence for **499** rows (one unresolved),
marking **85** as high-confidence review and **414** as standard review. The
output contains only `form_evidence`, probability, and routing metadata;
semantic labels remain null and automatic actions are disabled. Receipt:
`tools/classification_benchmark/receipts/periodicity_fft_review_queue_top500_v2.json`.

The queue was expanded to the top **1,000** of 7,027 candidates: **999** have
FFT evidence, **947** have bounded periodicity evidence, **128** are routed to
high-confidence review, and **819** to standard review. Fifty-two long or
undecodable files are explicitly unresolved; the 30-second periodicity guard
prevents quadratic tempogram work from stalling the pipeline. Semantic labels
remain null and automatic actions remain disabled. Receipt:
`tools/classification_benchmark/receipts/periodicity_fft_review_queue_top1000_v3.json`.

The chained physics pass now covers all **947** periodicity-resolved rows,
adding bounded repetition, onset-cadence, decay, and band-energy evidence. The
resolved local path is preserved strictly as provenance so later evidence
layers can chain without guessing by basename; semantic labels and automatic
actions remain disabled. Receipt:
`tools/classification_benchmark/receipts/periodicity_fft_physics_review_queue_top1000_v2.json`.

To turn that evidence into useful supervision without biasing the reviewer, a
candidate-hidden manifest selects **200** of **943** eligible, content-unique
rows. The deterministic sample contains 83 loop-temporal, 70 transient-
temporal, and 47 cross-signal-disagreement cases; candidate classes and feature
values are removed from the reviewer CSV. The first receipt/CSV are retained as
an audit trail:
`tools/classification_benchmark/receipts/fft_physics_label_manifest_200_v1.json`
and `tools/classification_benchmark/receipts/fft_physics_label_manifest_200_v1.csv`.

Before review, an independent v2 batch was regenerated excluding every path
already present in the verified label CSVs. It selects 200 of 925 remaining
eligible rows (84 loop-temporal, 69 transient-temporal, 47 disagreement), with
zero overlap against the known-label files:
`tools/classification_benchmark/receipts/fft_physics_label_manifest_200_v2.json`
and `tools/classification_benchmark/receipts/fft_physics_label_manifest_200_v2.csv`.

The existing crash-safe ear-label tool now consumes this receipt directly with
`--set fft_physics`; it accepts the manifest's content-addressed string ids,
keeps the reviewer blind to evidence and candidate classes, and writes a
separate resumable CSV. Example:

```bash
python3 tools/classification_benchmark/label_tool.py --set fft_physics \
  --manifest tools/classification_benchmark/receipts/fft_physics_label_manifest_200_v2.json \
  --csv tools/classification_benchmark/receipts/fft_physics_labels_reviewed_v2.csv
```

This output is still review data only. It must pass the existing hash- and
collection-aware import/approval workflow before entering any training corpus.
After review, verify the CSV against the exact receipt and current audio bytes
before importing it:

```bash
python3 tools/classification_benchmark/verify_fft_physics_labels.py \
  --manifest tools/classification_benchmark/receipts/fft_physics_label_manifest_200_v2.json \
  --labels tools/classification_benchmark/receipts/fft_physics_labels_reviewed_v2.csv \
  --out tools/classification_benchmark/receipts/fft_physics_labels_verification_v2.json \
  --require-complete
```

The verifier is fail-closed on stale audio, path/id mismatches, duplicate rows,
unknown labels, missing escape-hatch notes, or leaked candidate/evidence
columns. Its receipt remains review-only; it never trains or renames files.

### Targeted specialists

The existing offline experiments show where FFT is genuinely useful when the
task is constrained:

- Full-file spectral loop features separate Drum Loop from Percussion Loop at
  86.8% on the measured loop subset; the two-stage loop fusion improved the
  overall specialist benchmark from 71.8% to 76.1% before the sustained-energy
  gate, and to 77.9% after the crash-leak fix.
- Attack-window f0, salience, and low-band fraction improved the four-class
  drum one-shot detector from 71.5% to 80.1%; adding envelope/onset/MFCC
  features reached 84.2% in that specialist, with confidence-gated precision
  above 97% at the validated threshold.
- A broad 32-feature physics block is excellent for explanations and targeted
  mechanism rules, but adds effectively no held-out accuracy on top of the
  stronger encoder. This is redundancy, not evidence that FFT is useless.

These numbers come from offline, read-only experiments and must not be
interpreted as end-to-end production accuracy. Their value is in selecting the
right *conditional* use of FFT.

## Recommended production design

### Stage A — safe evidence (no head change)

Keep the existing FFT protocol and add a small, versioned evidence sidecar for
the fields that are already useful to product decisions:

- normalized energy in low (<150 Hz), mid (150–2 kHz), and high (>2 kHz)
  bands;
- normalized spectral flux and onset regularity across thirds;
- attack f0/salience for 30–600 Hz;
- harmonic purity/harmonicity and a bounded downward pitch-glide estimate;
- full-file early-to-tail energy contrast.

These values should be persisted with the analysis version, surfaced in the
evidence packet/inspector, and used for explanations or review prioritization.
They should not override a high-confidence neural result by themselves.

### Shipped in sidecar V1

`AudioAnalysisResult` now persists six native-resolution FFT facts alongside the
existing centroid/rolloff/onset fields: low/mid/high magnitude-energy ratios,
gain-normalised spectral-flux mean and standard deviation, and adaptive
spectral-flux peak rate (peaks/second). The cache schema is additive and the
analysis version is 8, so old rows are safely reanalysed. The frozen 520-D head
and 512-D similarity embedding are unchanged. The first consumer is the
conservative `Rhythmic` predicted tag, gated by an existing loop decision,
sustained energy, duration, and a bounded peak-rate range; no FFT-only label
can silently replace a neural or metadata result.

### Label-free review queue consumer

The evidence sidecar is now consumed by
`tools/classification_benchmark/build_fft_evidence_review_queue.py`. It joins
the GPU label-free receipt to the local content inventory by full-file SHA-256,
selects the highest-priority uncertain rows, and computes the native sidecar
only for that bounded queue. The output is explicitly review-only: semantic
labels remain null, source audio is untouched, and the three lanes
(`loop_temporal_evidence`, `transient_temporal_evidence`, and
`bright_spectral_evidence`) are explainable hints rather than classes.

The first run covered the top 500 of 7,027 label-free review candidates. All
500 resolved and decoded locally; 233 carried loop-temporal evidence, 128
transient-temporal evidence, and 73 bright-spectral evidence (lanes may
overlap). Receipt:
`tools/classification_benchmark/receipts/fft_evidence_review_queue_top500_20260914.json`.
This creates a focused, label-free audit surface for the next specialist
experiment without allowing FFT heuristics to become training ground truth.

The integration pass also fixed a numerical edge case in both native and
research extraction: a near-silent preceding frame could make normalized flux
explode. The first valid frame is now excluded from normalized comparisons and
the ratio is bounded at 100, while the historical raw onset proxy is left
untouched. The packet parser and parity receipts now reject malformed or
non-finite evidence instead of passing it downstream.

### Selective drum operating-point check

Because global accuracy is not the only product objective, a second receipt
measured precision after confidence-based abstention on the verified drum
corpus. At the 0.60 confidence threshold, attack features alone reached
94.085% accepted-set precision at 34.005% coverage; attack+FFT reached
94.328% precision at 34.522% coverage. The accepted-set macro-F1 also rose
from 69.565% to 73.311%. At 0.80, precision improved by +0.598 pp while
coverage fell by 0.775 pp; at 0.90, precision was slightly lower. This is
promising for a conservative selective/review policy, but it is below the
required +2.0 pp promotion gate for a production head change. Receipt:
`tools/classification_benchmark/receipts/fft_drum_selective_benchmark_v1.json`.

### Stage B — conditional specialists

Run a specialist only when the form gate says it applies:

- **Loop gate:** duration/onset periodicity/sustained-energy gate, then the
  full-file band model for Drum/Percussion/Hi-Hat/Foley loop families.
- **Drum one-shot gate:** short duration plus transient gate, then attack f0,
  salience, low-band energy, and onset multiplicity for Kick/Snare/Clap/
  Hi-Hat.
- **Low-end mechanism gate:** only when sub-band energy and pitch confidence
  are high; distinguish 808 glide, Sub Bass purity, Reese beating, and Bass Hit
  envelope. Do not run this on broadband or ambient material.

Every specialist needs its own grouped cross-validation receipt, per-class
coverage/precision, and an abstain path. A specialist may replace a class only
when its confidence gate is calibrated on held-out collections; otherwise its
output remains evidence-only.

### Stage C — retrained hybrid head (optional)

If a future benchmark proves an independent FFT feature adds at least **+2.0
pp** across repeated collection-held-out seeds, retrain the 520-D head with a
single canonical feature builder shared by Python and C++. Candidate replacement
for one redundant rolloff dimension is spectral-flux/temporal-contrast, but the
weights, parity tests, cache feature version, and OOD calibration must all be
bumped together. Never swap a feature into the frozen head at inference time.

## Implementation guardrails

- Use the same sample-rate policy, Hann window, FFT size, hop, band edges, and
  normalization in training and C++; add a bit-identical parity test.
- Aggregate robustly (median/trimmed mean or quantiles) rather than letting one
  loud frame define a file-level label.
- Keep FFT extraction off the real-time audio thread; use the existing scan
  worker and cache versioning path.
- Treat short files and near-silence as `unknown`, not zero-valued evidence that
  looks like a real measurement.
- Do not use filename/folder labels as ground truth when evaluating an FFT
  specialist; split by collection/vendor to avoid leakage.
- Preserve `embedding` as the 512-D PANNs vector. Any classifier feature block
  is assembled separately and is never appended to the persisted similarity
  vector.

## Next experiment to run

The binary loop override is now rejected at the taxonomy level. The highest-
value next run is a pre-registered, collection-held-out comparison of a
**class-conditional specialist fusion**:

1. incumbent model only;
2. incumbent + loop-family specialist (trained only on loop classes);
3. incumbent + drum one-shot specialist;
4. both specialists with calibrated abstention and the review-only FFT queue.

First expand the independently reviewed loop-family batch, then report overall
accuracy, macro-F1, per-class precision/coverage, and the exact number of
samples deferred. Promote only if the fused arm clears the +2.0 pp gate without
reducing 95%-precision coverage or increasing false automatic renames.
