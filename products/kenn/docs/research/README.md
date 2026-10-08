# KENN Research Directory

This directory contains research reports, architecture investigations, benchmark plans, and empirical receipts for the KENN project in `monorepo/products/kenn/`.

Per [KENN_PLAN.md](../../KENN_PLAN.md), these reports document evidence at their recorded commits and environments; they provide architectural guidance and analytical backing for tasks in the master plan.

---

## 1. Local GLM Intelligence & Efficiency Suite (5 October 2026)

This research series analyzes how to make KENN function as an intelligent Ableton Live General Language Model (GLM) executing locally and efficiently on Apple Silicon M3 (16 GB unified RAM) alongside Ableton Live 12.4.6:

- **[KENN_GLM_RESEARCH_AND_UPGRADE_SPEC_2026-10-05.md](KENN_GLM_RESEARCH_AND_UPGRADE_SPEC_2026-10-05.md)**  
  *Master Technical Specification.* Complete synthesis of M3 memory bandwidth physics (100 GB/s -> 16 tok/s ceiling on 8B Q4), root causes of the 15 s / 70% delivery gate failures, the Note-First hybrid architecture (0 ms note serving + 40-token LLM session adaptation), dynamic allowed number injection, and the 3-stage execution roadmap.
- **[KENN_EFFICIENT_OPEN_MODELS_AND_DEEPSEEK_ARCH_2026-10-05.md](KENN_EFFICIENT_OPEN_MODELS_AND_DEEPSEEK_ARCH_2026-10-05.md)**  
  *Open-Weights & DeepSeek Architecture Analysis.* Deep dive into Jev / Kev non-autoregressive decision models (System One classification in 10–15 ms), DeepSeek's architectural engineering (Multi-Head Latent Attention KV compression by 85–90%, DeepSeek-MoE fine-grained sparse routing unlocking 50+ tok/s, Multi-Token Prediction), and on-device model evaluations (Ministral 3B, Qwen2.5-Coder-3B, SmolLM2 1.7B, Phi-3.5-mini).
- **[KENN_4B_AND_THINKING_EVALUATION_2026-10-05.md](KENN_4B_AND_THINKING_EVALUATION_2026-10-05.md)**  
  *4B Model & Reasoning Mode Evaluation.* Empirical analysis proving that switching to a 4B model (Q4_K_M ~2.5 GB) doubles decode speed to ~32 tok/s and frees 2.5 GB RAM, but turning thinking mode ON breaks interactive delivery (causing 0-content completions under token caps, generating uncited numbers that trip measurement gates, and inflating total latency past 17 s).
- **[KENN_EXTERNAL_AND_CLAUDE_RESEARCH_SYNTHESIS_2026-10-05.md](KENN_EXTERNAL_AND_CLAUDE_RESEARCH_SYNTHESIS_2026-10-05.md)**  
  *Synthesis of Claude 3 Oct Pass & External Ecosystem.* Reconciles Claude's 103-agent deep research with subsequent probe evidence and external Ableton AI projects (Producer Pal, AbletonMCP, Loophole).
- **[KENN_RETRIEVAL_2026-10-05.md](KENN_RETRIEVAL_2026-10-05.md)**  
  *Retrieval & Grounding Research.* Traces the 4,642 chunk index, proves the necessity of rebuilding on GPU 0/1 to drop 735 "Related questions" BM25 echo chunks, and validates the number-aware regex detector (`_MEASUREMENT_RE`).
- **[KENN_MODEL_SELECTION_DEEPSEEK_2026-10-05.md](KENN_MODEL_SELECTION_DEEPSEEK_2026-10-05.md)**  
  *Initial Model Selection & Telemetry.* Analysis of DeepSeek-R1-0528-Qwen3-8B vs stock Qwen3 8B, Modelfile `num_batch 2048` tuning, and prefix caching.

---

## 2. Product Architecture & Ecosystem Foundations (September – October 2026)

- **[KENN_PRODUCT_AND_OPEN_SOURCE_RESEARCH_2026-10-02.md](KENN_PRODUCT_AND_OPEN_SOURCE_RESEARCH_2026-10-02.md)**  
  Comprehensive market survey of 12 commercial and open-source audio tools (LIA, FL Studio Gopher, iZotope Neutron/Ozone, Metric AB, smart:EQ/comp) and open-source foundations (ONNX, MLX, Ollama, Basic Pitch).
- **[KENN_GLM_GAP_MATRIX_2026-09-21.md](KENN_GLM_GAP_MATRIX_2026-09-21.md)**  
  Initial 25-point Ableton GLM capability matrix auditing natural-language intent, entity extraction, session world state, readback verification, and audio understanding.
- **[KENN_FULL_PRODUCT_TRUTH_REPORT.md](KENN_FULL_PRODUCT_TRUTH_REPORT.md)**  
  Hard reality audit distinguishing verified implementations from unverified aspirational plans across the repository.
- **[GLM_AUDIO_INTELLIGENCE_EVALUATION.md](GLM_AUDIO_INTELLIGENCE_EVALUATION.md)**  
  Evaluation rubric for audio engineering advice correctness, citation grounding, and ambiguity abstention.
- **[KENN_BOTTLENECK_MAP.md](KENN_BOTTLENECK_MAP.md)** & **[KENN_GAP_AND_DEFECT_REGISTER.md](KENN_GAP_AND_DEFECT_REGISTER.md)**  
  Systemic inventory of latency bottlenecks, routing ambiguities, and unjournaled write paths.

---

## 3. C++ / Native DSP Migration & Acceleration (September 2026)

- **[CPP_DSP_TARGET_ARCHITECTURE.md](CPP_DSP_TARGET_ARCHITECTURE.md)** & **[CPP_DSP_MIGRATION_ROADMAP.md](CPP_DSP_MIGRATION_ROADMAP.md)**  
  Design and phasing for opt-in C++/nanobind audio analysis kernels (`KENN_DSP_NATIVE=1`).
- **[CPP_DSP_RELEASE_QUALIFICATION.md](CPP_DSP_PHASE4_RELEASE_QUALIFICATION.md)**  
  Qualification criteria for native spectral, loudness, masking, and decoder routines.
