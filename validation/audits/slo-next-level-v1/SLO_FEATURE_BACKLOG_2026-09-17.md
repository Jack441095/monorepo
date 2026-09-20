# SLO Feature Backlog — 2026-09-17
RICE = (Reach × Impact × Confidence) / Effort. Reach = libraries/mo affected (estimate, stated). Effort = person-weeks.
All reuse paths under `SmartSampleManager/Source/` unless noted.

## Tier 1 — Quick wins (≤1 week)
- F-01 · UNKNOWN review queue + confidence bands · Problem: 72% cross-vendor false-known hidden without triage (B-007) · Capability: filterable UNKNOWN list with evidence chips (ml_ood/FILENAME/FOLDER/DSP), confidence High/Med/Low (`PluginEditor.cpp:1514`, `ClassificationPresentation.h:124`), one-click correct → `CorrectionLog.h` · Reuse: `AcousticClassifier.h:338-343`, `MlOverrideGate.h:90`, `CorrectionLog.h:1-2` · Pays: every beta user · Effort 1wk · RICE: (400×3×0.8)/1 = 960 → scaled 18.0 (normalized) · Metric: % UNKNOWN resolved/wk · Kill: <10% queue usage in 2 wks.
- F-02 · Audio-only vs fused split display · Problem: 96.5% vs 30.2% confusion blocks trust · Capability: per-result tabs/badges showing audio-only label/conf vs fused label/conf + winningEvidence · Reuse: `AbletonTaxonomy.h:33`, `ClassificationPresentation.h`, `LabelFreeEvidencePacket.h` · Effort 1wk · RICE 12.8 · Metric: support tickets about "wrong genre" −50% · Kill: users never toggle tabs.
- F-03 · Rescan-diff + prune messaging · Problem: incremental/prune invisible; unsupported formats silent · Capability: "12 added / 3 changed / 5 missing (prune?)" dialog + skip-count for non-WAV · Reuse: `TestPruneMissing`, `hydratePersistedSamples`, `addPathToQueue` · Effort 1wk · RICE 12.0 · Metric: rescan support questions −40%.
- F-04 · Copy-report / diagnostics export · Problem: beta feedback unstructured · Capability: one-click JSON+log bundle (versions, thresholds, evidence split) · Reuse: `AppLogger.h`, `LabelFreeEvidencePacket.h:344`, benchmark receipt contract · Effort 0.5wk · RICE 11.0.
- F-05 · Sort preview hardening (already CLOSED B-011 — expose) · Capability: surface Copy/Move/Cancel + journal + async (`TestSortPreviewAndUndo/Async`) as default-on first-run coach marks · Effort 0.5wk · RICE 10.0.

## Tier 2 — Differentiation (1–6 weeks)
- F-06 · Filename-fusion v2 + adversarial audit · Ablate FILENAME/FOLDER/TagLib weights; duration-override generalize (`fusion_classify.py:13`); golden-adversarial gate ≥ bar (currently 0%) · Reuse: `MlOverrideGate.h:32,72`, `AbletonTaxonomy.cpp:75-394` · Effort 3wk · RICE 9.6 · Metric: fused ≥65% + adversarial ≥40% cross-vendor · Kill: adversarial stays <20% after reweight.
- F-07 · Taxonomy v2: loop/one-shot repair + multi-label pilot · Duration + periodicity-FFT + tempo-marker evidence; fix Bass/Synth Loop F1 0, Vocal Loop 7.5% · Reuse: `AbletonTaxonomy.*`, `periodicity_fft_*`, `fft_loop_family_*`, `AuditionTempo.h` · Effort 4wk · RICE 8.0 · Metric: loop-family macro-F1 ≥0.70 vendor-held-out · Kill: <0.50 after repair.
- F-08 · Combined-query "find more like this" · Similarity + Bright/Dark + duration + subtype in one query (backend 6/6 PASS, never combined) · Reuse: `AudioSimilarity.h`, `SampleManagerEngine.h:349-351,439`, `test_find_similar_weighted` · Effort 3wk · RICE 7.5 · Metric: task success on 5 producer briefs · Kill: <3/5 prefer vs manual crate-digging.
- F-09 · Auto-tag pack (mono/stereo, rhythmic, BPM/key suffix, folder loops token) · Productize `test_auto_tagging`, `SLO_TEMPO_ESTIMATOR_V5` (review-only), `test_taxonomy` · Effort 2wk · RICE 7.0.
- F-10 · Subtype graduation (bass timbre, hi-hat, kick-length) · Promote leakage-free 92.9%/92.3% paths out of metadata-gating (B-014) · Reuse: `BassTimbreClassifier.h`, `HiHatTypeClassifier.h`, `test_kick_length` · Effort 2wk · RICE 6.5 · Kill: leakage-free drops >5pp on new vendor.
- F-11 · Ableton Browser export (XMP sidecar + taxonomy map) · `AbletonXmpWriter.h`, `AbletonTaxonomy.h:6-11`, `SLO_ABLETON_WORKFLOW_VALIDATION_V1.md` · Effort 3wk · RICE 6.0 (gated on B-004).

## Tier 3 — Platform (1–2 quarters)
- F-12 · Model registry + OTA with versioned invalidation · `embedding_model_version`/`classification_model_version` (`SampleManagerEngine.h:140,195`; migration `:1363,1371`) already schema-ready; add feed + staged rollout + rollback · Effort 6wk · RICE 6.0.
- F-13 · Correction flywheel → training set · `CorrectionLog.h` append-only + `user_tag_overrides` table → export → retrain (`train_gpu_classifier.py` gens) → OOF gate · Effort 6wk · RICE 5.3 · Kill: correction rate <2% of tags.
- F-14 · CLAP hybrid promotion track (GATED) · C++ ONNX path + int8/quant + 744MB→budget + OOD recal + license + vendor-held-out + latency/RSS · Reuse: `export_clap_audio_onnx.py`, `compare_encoders.py`, bakeoffs · Effort 8wk+ · RICE 6.0 IF gates pass else 1.0 · Kill: any gate fails twice.
- F-15 · Format expansion (AIFF/FLAC, then MP3) · JUCE decode for scan + 32k parity + TagLib carry + perf receipt · Effort 4wk · RICE 4.8 · Kill: scan throughput halves.
- F-16 · Shared classifier service for KENN/AudioGen · Extract OnnxEmbedder+Head as local IPC lib; KENN mix-review fault families as consumer · Effort 8wk · RICE 4.0.

## Tier 4 — New products (≥60% exists)
- F-17 · SLO Batch Cloud (opt-in, local-first preserved) · Missing 40%: queue/billing/scale; cheapest proof: concierge batch for 5 sample-pack vendors using current CLI + `run_benchmark.py` harness · RICE 3.0.
- F-18 · Sample-pack QA tool for vendors · Missing 40%: vendor dashboard; proof: run B-006 harness as paid audit on 3 vendor packs · RICE 2.8.
- Explicit non-bets: generative audio, Windows port — until B-001..B-005 + taxonomy gates closed.
