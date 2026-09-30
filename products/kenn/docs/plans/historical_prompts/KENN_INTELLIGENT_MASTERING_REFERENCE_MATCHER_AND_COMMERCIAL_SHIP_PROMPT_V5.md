# KENN INTELLIGENT MASTERING, REFERENCE TRACK MATCHER & COMMERCIAL SHIP READINESS — AGENT PROMPT (V5)

> **What this file is:** The definitive autonomous execution prompt that drives an AI coding assistant (Antigravity / Claude Code / Codex) to implement KENN Version 5.0: completing the final production tier of the studio suite with an **Autonomous Intelligent Mastering Engine, Reference Track AI Spectral Matcher, Real-Time Velvet Thunder In-DAW GUI Overlay, and Commercial Ship-Readiness Gate**.
>
> **How to execute autonomously:** Open the workspace root (`~/Nite-DSP`) and prompt the agent:
> ```bash
> Execute root-docs/KENN_INTELLIGENT_MASTERING_REFERENCE_MATCHER_AND_COMMERCIAL_SHIP_PROMPT_V5.md in full. Produce every deliverable in §7 with 100% test passing and tri-repo synchronization.
> ```
>
> **Owner:** NITE DSP · **Created:** 2026-09-19 · **Predecessors:**
> - `KENN_LLM_SPEEDUP_PROMPT_V1.md` (68–85% latency cut)
> - `KENN_SUBSECOND_LATENCY_AND_AI_EXPANSION_PROMPT_V2.md` (sub-second streaming + Metal MLX persistent Unix domain socket server)
> - `KENN_AUTONOMOUS_GLM_CO_PRODUCER_PROMPT_V3.md` (Dual-GLM closed loop, 7-step ReAct, ERB calibration, telemetry bridge)
> - `KENN_AUTONOMOUS_AUTO_MIXER_AND_IN_DAW_COPILOT_PROMPT_V4.md` (0–100 MQM Session Doctor, Multi-Stem Dynamic Unmasking, Local Voice Control)

---

## 0. Executive Mission & System Architecture

With KENN V4.0 providing full-session multi-track mixing audits (0–100 MQM) and dynamic pairwise stem unmasking, KENN V5.0 delivers the **commercial mastering and release delivery tier**, providing:

1. **Intelligent Autonomous Mastering Engine**: Multi-platform delivery profiles (Spotify, Apple Music, YouTube, Club/DJ master) with linear-phase subsonic filtering, Mid/Side stereo imaging (Mono Bass Maker below $120\text{ Hz}$), harmonic density saturation, and intersample peak (ISP) limiter tuning.
2. **Reference Track AI Spectral Matcher**: Computes 40-band LTAS difference curves against commercial reference tracks (e.g. Skrillex, Billie Eilish, Chris Lake) and synthesizes musical, non-destructive matching curves ($\le \pm 2.5\text{ dB}$).
3. **Velvet Thunder In-DAW GUI HUD & Real-Time Visualizers**: 5-axis MQM radar chart, 40-band ERB spectrum overlay, stereo correlation goniometer, and 1-click A/B loudness-matched auditioning directly inside the VST3 editor window.
4. **Continuous Background Gain Staging Daemon**: Non-blocking telemetry monitor alerting and trimming bus headroom creep before clipping occurs.
5. **Production Ship Gate & Benchmark Suite**: 100% test pass rate across all suites, zero performance regressions, and tri-repo synchronization.

