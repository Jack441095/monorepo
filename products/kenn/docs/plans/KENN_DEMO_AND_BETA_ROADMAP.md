# KENN: Roadmap to Demo & Public Beta

**Status**: Active Roadmap

**Target Platform**: macOS (Apple Silicon arm64 / Intel x86_64) · Ableton Live 12 (Suite / Standard)

**Date**: September 17, 2026

**Architecture**: Native JUCE VST3/AU Plug-in + Local Python Companion (8090) + AbletonOSC Bridge + Hybrid Vector Retrieval (3,415 chunks) + Remote GPU 1

---

## Executive Summary

KENN has achieved foundational readiness:
- **Full Hybrid Knowledge Engine**: 389 approved production notes, the complete Ableton Live 12 Manual (1,689 chunks), and pro artist masterclass notes (Virtual Riot, Noisia, Feed Me) fully indexed in ONNX embeddings (`v-a811d631df5c`).
- **Autonomous Session Doctor**: Live session auditing for clipping, stereo correlation inversions ($\rho < 0$), sub-bass phase widening, and low-end mud, with atomic batch remediation.
- **Generative MIDI & Clip Composer**: Scale-aware chord progressions, Bjorklund Euclidean rhythms, and Drum Rack pattern builders.
- **Universal Plug-in Suite**: JUCE 8 VST3 and AU bundles compiled, signed, and installed to `~/Library/Audio/Plug-Ins/`.
- **Verified Control & Safety**: Confirmation-gated mutations, cryptographic HMAC tokens, readback receipts, and one-click undo.

This roadmap outlines the strict path from **today's working codebase** to an **impressive end-to-end Demo**, followed by a **hardened, packaged Beta release**.

---

```
                                  KENN ROADMAP TIMELINE


  [CURRENT STATE]
   • 3,415-chunk vector index active
   • Session Doctor & Gen MIDI engine built
   • VST3/AU plug-ins compiled on macOS
   • 52/52 server & 89/89 MCP tests passing
          │
          ▼
  ┌─────────────────────────────────────────────────────────────┐
  │  MILESTONE 1: THE INTERACTIVE LIVE 12 DEMO (Days 1–2)       │
  │  - Curated Demo Project (`KENN_Demo_Project.als`)           │
  │  - 4-Act Live Narrative Script (Q&A, Gen MIDI, Doctor, Undo)│
  │  - 4K Screen Recording & Walkthrough Assets                 │
  └─────────────────────────────────────────────────────────────┘
          │
          ▼
  ┌─────────────────────────────────────────────────────────────┐
  │  MILESTONE 2: UX UNIFICATION & LATENCY TUNING (Days 3–5)    │
  │  - Seamless VST3 Webview UI (Vue 3 embedded)                │
  │  - Low-latency query caching (<200ms Live state snapshots)  │
  │  - Fail-closed boundary testing with Ableton 12             │
  └─────────────────────────────────────────────────────────────┘
          │
          ▼
  ┌─────────────────────────────────────────────────────────────┐
  │  MILESTONE 3: BETA PACKAGING & INSTALLATION (Week 2)        │
  │  - One-click macOS Installer (.pkg / .dmg)                  │
  │  - Developer ID Codesigning & Apple Notarization            │
  │  - Automated AbletonOSC & Remote Script Installer           │
  │  - Standalone Companion App Bundling                        │
  └─────────────────────────────────────────────────────────────┘
          │
          ▼
  ┌─────────────────────────────────────────────────────────────┐
  │  MILESTONE 4: CLOSED BETA LAUNCH (Weeks 3–4)                │
  │  - 15-Pro Producer Cohort (Bass, EDM, Hip-Hop, Pop)         │
  │  - Structured Feedback Harness & Telemetry                  │
  │  - Zero-Crash Hardening & Iterative Polish                  │
  └─────────────────────────────────────────────────────────────┘
```

---

## Milestone 1: The Interactive Live 12 Demo (Days 1–2)

### Objective
Produce a flawless, repeatable 3-to-5 minute video and live demonstration of KENN operating inside Ableton Live 12.

### Deliverables
1. **Curated Ableton Live 12 Disposable Demo Set** (`assets/demo/KENN_Live12_Demo.als`):
   - Track 1: `Drums` (Kick, Snare, Hi-hats).
   - Track 2: `Sub Bass` (deliberately widened or offset to showcase Session Doctor).
   - Track 3: `Synth Leads` (slightly harsh high-mids, missing EQ Eight).
   - Track 4: `Vocal Stem` (needs de-mudding and headroom cleanup).
   - Track 5: `Empty MIDI` (target for generative composition).

