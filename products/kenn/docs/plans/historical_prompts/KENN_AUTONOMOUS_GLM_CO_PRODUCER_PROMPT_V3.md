# KENN AUTONOMOUS DUAL-GLM CO-PRODUCER — AGENT PROMPT (V3)

> **What this file is:** The definitive implementation prompt that drives an AI coding agent (Antigravity / Claude Code / Codex) to transform KENN from a reactive tool bridge into an **autonomous, closed-loop studio co-producer** operating on the **Dual-GLM Architecture** (Frontier Reasoning Brain + Hardware-Grade Deterministic Calibration & Control).
>
> **How to use it:** Open the workspace root (`~/Nite-DSP`) and instruct the agent: *"Execute `root-docs/KENN_AUTONOMOUS_GLM_CO_PRODUCER_PROMPT_V3.md` in full. Produce every deliverable in §7."* Run in Plan/read-only mode first; do not modify files until the plan is reviewed.
>
> **Owner:** NITE DSP · **Created:** 2026-09-18 · **Predecessors:** `KENN_LLM_SPEEDUP_PROMPT_V1.md` (68–85% latency cut), `KENN_SUBSECOND_LATENCY_AND_AI_EXPANSION_PROMPT_V2.md` (sub-second streaming + telemetry)

---

## 0. Mission and The 7-Step GLM Closed Loop

Your mission is to elevate KENN into an **autonomous studio mixing engineer and production co-pilot**. 

Unlike naive LLM wrappers that guess blindly in open-loop prose, KENN operates on the **Deterministic GLM Closed Loop**:

```text
  [1. OBSERVE]  Live Ableton session graph + real-time audio telemetry (LUFS, dBTP, ERB spectrum)
        │
  [2. REASON]   Diagnose sonic problems (masking, clipping, resonant mud, phase cancellation)
        │
  [3. PROPOSE]  Formulate typed, bounded, parameter-exact action cards (before/after values)
        │
  [4. CONFIRM]  User authorization gate (one-click apply or full agentic auto-run)
        │
  [5. ACT]      Execute surgical DAW commands via AbletonOSC / Live API (no arbitrary writes)
        │
  [6. VERIFY]   Read back new state from Ableton Live to prove parameter landed accurately
        │
  [7. LEARN]    Commit receipt journal, trigger Loudness-Matched A/B audition, update memory
```

---

## 1. The Dual-GLM Architectural Paradigm

KENN achieves frontier capability by uniting two distinct definitions of **GLM**:

```text
═══════════════════════════════════════════════════════════════════════════════════
                   THE KENN DUAL-GLM AUTONOMOUS ARCHITECTURE
═══════════════════════════════════════════════════════════════════════════════════

  ┌─────────────────────────────────────────────────────────────────────────────┐
  │ 1. SENSORY & TRANSPORT PLANE (AbletonOSC + C++ Telemetry Engine)            │
  │    - Real-time track graph: tracks, armed clips, device chains, return buses │
  │    - Live audio meters: integrated LUFS, true peak dBTP, phase correlation   │
  └──────────────────────────────────────┬──────────────────────────────────────┘
                                         │
                                         ▼
  ┌─────────────────────────────────────────────────────────────────────────────┐
  │ 2. FRONTIER REASONER & WORLD MODEL ("The Producer Brain" / GLM 1)           │
  │    - Local fine-tuned Metal MLX model (sub-second streaming, TTFB < 200ms)  │
  │    - ReAct Multi-Step Agent: decomposes high-level intent into recipe DAGs  │
  │    - Grounded in 737+ distilled masterclass notes (FabFilter, Live 12, etc.) │
  └──────────────────────────────────────┬──────────────────────────────────────┘
                                         │
                                         ▼
  ┌─────────────────────────────────────────────────────────────────────────────┐
  │ 3. HARDWARE-GRADE ACOUSTIC CALIBRATION (The "Genelec GLM Loop" / GLM 2)      │
  │    - 40-band Glasberg & Moore ERB filter banks & Terhardt ATH thresholds    │
  │    - Pairwise spectral masking matrix calculation (Kick vs Bass, Vocals)   │
  │    - Complementary surgical EQ curve synthesis (max ±2.5 dB, Q ∈ [1.4, 2.2])│
  └──────────────────────────────────────┬──────────────────────────────────────┘
                                         │
                                         ▼
  ┌─────────────────────────────────────────────────────────────────────────────┐
  │ 4. SAFE ACTION CONTROLLER & VERIFICATION ENGINE (Reversible Execution)       │
  │    - Typed proposal tokens, stale-state checks, idempotency, readback proof │
  │    - Zero-bias loudness-matched A/B audition panel (±0.0 LUFS matched)      │
  │    - Immutable receipt journal with one-click atomic undo                   │
  └─────────────────────────────────────────────────────────────────────────────┘
```

