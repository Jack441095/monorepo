# KENN SUB-SECOND LATENCY & ADVANCED AI EXPANSION — AGENT PROMPT (V2)

> **What this file is:** A production-grade, self-contained prompt that drives an AI coding agent (Antigravity / Claude Code / Codex) to push KENN's local intelligence into **sub-second inference (<800ms p50, <200ms TTFB)** and expand KENN with **advanced multimodal audio telemetry, agentic mix planning, and expanded DAW co-pilot capabilities**.
>
> **How to use it:** Open the workspace root (`~/Nite-DSP`) and instruct the agent: *"Execute `root-docs/KENN_SUBSECOND_LATENCY_AND_AI_EXPANSION_PROMPT_V2.md` in full. Produce every deliverable in §7."* Run in Plan mode first; obtain user approval before modifying files.
>
> **Owner:** NITE DSP · **Created:** 2026-09-18 · **Predecessor:** `KENN_LLM_SPEEDUP_PROMPT_V1.md` (achieved 68–85% latency reduction, 1.55s p50)

---

## 0. Role, Mission, and Target SLOs

You are a **principal audio AI systems architect and performance engineer** specializing in high-throughput on-device inference (Apple Silicon Metal MLX, PyTorch MPS, C++ DSP, and real-time DAW telemetry).

### Mission:
1. **Drive Latency into the Sub-Second Realm**: Cut warm steady-state latency from 1.56s to **< 800ms p50** and stream tokens to the UI with **TTFB < 200ms**.
2. **Transform KENN into an Active Audio Co-Pilot**: Equip KENN with multi-modal audio telemetry ingest (listening to live LUFS, spectral balance, and phase correlation), multi-step agentic mix planning (DAG-based recipe chains), and expanded Tier 2/3 DAW execution.

### Target Performance SLOs:
- **Warm Steady-State p50**: $\le 800\text{ ms}$ (Down from 1.56s baseline)
- **Time to First Token (TTFB)**: $\le 200\text{ ms}$ via native MLX token streaming over SSE / Unix socket
- **Cold Start Latency**: $\le 5.0\text{ s}$ (Pre-warmed daemon with instant background load)
- **Token Cost**: **$0.00** (Strictly zero-cloud token cost; 100% on-device Metal MLX)
- **Grounding Integrity**: **100%** (Zero hallucinated audio parameters or unsupported measurements)

---

## 1. Ground Rules (Non-Negotiable)

- **R1 — Measure Before and After.** Every latency optimization must be benchmarked with a before/after number logged to `benchmarks/`.
- **R2 — Quality is a Hard Gate.** No optimization may break schema validation, cause truncated responses, or hallucinate audio units (`dB`, `Hz`, `ms`, `LUFS`).
- **R3 — Zero API Costs.** All inference must run locally on Apple Silicon Metal or dedicated remote GPU 1. No paid external endpoints.
- **R4 — Unified Tri-Repo Parity.** Any core changes made to `monorepo/products/kenn/` must be synchronized to `Shenrendao/KENN/source/kenn/` and `UX/velvet_thunder/studio/kenn/`.
- **R5 — Keep the Fallback Ladder.** Persistent Unix Socket $\to$ MLX Subprocess $\to$ HF/PEFT $\to$ Ollama must remain functional.

---

## 2. Track 1: Sub-Second Latency Architecture (<800ms & <200ms TTFB)

### 2.1 Native MLX Token Streaming over Unix Domain Socket
- **Problem**: Current persistent server buffers the entire response and sends it as one monolithic JSON blob after completion. Perceived latency equals total generation time (1.2–2.0s).
- **Solution**:
  - Update `kenn_lm_server.py` to stream tokens incrementally over the Unix domain socket as newline-delimited chunks:
    `{"type": "token", "delta": "Set "}\n{"type": "token", "delta": "the attack "}\n...`
  - In `UX/app.js` and Velvet Thunder, connect via Server-Sent Events (SSE) or WebSockets.
  - **Target**: User perceives the answer starting in **< 200ms**, eliminating perceived waiting time.

### 2.2 KV-Cache Prefix Reuse (Pre-Computed Prompt Cache)
- **Problem**: Every generation turn re-tokenizes and re-computes the KV cache for the system prompt and retrieved knowledge context chunks (~400-800 tokens of prefill).
- **Solution**:
  - Implement `mlx_lm.models.cache.make_prompt_cache` in `kenn_lm_server.py`.
  - Maintain a persistent prompt cache for KENN's core system persona and prompt prefix.
  - When consecutive turns share context or system prompts, only compute tokens for the new user query.
  - **Target**: Slashes prefill time by 60–80%, dropping generation time by an additional 300–500ms.

### 2.3 Speculative Decoding with a Micro-Draft Model
- **Concept**: Use an ultralight 0.5B draft model (e.g., `Qwen2.5-0.5B-Instruct-4bit`) to generate draft token sequences at ~90 tok/s, verified in parallel batches by the primary 1.5B model on Metal.
- **Benchmark**: Measure acceptance rate on audio engineering prompts. If acceptance rate $\ge 70\%$, activate speculative decoding in `kenn_lm_server.py`.

### 2.4 Vector Cache Early-Exit (<5ms Instant Answers)
- **Mechanism**: In `kenn/llm/llm_rewrite.py`, calculate cosine similarity against the SQLite answer cache embeddings.
- If similarity $\ge 0.94$ against an existing verified answer, return the cached answer with zero LLM generation passes.

