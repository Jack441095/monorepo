# KENN AUTONOMOUS GENERATIVE ARRANGER, STEM DELIVERY & COMMERCIAL DISTRIBUTION — AGENT PROMPT (V6)

> **What this file is:** The definitive autonomous execution prompt that drives an AI coding assistant (Antigravity / Claude Code / Codex) to implement KENN Version 6.0: completing the creative composition and commercial distribution tier of the studio suite with an **Autonomous Arrangement Doctor & Energy Profiler, Generative In-DAW MIDI Copilot, Commercial Stem Packaging Pipeline, and Vocal Resonance Surgeon**.
>
> **How to execute autonomously:** Open the workspace root (`/Volumes/Jack_Gandy_1TB_SSD/Nite-DSP`) and prompt the agent:
> ```bash
> Execute root-docs/KENN_AUTONOMOUS_GENERATIVE_ARRANGER_STEM_DELIVERY_AND_DISTRIBUTION_PROMPT_V6.md in full. Produce every deliverable in §7 with 100% test passing and tri-repo synchronization.
> ```
>
> **Owner:** NITE DSP · **Created:** 2026-09-19 · **Predecessors:**
> - `KENN_LLM_SPEEDUP_PROMPT_V1.md` (68–85% latency cut)
> - `KENN_SUBSECOND_LATENCY_AND_AI_EXPANSION_PROMPT_V2.md` (sub-second streaming + Metal MLX persistent Unix domain socket server)
> - `KENN_AUTONOMOUS_GLM_CO_PRODUCER_PROMPT_V3.md` (Dual-GLM closed loop, 7-step ReAct, ERB calibration, telemetry bridge)
> - `KENN_AUTONOMOUS_AUTO_MIXER_AND_IN_DAW_COPILOT_PROMPT_V4.md` (0–100 MQM Session Doctor, Multi-Stem Dynamic Unmasking, Local Voice Control)
> - `KENN_INTELLIGENT_MASTERING_REFERENCE_MATCHER_AND_COMMERCIAL_SHIP_PROMPT_V5.md` (Autonomous Mastering Suite, Reference Track AI Spectral Matcher, Velvet Thunder In-DAW GUI Overlay, Commercial Ship Gate)

---

## 0. Executive Mission & System Architecture

With KENN V1–V5 providing sub-second local LLM inference, autonomous closed-loop mixing audits (0–100 MQM), stem unmasking, and multi-platform commercial mastering (Spotify, Apple Digital Masters, Club/DJ), KENN V6.0 bridges **creative arrangement composition** and **post-master commercial release packaging**:

1. **Autonomous Arrangement Doctor & Energy Profiler**: Analyzes arrangement structure across macro-sections (Intro, Verse, Pre-Chorus, Build-up, Drop/Chorus, Bridge, Outro), computes longitudinal energy curves, and synthesizes tension/release automation recipes (HPF sweeps, pre-drop mutes, fill insertions).
2. **Generative In-DAW MIDI Copilot**: Generates key- and scale-aware melodic counterpoint, walking/rolling sub-basslines, and groove-quantized drum patterns directly injected into Ableton Live clip slots via `MidiClipActionService`.
3. **Commercial Stem Packaging Pipeline**: Automates standard multi-track stem exports (Drums, Bass, Synths/Guitars, Vocals, FX), verifies True Peak and LUFS compliance on every isolated stem, and generates a cryptographically hashed **Master Delivery Certificate** (`certificate.json`).
4. **Vocal Resonance & Sibilance Surgeon**: Detects harsh stationary room modes, microphone resonances (2.5–4.5 kHz), and sibilance bursts (6–9 kHz), synthesizing surgical dynamic notch filters with automatic Q adaptation.
5. **Production Ship Gate & Benchmark Suite**: 100% test pass rate across all suites ($\ge 38$ automated tests), zero regressions, and tri-repo synchronization with 0 byte differences.

