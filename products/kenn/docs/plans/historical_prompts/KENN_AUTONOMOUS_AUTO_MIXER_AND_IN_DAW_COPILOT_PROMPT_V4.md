# KENN AUTONOMOUS IN-DAW AUTO-MIXER, NATIVE VST3 SENSORY COPILOT & SESSION DOCTOR — AGENT PROMPT (V4)

> **What this file is:** The definitive autonomous execution prompt that drives an AI coding assistant (Antigravity / Claude Code / Codex) to implement KENN Version 4.0: transforming KENN from a single-track deliberative assistant into an **autonomous multi-track auto-mixer, in-DAW VST3 sensory copilot, and full-session acoustic doctor**.
>
> **How to execute autonomously:** Open the workspace root (`~/Nite-DSP`) and prompt the agent:
> ```bash
> Execute root-docs/KENN_AUTONOMOUS_AUTO_MIXER_AND_IN_DAW_COPILOT_PROMPT_V4.md in full. Produce every deliverable in §7 with 100% test passing and tri-repo synchronization.
> ```
>
> **Owner:** NITE DSP · **Created:** 2026-09-19 · **Predecessors:**
> - `KENN_LLM_SPEEDUP_PROMPT_V1.md` (68–85% latency cut)
> - `KENN_SUBSECOND_LATENCY_AND_AI_EXPANSION_PROMPT_V2.md` (sub-second streaming + Metal MLX socket)
> - `KENN_AUTONOMOUS_GLM_CO_PRODUCER_PROMPT_V3.md` (Dual-GLM closed loop, 7-step ReAct, ERB calibration, telemetry bridge)

---

## 0. Executive Mission & System Architecture

KENN V4 elevates the KENN engine into a **commercial-grade, autonomous in-DAW mixing copilot**. 

While V3 proved the closed-loop ReAct paradigm on single tracks, professional music producers require an agent that can:
1. **Audit an entire multi-track Ableton Live 12 project in seconds** and issue a deterministic 0–100 Mix Quality Metric (MQM).
2. **Resolve cross-track collisions autonomously** (Kick vs 808/Bass, Vocal vs Guitars/Synths, Snare vs Reverbs) using 40-band ERB psychoacoustic masking matrices and dynamic EQ/sidechain carving.
3. **Embed natively inside Ableton Live as a C++/JUCE VST3 plugin**, streaming lock-free audio feature frames (True Peak, ITU-R BS.1770-4 LUFS, phase correlation, ERB spectrum) to the local Metal engine over low-latency IPC.
4. **Accept hands-free spoken mixing commands** via sub-500ms local Speech-to-Intent on Apple Silicon Metal unified memory.
5. **Guarantee non-destructive execution** via hardware safety clamps ($\le \pm 3.0\text{ dB}$, master fader write-locked, limiter ceiling auto-remediation, and zero-bias loudness-matched A/B auditioning).

