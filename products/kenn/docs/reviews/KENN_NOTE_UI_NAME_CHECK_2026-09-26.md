# KENN notes: controls that don't exist in Live

**Checked:** 2026-09-26 · **Status:** approved by Jack (26 Sept); applied after soak #4, because the tester build copies the notes

KENN tells producers where to click, so a made-up control name is a wrong answer they can't follow. Every "Try this"
step in the 325 approved notes about Live was checked against the Live 12 manual (the owner's PDF, as text): each
quoted name, each run of Title Case words, and each name before "button", "switch", "knob", "menu" and so on
(`tooling/scripts/check_note_ui_names.py`). 1,572 names were checked and 87 weren't found. Most of those are fair
(sections plus controls like "Crackle Density", Max for Live CV Tools, third-party plug-ins, scale names). Each was read
against the manual by hand; these are the ones that are wrong.

Almost all come from the `ableton12-…` notes a notes model drafted on 18 Sept. They also all carry
"Source: Official Reference Documentation", which isn't accurate for them (nor for the 75 Baphometrix and 23 FabFilter
notes that carry the same line). Users don't see that line: KENN shows these notes as "Curated KENN guidance".

## Wrong, with a proposed correction

| Note | Step now | Proposed | Manual |
|---|---|---|---|
| `ableton12-launching-clips-pt3.md` | Set follow action to "Quantized Follow" in the clip's launch options. | Turn on Legato Mode in the clip's Launch settings, so the next clip takes over the play position without losing sync. | 16.3 Legato Mode |
| `ableton12-launching-clips-pt2.md` | Use Random Jump in Follow Actions for unpredictable remixes. | Use the Any or Other Follow Action for random order, or Jump with a Jump Target to go to a chosen clip. | 16.7 Follow Actions |
| `ableton12-clip-envelopes-pt3.md` | Enable "Unlink Envelopes" in the Clip Envelope Editor (right-click > "Unlink Envelopes"). | Unlink the envelope from the clip so it gets its own loop length. | "Clip envelopes can be unlinked from the clip to give them independent loop settings" |
| `ableton12-audio-clips-warping-pt3.md` | Adjust the Warp Strength to 100% for maximum precision. | Delete the step (Complex Pro's controls are Formants and Envelope). | 9.3.5 Complex and Complex Pro Mode |
| `ableton12-midi-fact-sheet-pt3.md` | Enable "Use Internal Clock" in Preferences > Audio > MIDI Settings. / enable "MIDI Through" and set buffer size to 128. / Enable "MIDI Sync" in Preferences > MIDI. | In Settings → Link, Tempo & MIDI, turn on Sync only for the port that sends or receives MIDI Clock; set the buffer size in Settings → Audio. Delete "Use Internal Clock" and "MIDI Through". | 17.3.1.2 Sync |
| `ableton12-mixing-pt2.md` | …select a curve from the context menu (e.g., "Slope 1" for sharp transitions). | …right-click the crossfader and pick one of its seven curves. | 18.5 Using Live's Crossfader |
| `ableton12-live-midi-effects-ref-pt3.md` | Click the "Add Envelope" button to create a new envelope. | In the clip's Envelopes panel, choose the device and then the parameter from the two choosers. | Clip Envelopes |
| `ableton12-using-tuning-systems-pt2.md` | Load an SCL file using the "Load Tuning System" button. | Double-click a tuning file in the browser, or select it and press Enter. | 15.1 Loading a Tuning System |
| `ableton12-live-audio-effect-reference-pt12.md` | Select a routing point from the Sidechain chooser (e.g., Master Output). | …(e.g., the Main track). Live 12 calls it Main. | 18.4 Return Tracks and the Main track |
| `ableton12-live-instruments-ref-pt8.md` | Enable Modulation in the global display and set Modulation Source to "Osc A" and Modulation Destination to "Osc B". | Pick an algorithm in the global display where oscillator A modulates B; A's Level sets how much. | Operator |
| `ableton-clip-envelopes.md` | select "EQ Eight" > "Frequency 1" | select "EQ Eight" > "1 Frequency A" | parameter chooser names |

## Not in the manual, worth a check

- `ableton12-editing-midi-pt4.md`: "Play All/Play One" probability groups. May be newer than this manual (12.0).
- `ableton12-live-instruments-ref-pt4.md` (Drift): "Freq Mod Source", "Freq Mod Amount".
- `ableton12-live-audio-effects-ref-pt17.md` (Spectral Time): "Freeze Time Unit", "Delay Parameters".

## What this doesn't catch

Only names are checked. A step can use real names and still be wrong (the MPE note says to enable "MPE" in an
instrument's MIDI tab, which isn't how Live does it). Checking the claims themselves needs a person or a much stronger
model with the manual section; Qwen3 8B was tried as a judge and flagged too many true steps to be useful.

## What's applied (`workspace/tmp/kenn-ops/apply_note_corrections.py`, originals backed up first)

Reading the whole of each flagged note showed that in five of them most steps were invented, not just one name, so
those go to **Status: Draft** (the index skips drafts) rather than being patched: `launching-clips-pt3`,
`clip-envelopes-pt3`, `live-midi-effects-ref-pt3`, `midi-fact-sheet-pt3`, `live-instruments-ref-pt8` (Operator).
KENN still has correct notes on each topic. Crossfader, tuning systems and Complex Pro get their "Try this" rewritten
from the manual; Follow Actions, Multiband Dynamics' sidechain and the EQ Eight parameter name get the one-step fixes
above (the rest of the Multiband note matches the manual). Then the index is rebuilt and the intelligence gate and review
packet re-run on the next build.

## Full review of the ableton12-… notes (26 Sept, Jack: "do the full review pass")

A random sample of 20 found roughly 4 in 10 with a wrong step and 1 in 7 wrong throughout, so every one of the 201
remaining approved `ableton12-…` notes was read against the Live 12 manual (control names, menus, what things do;
anything uncertain was looked up in the manual text). The manual overruled the reviewer several times ("Enable Send",
Capture MIDI's 80-160 BPM range, Drift's Freq Mod section and Probability Groups are all real), so those stayed.

| Outcome | Notes |
|---|---|
| Kept as they are | 148 |
| Wrong steps fixed or removed | 25 |
| Moved to Draft (invented throughout) | 28 |

With the 11 above, 33 notes go to Draft and 31 are corrected. Decisions, with the exact step text changed, are in
`KENN_ABLETON12_NOTE_REVIEW_2026-09-26.json`; `workspace/tmp/kenn-ops/apply_note_corrections.py` applies them all after
soak #4 (originals backed up; every step must match exactly or nothing is written).

What the review can't promise: kept notes use real controls in a sensible order, but their example values ("Rate 2 Hz",
"Drive 50%") are starting points, not checked recommendations.