```text
═════════════════════════════════════════════════════════════════════════════════════════════════════
                 KENN V6.0 GENERATIVE ARRANGEMENT & COMMERCIAL RELEASE ARCHITECTURE
═════════════════════════════════════════════════════════════════════════════════════════════════════

   ┌───────────────────────────────────────────────────────────────────────────────────────────────┐
   │                         1. ARRANGEMENT & TIMELINE SENSORY PLANE                               │
   │  ┌─────────────────────────────────────────┐   ┌───────────────────────────────────────────┐  │
   │  │ Macro-Section & Energy Profiler         │   │ Musical Harmony & Scale Ingest            │  │
   │  │ - Longitudinal RMS & Crest trajectory   │   │ - Key & scale detection (Camelot / pitch) │  │
   │  │ - Clip density & transition boundary ID │   │ - Tempo, time signature, & swing grid     │  │
   │  └────────────────────┬────────────────────┘   └─────────────────────┬─────────────────────┘  │
   └───────────────────────┼──────────────────────────────────────────────┼────────────────────────┘
                           │                                              │
                           ▼                                              ▼
   ┌───────────────────────────────────────────────────────────────────────────────────────────────┐
   │                         2. KENN GENERATIVE & CREATIVE REASONING ENGINE                        │
   │  ┌─────────────────────────────────────────┐   ┌───────────────────────────────────────────┐  │
   │  │ Arrangement Doctor & Transition Crafter │   │ Generative In-DAW MIDI Copilot            │  │
   │  │ - Build-up filter sweep automation      │   │ - Counterpoint melody generator           │  │
   │  │ - 1-bar pre-drop silent cutout          │   │ - Rolling sub-bassline synthesizer        │  │
   │  │ - Dynamic density pacing                │   │ - Genre micro-timing humanizer (MPC/Dilla)│  │
   │  └────────────────────┬────────────────────┘   └─────────────────────┬─────────────────────┘  │
   │                       │                                              │                        │
   │                       ▼                                              ▼                        │
   │  ┌─────────────────────────────────────────────────────────────────────────────────────────┐  │
   │  │ Vocal Resonance Surgeon & Sibilance Suppressor                                          │  │
   │  │ - 2.5–4.5 kHz harshness tracking & 6–9 kHz sibilance suppression                        │  │
   │  │ - Automatic dynamic notch Q calibration ($Q \in [3.0, 8.0]$)                            │  │
   │  └─────────────────────────────────────────────────────────────────────────────────────────┘  │
   └────────────────────────────────────────────┬──────────────────────────────────────────────────┘
                                                │
                                                ▼
   ┌───────────────────────────────────────────────────────────────────────────────────────────────┐
   │                         3. COMMERCIAL STEM PACKAGING & SHIP GATE                              │
   │  - Multi-track stem export recipe (Drums, Bass, Melodic, Vocals, FX)                          │
   │  - Stem-level True Peak & headroom validation                                                 │
   │  - Master Quality Release Certificate (`certificate.json` + SHA-256 provenance)              │
   │  - Velvet Thunder Export Portal & 1-Click Stem Archiver                                       │
   └───────────────────────────────────────────────────────────────────────────────────────────────┘
```

---

## 1. Phase 1: Autonomous Arrangement Doctor & Energy Profiler

### 1.1 Implementation Target
- Create: `source/kenn/core/arrangement_doctor.py`
- Expose via: `source/kenn/server.py` (`POST /api/arrangement/analyze`, `POST /api/arrangement/remediate`)
- Integrate into: `source/kenn/autonomous_agent.py` as `tool_analyze_arrangement`

### 1.2 Macro-Section Identification & Energy Trajectory
The engine analyzes the arrangement timeline:
1. **Section Segmentation**: Identifies boundaries for `INTRO`, `VERSE`, `BUILDUP`, `DROP_CHORUS`, `BRIDGE`, `OUTRO`.
2. **Energy Metric**: Computes normalized Energy Index $E(t) \in [0.0, 1.0]$ based on active track count, RMS density, and high-frequency content.
3. **Contrast Validation**: Asserts that transitions into `DROP_CHORUS` provide a contrast delta $\Delta E \ge +0.25$ over the preceding `BUILDUP`.

