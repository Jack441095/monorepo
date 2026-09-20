# Live R&D Agent Table

| Track | Worker | Scope | Repository | Mode | Status | Dependencies | Output | Next action |
|---|---|---|---|---|---|---|---|---|
| R&D-A | Controller + completed audit worker | Audio capability inventory | Production repos read-only | READ_ONLY / RESEARCH | COMPLETE | None | `reports/RND_AUDIO_INTELLIGENCE_REPORT.md` | Cross-language parity fixtures |
| R&D-B | Completed audit worker | SLO V5 architecture, filename, OOD, BPM | `Nite_DSP_01` read-only | READ_ONLY / RESEARCH | COMPLETE | Licensed multi-vendor data | `reports/RND_SLO_V5_REPORT.md` | Acquire held-out-vendor data |
| R&D-C | Controller | KENN synthetic qualification | Isolated `Nite_DSP_RnD` | EXPERIMENTAL_WRITE | COMPLETE | More golden cases | `kenn_eval/results.json/.csv` | Parameter sweeps and human review |
| R&D-D | Controller | Product #2 market/technical triage | Isolated `Nite_DSP_RnD` | RESEARCH | COMPLETE | Customer interviews | `reports/RND_PRODUCT_DISCOVERY_REPORT.md` | Validate layer-alignment pain |
| R&D-E | Controller | Reconstruction sampler bake-off | Isolated `Nite_DSP_RnD` | EXPERIMENTAL_WRITE | COMPLETE | Listening set, legal assets | `reconstruction_sampler/results.json/.csv` | Multi-sample zone mapping |
| R&D-F | Controller | Typed marketing planner | Isolated `Nite_DSP_RnD` | EXPERIMENTAL_WRITE | Schema/provenance review | `marketing_agent/plan.json` | Add approval/provenance |
| R&D-G | Controller | Cross-product ML/DSP triage | Production repos read-only | READ_ONLY / RESEARCH | COMPLETE | Diverse licensed data | `reports/RND_AUDIO_ML_REPORT.md` | Embedding/OOD bake-off |
| Cross-review | Controller; independent worker unavailable due rate limit | Falsify major conclusions | Isolated `Nite_DSP_RnD` | RESEARCH | COMPLETE WITH LIMITATION | Second reviewer capacity | `controller/cross_review.md` | Re-review when capacity returns |
