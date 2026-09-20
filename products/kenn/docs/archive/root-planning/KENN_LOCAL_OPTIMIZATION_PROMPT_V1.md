# KENN: Local Mac Optimization & High-Efficiency Intelligence Engine (Prompt V1)

**Target Platform**: macOS (Apple Silicon arm64: M1/M2/M3/M4)

**Host Architecture**: Ableton Live 12 + KENN VST3/AU Plug-in + Local Python Companion (Port 8090)

**Hardware Profile**: Apple Unified Memory Architecture (UMA), Apple Metal Performance Shaders (MPS), Apple MLX Core

**Performance Budget**:
- **Time-to-First-Token (TTFT)**: $\le 120\text{ ms}$
- **Inference Throughput**: $85 - 120\text{ tokens/sec}$
- **RAM / VRAM Footprint**: $\le 1.8\text{ GB}$ (leaving $\ge 85\%$ unified memory for Ableton Live audio buffers, Kontakt, Serum, and Omnisphere)
- **Zero-Audio Privacy Guarantee**: Strictly $0\text{ dB}$ audio data sent to cloud; $100\%$ local inference

---

## 1. Executive Strategy: Why Local Apple Silicon MLX Outperforms Cloud & Ollama

Running real-time AI inside a Digital Audio Workstation (DAW) like Ableton Live requires a fundamentally different architecture than standard web chatbots:

```
                   CONVENTIONAL SETUP vs. KENN MLX NATIVE ARCHITECTURE

  ❌ Conventional / Cloud / Raw Ollama:
  [Max for Live] ──(HTTP)──> [Ollama / Remote API] ──(Wait for Full String 2-15s)──> [UI Update]
                                  │
                          (Heavy CPU/VRAM swap,
                           causes Ableton audio dropouts)

  ✅ KENN Apple Silicon Native MLX Pipeline:
  [Live / Max / UI] ◄──WebSocket Stream (TTFT < 100ms)──┐
                                                        │
  [KENN Companion 8090] ──> [Pre-Warmed MLX Metal Cache] ──> [Zero-Copy Unified Memory (1.4 GB)]
                                                        │
                            [4-bit Qwen2.5-1.5B / 3B] ──┘ (Zero Network Latency, 100 tok/s)
```

### The 4 Bottlenecks Broken:
1. **Zero-Copy Memory Bus**: Apple Silicon shares physical LPDDR5/LPDDR5X RAM between CPU and GPU with up to $150 - 800\text{ GB/s}$ bandwidth. Using `mlx_lm` with 4-bit quantization allows direct Metal GPU execution without copying memory buffers across PCIe buses.
2. **Elimination of Ollama Process Overhead**: Ollama runs an external server daemon with Go/C++ IPC abstraction layers and dynamic thread contention. Direct native in-process or companion Python `mlx_lm` eliminates $200 - 500\text{ ms}$ of process management overhead.
3. **KV Cache Prefix Pinning**: KENN's `CONVERSATIONAL_SYSTEM_PROMPT` (the Senior Studio Engineer persona) is static ($\sim 500\text{ tokens}$). Re-evaluating this on every turn wastes $150\text{ ms}$. With KV Cache persistence, the system prompt is evaluated **once** and reused across all subsequent turns.
4. **Fast-Path Semantic Routing (<1ms)**: Replacing LLM route classification with zero-inference heuristics and local ONNX embedding similarity avoids calling an LLM just to decide between conversational chat and Live actions.

---

## 2. The 5-Plane Optimization Matrix

| Plane | Optimization Lever | Current Baseline | Optimized Target | Impact |
| :--- | :--- | :--- | :--- | :--- |
| **1. Model Engine** | `mlx-community/Qwen2.5-1.5B-Instruct-4bit` | Ollama fallback (17–60s) | Apple Metal MLX native | **10x–50x speedup** |
| **2. Context Caching** | Static System Prompt KV Cache | Evaluated per turn | Pre-compiled KV Cache in RAM | **TTFT drops to <100ms** |
| **3. Intent Routing** | Vector / Heuristic Fast-Path | LLM Route call ($\sim 400\text{ ms}$) | ONNX / Regex Router ($\le 1.2\text{ ms}$) | **Saves 400ms per turn** |
| **4. Retrieval (RAG)**| Memory-Mapped Vector Index (`mmap`) | File read on query | In-Memory Cosine dot-product | **Search latency $\le 2\text{ ms}$** |
| **5. Frontend UX** | Streaming Token Generator (SSE/WS) | Wait for complete block | Real-time token streaming | **Instant perception (<120ms)** |

---

## 3. Immediate Configuration (Drop-in `.env`)

Add the following environment variables to your KENN `.env` file to immediately lock the engine into high-speed local mode:

```bash
# ==============================================================================
# KENN APPLE SILICON ULTRA-FAST LOCAL INFERENCE CONFIGURATION
# ==============================================================================
# Force MLX engine as primary provider
KENN_LLM_ENABLED=1
KENN_USE_MLX=1
KENN_LLM_PROVIDER=mlx

# Optimal balance between audio engineering IQ and 100 tok/s speed
# Model choices:
# 1) mlx-community/Qwen2.5-1.5B-Instruct-4bit (Default: 1.1 GB RAM, ~110 tok/s, ultra-fast)
# 2) mlx-community/Qwen2.5-3B-Instruct-4bit   (Deep reasoning: 2.1 GB RAM, ~75 tok/s)
KENN_MLX_MODEL=mlx-community/Qwen2.5-1.5B-Instruct-4bit

# Generation tuning for studio latency
KENN_LLM_MAX_TOKENS=384
KENN_LLM_TEMPERATURE=0.2

# Pre-warm MLX weights on companion startup (0 = lazy, 1 = instant warm)
KENN_MLX_PREWARM=1

# Memory limits to protect Ableton Live audio engine buffers
KENN_MLX_MAX_MEMORY_MB=2048
```

