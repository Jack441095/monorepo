# KENN private beta: tester guide

Thanks for testing KENN. This guide covers what the beta does, how to install it, and what to do when something
goes wrong. It describes only what ships in this build.

**Needs:** an Apple Silicon Mac (M1 or later) and Ableton Live 12 (Suite, Standard or Intro).
Tested so far on Live 12.4.6 Suite; other Live 12 versions are expected to work but are not yet verified.
Intel Macs and Live 11 are not supported.

## What KENN does in this beta

1. **Knows your session.** Ask about your tracks, what's selected, your devices, returns and master, and what KENN
   changed recently.
2. **Changes Live safely.** Ask for a change ("bring the bass down 2 dB", "pan the synth hard left"). KENN shows
   exactly what it will change and does nothing until you press **Apply to Live 12**. It then checks Live did it,
   and every change can be undone.
3. **Answers with sources.** Ask how a device or technique works; answers cite KENN's notes, which cover 77 of
   Live 12's 78 built-in devices. When it doesn't know, it says so.
4. **Listens to an exported mix.** Load a WAV of your mix (and optionally a reference) in the **Inputs** panel for a
   review of loudness, true peak, clipping and balance.
5. **Refuses risky requests.** It won't delete things, push your master level, or change anything you didn't Apply.

**Not in this beta:** the AI planner changing Live on its own, automatic mixing, audio generation and voice control.

## Install (about 5 minutes)

1. Open `KENN-beta-….dmg` and drag **KENN** into **Applications**.
2. The first time only, **right-click KENN in Applications and choose Open**, then **Open** again. (This beta
   build isn't notarized by Apple yet, so a normal double-click is blocked the first time.)
3. KENN opens on **Set up KENN** with three checks:
   - **Ableton Live 12 is installed**
   - **KENN's AbletonOSC is in Live's User Library** — press **Install KENN's AbletonOSC**. KENN finds your User
     Library automatically, including one on an external drive. An older copy is kept in a hidden backup folder.
   - **Live is connected to KENN** — in Live, open **Settings → Link, Tempo & MIDI**. In a free **Control Surface**
     slot choose **AbletonOSC**, with Input and Output set to **None**. If Live was already open when you installed,
     quit and reopen Live.
4. When all three are ticked, press **Open KENN**. Next time KENN goes straight in.

Only select **AbletonOSC** for KENN. Don't also enable other KENN or OSC scripts: they use the same port and stop
KENN connecting.

## Things to try

| Ask | What happens |
|---|---|
| `How many tracks do I have?` / `What's selected?` / `Describe this session.` | Answers from your open set |
| `Bring the bass down 2 dB` / `Put the kick at -12 dB` | A proposal in dB; nothing changes until Apply |
| `Pan the synth 20% left` / `Mute the hats` | Proposal, Apply, then "Readback Verified" |
| `Undo that` or the **Undo** button on a card | Puts the exact previous value back |
| After a change: `Do that on the snare too` / `Same for the hats` / `Do the opposite on the vocal` | The same change on another track, as a new proposal |
| Wrong track? `No, I meant the snare` / `Sorry, the kick` | Moves the change to the track you meant; if you'd already applied it, KENN says so and you can say `undo` |
| When KENN asks "By how much?" or "Which side?", just answer: `3 dB`, `30%`, `left` | Finishes the request you started |
| `What did you change?` | The recent changes, with before and after values |
| `What does Note Echo do?` | A cited answer from KENN's notes |
| A mix WAV in **Inputs** | Review of loudness, true peak, clipping and balance |

## Your data stays on your Mac

- KENN keeps its settings, chat history and change history in `~/Library/Application Support/KENN`.
- Audio you load for a review is analysed on your Mac and not kept or sent anywhere.
- This build sends nothing to any server: no AI service is switched on, and telemetry is off.

## Updating

Quit KENN and replace **KENN** in Applications with the new version. Your settings and history are kept. If the new
version ships a newer AbletonOSC, the setup page will offer an update the next time you open KENN.

## Uninstalling

1. Quit KENN and drag it from Applications to the Bin.
2. In Live, set the AbletonOSC **Control Surface** slot back to **None**.
3. Optional: delete `AbletonOSC` and the hidden `.kenn-backups` folder from your User Library's `Remote Scripts`
   folder, and delete `~/Library/Application Support/KENN` and `~/Library/Logs/KENN Desktop Companion`.

## When something goes wrong

- **"Live is connected" stays unticked:** check AbletonOSC is selected as a Control Surface, then quit and reopen
  Live. After a long idle, the first reply from Live can be slow; press **Check again**.
- **KENN seems stuck:** quit and reopen KENN. Nothing in your set changes without Apply, so it's always safe to
  restart.
- **Reporting a problem:** tell us what you asked, what you expected and what happened. Then press
  **Setup & Support** in KENN's toolbar and **Save diagnostics for support**, and attach the file it names (in
  `~/Library/Application Support/KENN/diagnostics`). It holds counts and timings only: which kinds of changes KENN
  made and how they ended, how fast it answered, and your versions. No track names, audio, questions or file paths.
  If we ask for more, the full logs are `~/Library/Logs/KENN Desktop Companion/server.log` and
  `~/Library/Application Support/KENN/runtime/logs/kenn.log` (fuller; look through them before sending).
  Feedback channel: _(to be confirmed)_

## Known limitations in this build

- KENN understands common phrasing, but not everything; when it isn't sure, it asks. Please send us phrasings it
  misunderstood.
- Follow-ups ("do that on the snare too") repeat track volume, pan, mute, solo and arm changes and device settings
  (the device must be on that track too); two tracks at once ("the snare and the kick") aren't repeated yet, so KENN
  asks. Corrections work the same way; "no, the other one" still asks you to name the track.
- Device control in real units covers a starter set (EQ Eight band gain, Compressor, Saturator, Auto Filter and a
  few more); other device parameters can be read but not yet set in real units.
- KENN inserts only 10 audio effects so far, and no instruments or MIDI effects.
- The download is large (~240 MB) because KENN runs entirely on your Mac.
