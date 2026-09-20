# NITE DSP — Unlimited Credits R&D Sprint Final Report

## Executive Result

The sprint reduced uncertainty without mutating production. The highest-confidence technical finding is that SLO V5 must begin with a leakage-controlled, held-out-vendor dataset. The highest-value architectural finding is a limited shared audio measurement contract, not a broad platform. The recommended Product #2 is intelligent layer alignment; the sampler remains technically interesting but its first prototype did not beat the baseline on quality proxies.

## Sprint Duration

2026-08-22 execution window.

## Compute / Agent Utilisation

Controller plus two attempted parallel specialist workers. One specialist completed the SLO audit; the second launch was blocked by the provider rate limit. The controller completed the remaining isolated experiments and synthesis. Peak parallel workers: 2 attempted, 1 productive.

## Repository Ownership / Safety

The ownership audit found active or valuable work in every production repository. All were treated as READ_ONLY. A local no-remote git repository was created at `Nite_DSP_RnD/`. No production checkout, owner data, cache, installed plugin, credential, or external system was modified.

## Tracks Executed

R&D-A through R&D-G: 7/7 completed at research/report level. Two formal audio benchmarks and one marketing contract validation were run.

## Experiments Run

1. `KENN_MIX_EVAL_0.1` — PASS.
2. `SAMPLER_RECON_EVAL_0.1` — FAIL for the stated quality hypothesis; duration-only benefit preserved as a finding.
3. `MARKETING_CONTRACT_0.1` — PASS.

Machine-readable registry: `controller/experiment_registry.json`.

## Benchmarks Created

- `kenn_eval/results.json` and `kenn_eval/results.csv`
- `reconstruction_sampler/results.json` and `reconstruction_sampler/results.csv`

## Negative Results

The phase-vocoder sampler prototype restored duration but worsened mean pitch error from 18.1 Hz to 32.3 Hz and did not materially improve the centroid-drift proxy. Current BPM evidence is also negative for promotion: 18.7% ±2 BPM accuracy and 42.6 BPM MAE on real loops in the frozen SLO research baseline.

## R&D-A — Audio Intelligence Core

**SHARED CORE: LIMITED.** Share a versioned `AudioAnalysisSnapshot` contract for sample-rate/channel metadata, level, spectral bands, and stereo metrics. Keep SLO taxonomy/classifier/OOD and KENN diagnosis/recommendation policies product-owned. Production promotion: not yet; parity and audio-thread allocation tests are required.

## R&D-B — SLO V5

**V5 direction:** held-out-vendor generalisation, then weighted filename evidence and calibrated abstention, then OOD bake-off. Baseline is known accuracy 76.4%, macro-F1 0.6898, OOD AUROC 0.911, and OOD false-known 41.6% full / 47.2% holdout on a 100% KSHMR corpus. BPM remains experimental. Production classifier modified: NO.

## R&D-C — KENN

`KENN_MIX_EVAL_0.1`, 5 cases. On four injected issues: detection 100%, evidence 100%, diagnosis 100%, severity MAE 0.0, recommendation safety 100%. Healthy false-positive rate 0% on one healthy case. Biggest weakness is benchmark breadth and real-mix generalisation, not the fixture harness.

## R&D-D — Product Discovery

15 products evaluated. Top 5: intelligent layer alignment, mix translation assistant, source reconstruction sampler, stereo/phase intelligence, resonance intelligence. Top 3: intelligent layer alignment, source reconstruction sampler, mix translation assistant. **Recommended Product #2: intelligent layer alignment.** Confidence 67/100. Most technically interesting: sampler. Most commercially attractive: alignment wedge.

## R&D-E — Reconstruction Sampler

**FEASIBILITY: PROMISING WITH LIMITATIONS.** Best approach is a hybrid offline representation plus multi-sample source-zone intelligence. Current prototype quality gain versus resampling: none demonstrated; duration was preserved but pitch error worsened. CPU/real-time architecture is plausible only with offline analysis and precomputed playback data. Biggest risk is artifact and perceptual-quality mismatch.

## R&D-F — Marketing Agent

**MARKETING AGENT: PROTOTYPE READY.** Typed Campaign, Audience, Insight, Experiment, and evidence-kind concepts are implemented. Proposed Thursday contract: `marketing.launch.plan`, `marketing.campaign.status`, `marketing.content.plan`, `marketing.market.research`, `marketing.experiments.list`. External writes: NONE.

## R&D-G — Audio ML / DSP

High potential: embeddings for retrieval/OOD, confidence calibration/OOD, lightweight pitch/transient representations. Watch: ONNX runtime inference, source separation, timbre similarity learning. Low priority: neural bandwidth extension and audio-text embeddings until workflow, data, licensing, and resource constraints are concrete. Best shared opportunity: an evaluation harness, not immediate model integration.

## Cross-Product Findings

- Retrieval, OOD, and future sampler mapping could share embedding evaluation infrastructure, but no single model has yet earned cross-product promotion.
- Measurement primitives are reusable; interpretation and intervention are not.
- Evidence quality dominates attractive prototypes: single-vendor SLO metrics and synthetic KENN results must not be generalized.

## Shared Technology Opportunities

1. Versioned, cross-language audio measurement fixtures and contracts.
2. Leakage-controlled dataset manifest tooling.
3. Embedding/retrieval/OOD evaluation harness with environment capture.
4. Evidence-grounded recommendation schema for KENN and Marketing Agent outputs.

## Product Council

**Recommended next product:** intelligent layer alignment.

**Alternative:** source reconstruction sampler, beginning with multi-sample mapping.

**Do not build now:** generic audio restoration suite, production acoustic BPM promotion, and a broad shared intelligence platform.

## Technology Council