```text
═════════════════════════════════════════════════════════════════════════════════════════════════════
                       KENN V5.0 COMMERCIAL MASTERING & SHIP ARCHITECTURE
═════════════════════════════════════════════════════════════════════════════════════════════════════

   ┌───────────────────────────────────────────────────────────────────────────────────────────────┐
   │                         1. COMMERCIAL REFERENCE & SENSORY PLANE                               │
   │  ┌─────────────────────────────────────────┐   ┌───────────────────────────────────────────┐  │
   │  │ Commercial Reference Track Analyzer     │   │ Live AbletonOSC & VST3 Telemetry Bus      │  │
   │  │ - 40-band LTAS spectrum extraction      │   │ - 250ms multi-channel metering            │  │
   │  │ - Crest factor & dynamic profile        │   │ - Intersample True Peak (4x polyphase)    │  │
   │  │ - Stereo width across 3 sub-bands       │   │ - ITU-R BS.1770-4 LUFS (M, S, I)          │  │
   │  └────────────────────┬────────────────────┘   └─────────────────────┬─────────────────────┘  │
   └───────────────────────┼──────────────────────────────────────────────┼────────────────────────┘
                           │                                              │
                           ▼                                              ▼
   ┌───────────────────────────────────────────────────────────────────────────────────────────────┐
   │                         2. KENN LOCAL REASONING & MASTERING ENGINE                            │
   │  ┌─────────────────────────────────────────┐   ┌───────────────────────────────────────────┐  │
   │  │ Intelligent Mastering Suite             │   │ Reference Track AI Matcher                │  │
   │  │ - Subsonic linear-phase cut (< 25 Hz)   │   │ - Spectral delta: $\Delta(f) = S_{ref} - S_{mix}$  │
   │  │ - Mid/Side Mono Bass (< 120 Hz)         │   │ - Musically smoothed curve synthesis      │  │
   │  │ - Harmonic saturation profile           │   │ - Safe delta clamping ($\le \pm 2.5\text{ dB}$)│  │
   │  │ - Multi-target ISP limiter tuning       │   │ - Automatic genre profile matching        │  │
   │  └────────────────────┬────────────────────┘   └─────────────────────┬─────────────────────┘  │
   │                       │                                              │                        │
   │                       ▼                                              ▼                        │
   │  ┌─────────────────────────────────────────────────────────────────────────────────────────┐  │
   │  │ Frontier ReAct Reasoner & Voice Copilot (Metal MLX Socket Server)                       │  │
   │  │ - Natural language mastering intent ("Master for Spotify", "Match reference curve")     │  │
   │  │ - Continuous background auto-gain staging daemon                                        │  │
   │  └─────────────────────────────────────────────────────────────────────────────────────────┘  │
   └────────────────────────────────────────────┬──────────────────────────────────────────────────┘
                                                │
                                                ▼
   ┌───────────────────────────────────────────────────────────────────────────────────────────────┐
   │                         3. VELVET THUNDER IN-DAW VISUAL ENGINE & CONTROLLER                   │
   │  - 5-Axis MQM radar chart (Dynamic Health, Low-End, Spectral, Separation, Stereo)            │
   │  - Real-time 40-band ERB spectrum comparison overlay                                          │
   │  - Zero-bias $\pm 0.0\text{ LUFS}$ loudness-matched A/B audition toggle                       │
   │  - 1-click atomic undo journal                                                                │
   └───────────────────────────────────────────────────────────────────────────────────────────────┘
```

---

## 1. Phase 1: Intelligent Autonomous Mastering Engine

### 1.1 Implementation Target
- Create: `source/kenn/core/mastering_engine.py`
- Expose via: `source/kenn/server.py` (`POST /api/mastering/profile`, `POST /api/mastering/apply`)
- Integrate into: `source/kenn/autonomous_agent.py` as `tool_master_session`

### 1.2 Multi-Platform Delivery Profiles
KENN V5 supports 4 industry-standard delivery targets:
1. **Streaming Standard (Spotify / Tidal / Amazon)**:
   - Target Integrated Loudness: $-14.0\text{ LUFS} \pm 0.5\text{ LUFS}$
   - Maximum True Peak: $-1.0\text{ dBTP}$
   - Crest Factor: $\ge 8.0\text{ dB}$
2. **Apple Digital Masters (Apple Music / Sound Check)**:
   - Target Integrated Loudness: $-16.0\text{ LUFS} \pm 0.5\text{ LUFS}$
   - Maximum True Peak: $-1.0\text{ dBTP}$
   - Strict inter-sample peak compliance (zero reconstructed overshoot)
3. **Club / DJ / Festival Master**:
   - Target Integrated Loudness: $-8.0\text{ to } -9.5\text{ LUFS}$
   - Maximum True Peak: $-0.3\text{ dBTP}$
   - Controlled soft clipping + harmonic density
4. **Dynamic Classical / Acoustic Master**:
   - Target Integrated Loudness: $-18.0\text{ LUFS}$
   - Maximum True Peak: $-1.5\text{ dBTP}$
   - Unconstrained dynamic crest ($\text{PLR} \ge 14.0\text{ dB}$)

### 1.3 Mastering Chain Synthesis
The engine synthesizes a 5-stage mastering DAG:
1. **Subsonic Clean**: Linear-phase High-Pass filter at $25\text{ Hz}$ ($18\text{ dB/octave}$) to eliminate inaudible DC offset and subsonic speaker excursion.
2. **Mid/Side Mono Maker**: Frequencies below $120\text{ Hz}$ collapsed to $100\%$ Mid (Sides attenuated by $-12\text{ dB}$ below $120\text{ Hz}$) to preserve vinyl/club punch and phase stability.
3. **Surgical Tonal Balancing**: Compensates for any residual 200–500 Hz boxiness or 3–5 kHz harshness identified by Mix Doctor.
4. **Gentle Harmonic Enhancement**: Transparent tape/tube saturation adding 2nd/3rd harmonics ($+0.5\text{ to } +1.5\text{ dB}$ perceived loudness increase without raising True Peak).
5. **Master Limiter Calibration**:
   - Ceiling clamped to target profile dBTP ($-1.0\text{ or } -0.3\text{ dBTP}$).
   - Lookahead set to $3.0\text{ ms}$.
   - Auto-release optimized for session tempo.

---

## 2. Phase 2: Reference Track AI Spectral Matcher

### 2.1 Implementation Target
- Create: `source/kenn/core/reference_matcher.py`
- Expose via: `source/kenn/server.py` (`POST /api/reference/analyze`, `POST /api/reference/match-curve`)
- Integrate into: `source/kenn/autonomous_agent.py` as `tool_match_reference_track`

