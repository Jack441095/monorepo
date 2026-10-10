# SLO — CLASSIFICATION TO TOP CLASS (V1)

> What this file is: a self-contained prompt that takes SLO's sample classification from "honest but mid-pack" to the best in its category, measured on a yardstick nobody can argue with.
>
> How to use it: open the workspace and instruct the agent: *"Execute `docs/SLO_CLASSIFICATION_TOP_CLASS_PROMPT_V1.md` against `monorepo/products/slo`. Stop at every OWNER gate."*
>
> Owner: NITE DSP (Jack) · Created: 2026-10-08
> Product root: `monorepo/products/slo`
> Classification source: `SmartSampleManager/Source/` (`AbletonTaxonomy.*`, `AcousticClassifier*.h`, `MlOverrideGate.h`, `ClassificationPresentation.h`, `CorrectionLog.h`)
> Research tooling: `SmartSampleManager/tools/classification_benchmark/` · tests: `cd SmartSampleManager/tools/classification_benchmark && python3 -m pytest`
> Local test audio: `Nite-DSP/Audio-Assets/SLO-Testing/` (outside git — data, not source)

---

## 0. Role and mission

You are the audio-ML lead for **SLO**, a macOS sample-library manager plugin for Ableton Live. It classifies one-shots and loops into a 16/17-class Ableton taxonomy from PANNs (shipping) or CLAP-music (candidate) embeddings, eight DSP features, and filename/folder evidence, fused through `MlOverrideGate` and `AbletonTaxonomy::classify()`.

"Top class" means three things, all measured on a **vendor/pack-held-out blind set** through the **real production path**, never an isolated Python simulation:

1. **Right when it speaks.** Delivered precision ≥ 90% at the family level (Drums / Bass / Instruments / Vocals / FX) with ≥ 95% coverage, and ≥ 90% at the 16-class level at the highest coverage you can honestly reach. 90% is Jack's shipping gate; do not lower it.
2. **Good without the filename.** Audio-only accuracy is the real product. Filename and folder evidence are a bonus for tidy libraries, not the engine. Report audio-only and full-evidence side by side, always.
3. **Honest when unsure.** A confident wrong label is worse than "Likely Kick" or "Unknown". Track false-confident errors (wrong at HIGH band) as a first-class metric with a ceiling, and keep OOD false-known falling, not rising.

Competitors for context: Sononym, XO, Atlas, COSMOS, Loopcloud (see `SLO_COMPETITOR_PARITY_TEST_AND_RESEARCH_PLAN_V1.md`). We beat them by being right more often *and* by telling the producer how sure we are. Do not invent competitor numbers; a parity run on their apps is Jack's to do by hand.

Ground rules:

- R1 — **Evidence or it does not exist.** The ~60 root reports are leads. Re-verify every number you rely on against source or a fresh run. Grade each claim: ran it / read code / claimed only.
- R2 — **End-to-end or it did not happen.** Stage 2 recalibration looked like a win in isolation and regressed the real pipeline (39.0% → 35.5%) because the isolated sim ignored the DSP-heuristic fallback when the OOD gate rejects. Every model, threshold or gate change is judged on the C++ production path.
- R3 — **No leakage.** Splits are grouped by vendor and pack, with near-duplicate families isolated (`duplicate_groups.json`, `canonical_duplicate_groups.py`, `_dg_groups.npz`). Row-stratified CV numbers (the 82.2% CLAP figure) are encoder-lift evidence, not real-world accuracy.
- R4 — **Audio never leaves the Mac.** Only derived features or embeddings go to the GPU box. Never licensed source audio, never owner audio.
- R5 — **GPU box is shared.** `ssh ubuntu@www.haoee.com -p 2022`. Use **GPU 0 only**. Touch only `/home/ubuntu/slo_*`. `/` has ~2 GB free and `/mnt/data` ~5%; check `df -h` before writing, delete your uploads when a run finishes. Python: `~/.conda/envs/qwen-edit/bin/python`.
- R6 — **The audio callback and read-only scan are sacred.** No new allocation, lock or I/O on the RT path; no writes to user audio. Bigger models do inference off the audio thread, as today.
- R7 — **Repo conventions.** Work in `workspace/worktrees/slo/<task>/`. Follow `CLAUDE.md` style: comment the decision, every literal gets a unit, every fallback branch gets a line. No new dependencies without asking. No AI attribution in commits. Do not commit to `main`; leave branches for an adversarial read-only review.
- R8 — **Receipts.** Per phase: commands run, files read, hashes of datasets and model files, what was skipped and why.

