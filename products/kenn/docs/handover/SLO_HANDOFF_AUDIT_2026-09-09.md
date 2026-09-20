# SLO → KENN handoff audit — 2026-09-09

## Decision

**Status: blocked pending a portable export and KENN-bound evaluation evidence.**

No SLO checkpoint, training code, sample audio, or training data was copied
into KENN, and no classifier was enabled. The audit read the sibling SLO
checkout only.

## Fresh read-only repository check — 2026-09-09

The sibling checkout currently has a newer local checkpoint at
`products/slo/SmartSampleManager/tools/classification_benchmark/slo_classifier_v4_hybrid.pt`
(SHA-256 `c5e745f534cb611d959ad7618b11102bdaaa1af2d0bcd139ab62c000853154ea`,
modified 2026-09-09). It is a PyTorch `.pt` file, not a portable KENN export.
No file matching KENN's required `kenn.slo_artifact_manifest.v1` handoff was
found anywhere under the SLO product checkout.

The SLO `main` checkout is also materially dirty, with modified classifier
source/evaluation files and untracked release/audit material. Its own
`SLO_PRODUCT_TRUTH_MANIFEST_V1.json` says `product_stage` is an internal
read-only pilot candidate and `release_status` is `blocked`; it does not bind
the new v4 checkpoint to a label map, preprocessing, calibration/OOD data, or
an evaluation receipt. The repository-held `slo_classification_metrics_v1.json`
is explicitly marked historical/not fresh, and its recorded golden-set
audio-only accuracy is 5.9%, so neither that file nor the new checkpoint's
existence can support the 85% KENN intake threshold.

The calibration and general metrics files currently present in the SLO
benchmark directory have older modification dates; the OOD summary was
refreshed later, but neither set has an immutable identity tying it to v4.
KENN therefore keeps the classifier disabled and does not copy any of these
artifacts, training data, or SLO-generated folders into this repository.

## Latest artifact snapshot — 2026-09-09

The checkpoint and OOD summary were rechecked after the initial audit. The
checkpoint is now confirmed as SHA-256
`c5e745f534cb611d959ad7618b11102bdaaa1af2d0bcd139ab62c000853154ea`, but the
newer file still has no accompanying KENN manifest or identity-bound
evaluation receipt. The OOD summary is newer than the general benchmark
metrics and remains a release blocker:

- closed-set/fusion metrics: **96.54% accuracy**, **96.45% macro F1** on 1,272
  clean samples; the fusion-adversarial result is **88.29%**;
- OOD gate: **168/168 false-known (100%)** in the sampled OOD sources;
  false-unknown is **17.74%** on the reported known-class sample;
- embedding bakeoff: logistic regression reaches **90.62% pack F1** and
  **86.85% vendor F1**, but OOD mean confidence is **0.851** with **14**
  high-confidence OOD errors;
- performance receipt: cold scan mean **25.0 s**, cached scan mean **0.92 s**,
  and peak RSS **2.44 GB**.

These figures are useful diagnostic evidence, but they are not interchangeable
with KENN's required audio-only, project-disjoint, calibrated, OOD-safe
receipt. In particular, the 100% false-known OOD result means KENN must not
use this checkpoint to make confident specialist labels outside its measured
domain.

## What the SLO work currently shows

- The corrected PANNs-plus-DSP arm is about **73.6% OOF** on the current
  keyword-agreement benchmark.
- The CLAP-music-plus-DSP bakeoff arm is about **82.5% OOF**, a meaningful
  experimental improvement on that same benchmark.
- These are not real no-evidence user-library accuracy figures. The SLO report
  says the population KENN would most need to classify still requires hand
  labels.
- The strongest current checkpoint is still a PyTorch training checkpoint, not
  a self-contained KENN export. The CLAP encoder artifacts do not by themselves
  provide a KENN-compatible classifier handoff.
- Existing OOD evidence is not strong enough for KENN's advisory intake gate;
  SLO's own readiness material keeps Unknown/OOD visible and disallows
  unqualified automatic tagging.

## Why KENN cannot accept it yet

KENN requires one immutable manifest binding all of these files and hashes:

1. model in ONNX, TorchScript, or safetensors format;
2. exact label map;
3. exact preprocessing and feature configuration;
4. calibration and OOD thresholds;
5. a `kenn.slo_adapter_evaluation.v1` receipt with separate audio-only and
   metadata-assisted results, per-class metrics, calibration, OOD rejection,
   project buckets, and latency.

The intake gate additionally requires, at minimum, 100 evaluated cases across
three project buckets, audio-only accuracy and macro F1 of at least 0.85,
audio-only ECE no higher than 0.15, at least five Unknown and five
out-of-distribution cases with 0.90 correct rejection, and latency p95 no
higher than 1 second. None of these requirements may be inferred from a
training accuracy, a keyword-agreement score, or a file that merely exists.

## KENN work completed in this audit

- The existing disabled-by-default adapter and intake validator were reviewed.
- Manifest inspection now requires the explicit
  `kenn.audio_classification.v1` contract before reporting a structurally
  valid manifest.
- The eventual integration remains advisory-only: it can inform context,
  ranking, and explanations, but cannot directly mutate Live, rename files, or
  delete anything.

## Next handoff steps

When SLO training and evaluation are explicitly complete:

1. export the selected model in a supported portable format;
2. freeze the label map, preprocessing, calibration/OOD data, and model/export
   versions;
3. generate the immutable manifest and KENN-bound evaluation receipt, including
   the new checkpoint's hash and identity-bound OOD/calibration outputs;
4. run `scripts/inspect_slo_artifact.py` and
   `scripts/verify_slo_artifact_intake.py` from this checkout;
5. run the fixed KENN retrieval/context/latency evaluation;
6. enable only the advisory registration path if every gate passes.

Until then, KENN continues improving its Live capabilities, evidence-backed
mix guidance, session continuity, and supervised evaluation without depending
on the SLO training repository.

## Follow-up read-only audit — 2026-09-10

The newer `slo_classifier_v4_hybrid.pt` checkpoint was inspected again without
copying or modifying the SLO checkout. Its embedded metadata identifies a
`ClassifierV4_ArcFace_Hybrid` model over 16 labels, but reports approximately
**68.83% cross-validation out-of-fold accuracy** and **61.79% full-fit
accuracy**. The accompanying `results_real_corpus_v2_*` and OOD JSON files are
per-sample diagnostic exports rather than a KENN-bound evaluation receipt: the
ML-evaluated fields are unset in those rows, and the files contain raw source
paths and embeddings that KENN must not ingest. The OOD summary still reports
**168/168 false-known** samples. This confirms that the checkpoint is not
eligible for KENN intake and that the classifier remains disabled.
