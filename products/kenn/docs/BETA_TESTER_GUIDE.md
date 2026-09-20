# KENN Mix Assistant — Closed Beta Producer Onboarding Guide

**Version:** 0.2.0-beta

**Build:** Universal macOS (Apple Silicon M1/M2/M3/M4 & Intel x86_64)

**Supported DAWs:** Ableton Live 11.1+ and Ableton Live 12+ (Suite recommended)

**Security & Privacy:** Hardware-Grade Safety Guardrails · Zero-Audio Telemetry Guarantee

**In-DAW GUI:** Native JUCE 8 WebBrowserComponent with bi-directional DAW parameter synchronization

**Daemon:** Automated background LaunchAgent (`com.shenrendao.kenn.companion`)


---

## 1. Welcome to the Closed Beta

KENN Mix Assistant is an autonomous, on-device AI copilot and mix engineer built specifically for Ableton Live producers. Unlike generic LLMs that generate text disconnected from your session, KENN maintains an active **Semantic Session World Model** of your Ableton set, executes scale-aware generative MIDI, conducts 40-band ERB psychoacoustic mix audits, and applies reversible, confirmation-gated DAW mutations.

With v0.2.0, KENN features an ultra-low-latency pipeline:
- **Instant Fast-Path:** Conversational greetings and state routing in **< 15 ms**.
- **Live OSC Topology:** Sub-millisecond (**< 0.2 ms**) Ableton session inspection.
- **Apple Silicon Acceleration:** Apple MLX 4-bit local LLM inference (>100 tokens/sec) and CoreML ANE-accelerated vector embeddings.
- **Embedded Web UI:** The native VST3 and AU plugins embed an interactive JUCE 8 `WebBrowserComponent` connecting directly to the local companion.

---

## 2. System Requirements

- **Operating System:** macOS 12 Monterey, macOS 13 Ventura, macOS 14 Sonoma, or macOS 15 Sequoia / macOS 26.
- **Architecture:** Apple Silicon (arm64 native) or Intel (x86_64).
- **DAW:** Ableton Live 11.1+ or Ableton Live 12+.
- **Free Disk Space:** 500 MB (includes ONNX hybrid vector embeddings and local runtime).
- **Network:** 100% on-device local companion runner (`127.0.0.1:8090`); zero audio ever leaves your machine.

---

## 3. Installation Options

### Option A: 1-Click Native Installer (Recommended)
1. Double-click `dist/KENN_Mix_Assistant_v0.2.0.pkg` (SHA-256: `75835fd8bf4de0779ec1e792f3a20e6f6450c091e18bada6fb8e8f7410218e2e`).
2. Follow the standard macOS installer prompts (requires admin authentication).
3. The installer automatically deploys:
   - **VST3 Plugin:** `/Library/Audio/Plug-Ins/VST3/KENN Mix Assistant.vst3`
   - **Audio Unit:** `/Library/Audio/Plug-Ins/Components/KENN Mix Assistant.component`
   - **Remote Scripts:** Links `KENN_Bridge` and `AbletonOSC` into `~/Music/Ableton/User Library/Remote Scripts/`.
   - **Demo Session:** Installs `KENN_Live12_Demo.als` into your User Library.
4. Enable the background companion LaunchAgent:
   ```bash
   bash scripts/install_launchagent.sh
   ```
   The companion daemon will automatically start at login, listening at `http://127.0.0.1:8090` with logs written to `~/Library/Logs/KENN/kenn_companion.log`.

### Option B: Manual Installation
If you prefer manual setup:
1. Copy `KENN Mix Assistant.vst3` to `~/Library/Audio/Plug-Ins/VST3/`.
2. Copy `KENN Mix Assistant.component` to `~/Library/Audio/Plug-Ins/Components/`.
3. Copy `integrations/ableton-remote-script/KENN_Bridge` to `~/Music/Ableton/User Library/Remote Scripts/`.
4. Install and load the LaunchAgent:
   ```bash
   cp source/launchd/com.shenrendao.kenn.companion.plist ~/Library/LaunchAgents/
   launchctl load -w ~/Library/LaunchAgents/com.shenrendao.kenn.companion.plist
   ```

---

## 4. Ableton Live Configuration

To allow KENN to read your session hierarchy and automate mixing workflows:

1. Launch **Ableton Live 11** or **Ableton Live 12**.
2. Open **Settings** (macOS: `Cmd + ,`), then navigate to the **Link / Tempo / MIDI** tab.
3. Under **Control Surfaces**:
   - **Slot 1:**
     - *Control Surface:* Select **`AbletonOSC`**
     - *Input / Output:* Set both to **`None`**
   - **Slot 2:**
     - *Control Surface:* Select **`KENN_Bridge`**
     - *Input / Output:* Set both to **`None`**
4. Close Settings. Ableton is now linked to KENN's local OSC bridge.

### Port Topology Reference
- **OSC Send Port (DAW -> Companion):** UDP `11000`
- **OSC Receive Port (Companion -> DAW):** UDP `11001`
- **Companion REST API & Web Hub:** HTTP `http://127.0.0.1:8090`

---

## 5. Five Core Studio Workflows & Cheat-Sheet

### Workflow 1: Grounded Knowledge Retrieval
Ask KENN technical sound design, mixing, and routing questions. KENN retrieves exact parameters and macros from 3,415 artist masterclass chunks.

