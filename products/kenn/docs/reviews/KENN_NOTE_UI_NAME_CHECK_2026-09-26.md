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