```text
═════════════════════════════════════════════════════════════════════════════════════════════
                       KENN V4.0 FULL-SESSION AUTONOMOUS ARCHITECTURE
═════════════════════════════════════════════════════════════════════════════════════════════

   ┌───────────────────────────────────────────────────────────────────────────────────────┐
   │                         1. IN-DAW SENSORY & TRANSPORT LAYER                           │
   │  ┌───────────────────────────────────────┐   ┌─────────────────────────────────────┐  │
   │  │ AbletonOSC Remote Transport Engine    │   │ Native C++/JUCE VST3 Sensor Plugin  │  │
   │  │ - Multi-track graph (16–64 tracks)    │   │ - Lock-free ring buffer telemetry   │  │
   │  │ - Device parameters & routing chains  │   │ - 4x oversampled True Peak (dBTP)   │  │
   │  │ - 250ms master & track meter polling  │   │ - ITU-R BS.1770-4 LUFS (M, S, I)    │  │
   │  └───────────────────┬───────────────────┘   └──────────────────┬──────────────────┘  │
   └──────────────────────┼──────────────────────────────────────────┼─────────────────────┘
                          │                                          │
                          ▼                                          ▼
   ┌───────────────────────────────────────────────────────────────────────────────────────┐
   │                         2. KENN LOCAL INTELLIGENCE ENGINE                             │
   │  ┌───────────────────────────────────────┐   ┌─────────────────────────────────────┐  │
   │  │ Full-Session Mix Doctor (0–100 MQM)   │   │ Multi-Stem Dynamic Unmasking Engine │  │
   │  │ - Dynamic Crest & Headroom (20 pts)   │   │ - 40-band ERB cross-spectral matrix │  │
   │  │ - Low-End Mono & Sub Phase (20 pts)   │   │ - Pairwise collision index ($M(f)$) │  │
   │  │ - Spectral Balance / Mud (20 pts)     │   │ - Surgical dynamic EQ synthesis     │  │
   │  │ - Pairwise Separation (20 pts)        │   │ - Safe parameter clamping ($\le 3dB$)│  │
   │  │ - Stereo Correlation / Mono (20 pts)  │   │                                     │  │
   │  └───────────────────┬───────────────────┘   └──────────────────┬──────────────────┘  │
   │                      │                                          │                     │
   │                      ▼                                          ▼                     │
   │  ┌─────────────────────────────────────────────────────────────────────────────────┐  │
   │  │ Frontier Reasoning Brain (Persistent Metal MLX Unix Socket Server)              │  │
   │  │ - Sub-second ReAct loop ($p50 < 0.98\text{s}$, TTFB $< 275\text{ms}$)          │  │
   │  │ - Grounded in 744 schema-validated mixing & DSP masterclass notes               │  │
   │  │ - Local Speech-to-Intent (Whisper/Moonshine on Metal, $< 200\text{ms}$ voice)   │  │
   │  └─────────────────────────────────────────────────────────────────────────────────┘  │
   └──────────────────────────────────────────┬────────────────────────────────────────────┘
                                              │
                                              ▼
   ┌───────────────────────────────────────────────────────────────────────────────────────┐
   │                         3. SAFE ACTION & AUDITION CONTROLLER                          │
   │  - Master fader strictly write-locked (prevent acoustic damage)                       │
   │  - Zero-bias loudness-matched A/B audition engine ($\pm 0.0\text{ LUFS}$ trim)        │
   │  - Immutable receipt journals with 1-click atomic rollback                            │
   │  - Live in-DAW Velvet Thunder HUD (Web / JUCE WebBrowserComponent)                    │
   └───────────────────────────────────────────────────────────────────────────────────────┘
```

---

## 1. Phase 1: Full-Session Mix Doctor & 0–100 Mix Quality Metric (MQM)

### 1.1 Implementation Target
- Create: `source/kenn/core/mix_doctor.py`
- Expose via: `source/kenn/server.py` (`POST /api/mix-doctor/audit`, `GET /api/mix-doctor/scorecard`)
- Integrate into: `source/kenn/autonomous_agent.py` as an autonomous tool (`tool_audit_full_mix`)

### 1.2 The Deterministic Mix Quality Metric (MQM) Formula
The Mix Quality Metric is a deterministic $0–100$ score computed across five objective psychoacoustic dimensions ($20\text{ points each}$):

$$\text{MQM} = S_{\text{dynamic}} + S_{\text{low\_end}} + S_{\text{spectral}} + S_{\text{unmasking}} + S_{\text{stereo}}$$

1. **Dynamic Health & Crest Factor ($S_{\text{dynamic}} \in [0, 20]$)**:
   - Evaluates Peak-to-Loudness Ratio ($\text{PLR} = \text{Peak}_{\text{dBTP}} - \text{LUFS}_{\text{integrated}}$).
   - Target for modern electronic/pop master: $\text{PLR} \in [8.0, 12.0\text{ dB}]$.
   - Score penalties:
     - Hyper-compressed / squashed ($\text{PLR} < 6.0\text{ dB}$): $-5\text{ to } -15\text{ pts}$.
     - Weak / under-compressed ($\text{PLR} > 16.0\text{ dB}$ with peak $< -6.0\text{ dBTP}$): $-4\text{ to } -10\text{ pts}$.
     - True Peak clip risk ($\text{Peak}_{\text{dBTP}} > -0.2\text{ dBTP}$): $-10\text{ pts}$ immediately.

2. **Low-End Control & Sub Phase ($S_{\text{low\_end}} \in [0, 20]$)**:
   - Evaluates frequencies $< 120\text{ Hz}$ across all tracks and master bus.
   - Low-end mono compatibility: Sub stereo correlation must satisfy $r_{\text{sub}} \ge 0.85$.
   - Sub rumble check: Unfiltered energy below $25\text{ Hz}$ on non-bass tracks (vocals, guitars, percussion) triggers low-cut recommendation and $-2\text{ pts}$ per offending track.
   - Kick/Bass headroom check: Combined sub energy must not exceed $+3.0\text{ dB}$ above average pink noise curve.

