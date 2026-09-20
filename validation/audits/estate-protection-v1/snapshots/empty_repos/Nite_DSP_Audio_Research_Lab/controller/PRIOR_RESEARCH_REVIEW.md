# Prior Research Review — Authority Documents & Classification

Reviewed 2026-08-22 by the Audio Engineering Research Lab programme before any new experiment.
Sources read read-only; no production repository modified.

## Sources inspected

| Source | Location |
|---|---|
| Canonical workspace map | `Nite_DSP/CANONICAL_WORKSPACE.md` |
| Ownership policy | `Nite_DSP/OWNERSHIP.md` |
| Prior R&D sprint final report | `Nite_DSP_RnD/reports/NITE_DSP_RND_SPRINT_FINAL_REPORT.md` |
| Product discovery report | `Nite_DSP_RnD/reports/RND_PRODUCT_DISCOVERY_REPORT.md` |
| Reconstruction sampler report | `Nite_DSP_RnD/reports/RND_RECONSTRUCTION_SAMPLER_REPORT.md` |
| Audio intelligence core report | `Nite_DSP_RnD/reports/RND_AUDIO_INTELLIGENCE_REPORT.md` |
| Audio ML report | `Nite_DSP_RnD/reports/RND_AUDIO_ML_REPORT.md` |
| SLO V5 report | `Nite_DSP_RnD/reports/RND_SLO_V5_REPORT.md` |
| KENN intelligence report | `Nite_DSP_RnD/reports/RND_KENN_INTELLIGENCE_REPORT.md` |
| Experiment registry | `Nite_DSP_RnD/controller/experiment_registry.json` |
| R&D backlog | `Nite_DSP_RnD/controller/RND_BACKLOG.md` |
| AutoMix improvement report | `AUTOMIX_WORLD_CLASS_IMPROVEMENT_REPORT_2026.md` |

## Classification

| Prior item | Status | Evidence | Disposition this programme |
|---|---|---|---|
| KENN synthetic fixture harness (`KENN_MIX_EVAL_0.1`) | NEEDS REPLICATION | PASS but n=5 cases, single healthy control | Not repeated blindly; healthy-control and near-miss discipline adopted lab-wide (>=25% controls) |
| Phase-vocoder single-sample reconstruction | FAILED (CONFIRMED negative) | Pitch error regressed 18.1 -> 32.3 Hz; no centroid benefit | Do NOT repeat single-source PV. Track J tests the *multi-source* hypothesis instead |
| Acoustic BPM promotion on real loops | FAILED | 18.7% ±2 BPM acc, 42.6 BPM MAE | DROPPED — excluded from inventory experiments |
| SLO classifier metrics (76.4% acc, macro-F1 0.69) | PARTIAL | 100% single-vendor KSHMR corpus; external validity unproven | Out of scope (no licensed multi-vendor data available); SLO candidates labelled only |
| Layer alignment recommended as Product #2 | UNPROVEN | Ranked 82/100 by judgment, zero experiments executed | PRIMARY falsification target (Track A) — attempt to kill it |
| Multi-sample mapping idea (sampler) | UNPROVEN | Named promising but never tested | Track J executes first controlled comparison |
| Shared `AudioAnalysisSnapshot` contract | UNPROVEN | Design only | Partially exercised via shared measurement library built here |
| Embedding bake-off | UNPROVEN | No models compared locally; licensing unknown | Deferred unless local legal models exist; not faked |
| AutoMix transient shaper / resonance substrate | PARTIAL | Unit tests pass in Audio_Too (read-only); no ground-truth benchmarks | Informs Tracks D/F design; production code untouched |
| Marketing agent contract | OUT OF SCOPE | Non-audio | Excluded from this audio programme |

## Rule applied

No experiment below repeats work classified CONFIRMED (either direction) without a materially different hypothesis.