### 2.2 Algorithm & Safe Curve Synthesis
1. **Reference Ingestion**: Ingests LTAS spectrum array or audio file path of commercial reference.
2. **Spectral Normalization**: Normalizes both session mix and reference track to equal integrated energy ($1\text{ kHz}$ anchor).
3. **Delta Calculation**:
   $$\Delta(f_k) = S_{\text{reference}}(f_k) - S_{\text{session}}(f_k) \quad \text{for } k \in [1, 40] \text{ ERB bands}$$
4. **Musical Smoothing & Clamping**:
   - Applies 3-band Gaussian smoothing to eliminate narrow resonant spikes.
   - Enforces strict hardware safety bounds: maximum gain adjustment $\le \pm 2.5\text{ dB}$ per band.
   - Emits an exact parametric EQ recipe (Ableton `Eq8` or FabFilter `Pro-Q 3` 4-to-6 band configuration).

---

## 3. Phase 3: Velvet Thunder In-DAW GUI Overlay

### 3.1 Implementation Target
- Update: `UX/app.js` & `UX/styles.css`
- Update: `vst3-plugin/Source/PluginEditor.cpp` & `PluginEditor.h`

### 3.2 UI Capabilities
1. **5-Axis MQM Radar Pentagon**:
   - Real-time animated canvas plotting:
     - Dynamic Health ($0–20$)
     - Low-End Control ($0–20$)
     - Spectral Balance ($0–20$)
     - Stem Separation ($0–20$)
     - Stereo Imaging ($0–20$)
   - Overall MQM score badge with color-coded grade (`S`, `A`, `B`, `C`, `D`, `CRITICAL`).
2. **40-Band ERB Spectral Overlay**:
   - Plots live session spectrum vs reference target curve in real-time.
3. **Zero-Bias A/B Audition Switch**:
   - Prominent toggle button with matched LUFS indicator ($\pm 0.0\text{ LUFS}$ delta badge).
   - 1-click Undo button restoring previous session snapshot.

---

## 4. Phase 4: Continuous Background Gain Staging Daemon

### 4.1 Implementation Target
- Create: `source/kenn/core/auto_gain_stager.py`
- Wire into: `source/kenn/server.py` & `audio_telemetry.py`

### 4.2 Auto-Gain Staging Logic
1. **Non-Blocking Background Poller**: Ingests track and bus RMS levels every $500\text{ ms}$.
2. **Headroom Creep Warning**: If summing bus or group tracks exceed $-3.0\text{ dBFS}$ before processing, issues proactive gain trim advisory.
3. **Auto-Trim Recipe**: Computes linear gain trim offsets across all input tracks to maintain optimal $-18\text{ dBFS}$ nominal operating level before plugin chains.

---

## 5. Phase 5: Production Ship Gate & Tri-Repo Synchronization

### 5.1 Parity Across 3 Codebases
All code must be byte-for-byte synchronized across:
1. `Nite-DSP-Operations/Shenrendao/KENN/`
2. `Nite-DSP-Operations/monorepo/products/kenn/`
3. `Nite-DSP-Operations/Shenrendao/KENN/UX/velvet_thunder/studio/kenn/`

### 5.2 Test Suites to Implement & Pass
1. `products/kenn/tests/test_mastering_engine.py`:
   - `test_mastering_profiles_compliance`: Asserts each delivery profile generates compliant LUFS and True Peak targets.
   - `test_mastering_chain_dag_synthesis`: Asserts 5-stage mastering DAG adheres strictly to safety clamping.
2. `products/kenn/tests/test_reference_matcher.py`:
   - `test_spectral_delta_calculation`: Validates 40-band ERB reference curve extraction and delta computation.
   - `test_reference_curve_safety_clamping`: Asserts synthesized EQ moves never exceed $\pm 2.5\text{ dB}$.
3. `products/kenn/tests/test_auto_gain_stager.py`:
   - `test_gain_creep_detection`: Proves summing bus overload triggers automatic $-18\text{ dBFS}$ nominal trim recipe.
4. Full Regression Pass:
   - Ensure all existing 21 tests from V1–V4 continue to pass with 100% success rate.

---

## 6. Deliverables & Acceptance Criteria

1. **Source Code**:
   - `source/kenn/core/mastering_engine.py`
   - `source/kenn/core/reference_matcher.py`
   - `source/kenn/core/auto_gain_stager.py`
   - Updated `autonomous_agent.py`, `server.py`, `app.js`, `styles.css`
2. **Test Suites**:
   - `tests/test_mastering_engine.py`
   - `tests/test_reference_matcher.py`
   - `tests/test_auto_gain_stager.py`
   - Minimum **28 passing tests** across all suites.
3. **Tri-Repo Parity**:
   - 0 byte differences across `Shenrendao/KENN`, `monorepo/products/kenn`, and `velvet_thunder/studio/kenn`.
4. **Reports**:
   - `KENN_V5_MASTERING_AND_COMMERCIAL_SHIP_VERIFICATION_REPORT.md`
   - Update `walkthrough.md`
   - Update `root-docs/KENN_DAILY_EXECUTION_LOG_2026-09-18.md`