2. **The 4-Act Demo Narrative**:
   - **Act 1: Production Intelligence (Knowledge Retrieval)**:
     - Prompt: *"How does Virtual Riot configure the Fat Rack multiband OTT macro chain?"*
     - Outcome: Instant grounded response quoting the masterclass notes with precise frequency bands and macro depth settings.
   - **Act 2: Generative Musical Assistance (Live 12 MIDI Tools)**:
     - Prompt: *"Generate a 16-step Euclidean rhythm for hi-hats and a D minor chord progression."*
     - Outcome: Real-time creation of MIDI clips in Live 12 with scale-quantized notes and velocity dynamics.
   - **Act 3: Autonomous Session Doctor (Mix Audit)**:
     - Prompt: *"Run Session Doctor and check my mix headroom and low-end phase."*
     - Outcome: Discovers sub-bass phase cancellation and track 4 clipping risk; presents an atomic remediation card.
   - **Act 4: Confirmation Gating & Reversible Live Control**:
     - Prompt: *"Add EQ Eight to Synth Lead and cut 3 dB at 250 Hz."*
     - Action Card appears with cryptographic token; user clicks **Confirm**; EQ Eight is inserted into Live 12; readback receipt validates state; user clicks **Undo** to demonstrate zero risk.

3. **Automated Demo Runner**:
   - Enhance [`scripts/record_demo_live.py`](file://<WORKSPACE_ROOT>/Nite-DSP-Operations/Shenrendao/KENN/scripts/record_demo_live.py) to run the 4-act demo automatically and record audio/screen.

### Exit Criteria
- Video demo recorded with crisp 60fps audio/video, displaying both the Ableton Live 12 window and the KENN VST3 plugin UI with zero glitches.

---

## Milestone 2: UX Unification & Latency Tuning (Days 3–5)

### Objective
Ensure instantaneous interaction and seamless UI rendering across both standalone browser and embedded VST3/AU plug-ins.

### Tasks
1. **Webview UI Embedding Verification**:
   - Validate `juce::WebBrowserComponent` within the native VST3/AU shell connecting to `http://127.0.0.1:8090`.
   - Ensure responsive layout adaptation for standard plugin window dimensions ($800 \times 600$ to $1200 \times 800$).
   - Fallback graceful state if companion is restarting or stopped (displaying "Local Mix Check" offline meters).

2. **Latency Budget Enforcement (< 1,500 ms Total Turnaround)**:
   - Live Session Snapshot: < 100 ms (batched OSC querying).
   - Knowledge Vector Retrieval: < 60 ms (pre-warmed ONNX embeddings).
   - Action Card Generation: Streaming first token within 300 ms.

3. **Fail-Closed Safety Stress Testing**:
   - Verify that invalid commands, out-of-range gains ($> \pm 3.0\text{ dB}$), and unauthorized tracks are rejected cleanly.

### Exit Criteria
- `test_kenn_live_subsystems.py` runs with 100% pass rate in under 15 seconds.
- Mean turnaround time for Live inspection queries is under 1.5 seconds.

---

## Milestone 3: Beta Packaging & Distribution (Week 2)

### Objective
Create a consumer-ready, self-contained installer for macOS that installs KENN with one click.

### Deliverables
1. **macOS Universal Installer Package (`KENN_Mix_Assistant_v0.1.0.pkg`)**:
   - Installs `KENN Mix Assistant.vst3` to `/Library/Audio/Plug-Ins/VST3/`.
   - Installs `KENN Mix Assistant.component` to `/Library/Audio/Plug-Ins/Components/`.
   - Installs `AbletonOSC` into `~/Music/Ableton/User Library/Remote Scripts/`.

2. **Companion Service Runner (`KENN Companion.app`)**:
   - Lightweight macOS status bar / tray app (or launchd daemon) that manages the background Python server and index cache.
   - Clean Start / Stop / Status toggle with health monitor.

3. **Code Signing & Notarization**:
   - Sign all Mach-O binaries and bundles with Apple Developer ID.
   - Run `xcrun notarytool submit` and staple tickets to allow Gatekeeper approval without security warnings.

4. **Beta User Guide (`docs/BETA_QUICKSTART_GUIDE.md`)**:
   - 3-step setup: Install pkg $\rightarrow$ Select KENN Bridge in Ableton MIDI Preferences $\rightarrow$ Insert KENN VST3 on Master Track.

### Exit Criteria
- Fresh macOS machine (clean VM or test profile) can install KENN via PKG and achieve full Live 12 bidirectional control in under 3 minutes without terminal commands.

---

## Milestone 4: Closed Beta Rollout (Weeks 3–4)

### Objective
Distribute to 15-20 trusted music producers, mixing engineers, and sound designers to gather real-world telemetry and workflow feedback.

### Beta Cohort Segmentation
- **Cohort A (Electronic / Sound Design)**: Virtual Riot / dubstep style sound designers testing macro modulation and generative rhythms.
- **Cohort B (Hip-Hop / Trap / Beatmakers)**: Drum pattern generation, 808 sub-bass phase centering, and sample slicing.
- **Cohort C (Mix / Mastering Engineers)**: Headroom management, stem masking analysis, and reference curve matching.

### Telemetry & Feedback Mechanics
- Redacted crash reports and telemetry logs (strictly zero raw audio files transmitted).
- Weekly triage of requested Live 12 device parameter controls.
- Exit criteria for Public Launch: Zero crash reports across 100+ active studio hours.

---

## Immediate Action Items (Today)

1. **Step 1**: Assemble `assets/demo/KENN_Live12_Demo.als` with the standard 4-track template.
2. **Step 2**: Test the 4-act demo sequence using `scripts/demo_plugin_live.py`.
3. **Step 3**: Verify the embedded VST3 plugin inside Ableton Live 12.