3. **Spectral Balance & Mud Accumulation ($S_{\text{spectral}} \in [0, 20]$)**:
   - Compares session frequency curve against calibrated tilt targets (e.g. $-3.0\text{ to } -4.5\text{ dB/octave}$ pink noise slope).
   - Boxiness / Mud accumulation ($200–500\text{ Hz}$): Detects excessive low-mid buildup across simultaneous tracks.
   - Harshness accumulation ($3–6\text{ kHz}$): Detects resonant fatigue peaks.
   - Air extension ($> 10\text{ kHz}$): Verifies open high end without brittle aliasing.

4. **Pairwise Stem Separation & Collision Index ($S_{\text{unmasking}} \in [0, 20]$)**:
   - Evaluates pairwise cross-spectral overlap across key stems:
     - Kick vs Bass / 808 ($40–120\text{ Hz}$)
     - Lead Vocal vs Guitars / Keyboards ($500\text{ Hz}–3.5\text{ kHz}$)
     - Snare vs Background Claps / Noise ($150–250\text{ Hz}$ & $3–5\text{ kHz}$)
   - Collision index $M_{A,B} > 0.65$ triggers unmasking penalty ($-4\text{ pts}$ per critical collision).

5. **Stereo Imaging & Mono Compatibility ($S_{\text{stereo}} \in [0, 20]$)**:
   - Evaluates wideband and multi-band phase correlation:
     - Master correlation $r_{\text{master}} \ge 0.50$ (Optimal).
     - Phase cancellation warning ($0.0 \le r < 0.2$): $-8\text{ pts}$.
     - Destructive out-of-phase audio ($r < 0.0$): $-15\text{ pts}$.
   - Panning balance: Verifies Left/Right RMS balance within $\pm 0.8\text{ dB}$.

### 1.3 Executive Audit Scorecard & Remediation Plan
`MixDoctor` generates a structured, serializable `MixAuditReport`:
```python
@dataclass
class MixAuditReport:
    mqm_score: float                # 0.0 - 100.0
    grade: str                      # "S", "A", "B", "C", "D", "CRITICAL"
    dimension_scores: Dict[str, float]
    critical_issues: List[MixIssue] # Issues requiring immediate attention
    remediation_dag: List[RecipeStep] # Bounded, parameter-exact action steps
    loudness_telemetry: Dict[str, float]
    timestamp: str
```

---

## 2. Phase 2: Autonomous Multi-Stem Dynamic Unmasking Engine

### 2.1 Implementation Target
- Create: `source/kenn/core/stem_unmasking.py`
- Integrate into: `source/kenn/agent/react_engine.py` and `source/kenn/core/acoustic_calibration.py`
- Expose via: `POST /api/unmasking/analyze` and `POST /api/unmasking/carve`

### 2.2 Psychoacoustic Unmasking Algorithm
1. **Stem Role Detection**:
   - Inspects track names, audio telemetry, and MIDI pitch ranges to classify tracks into functional roles:
     `KICK`, `BASS_SUB`, `SNARE`, `LEAD_VOCAL`, `BACKING_VOCAL`, `GUITAR_SYNTH`, `PERCUSSION`, `FX_RETURN`.
2. **40-Band ERB Cross-Correlation**:
   - For competing pairs (e.g. $A = \text{Kick}$, $B = \text{Bass}$), compute cross-spectral energy ratio across each Glasberg & Moore ERB critical band:
     $$C_k = \frac{\min(E_A[k], E_B[k])}{\max(E_A[k], E_B[k])} \cdot \left(\frac{E_A[k] + E_B[k]}{E_{\text{total}}}\right)$$
   - Identify peak conflict band $k^*$ and center frequency $f^*$.
3. **Dynamic Carving Synthesis**:
   - Automatically configure an Ableton Live `Eq8` or FabFilter `Pro-Q 3` instance on Track $B$:
     - Band Filter Type: `Bell`
     - Frequency: $f^* \pm 5\%$
     - $Q$: $2.0 \in [1.4, 2.5]$ (surgical, non-audible ringing)
     - Gain Delta: Clamped to $[-3.0, -1.0]\text{ dB}$ (never exceeds hardware safety limit)
   - Alternatively, configure `Compressor` sidechain routing from Track $A$ to Track $B$ with:
     - Attack: $2.0\text{ ms}$ (transparent)
     - Release: Synced to song tempo (e.g. $1/16\text{ note}$ or $120\text{ ms}$)
     - Gain Reduction: Max $-3.0\text{ dB}$