---

## 2. Deep Research: The Problem with Traditional Audio AI

### 2.1 Why Generalist LLMs Fail at Music Production
1. **Open-Loop Hallucination**: Generic LLMs invent plugin settings, track names, and audio measurements that have no grounding in the actual project. A producer asking "Why does my mix sound muddy?" receives boilerplate essays rather than a diagnosis of their actual 310 Hz resonance.
2. **Deafness (No Sensory Plane)**: Without live telemetry, the model cannot hear that the vocal is peaking at +0.6 dBTP or that the bass has a negative phase correlation of -0.3.
3. **Unsafe Direct Control**: Giving an unconstrained LLM access to execute OSC/MIDI commands leads to destructive errors (overwriting track volume to +6 dB, muting master buses, or breaking gain staging).
4. **Volume Bias in Audition**: Human hearing perceives louder audio as "better" (Fletcher-Munson equal-loudness curves). An AI that applies an EQ boost without loudness matching deceives the producer.

### 2.2 How KENN's Dual-GLM Solves It
- **Auditory Perception**: Ingests live telemetry frames every 100ms from the master bus and active tracks.
- **Session World Model**: Maintains an exact, typed representation of the Ableton track tree, preventing invalid references.
- **Bounded Surgical Proposals**: Generates reversible action cards with strict bounds (e.g. gain cuts capped at -3 dB, Q locked to surgical bells).
- **Loudness-Matched A/B**: Every applied recipe automatically calculates LUFS delta and trims the audition output so the producer compares tonal changes with zero volume bias.

---

## 3. Phase 1 — Session World Model & Live Audio Ingest

### 3.1 Session World Model (`source/kenn/core/session_world_model.py`)
- Continuously syncs Ableton Live's state via AbletonOSC:
  - Track list: name, index, color, volume, pan, mute, solo, arm.
  - Device list per track: name, class (`Eq8`, `Compressor`, `Limiter`, `DrumBuss`), parameter values.
  - Return tracks and master bus routing.
- Provides thread-safe query APIs:
  - `find_track(name_or_role: str) -> TrackSnapshot | None` (resolves "vocal", "kick", "sub", "snare")
  - `find_device(track_idx: int, device_name: str) -> DeviceSnapshot | None`
  - `get_routing_matrix() -> RoutingGraph`

### 3.2 Real-Time Audio Telemetry Ingest (`audio_telemetry.py`)
- High-frequency ingest of live audio metrics:
  - Integrated LUFS, Short-Term LUFS, Momentary LUFS.
  - True Peak (dBTP) with inter-sample clipping detection.
  - Phase correlation ($[-1.0, +1.0]$) with mono cancellation alerts.
  - Spectral energy distribution (Sub 20–60Hz, Low-Mid 200–500Hz, High-Mid 2–6kHz, Air 10–20kHz).
  - Crest factor ($>12\text{ dB}$ dynamic, $<6\text{ dB}$ squashed).

---

## 4. Phase 2 — Autonomous ReAct Agent Loop ("The Producer Brain")

### 4.1 Multi-Step ReAct Engine (`source/kenn/agent/react_engine.py`)
Implement an autonomous ReAct loop:
1. **Thought**: The model reasons about the goal based on the Session World Model and live telemetry.
2. **Action**: Invokes a tool from the KENN Tool Registry (`get_session_state`, `read_telemetry`, `calculate_masking`, `synthesize_eq_recipe`).
3. **Observation**: Collects the tool execution result and updates internal state.
4. **Loop**: Repeats until a complete, verified proposal DAG is formed.