### Moved to Draft

- `ableton12-arrangement-view-pt4.md`: clip envelopes have no attack/release, sine shape, lock or stretch settings, and there is no MIDI Controller Clip Envelope option
- `ableton12-audio-clips-warping-pt4.md`: Warp Resolution, Transient Preservation and a Beats setting inside Complex Pro don't exist
- `ableton12-audio-effect-racks-parallel-chain-splitting.md`: suggests Kontakt 6 as a compressor and Drum Rack pads for frequency splitting
- `ableton12-audio-effect-racks-pt4.md`: devices don't output to a main or parallel chain, and the Zone Editor doesn't route audio
- `ableton12-audio-fact-sheet-pt2.md`: there is no global 32-bit float setting in Settings > Audio, and Utility's Width doesn't manage panning loss
- `ableton12-automation-and-editing-envelopes-pt3.md`: no Thin Automation switch, and envelopes have no attack/release
- `ableton12-comping-pt2.md`: there are no Take 1/2/3 buttons or Crossfade tool; take lanes come from recording
- `ableton12-comping-pt3.md`: no Crossfade tool, Auto-Align or Comping device in Live
- `ableton12-computer-audio-latency-pt2.md`: no Device > Device Delay Compensation menu; the Track Freeze steps repeat
- `ableton12-computer-audio-latency-pt3.md`: delay compensation isn't in Preferences > Audio > MIDI Timing; returns don't bypass effects
- `ableton12-converting-audio-to-midi-pt2.md`: invented settings (Sensitivity, Threshold, MIDI Note Stretch) and a wrong location for the conversion commands
- `ableton12-converting-audio-to-midi-pt3.md`: there is no Convert to MIDI render with rendering settings; mixes up the audio fact sheet
- `ableton12-editing-mpe-pt2.md`: no Preferences > MIDI > MPE path and no MPE mode inside a clip
- `ableton12-editing-mpe-pt3.md`: instruments have no MIDI tab with MPE and Per Note settings
- `ableton12-live-audio-effect-reference-pt16.md`: Shifter's delay isn't set in Hz, and Spectral Resonator's Stretch and Harmonics don't do what it says
- `ableton12-live-audio-effects-ref-pt13.md`: Redux and Resonators have no LFO2 or envelope follower section
- `ableton12-live-audio-effects-ref-pt20.md`: invented Push 2 features: a 64-pad step mode setting, 32-note loops, MIDI learn to pads
- `ableton12-max-for-live-devices-pt5.md`: invented connections: an LFO into Shaper's frequency input at 440 Hz, a Shaper Waveform mode with resonance
- `ableton12-midi-fact-sheet-pt2.md`: Clip Quantization is launch quantization, and there is no Groove tab or Groove Strength in the MIDI Note Editor
- `ableton12-midi-tools-pt4.md`: no Arpeggiator mode in the MIDI Tools, and Seed, Time Warp and Strum don't have those settings
- `ableton12-midi-tools-pt5.md`: there is no MIDI Transform device or Note Mode on a track
- `ableton12-mixing-manual-pt3.md`: fixed return and main levels as rules, and the crossfader doesn't blend returns with the main track
- `ableton12-routing-and-io-pt2.md`: return tracks have no input choosers and can't be armed to record
- `ableton12-routing-and-io-pt4.md`: no Group or Monitor buttons on track headers for routing to a group, and sends aren't set in percent
- `ableton12-session-view-pt3.md`: no Add Envelope button, envelope attack/sustain/release or Link to Clip option
- `ableton12-stem-separation-pt2.md`: the command and a Separation Speed setting are invented; the rest is generic effect settings
- `ableton12-stem-separation-pt3.md`: stems are audio, not MIDI; the steps don't describe stem separation
- `ableton12-using-tuning-systems-pt3.md`: no Device > MIDI > MIDI Settings menu or Sync to Live option; MIDI sync is set per port in Link, Tempo & MIDI