---

## 3. Phase 3: Native C++/JUCE VST3 Plugin Telemetry Bridge & In-DAW HUD

### 3.1 Implementation Target
- Source directory: `Nite-DSP-Operations/Shenrendao/KENN/vst3-plugin/Source/`
- Core C++ files:
  - `MeterAnalyzer.h`
  - `PluginProcessor.cpp` / `PluginProcessor.h`
  - `PluginEditor.cpp` / `PluginEditor.h`
  - `CMakeLists.txt`

### 3.2 Real-Time Audio DSP Pipeline
Inside the VST3 audio processing block (`processBlock`):
1. **True Peak Oversampling (4x Polyphase FIR)**:
   - Oversamples audio 4x using polyphase half-band filter to capture intersample peaks (ISPs) compliant with ITU-R BS.1770-4.
2. **K-Weighting & Loudness Filtering**:
   - High-pass shelf (Stage 1) + high-frequency boost (Stage 2) feeding:
     - Momentary LUFS ($400\text{ ms}$ rectangular window)
     - Short-term LUFS ($3.0\text{ s}$ sliding window)
     - Integrated LUFS (gated at $-70\text{ LKFS}$ and $-10\text{ LU}$ relative)
3. **Phase Correlation**:
   - Vectorized dot product $r = \frac{\langle L, R \rangle}{\|L\|_2 \|R\|_2}$ with $100\text{ ms}$ smoothing.
4. **Lock-Free Ring Buffer & Background IPC**:
   - DSP audio thread pushes feature frames to a lock-free Single-Producer Single-Consumer (SPSC) queue.
   - Non-realtime background thread pulls from the queue, batches at 60 Hz, and streams HTTP POST to `http://127.0.0.1:8999/api/plugin-handoff`.
   - Never allocations, mutex locks, or syscalls on the real-time audio thread.

### 3.3 In-DAW UI Integration
- Update `PluginEditor.cpp` to render:
  - Multi-band telemetry meters (True Peak, LUFS, Correlation bar).
  - One-click "Audit Session" button triggering KENN's Mix Doctor.
  - Active proposals card with "A/B Audition" and "Apply" buttons.

---

## 4. Phase 4: Sub-500ms Local Speech-to-Intent Studio Voice Control

### 4.1 Implementation Target
- Create: `source/kenn/speech/voice_copilot.py`
- Expose via: `source/kenn/server.py` (`POST /api/voice/intent`, `POST /api/voice/audio-chunk`)
- Integrate into: `source/kenn/agent/react_engine.py`

### 4.2 Architecture & Latency Budget
Mixing engineers have hands occupied on keyboards and controllers. KENN V4 introduces hands-free spoken mixing assistance:
```text
  [Spoken Query] ──(Microphone)──> [Metal MLX Audio Feature Extractor] (< 80ms)
                                                │
                                                ▼
                                   [Fast Acoustic Classifier]          (< 120ms)
                                                │
                                                ▼
                                   [Semantic Slot Filler]             (< 50ms)
                                                │
                                                ▼
                                   [ReAct Engine via MLX Socket]      (< 250ms)
                                                │
                                                ▼
                                   [Auditory Chime + HUD Card]        (Total: < 500ms)
```

1. **Local Intent Classification**:
   - Supported intent categories:
     - `AUDIT_SESSION`: "KENN, audit the mix" / "How does my low end look?"
     - `UNMASK_TRACKS`: "Fix the kick and bass conflict" / "Carve room for the vocal"
     - `CHECK_HEADROOM`: "Am I clipping?" / "What is my true peak?"
     - `APPLY_REMEDY`: "Apply proposal" / "Confirm EQ cut"
     - `AUDITION_TOGGLE`: "A/B test" / "Switch to original"
     - `ATOMIC_UNDO`: "Undo last move" / "Rollback"
2. **Zero Cloud Dependency**:
   - 100% running locally on Apple Silicon Metal MLX unified memory.

---

## 5. Phase 5: Production-Ready Tri-Repo CI/CD & Automated Verification

