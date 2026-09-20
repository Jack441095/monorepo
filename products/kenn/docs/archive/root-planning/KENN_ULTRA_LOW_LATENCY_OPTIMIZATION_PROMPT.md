# KENN SPRINT: ULTRA-LOW-LATENCY LLM & CHAT ENGINE OPTIMIZATION PASS
================================================================================
Role: Principal AI Systems Engineer, Apple Silicon Metal Optimization Specialist & Real-Time Audio Software Architect
Repository: `<WORKSPACE_ROOT>/Nite-DSP-Operations/Shenrendao/KENN`
Platform: macOS (Apple Silicon arm64 M1/M2/M3/M4), Ableton Live 12 Suite, JUCE 8 VST3/AU, Python 3.13, Apple MLX

OBJECTIVE:
Execute an aggressive, end-to-end latency elimination pass across the entire KENN chat,

LLM inference, retrieval, and DAW communication pipelines. Reduce Time-To-First-Token (TTFT)

from ~2-4s down to <100ms, achieve >100 tokens/sec sustained generation, and guarantee sub-millisecond

(<1ms) fast-path handling for all studio intents, greetings, and live state inspections.

TARGET LATENCY BUDGETS:
+------------------------------------+--------------------+--------------------+
| Operation                          | Baseline / Legacy  | Optimized Target   |
+------------------------------------+--------------------+--------------------+
| 1. Casual Greetings & Studio Slang | ~16,200 ms         | < 1.0 ms (RAM Fast)|
| 2. Instant DAW Inspection (Tracks) | 750 - 1,500 ms     | < 2.0 ms (Cached)  |
| 3. Time-To-First-Token (TTFT)      | 1,800 - 3,500 ms   | < 80 ms (Metal GPU)|
| 4. Generation Throughput           | 25 - 40 tok/sec    | 90 - 130 tok/sec   |
| 5. Knowledge RAG Retrieval         | 250 - 800 ms       | < 5.0 ms (Acceler) |
| 6. In-DAW VST3 WebView Round-Trip  | 100 - 300 ms       | < 5.0 ms (Local IPC|
+------------------------------------+--------------------+--------------------+

================================================================================
TASKS TO EXECUTE:

--------------------------------------------------------------------------------
TASK 1: IMPLEMENT MLX STATIC SYSTEM PROMPT KV CACHE PREFIX PINNING
Files: `apps/backend/src/kenn/llm/mlx_inference_engine.py`, `apps/backend/src/kenn/llm/llm_rewrite.py`

Problem:
KENN's Senior Studio Engineer system prompt and studio identity is ~800 tokens. Currently,

every conversational turn re-evaluates and pre-fills these 800 tokens from scratch on the

Metal GPU, wasting 250-500ms of prefill computation per turn.

Action:
1. In `MLXInferenceEngine`:
   - Pre-compute and pin the static system prompt KV cache in Apple Silicon Unified Memory during engine initialization (`prewarm()`).
   - For all subsequent incoming user queries, fork the pinned KV cache and only compute prefill for the new query tokens (`delta_tokens = prompt[prefix_len:]`).
   - Implement `make_prompt_cache` or use MLX's native KV cache prefix reuse (`KVCache`).
2. Implement strict stop token sequences (`["\nUser:", "User:", "Human:", "Ableton>", "###", "\n\n\n"]`) to immediately halt generation when the thought is complete, eliminating lingering token budget waste.
3. Clamp maximum new tokens intelligently:
   - Studio quick answers: `max_tokens=128`
   - Detailed mixing/routing explanations: `max_tokens=384`
   - Action confirmations: `max_tokens=64`

--------------------------------------------------------------------------------
TASK 2: UNIVERSAL TOKEN STREAMING (SSE) ACROSS SERVER, WEBVIEW & CLI
Files: `apps/backend/src/kenn/server.py`, `apps/backend/src/kenn/core/chat_cli.py`, `UX/index.html`, `UX/velvet_thunder/`

Problem:
Waiting for the complete LLM response string before returning JSON causes 2-4 seconds of

perceived silence in the DAW UI.

Action:
1. Ensure the `/api/ask` endpoint streams tokens via Server-Sent Events (SSE) as the primary transport.
2. In `UX/index.html` (and the embedded JUCE WebBrowserComponent):
   - Update the chat frontend to consume `EventSource` / `fetch` readable streams.
   - Stream incoming tokens directly into the chat bubble using `requestAnimationFrame` DOM batching.
   - Render markdown formatting incrementally without UI flicker.
3. In `apps/backend/src/kenn/core/chat_cli.py`:
   - Add streaming output in the CLI loop (`sys.stdout.write(token); sys.stdout.flush()`) for instantaneous feedback.

--------------------------------------------------------------------------------
TASK 3: ASYNCHRONOUS PUSH-BASED DAW STATE ENGINE (ZERO-WAIT LOM READS)
Files: `apps/backend/src/kenn/ableton_osc_bridge.py`, `apps/backend/src/kenn/core/session_world_model.py`, `integrations/ableton-remote-script/KENN_Bridge/KENN_Bridge.py`

Problem:
Querying track names, mute/solo states, or device parameters via synchronous OSC blocks

the chat engine for 100-750ms waiting for UDP round-trips and timeouts.

Action:
1. In `KENN_Bridge.py` (Remote Script):
   - Add listeners on track list changes, selected track changes, playback state, tempo, and volume/pan changes.
   - Emit state deltas proactively over UDP port 11001 when Live state mutates.
2. In `ableton_osc_bridge.py` & `session_world_model.py`:
   - Maintain a synchronized, in-memory `LiveSessionWorldModel` cache updated asynchronously by background UDP listener packets.
3. In `live_action_service.py` & `chat_answer.py`:
   - All chat inquiries regarding DAW state ("what tracks are muted?", "what's the tempo?", "what devices are on track 2?") must read from the zero-latency in-memory `SessionWorldModel` in <0.2ms with zero blocking network calls to Live.

--------------------------------------------------------------------------------
TASK 4: ACCELERATE VECTOR RETRIEVAL (RAG) WITH APPLE ACCELERATE / BLAS
Files: `apps/backend/src/kenn/core/chat_retrieval.py`, `apps/backend/src/kenn/retrieval/index_store.py`

Problem:
Linear scans or unoptimized CPU numpy dot-products over 3,400+ knowledge chunks take 50-200ms.

Action:
1. Pre-load all document embeddings into a contiguous C-aligned float32 matrix in memory during server startup (`warm_index()`).
2. Use Apple Silicon Accelerate framework (via `scipy.linalg.blas` or optimized `np.dot` with Apple Accelerate BLAS) for vector cosine similarity:
   - Compute full cosine search across 3,415 chunks in <1.5ms.
3. Implement a 2-Tier Fast Filter:
   - Tier 0: Direct Keyword / Title Hash Lookup (<0.05ms) for exact production terms ("compression", "sidechain", "nyquist", "reverb", "limiter").
   - Tier 1: Vector BLAS Search (<1.5ms) only when keyword lookup requires broader context.
4. Pre-filter chunk candidates before formatting prompts.

--------------------------------------------------------------------------------
TASK 5: ULTRA-FAST HEURISTIC & INTENT SHORT-CIRCUIT ROUTER
Files: `apps/backend/src/kenn/core/chat_routing.py`, `apps/backend/src/kenn/core/chat_answer.py`

Problem:
Any query that doesn't actually need an LLM or vector search must never touch PyTorch, ONNX, or MLX.

Action:
1. Build a high-performance regex & trie-based short-circuit router that evaluates in <0.1ms:
   - Instant Greetings: `"hello"`, `"hi"`, `"hey"`, `"yo"`, `"good morning"` -> Instant studio response.
   - Single-Word Confirmations: `"yes"`, `"y"`, `"no"`, `"n"`, `"proceed"`, `"cancel"` -> Instant action proposal trigger.
   - Direct Transport / Mix Commands: `"play"`, `"stop"`, `"undo"`, `"mute track 1"`, `"solo drums"` -> Instant typed proposal.
   - Status Inquiries: `"status"`, `"are you connected"`, `"what model is loaded"` -> Instant telemetry dump.
2. Place this short-circuit router at the absolute top of the request lifecycle, completely bypassing the semantic cache, vector embeddings, and LLM engines.

--------------------------------------------------------------------------------
TASK 6: CONNECTION POOLING & HTTP/IPC MICRO-OPTIMIZATION
Files: `apps/backend/src/kenn/server.py`, `plugins/kenn-vst3-au/Source/PluginProcessor.cpp`

Action:
1. Enable `keep-alive` HTTP connection pooling and disable Nagle's algorithm (`TCP_NODELAY`) on all local sockets between the VST3/AU plug-in, CLI, and Python companion (port 8090).
2. Eliminate any synchronous disk logging or SQLite writes from the request hot-path (offload telemetry and feedback logs to a background `queue.Queue` worker thread).
3. Ensure zero-copy memory transfers between the JUCE audio thread and webview IPC.

================================================================================
VERIFICATION & BENCHMARK SUITE:

1. Interactive CLI Latency Benchmark:
   Run: `PYTHONPATH=source python3 scripts/benchmark_chat_cli_full.py`
   Validate:
   - Bare greetings ("hello", "hey"): < 2 ms
   - Direct DAW commands ("stop transport", "mute bass"): < 5 ms
   - Knowledge RAG query ("how do I sidechain in Live 12?"): TTFT < 100 ms
   - Sustained token generation speed: > 90 tokens/sec on Apple Silicon M-Series.

2. Web Chat & SSE Verification:
   Curl test the streaming endpoint:
   `curl -N -X POST http://127.0.0.1:8090/api/ask -H "Content-Type: application/json" -d '{"question": "explain NY compression", "stream": true}'`
   Verify first chunk arrives in < 100 ms and subsequent tokens stream smoothly.

3. Ableton Live 12 OSC Bridge Readback Verification:
   With Ableton Live 12 running and KENN Bridge connected:
   Verify track and device status queries respond in < 2 ms from the in-memory world model.

4. Run Full Regression Test Suite:
   Run: `pytest apps/backend/src/kenn/tests/ -v`
   Ensure all 40/40 Ableton capabilities, safety guardrails, and grounding tests pass 100%.
================================================================================