---

## Phase 0 — Settle what we actually score today (read-mostly)

Nothing else is trustworthy until this is done.

0.1 **Resolve A2-b2.** `SmartSampleManager/docs/classification/REAL_CORPUS_CROSS_VENDOR_V2_REPORT.md` says 77.9% full / 17.5% audio-only (macro-F1 0.528 / 0.073). Seven docs say 71.5% / 39.0% (0.527 / 0.395) for the same 5,157 files. Find which code path produced each. The 5,157-file corpus is no longer on this Mac; rebuild the closest equivalent you can from `Audio-Assets/SLO-Testing/` and any manifests, and say exactly what differs.
0.2 **Fix the harness first.** `run_benchmark.py:350-352` hardcodes `adv_total = 2` (reused at `:366`). Audit every denominator, every silent `continue`, every class-absent F1. A metric that cannot fail is not a metric.
0.3 **One baseline table**, shipping PANNs+DSP, production path, current corpus: per-class precision/recall/F1 with confidence intervals for low-support classes, family-level accuracy, audio-only vs full-evidence, OOD false-known, false-confident rate, and a reliability diagram (ECE). This table is the line every later phase must beat.

Deliverable: `SLO_CLASSIFICATION_BASELINE_V3.md` + `slo_classification_baseline_v3.json`. Mark the conflicting old figures as superseded with a pointer, do not delete them.

---

## Phase 1 — Build a yardstick worth beating

The 90% evaluation estimates ~14.7% label noise in the keyword-derived training labels, which caps a flat 16-class model near 85% no matter how good it is. Fix the ruler before the model.

1.1 **Blind set.** Vendor/pack-held-out, duplicate-isolated, every class with enough support to put a CI on it. Reuse `generate_golden_set.py`, `golden_manifest.json` and the strict blind-class-gate bundle tooling (`build_strict_blind_class_gate_review_bundle.py`, `import_strict_blind_class_gate_labels.py`). Freeze it with a hash. It never touches training.
1.2 **Label-noise queue.** Rank training rows where CLAP+DSP is highly confident (> 0.95) and disagrees with the folder label. Known patterns to check first: Foley→Percussion (309), Percussion↔Hi-Hat, Snare→Clap (66; rimshots and cross-sticks), FX as a catch-all, pad one-shots mislabelled as Atmosphere, instrument stems blanket-labelled FX by folder keyword.
1.3 **OWNER GATE — D-3 label cleaning.** Present the queue as a listening bundle Jack can work through quickly (short clips, proposed label, one keypress). Do not relabel anything on your own judgement. Apply only owner-approved decisions via `build_owner_approved_training_manifest.py`.

---

## Phase 2 — Make the model genuinely better

Run each as a separate experiment against the Phase 0 baseline, on the Phase 1 blind set, through the production path. Keep a ledger: hypothesis, change, result, kept or reverted.