### 5.1 Parity Targets across 3 Codebases
Every modification must be strictly synchronized across:
1. `Nite-DSP-Operations/Shenrendao/KENN/`
2. `Nite-DSP-Operations/monorepo/products/kenn/`
3. `Nite-DSP-Operations/Shenrendao/KENN/UX/velvet_thunder/studio/kenn/`

### 5.2 Test Suites to Implement & Pass
1. `products/kenn/tests/test_mix_doctor.py`:
   - `test_mix_doctor_audit_synthetic_session`: Asserts 16-track session yields valid 0–100 MQM score with exact dimension breakdown.
   - `test_mix_doctor_detects_clipping_and_boxiness`: Verifies synthetic $+0.5\text{ dBTP}$ track triggers Critical clipping remediation and $-10\text{ pt}$ penalty.
   - `test_mix_doctor_mono_correlation_penalty`: Verifies $r = -0.4$ out-of-phase track triggers phase warning and $-15\text{ pt}$ penalty.
2. `products/kenn/tests/test_stem_unmasking.py`:
   - `test_kick_bass_erb_unmasking_synthesis`: Proves 40-band ERB cross-correlation isolates 65 Hz collision and synthesizes $\le -2.5\text{ dB}$ dynamic cut.
   - `test_vocal_acoustic_unmasking`: Proves vocal vs guitar collision synthesizes complementary $1.2\text{ kHz}$ pocket.
3. `products/kenn/tests/test_voice_copilot.py`:
   - `test_speech_intent_extraction_accuracy`: Tests 12 standard mixing voice prompts and verifies 100% intent classification accuracy.
   - `test_voice_intent_end_to_end_latency`: Verifies simulated voice intent extraction completes in $\le 300\text{ ms}$.
4. Regression validation:
   - Ensure all existing 13 tests in `products/kenn/tests/test_audio_ai_features.py`, `test_kenn_lm_server.py`, and `test_react_dual_glm.py` continue to pass at 100%.

---

## 6. Execution Directives for the Autonomous Agent

When executing this prompt:
1. **Planning Mode First**:
   - Conduct full read-only review of existing files (`audio_telemetry.py`, `autonomous_agent.py`, `react_engine.py`, `plugin_handoff.py`).
   - Create `implementation_plan.md` detailing the new modules and test cases.
2. **Implementation Sequence**:
   - Step 1: Implement `mix_doctor.py` and unit tests.
   - Step 2: Implement `stem_unmasking.py` and unmasking tests.
   - Step 3: Implement `voice_copilot.py` and intent parser tests.
   - Step 4: Integrate new tools into `autonomous_agent.py` and `server.py`.
   - Step 5: Update C++/JUCE VST3 plugin files and HUD endpoints.
   - Step 6: Synchronize all code across the three target repositories.
   - Step 7: Run full pytest suite across all test files and confirm 100% passing.
3. **Safety & Zero-Cost Policy**:
   - Zero external cloud API calls ($0.00 cost).
   - Master volume fader must remain strictly write-locked.
   - Parameter adjustments must strictly obey the $\le \pm 3.0\text{ dB}$ safety ceiling.

---

## 7. Deliverables & Acceptance Criteria

1. **Source Code**:
   - `source/kenn/core/mix_doctor.py` (Full Session Mix Doctor & 0–100 MQM)
   - `source/kenn/core/stem_unmasking.py` (Multi-Stem 40-band ERB Unmasking)
   - `source/kenn/speech/voice_copilot.py` (Sub-500ms Local Speech-to-Intent)
   - Updated `source/kenn/autonomous_agent.py`, `server.py`, `plugin_handoff.py`
2. **Tri-Repo Parity**:
   - All changes synchronized into `monorepo/products/kenn/` and `velvet_thunder/studio/kenn/`.
3. **Automated Verification**:
   - Full test suite passing: `pytest -v products/kenn/tests/` with 0 failures, 0 regressions.
4. **Reports & Logs**:
   - Create `KENN_V4_AUTONOMOUS_AUTO_MIXER_VERIFICATION_REPORT.md` documenting:
     - 0–100 MQM benchmark performance.
     - Measured latencies (Mix Doctor audit time, unmasking DAG calculation, speech-to-intent).
     - Test execution logs.
   - Update `root-docs/KENN_DAILY_EXECUTION_LOG_2026-09-18.md` with V4 achievements.

