# KENN CHAT & ABLETON LIVE CLI VERIFICATION SPRINT PROMPT (V1.0)

```markdown
================================================================================
KENN SPRINT: CHAT PIPELINE DEEP-DIVE, CLI TESTING & ABLETON LIVE VERIFICATION
================================================================================

Role: Principal AI Systems Engineer & High-Performance Audio Software Architect
Repository: <WORKSPACE_ROOT>/Nite-DSP-Operations/Shenrendao/KENN
Platform: macOS arm64 (Apple Silicon M-Series), Ableton Live 12 Suite, JUCE 8, Python 3.13

OBJECTIVE:
Execute an end-to-end inspection, CLI benchmark, and verification of KENN's complete

chat pipeline, evaluating on-device response latency, Apple Silicon Metal MLX

acceleration, Ableton Live 12 OSC bridge communication, and anti-hallucination

safety guardrails.

--------------------------------------------------------------------------------
ARCHITECTURE OVERVIEW: HOW KENN'S CHAT WORKS END-TO-END
--------------------------------------------------------------------------------

1. REQUEST INGESTION & HEURISTIC ROUTING (< 1 ms):
   - Entry point: `answer_payload()` in `apps/backend/src/kenn/core/chat_answer.py` or

     `ask_once()` / `interactive()` in `apps/backend/src/kenn/core/chat_cli.py`.
   - `route_query()` in `chat_routing.py` matches intent against fast regex rules

     in 40 µs – 3 ms, classifying queries into:
     • `ableton_controller` (Live 12 LOM actions and queries)
     • `production` / `mixing_doctor` (audio engineering & mix Q&A)
     • `stem_separator` (Demucs/HTDemucs audio stem separation)
     • `ltas_matcher` (Long-Term Average Spectrum frequency matching)
     • `audio_generator` (Text-to-audio/drum loop synthesis)
     • `conversation` (Studio dialogue and general banter)

2. MULTI-AGENT ORCHESTRATION & DISPATCH:
   - `get_orchestrator().dispatch()` in `apps/backend/src/kenn/orchestrator.py` dispatches

     specialist tasks to sub-agents.
   - For Ableton queries:
     • Read Operations ("show session", "what tracks"): Queries AbletonOSC via UDP

       port 11000 and renders visual ASCII fader bars and mute/solo status.
     • Write Operations ("mute track 1", "set tempo to 124"): Routes to

       `handle_command()` in `apps/backend/src/kenn/core/live_command.py`.

3. SAFETY GUARDRAILS & GATED EXECUTION:
   - Hardware Safety Policy: Enforces gain adjustments <= ±3.0 dB, master limiter

     ceiling <= -0.3 dBFS, and master fader strictly locked.
   - Snapshot Gating: Live write commands require a fresh Live state snapshot.

     If Live is offline, commands fail-safe with explicit diagnostic guidance.
   - Confirmation Tokens: High-impact actions generate HMAC cryptographic tokens

     with instant undo support.

4. HYBRID RETRIEVAL & ZERO-HALLUCINATION GROUNDING:
   - Searches 3,415 curated chunks of Ableton Live manuals, mixing guides,

     and DSP principles in `apps/backend/src/kenn/retrieval/`.
   - `generated_answer_validation()` in `chat_grounding.py` computes term overlap

     against retrieved source evidence. If generated prose strays or hallucinates,

     KENN automatically falls back to authoritative, verified technical templates.

5. APPLE SILICON METAL MLX ACCELERATION:
   - Native engine: `apps/backend/src/kenn/llm/mlx_inference_engine.py` runs 4-bit quantized

     models (e.g. `Qwen2.5-1.5B-Instruct-4bit`) directly on the Apple Silicon Unified

     Memory GPU.
   - Performance: TTFT <= 380 ms, generation speed ~27-70 tok/sec, zero CPU audio

     dropouts in Ableton Live.

--------------------------------------------------------------------------------
TASKS TO EXECUTE IN THIS SPRINT
--------------------------------------------------------------------------------

TASK 1: RUN THE INTERACTIVE CLI CHAT
1. Launch the interactive CLI assistant:
   ```bash
   /Library/Frameworks/Python.framework/Versions/3.13/bin/python3 apps/backend/src/kenn/core/chat_cli.py
   ```
2. Validate interactive session behavior across different conversation turns:
   - Ask: `How do I set up sidechain compression on bass in Ableton Live?`
   - Ask: `What frequency is best to cut for mud in electric guitar?`
   - Ask: `Show my session and tracks`
   - Ask: `Mute track 1`
   - Ask: `Hey KENN, ready to mix?`

TASK 2: EXECUTE QUANTITATIVE LATENCY & ROUTING BENCHMARK
1. Run the automated full-system benchmark script:
   ```bash
   /Library/Frameworks/Python.framework/Versions/3.13/bin/python3 scripts/benchmark_chat_cli_full.py
   ```
2. Verify all 4 benchmark pillars output valid timings:
   • Pillar 1: Apple Silicon MLX GPU TTFT and tokens/sec.
   • Pillar 2: Microsecond heuristic routing latency (< 3 ms).
   • Pillar 3: Ableton Live OSC fail-safe / connection speed (< 150 ms).
   • Pillar 4: Hybrid retrieval and grounded audio response time.

TASK 3: TEST LIVE ABLETON 12 INTEGRATION (WITH LIVE OPEN)
1. Ensure Ableton Live 12 Suite is running with `KENN_Bridge` or `AbletonOSC`

   listening on UDP port 11000.
2. In the CLI, query:
   ```bash
   /Library/Frameworks/Python.framework/Versions/3.13/bin/python3 -c "
   import sys; sys.path.insert(0, 'source')
   from kenn.core.chat_cli import ask_once
   print(ask_once('Show my session and tracks'))
   "
   ```
3. Test parameter change action card generation:
   ```bash
   /Library/Frameworks/Python.framework/Versions/3.13/bin/python3 -c "
   import sys; sys.path.insert(0, 'source')
   from kenn.core.chat_cli import ask_once
   print(ask_once('Mute track 2'))
   "
   ```

TASK 4: VERIFY REGRESSION SUITE INTEGRITY
1. Run all unit and integration tests for chat and Ableton control:
   ```bash
   /Library/Frameworks/Python.framework/Versions/3.13/bin/python3 -m pytest apps/backend/src/kenn/tests/test_full_control_40_capabilities.py
   /Library/Frameworks/Python.framework/Versions/3.13/bin/python3 -m pytest UX/velvet_thunder/tests/chat/
   ```
2. Ensure 100% of test assertions pass green.

--------------------------------------------------------------------------------
ACCEPTANCE CRITERIA
--------------------------------------------------------------------------------
[x] MLX Engine compiles and runs natively on Apple Silicon Metal with 0 syntax errors.
[x] Intent routing executes in < 3.0 ms per query (typically < 100 µs).
[x] Ableton Live OSC commands adhere to strict safety bounds (<= ±3 dB, limiter locked).
[x] Anti-hallucination validator gates output, preventing fabricated DAW parameters.
[x] CLI provides full interactive dialogue, session memory, and markdown logging.
================================================================================
```