Promote research infrastructure and parity fixtures. Keep SLO classifier/taxonomy, KENN decisions, and Thursday orchestration product-specific. Do not integrate R&D code into live products in this phase.

## Top Technical Discoveries

1. SLO’s largest unresolved risk is external validity, not another classifier architecture.
2. A duration-preserving sampler prototype can regress pitch/timbre proxies.
3. KENN qualification must score detection, evidence, diagnosis, safety, and abstention separately.

## Top Commercial Discoveries

1. Sample discovery is already a core DAW expectation; differentiation must be workflow-specific.
2. Alignment attacks repeated manual work with a bounded technical promise.
3. Restoration has proven demand but severe competition and high scope.

## What We Should NOT Build

- A giant shared audio platform before semantic parity is proven.
- A universal one-sample timbre-preserving sampler based on the current prototype.
- Production BPM classification based on current real-loop accuracy.
- Live marketing automation or external publishing in R&D.

## What Should Enter Engineering

Only planning and test design at this point: held-out-vendor SLO data acquisition, the narrow audio-analysis parity contract, expanded KENN golden cases, and customer discovery for layer alignment. No production implementation was promoted.

## What Should Stay R&D

Sampler reconstruction, model bake-offs, neural bandwidth extension, audio-text embeddings, and all unvalidated OOD alternatives.

## Recommended Product #2

Intelligent layer alignment, starting offline with transient timing, polarity/phase, and spectral-overlap evidence; validate against manual edits before real-time development.

## Recommended SLO V5 Direction

Acquire legally usable multi-vendor data, split by vendor/pack/naming convention, and benchmark calibrated abstention before changing the frozen production classifier.

## Recommended KENN Direction

Expand the versioned golden-case benchmark with parameter sweeps, near misses, mixed issues, healthy mixes, and human-reviewed acceptable interpretations.

## Recommended Marketing Agent Direction

Add schema validation, provenance, expiry, approval state, and five synthetic launch evaluations. Keep every capability read-only.

## Highest-Leverage Shared Technology

A versioned audio measurement and embedding evaluation harness with deterministic fixtures and machine-readable results.

## R&D Backlog

See `controller/RND_BACKLOG.md`. Priority items are held-out-vendor data, cross-language feature parity, KENN golden-case expansion, and layer-alignment customer discovery.

## Risks

Data licensing and label quality; vendor/naming leakage; synthetic-to-real transfer; CPU/latency budgets; subjective listening disagreement; provider capacity limits; and premature production integration.

## Repository / Production Mutation Check

Production repositories modified: NONE. SLO production modified: NO. Thursday production modified: NO. KENN production modified: NO. Website modified: NO. Installed plugins modified: NO. Owner data modified: NO. External business writes: NONE.

## Commits / Pushes

One local initialization commit in the isolated no-remote R&D repository. No production commits, pushes, branches, merges, or history rewrites.

## Recommended Next Sprint

Run a licensed held-out-vendor SLO benchmark and an expanded KENN golden-case suite in parallel with 10–15 producer interviews focused on layer-alignment workarounds.

---

## Required Final Status Block

NITE DSP R&D SPRINT: **PASS WITH LIMITATIONS**

R&D TRACKS: **7 / 7**

EXPERIMENTS: **3**

BENCHMARKS CREATED: **2 formal audio benchmarks**

PARALLEL WORKERS PEAK: **2 attempted / 1 productive**

PRODUCTION REPOSITORIES MODIFIED: **NONE**

SLO PRODUCTION MODIFIED: **NO**

THURSDAY PRODUCTION MODIFIED: **NO**

KENN PRODUCTION MODIFIED: **NO**

WEBSITE MODIFIED: **NO**

INSTALLED PLUGINS MODIFIED: **NO**

OWNER DATA MODIFIED: **NO**

EXTERNAL BUSINESS WRITES: **NONE**

AI ATTRIBUTION IN COMMITS: **NONE**

AUDIO INTELLIGENCE CORE: **LIMITED shared measurement contract; not promoted**

SLO V5: **held-out-vendor dataset and calibrated abstention first**

KENN QUALIFICATION: **synthetic benchmark PASS; broaden before production claims**

PRODUCT #2: **intelligent layer alignment**

RECONSTRUCTION SAMPLER: **promising with limitations; prototype quality hypothesis failed**

MARKETING AGENT: **prototype ready; research-only**

AUDIO ML: **embeddings/OOD and lightweight representations high potential**

HIGHEST-CONFIDENCE DISCOVERY: **SLO’s 100% single-vendor corpus blocks claims of multi-vendor generalisation**

BIGGEST NEGATIVE RESULT: **phase-vocoder sampler worsened pitch error and did not improve centroid drift**

MOST VALUABLE SHARED TECHNOLOGY: **versioned audio measurement/evaluation harness**

RECOMMENDED PRODUCT #2: **intelligent layer alignment**

TOP 5 ENGINEERING PROMOTIONS:
1. Held-out-vendor SLO dataset and benchmark manifest
2. Cross-language audio measurement parity fixtures
3. Expanded KENN golden-case evaluator
4. Layer-alignment discovery and manual-edit benchmark
5. Marketing Agent schema/provenance/approval layer

TOP 3 CONTINUED R&D ITEMS:
1. Multi-sample sampler mapping and reconstruction
2. Embedding/OOD bake-off on diverse licensed data
3. Hierarchical filename evidence and abstention

TOP 3 THINGS TO DROP/PARK:
1. Production acoustic BPM promotion
2. Universal restoration-suite strategy
3. Neural bandwidth extension until a concrete workflow exists

NEXT STEP: **Acquire a legally usable held-out-vendor SLO evaluation set and lock its manifest before changing any production intelligence.**