---

## 3. Track 2: Advanced AI Audio Capabilities

### 3.1 Live Audio Telemetry Ingest ("KENN Can Hear the Mix")
- **Architecture**:
  - Expose an ingest endpoint `/api/audio/telemetry` accepting real-time JSON frames from the DAW master or track meters:
    ```json
    {
      "integrated_lufs": -11.2,
      "short_term_lufs": -9.8,
      "true_peak_dbtp": +0.4,
      "spectral_energy": {
        "sub_20_60hz": 0.28,
        "low_mid_200_500hz": 0.35,
        "air_10k_20khz": 0.12
      },
      "phase_correlation": 0.72,
      "crest_factor_db": 8.1
    }
    ```
  - In `kenn_lm.py`, inject telemetry directly into the context window when available:
    `"Current Live Mix Telemetry: Integrated -11.2 LUFS, True Peak +0.4 dBTP (Clipping!), Low-Mid Energy elevated at 320 Hz."`
  - KENN immediately diagnoses the exact sonic problem without the user having to type measurements manually!

### 3.2 Autonomous Chain-of-Thought Mix Planner (Agentic Mix Plan)
- **Problem**: Complex audio tasks ("Clean up my muddy vocal and glue it to the trap beat") require multiple coordinated plugin steps.
- **Solution**:
  - Implement a multi-step DAG planner in `source/kenn/agent/mix_planner.py`.
  - Outputs a structured, ordered execution plan:
    1. *Step 1 (Surgical EQ)*: Attenuate 310 Hz by -2.5 dB on Vocal track (FabFilter Pro-Q / EQ Eight).
    2. *Step 2 (De-Essing)*: Engage dynamic band at 6.2 kHz with -3.0 dB threshold.
    3. *Step 3 (Sidechain Ducking)*: Duck vocal delay throw by -4 dB keyed to dry vocal.
    4. *Step 4 (Verification)*: Audition with Loudness-Matched A/B.

### 3.3 Tier 2/3 DAW Automation Expansion
- Expand KENN's DAW execution engine to control deeper Ableton Live / OSC functions:
  - **Dynamic EQ Sidechain Setup**: Automatically instantiate EQ / Compressor, toggle Sidechain, and map routing to Kick track.
  - **Automated Gain Staging**: Normalize track clip gain to -18 dBFS nominal headroom before hitting plugins.
  - **Mastering Limiter Ceiling Lock**: Automatically clamp True Peak ceiling to -1.0 dBTP on master limiter.

### 3.4 GraphRAG Cross-Topic Synthesis
- **Concept**: Connect the 737+ distilled knowledge notes into a relational graph linking:
  - `Problem` (e.g., "Bass Pumping", "Pre-ringing", "Sibilance")
  - `Tool / Plugin` (e.g., "FabFilter Pro-MB", "Live Drum Buss", "Wwise SoundBank")
  - `Audio Parameter` (e.g., "Attack < 5ms", "Linear Phase Crossover", "Oversampling 4x")
  - `Producer Technique` (e.g., "Dan Worrall Clean Mix Bus", "Virtual Riot Resampling")
- Enables KENN to synthesize combined advice from multiple masters in a single, hyper-targeted response.

---

## 4. Phase 1 — Diagnostics & Baseline Audit

1. **Verify Base State**:
   - Confirm baseline latency metrics from `benchmarks/results_after.txt` (p50: 1.559s, p95: 2.148s).
   - Verify that all 737 notes are loaded in index `v-99e592eaaa77`.
2. **Profile Stream Latency**:
   - Measure network and serialization latency of Unix domain socket streaming vs monolithic response.
   - Benchmark prompt prefill vs generation token timings on Metal MLX.

---

## 5. Phase 2 — Implementation Milestones

- **Milestone A (Sub-Second Streaming)**:
  - Implement socket streaming in `kenn_lm_server.py`.
  - Implement prompt prefix caching using MLX prompt cache.
  - Benchmark p50 latency and TTFB. Log to `benchmarks/results_v2_streaming.txt`.
- **Milestone B (Audio Telemetry Ingest)**:
  - Create `/api/audio/telemetry` endpoint and ingest schema.
  - Wire telemetry injection into prompt generation in `kenn_lm.py`.
  - Test with mock audio telemetry vectors (true peak clipping, excessive 300 Hz mud).
- **Milestone C (Agentic Mix Plan & Tier 2/3 Cards)**:
  - Implement multi-step DAG recipe generator in `source/kenn/agent/mix_planner.py`.
  - Render interactive step-by-step proposal cards in Velvet Thunder web UI (`UX/app.js`).
- **Milestone D (Regression Suite & Parity Sync)**:
  - Run full pytest test suite across `products/kenn/tests/` and `Audio_Too/tests/`.
  - Synchronize all files across the three repository trees.

---

## 6. Deliverables Required

1. **`benchmarks/results_v2_final.txt`**: Paired before/after report detailing TTFB (<200ms) and warm p50 (<800ms).
2. **`source/kenn/llm/kenn_lm_server.py` & `kenn_lm.py`**: Updated streaming and KV-cache implementation.
3. **`source/kenn/telemetry/audio_telemetry.py`**: Live audio meter ingest and context injection module.
4. **`source/kenn/agent/mix_planner.py`**: Multi-step DAG recipe planner.
5. **`walkthrough.md`**: Complete walkthrough documenting speedup metrics, live telemetry verification, and interactive mix plan cards.