---

## 4. Architectural Enhancements to Apply

### A. KV Cache Persistence in `mlx_inference_engine.py`
Cache the prompt evaluation for `CONVERSATIONAL_SYSTEM_PROMPT`:
```python
# In MLXInferenceEngine:
from mlx_lm.models.cache import make_prompt_cache

def precompute_system_cache(self, system_prompt: str):
    """Pre-compute and pin the KV cache for the system prompt."""
    if not self._loaded:
        self.load_model()
    tokens = self._tokenizer.encode(f"<|im_start|>system\n{system_prompt}<|im_end|>\n")
    self._system_cache = make_prompt_cache(self._model)
    # Forward pass over system prompt to fill the KV cache once
    # Reused across all conversational turns for near-zero TTFT
```

### B. Pre-Warming Thread in `server.py`
When KENN Companion launches, spin a background daemon thread to load weights before the user even opens Ableton:
```python
def prewarm_local_models():
    """Warm MLX Metal GPU weights and ONNX embeddings in background."""
    try:
        from kenn.llm.mlx_inference_engine import MLXInferenceEngine
        if MLXInferenceEngine.is_available():
            engine = MLXInferenceEngine.get_instance()
            engine.load_model()
            # Perform a 1-token dummy prompt to initialize Metal shaders
            engine.generate("hi", max_tokens=1)
            print("[✓] KENN MLX Apple Silicon Engine pre-warmed and ready.")
    except Exception as e:
        print(f"[!] Pre-warming skipped: {e}")
```

### C. Fast-Path Router Bypass
Ensure `chat_routing.py` executes rule-based and ONNX embedding checks before ever considering an LLM call for routing. Queries containing terms like *"hi"*, *"help"*, *"who are you"*, *"how do I EQ"*, *"what is sidechain"* immediately resolve to `studio_dialogue` in $<0.5\text{ ms}$.

---

## 5. Master Prompt: Copy & Paste for Coding Agent

Copy the prompt block below and paste it into Antigravity or any agent to execute the full local speed optimization:

```text
================================================================================
KENN LOCAL MAC SPEED & EFFICIENCY OPTIMIZATION SPRINT
================================================================================

Role: Senior Apple Silicon Systems Engineer & High-Performance Audio ML Architect
Repository: <WORKSPACE_ROOT>/Nite-DSP-Operations/Shenrendao/KENN
Platform: macOS arm64 (Apple Silicon M-Series), Ableton Live 12

OBJECTIVE:
Execute an end-to-end performance and latency optimization pass on KENN to achieve

ultra-low-latency on-device intelligence (TTFT <= 120ms, >= 90 tokens/sec, <= 1.8 GB RAM)
using native Apple Silicon Metal MLX acceleration, avoiding any Ableton audio dropouts.

TASKS TO EXECUTE:

1. MLX KV-CACHE & PRE-WARMING IMPLEMENTATION:
   - Enhance `apps/backend/src/kenn/llm/mlx_inference_engine.py`:
     a. Implement system prompt KV cache persistence (`make_prompt_cache`) so that

        KENN's conversational system prompt is not re-evaluated on every user query.
     b. Add an asynchronous or background pre-warming method `prewarm()` that loads weights
        and executes a warm-up token pass over Metal to compile all MPS compute shaders.
   - Update `apps/backend/src/kenn/server.py` to trigger `prewarm()` on companion boot when

     `KENN_USE_MLX=1` or on macOS arm64.

2. FAST-PATH ROUTING (<1ms DISPATCH):
   - Review `apps/backend/src/kenn/core/chat_routing.py`:
     a. Guarantee that conversational studio queries (general audio theory, EQ, compression,

        dialogue, greetings) route directly to `studio_dialogue` via fast regex/keyword

        and ONNX cosine heuristics without making any external or blocking LLM route call.
     b. Ensure total routing overhead is under 2.0ms.

3. STREAMING TOKEN UX INTEGRATION:
   - Verify that `apps/backend/src/kenn/llm/mlx_inference_engine.py` `stream_generate` is directly

     hooked up to `llm_rewrite.py` `enhance_stream`.
   - Ensure the companion server HTTP/WebSocket endpoints support Server-Sent Events (SSE)

     or chunked streaming so that the Ableton UI displays tokens in real-time as they

     are generated.

4. MEMORY & AUDIO ENGINE PROTECTION:
   - Constrain MLX memory allocation using `mlx.core.metal.set_cache_limit()` to prevent

     memory pressure or page swapping while Ableton Live is running large sample libraries.
   - Set thread priority to background/cooperative so CoreAudio real-time threads

     (HAL / AudioUnit thread priority 96) are never starved by LLM token generation.

5. VERIFICATION & BENCHMARKING:
   - Run `pytest apps/backend/src/kenn/tests/test_mlx_inference.py` and ensure all tests pass green.
   - Run a benchmark script measuring:
     1. Cold start load time (s)
     2. Time-to-First-Token (TTFT in ms)
     3. Generation throughput (tokens/sec)
     4. Peak resident memory footprint (MB)
   - Ensure all 73/73 regression tests in KENN continue to pass 100% green.

Produce a structured report showing the measured latency before and after optimization.
================================================================================
```