*Producer Prompt Ideas:*
- `"Virtual Riot fat rack multiband ott workflow macro"`
- `"How should I set the attack and release on a glue compressor for a punchy drum bus?"`
- `"What frequencies should I cut on synth pads to unmask lead vocals?"`

### Workflow 2: Scale-Aware Generative MIDI
Generate multi-voice chord progressions snapped to 16 musical modes, or Euclidean rhythms for complex percussion.

*Producer Prompt Ideas:*
- `"Generate a D Dorian 4-bar chord progression on Track 3"`
- `"Generate a 16-step Euclidean rhythm with 5 hits on Track 2 (Kick)"`
- `"Add a trap hi-hat pattern with 32nd note rolls on Track 4"`

### Workflow 3: Autonomous Session Doctor & Psychoacoustics
KENN audits your active Ableton set across 40 Glasberg & Moore ERB critical bands, flagging inter-sample peak risks, phase cancellations, and sub-bass panning errors.

*Producer Prompt Ideas:*
- `"Run session doctor on my mix"`
- `"Check for mud between 200 Hz and 400 Hz on my synths and bass"`
- `"Audit master bus headroom and stereo correlation"`

### Workflow 4: Hardware-Guarded Parameter Adjustments
KENN adheres to strict safety guardrails:
- **Gain Clamping:** Parameter changes are capped at $\Delta \le \pm 3.0\text{ dB}$ (0.20 normalized limit).
- **Master Bus Lock:** Master fader adjustments are strictly locked.
- **Confirmation Gating:** KENN returns a cryptographic HMAC-SHA256 proposal token. Changes only execute when you confirm.

*Producer Prompt Ideas:*
- `"Set Track 2 volume to -6 dB"`
- `"Add EQ Eight to Track 4 and boost 8 kHz by 2 dB"`
- `"Freeze track 3 to save CPU"`

### Workflow 5: 1-Click Zero-Risk Undo
Every action generates an atomic readback receipt recording exact pre-state values. Click **Undo** in the plugin UI or issue:
- `"Undo last change"`
KENN reverses the change instantaneously with zero risk of session corruption.

---

## 6. Menu Bar Companion & Tray Runner

You can manage the background companion server and access quick actions directly from your macOS menu bar:

```bash
python3 scripts/kenn_tray.py --gui
```

**Tray Menu Features:**
- **Status Indicator:** Shows live connection status to Ableton Live and KENN server.
- **Open KENN Web Hub:** Launches `http://127.0.0.1:8090` in your default browser.
- **Start / Stop KENN Server:** 1-click background process management.
- **Open Live 12 Demo Project:** Loads `KENN_Live12_Demo.als` with pre-configured routing and stems.
- **Install Live Remote Scripts:** Automatically verifies and updates your Ableton Remote Scripts.

---

## 7. Zero-Audio Telemetry Guarantee

Your music, stems, and creative ideas belong exclusively to you. KENN operates under a strict **Zero-Audio Telemetry Guarantee**:

- **NEVER Transmitted:**
  - Raw audio samples, buffers, or waveforms.
  - Stems or bounced tracks.
  - MIDI notes, pitches, or melodies.
  - Project file names or lyrics.
- **Anonymized Metrics Logged (Local Buffered):**
  - Session startup / shutdown timestamps.
  - Command latency and error codes (e.g., OSC timeout).
  - Feature engagement counts (e.g., number of Session Doctor audits run).
  - Stored locally in `~/.kenn/beta_telemetry.jsonl` (capped at 5 MB).
- **Opt-Out:** Set `export KENN_TELEMETRY_OPT_OUT=1` in your shell to completely disable telemetry logging.

---

## 8. Submitting Beta Feedback & Bug Reports

We value your real-world mixing feedback! You can submit comments, feature requests, or bug reports in two ways:

### Option 1: In-App Web Hub
Open `http://127.0.0.1:8090` and click the **Feedback** button in the top navigation bar.

### Option 2: Terminal Curl
```bash
curl -X POST http://127.0.0.1:8090/api/feedback \
  -H "Content-Type: application/json" \
  -d '{
    "kind": "beta_tester_feedback",
    "rating": "useful",
    "comment": "Session Doctor caught a +0.35 sub pan collision instantly.",
    "question": "Can KENN suggest sidechain curves for OTT?"
  }'
```

---

## 9. Troubleshooting & FAQ

**Q: KENN plugin says "Ableton OSC Offline".**

**A:** Verify that `AbletonOSC` is selected as an active Control Surface in Ableton Live `Preferences > Link/Tempo/MIDI`. Then verify port 11000 is not blocked by a third-party firewall.

**Q: Audio Unit is not showing up in Logic Pro or Ableton Live.**

**A:** Run macOS Audio Unit cache reset:
```bash
killall -9 AudioComponentRegistrar
auval -v aufx KnMa AECO
```

**Q: Companion server port conflict on 8090.**

**A:** Change the port using the `KENN_PORT` environment variable:
```bash
KENN_PORT=8095 python3 apps/backend/src/kenn/server.py
```

**Q: Where can I review my action logs and receipts?**

**A:** Action receipts and rollbacks are saved in your session journal at `~/.kenn/receipts/` or displayed directly in the KENN Web Hub.