### 1.3 Transition Automation Recipes
Synthesizes standard electronic / pop transition moves:
- **Build-up High-Pass Filter Sweep**: Automated `Eq8` band 1 high-pass filter rising from $30\text{ Hz}$ to $250\text{ Hz}$ across the 4 bars before the drop.
- **Pre-Drop Silence**: 1-beat or 1-bar master track or rhythm track mute immediately preceding beat 1 of the drop.
- **White Noise / Sub Drop Risers**: Synthesis instructions for transitional sweeps.

---

## 2. Phase 2: Generative In-DAW MIDI Copilot

### 2.1 Implementation Target
- Create: `source/kenn/core/midi_copilot.py`
- Expose via: `source/kenn/server.py` (`POST /api/midi/generate/counterpoint`, `POST /api/midi/generate/bassline`)
- Integrate into: `source/kenn/autonomous_agent.py` as `tool_generate_midi`

### 2.2 Musical Intelligence & Constraints
1. **Key & Scale Conformity**: Generates notes strictly conforming to the session scale:
   - Scales supported: `MAJOR`, `NATURAL_MINOR`, `HARMONIC_MINOR`, `DORIAN`, `PHRYGIAN`, `MIXOLYDIAN`, `PENTATONIC_MINOR`.
2. **Counterpoint Melodies**: Follows classical voice-leading heuristics (contrary motion to bass, stepwise motion with occasional leaps $\le \text{octave}$, resolution to chord tones on downbeats).
3. **Rolling Basslines**: Synthesizes genre-authentic bass patterns (16th-note rolling psy-trance, offbeat UK garage, syncopated tech-house, sustained 808 sub glide notes).
4. **Humanization & Micro-Timing Engine**:
   - Velocity jitter: Gaussian-modeled dynamic variation ($v \in [70, 110]$).
   - Micro-timing tick shift: Subtle groove offsets ($\pm 5\text{ to } 15\text{ ms}$) based on swing profiles (`MPC_16_SWING_58`, `STRAIGHT`, `DILLA_DRAG`).

---

## 3. Phase 3: Vocal Resonance & Sibilance Surgeon

### 3.1 Implementation Target
- Create: `source/kenn/core/vocal_surgeon.py`
- Expose via: `source/kenn/server.py` (`POST /api/vocal/audit`, `POST /api/vocal/de-resonate`)
- Integrate into: `source/kenn/autonomous_agent.py` as `tool_cure_vocal_resonances`

### 3.2 Acoustic Anomaly Detection & Remedy
1. **Harshness Hunter (2.5 kHz – 4.5 kHz)**: Detects excessive energy peaks representing microphone resonance or vocal strain.
2. **Sibilance Suppressor (6.0 kHz – 9.0 kHz)**: Detects high crest-factor bursts associated with un-de-essed consonants (/s/, /t/, /ch/).
3. **Surgical Dynamic Notch Synthesis**:
   - Filter type: Narrow parametric bell or dynamic notch.
   - Frequency: Exact center frequency identified by spectral peak finding.
   - Gain: Strictly clamped to $\le -3.0\text{ dB}$.
   - Q Factor: High selectivity ($Q \in [3.5, 8.0]$) to preserve vocal warmth and intelligibility.

---

## 4. Phase 4: Commercial Stem Packaging & Release Certificate

### 4.1 Implementation Target
- Create: `source/kenn/core/stem_packager.py`
- Expose via: `source/kenn/server.py` (`POST /api/stems/export-plan`, `GET /api/stems/certificate`)
- Integrate into: `source/kenn/autonomous_agent.py` as `tool_package_stems`