### 4.2 Available Agent Tools
- `tool_inspect_track(track_name_or_id)`: Returns volume, pan, active devices, and frequency profile.
- `tool_inspect_clipping()`: Identifies all tracks or master bus exceeding -0.1 dBTP.
- `tool_inspect_masking(track_a, track_b)`: Runs 40-band ERB cross-correlation to find masking frequencies.
- `tool_create_proposal(recipe)`: Emits a typed proposal card for user approval.
- `tool_execute_proposal(proposal_id)`: Dispatches the confirmed action to Ableton with readback verification.

---

## 5. Phase 3 — Closed-Loop Acoustic Calibration ("The Genelec GLM Loop")

### 5.1 Psychoacoustic Masking Engine (`source/kenn/core/acoustic_calibration.py`)
- Implement 40-band Glasberg & Moore Equivalent Rectangular Bandwidth (ERB) filter banks.
- Calculate Terhardt Absolute Threshold of Hearing (ATH) and Schroeder asymmetric frequency spreading.
- Generate pairwise spectral masking matrices between competing elements:
  - Kick vs 808 / Sub Bass (40–100 Hz conflict)
  - Lead Vocal vs Guitars / Synths (500 Hz–3 kHz conflict)
  - Snare vs Claps / Reverb wash (200 Hz body & 5 kHz crack)

### 5.2 Complementary Surgical EQ Synthesis
- When masking exceeds threshold ($\ge 6\text{ dB}$ masking depth):
  - Synthesize a narrow complementary bell cut on the masking instrument (e.g. -2.0 dB at 65 Hz on 808).
  - Synthesize a complementary pocket boost on the masked instrument (e.g. +1.5 dB at 65 Hz on Kick).
  - Enforce hardware-grade guardrails: gain $\le 3.0\text{ dB}$, $Q \in [1.4, 2.2]$.

---

## 6. Phase 4 — Studio Companion UX (Velvet Thunder / Web)

### 6.1 Real-Time Audio Telemetry HUD (`UX/app.js` & `UX/styles.css`)
- Persistent live HUD in the header showing:
  - Live integrated & short-term LUFS meter.
  - True Peak dBTP meter with pulsing red clipping warnings.
  - Phase correlation bar (green for $>+0.5$, yellow for $+0.2$ to $+0.5$, red for $<+0.2$).
- Clickable diagnostics flyout detailing detected anomalies and recommendations.

### 6.2 Interactive Reversible Mix Plan Cards
- Render step-by-step DAG execution chains:
  - Step status indicators: `Pending`, `Executing`, `Verified ✓`, `Failed`.
  - Live parameter diff view: `Eq8 Band 3: 310 Hz | 0.0 dB → -2.5 dB (Q 2.0)`.
  - Individual "Apply Step" button and global "Execute All" button.

### 6.3 Zero-Bias Loudness-Matched A/B Audition Panel
- Automated A/B toggle with $\pm 0.0\text{ LUFS}$ matching:
  - Button A: Original unprocessed mix.
  - Button B: Mix with KENN's proposals applied.
  - Loudness badge verifying equal perceptual volume so the user auditions purely tonal and dynamic differences.
- One-click atomic Undo button with receipt journal tracking.

---

## 7. Deliverables & Acceptance Criteria

### 7.1 Measurable SLO Gates:
1. **ReAct Loop Execution**: Multi-step audio task completes in $\le 3\text{ seconds}$ total reasoning time.
2. **Acoustic Calibration Accuracy**: Complementary EQ synthesis never exceeds $\pm 3.0\text{ dB}$ gain and always targets detected ERB masking peak within $\pm 10\text{ Hz}$.
3. **Execution Safety & Verification**:
   - 100% of DAW changes verified with an AbletonOSC readback probe.
   - 100% of executed proposals recorded with an immutable receipt for instant undo.
4. **Test Suite**:
   - Zero test regressions.
   - All tests in `source/kenn/tests/` and `products/kenn/tests/` pass with 100% success rate.
5. **Report & Documentation**:
   - Deliver `KENN_AUTONOMOUS_GLM_VERIFICATION_REPORT.md` citing every measured test and latency metric.
   - Update `walkthrough.md` with complete architecture diagram and operational guide.