### Corrected

- `ableton12-audio-effect-racks-pt1.md`
- `ableton12-clip-view-pt2.md`
- `ableton12-device-delay-compensation-and-latency.md`
- `ableton12-editing-midi-pt1.md`
- `ableton12-internal-audio-routing-and-sidechain-tapping.md`
- `ableton12-live-audio-effect-reference-pt7.md`
- `ableton12-live-audio-effect-reference-pt9.md`
- `ableton12-live-audio-effects-ref-pt16.md`
- `ableton12-live-audio-effects-ref-pt19.md`
- `ableton12-live-audio-effects-ref-pt8.md`
- `ableton12-live-concepts-pt2.md`
- `ableton12-live-instrument-reference-pt8.md`
- `ableton12-live-instruments-ref-pt1.md`
- `ableton12-live-instruments-ref-pt17.md`
- `ableton12-live-instruments-ref-pt18.md`
- `ableton12-live-instruments-ref-pt4.md`
- `ableton12-live-keyboard-shortcuts-pt2.md`
- `ableton12-live-midi-effect-reference-pt1.md`
- `ableton12-live-midi-effects-ref-pt4.md`
- `ableton12-managing-files-and-sets-pt2.md`
- `ableton12-midi-tools-pt3.md`
- `ableton12-mixer-gain-staging-and-headroom.md`
- `ableton12-mixing-manual-pt2.md`
- `ableton12-using-grooves-pt2.md`
- `ableton12-warp-algorithms-and-transient-preservation.md`