### 4.2 Standard Delivery Tiers & Validation
1. **Standard 5-Stem Grouping**:
   - `01_DRUMS` (Kick, Snare, Hi-hats, Percussion)
   - `02_BASS` (Sub Bass, Mid Bass, 808)
   - `03_INSTRUMENTS` (Guitars, Keys, Synths, Brass, Strings)
   - `04_VOCALS` (Lead Vocal, Backings, Ad-libs, Vocal FX)
   - `05_FX` (Sweeps, Impacts, Risers, Ambience)
2. **Per-Stem Quality Gate**:
   - Verifies each stem True Peak $\le -0.5\text{ dBTP}$.
   - Verifies no DC offset (subsonic filtered $< 20\text{ Hz}$).
3. **Master Release Certificate (`certificate.json`)**:
   - Song Title, Artist, BPM, Musical Key.
   - Final Session MQM Score & Letter Grade.
   - Final Integrated LUFS and True Peak dBTP.
   - SHA-256 hash of all stems for cryptographic provenance.

---

## 5. Phase 5: Velvet Thunder In-DAW GUI Upgrades

### 5.1 Implementation Target
- Update: `UX/app.js` & `UX/styles.css`
- Update: `vst3-plugin/Source/PluginEditor.h` & `PluginEditor.cpp`

### 5.2 UI Components
1. **Arrangement Macro-Timeline**: Horizontal energy bar visualization displaying detected song sections and energy dips.
2. **Generative MIDI Trigger Card**: 1-click generation buttons for "Generate Counter-Melody" and "Generate Rolling Bassline".
3. **Commercial Release & Stem Packaging Portal**: Summary badge displaying stem export readiness and certificate generator.

---

## 6. Phase 6: Production Ship Gate & Tri-Repo Synchronization

### 6.1 Parity Across 3 Codebases
All code must be byte-for-byte synchronized across:
1. `Nite-DSP-Operations/Shenrendao/KENN/`
2. `Nite-DSP-Operations/monorepo/products/kenn/`
3. `Nite-DSP-Operations/Shenrendao/KENN/UX/velvet_thunder/studio/kenn/`

### 6.2 Test Suites to Implement & Pass
1. `products/kenn/tests/test_arrangement_doctor.py`:
   - Validates section segmentation and pre-drop contrast synthesis.
2. `products/kenn/tests/test_midi_copilot.py`:
   - Validates key/scale conformity, voice leading, and swing humanization.
3. `products/kenn/tests/test_vocal_surgeon.py`:
   - Validates harshness/sibilance detection and narrow dynamic notch Q clamping.
4. `products/kenn/tests/test_stem_packager.py`:
   - Validates 5-tier stem grouping, True Peak verification, and certificate generation.
5. Full Regression Pass:
   - Ensure all existing 30 tests from V1–V5 continue to pass with 100% success rate (total $\ge 38$ passing tests).

---

## 7. Deliverables & Acceptance Criteria

1. **Source Code**:
   - `source/kenn/core/arrangement_doctor.py`
   - `source/kenn/core/midi_copilot.py`
   - `source/kenn/core/vocal_surgeon.py`
   - `source/kenn/core/stem_packager.py`
   - Updated `autonomous_agent.py`, `server.py`, `app.js`, `styles.css`, `PluginEditor.h`, `PluginEditor.cpp`
2. **Test Suites**:
   - `tests/test_arrangement_doctor.py`
   - `tests/test_midi_copilot.py`
   - `tests/test_vocal_surgeon.py`
   - `tests/test_stem_packager.py`
   - Minimum **38 passing tests** across all suites.
3. **Tri-Repo Parity**:
   - 0 byte differences across `Shenrendao/KENN`, `monorepo/products/kenn`, and `velvet_thunder/studio/kenn`.
4. **Reports**:
   - `KENN_V6_ARRANGEMENT_STEM_DELIVERY_AND_DISTRIBUTION_VERIFICATION_REPORT.md`
   - Update `walkthrough.md`
   - Update `root-docs/KENN_DAILY_EXECUTION_LOG_2026-09-18.md`