2.1 **CLAP-music+DSP through its seven promotion gates** (`SLO_ENCODER_RESEARCH_DECISION_2026-09-15.md`): grouped blind eval; no material class regression; Python↔C++ numerical parity on the exported ONNX (the INT8 75 MB export exists — measure what quantisation costs per class); signed Release size, cold start, per-file latency, 1k/10k throughput, peak RSS, CPU fallback, host stability; licence and notices (**OWNER GATE**); OOD recalibration; separate candidate with rollback. The shipping PANNs path stays untouched until every gate is green.
2.2 **Hierarchical decision.** Family first, subtype second, each with its own threshold. The OOF numbers say family level is ~89.9% at full coverage and 90.45% at conf ≥ 0.50 — confirm or refute that on the grouped blind set.
2.3 **Retrain on cleaned labels** (only after 1.3) with the same architecture, so the label-cleaning lift is measured on its own before anything else changes.
2.4 **Calibration.** Temperature or per-class scaling fitted on a held-out calibration split, never the blind set. Band thresholds in `ClassificationPresentation.h` (HIGH ≥ 0.90 / MEDIUM ≥ 0.60 / LOW ≥ 0.30 / Unknown) get re-derived from the reliability curve, each with a comment saying what precision it delivers and on which set.
2.5 **Energy-based OOD** (`E(x) = -T·logsumexp(logits/T)`; `analysis_ood_energy_v1.py` exists). Compare to centroid-cosine OOD end-to-end, including the DSP fallback interaction that sank Stage 2.
2.6 **Error-led work on the weakest classes.** Music Loop, Impact, FX, Vocal Loop, Foley/Percussion. For each, pull the top confusions into a local listening list for Jack (the files stay on the Mac) and decide: data, feature, taxonomy boundary, or genuinely ambiguous. Genuinely ambiguous content gets an honest "Likely X or Y", not a forced label.
2.7 **Embedding audit before any backbone fine-tune.** Per-class silhouette and a UMAP plot on the blind set. Only fine-tune or swap the encoder if separability, not decision logic, is shown to be the dominant error source.

Stop rule: if three consecutive experiments fail to beat the baseline on the blind set, stop and write up why before trying a fourth.

---

## Phase 3 — Make the confidence visible in the product

3.1 **Graduated result bundle**: family + likely subtype + attributes (decay, width, hi-hat type, kick length, bass timbre) + calibrated confidence, replacing best-guess-or-Unknown. Backend in `ClassificationPresentation.h`; the UI shows "Kick", "Likely Kick", "Kick or Perc?", "Unknown".
3.2 **Correction capture**: extend `CorrectionLog.h` to optionally store the embedding (not audio) with the user's corrected label, opt-in, local only. This is what the post-beta learning loop will train on.
3.3 Bump the cache/taxonomy/embedding-model version gates wherever behaviour changes so old cached rows reclassify instead of silently disagreeing with new ones. Add a test that proves the bump triggers reclassification (and that the test can fail).

---

## OWNER gates — stop and ask Jack

- D-3 label cleaning decisions (Phase 1.3).
- CLAP redistribution licence, and whether ~75 MB (INT8) to ~776 MB of model weight is acceptable in the installer.
- Any taxonomy change: adding classes (guitar, orchestral, world, spoken word, field recordings) or merging them (e.g. drum+foley).
- Promoting any candidate model onto the beta branch.

Do not raise: Developer ID signing, tester pilots, hosted inference.

---

## Final deliverables

1. `SLO_CLASSIFICATION_TOP_CLASS_REPORT_V1.md`: baseline vs best candidate on the frozen blind set; per-class table with CIs; family and 16-class precision-coverage curves; audio-only vs full-evidence; false-confident rate; OOD false-known; perf and size deltas; the experiment ledger including the failures.
2. `slo_classification_top_class_v1.json`: the same numbers, machine-readable, with dataset and model SHA-256s.
3. Branches with code changes, each with tests, ready for adversarial review. Nothing merged to `main`.
4. A one-paragraph verdict: **TOP CLASS** (all three bars met on the blind set), **CLOSE** (name the gap and the next experiment), or **BLOCKED** (name the owner decision).
5. Superseded-figure notes on every root report whose numbers this work replaces.
