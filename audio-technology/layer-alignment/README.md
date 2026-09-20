# NITE DSP — R&D Sprint Home (Isolated)

Temporary isolated R&D workspace. Created 2026-08-22 under the Unlimited
Credits Parallel R&D Sprint Controller.

## Ownership status

ALL production repositories are READ-ONLY for this programme:

| Repo | Branch | Reason |
|---|---|---|
| `Nite_DSP/Nite_DSP_01` | `engineering/slo-classification-analysis-v4` | V4 closeout session active (untracked report present, HEAD advanced) |
| `Nite_DSP/Nite_DSP_01-slo-ux-v3` | `ux/slo-v3-premium-product` | HISTORICAL / frozen |
| `Nite_DSP/Nite_DSP_01-web-v3` | `web/nitedsp-world-class-v3` | Active writer (multiple modified files) |
| `Nite_DSP/Nite_DSP_AI_Platform` | `main` | Active writer (`cli.py`, `runtime.py`, tests modified) |
| `Audio_Too` | `analysis/efficiency-and-streaming-core` | Production Thursday sprint active |
| `Nite_DSP/design-system` | `main` | FREE but not required |

This directory is a standalone local git repository (no remote). No production
repository will be mutated by this sprint.

## Structure

- `controller/` — sprint controller state, experiment registry
- `audio_intelligence/` — R&D-A shared audio intelligence core research
- `slo_v5/` — R&D-B SLO V5 intelligence lab
- `kenn_eval/` — R&D-C KENN qualification benchmark
- `product_discovery/` — R&D-D product #2 discovery
- `reconstruction_sampler/` — R&D-E source reconstruction sampler feasibility
- `marketing_agent/` — R&D-F marketing intelligence agent prototype
- `audio_ml/` — R&D-G cross-product audio ML/DSP research
- `shared/` — reusable experiment harness
- `reports/` — one primary report per track + final report
- `benchmarks/` — versioned benchmark definitions and results
- `datasets/` — synthetic dataset manifests and generators
- `experiments/` — experiment scripts and raw results

## Safety rules in force

- No writes to any production repository.
- No owner audio data modification (read-only inspection permitted where licensed).
- No external business writes (email, ads, social, payments).
- No AI attribution anywhere.
- Synthetic fixtures only for ground-truth experiments.
