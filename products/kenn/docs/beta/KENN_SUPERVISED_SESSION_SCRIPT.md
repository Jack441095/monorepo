# Running a supervised pilot session

For whoever runs a session with a tester. The release gate needs **ten sessions across at least three projects**,
every one passing, each recorded with `tooling/scripts/record_pilot_session.py`. Follow this the same way every
time, so every session counts. A session takes about 45 minutes, plus 10 minutes afterwards.

## Before (10 minutes)

Check each of these and don't start until all six are true. The recorder asks about them afterwards, and one "no"
means the session doesn't count.

1. **The set is a disposable copy.** Save As into a new folder; the tester's original project stays closed.
2. **Every change waits for Apply.** KENN has no auto mode, so this should always hold; confirm it on the first card.
3. **No unsaved work is open** anywhere in Live.
4. **Supported setup:** Live [12.4.5] (Live > About Live), macOS [26.5.2] and Apple Silicon (Apple menu > About
   This Mac).
5. **The tester can see the Undo button** on a change card before the first change.
6. **You know how to check the diagnostics file** for names and audio (step 2 of "After").

Write down the start time with its timezone (for example `2026-09-27T14:05:00+01:00`). The recorder needs it.

## During (30–40 minutes)

Let the tester drive with their own words. Suggest things only when they run dry. The session must include **at
least one change that's applied and then undone**; the gate checks for both.

Suggestions, roughly in this order:

- A question about the set: "What's on the drum bus?"
- A fader or pan change, then Apply: "bring the bass down 2 dB".
- **Undo it**, from the card or by saying "undo that". Check in Live that the value went back.
- A follow-up: "do that on the snare too". Or a correction: "no, I meant the hats".
- A device setting on a track that has the device: "set the compressor threshold on the drum bus to -20 dB".
- A how-to question: "how do I sidechain the bass to the kick?"
- A Mix Review on a bounce of the copy, if time allows.

Watch for, and note the time of, anything on this list. Each one is a safety incident, and the session doesn't
pass:

- Live changed without anyone pressing Apply.
- A card said "Readback Verified" but Live shows something else.
- An Undo didn't restore the previous value.
- The KENN companion crashed or had to be restarted.
- The set got into a state Undo couldn't fix.

Anything else odd (a wrong answer, a confusing card, a slow reply) isn't an incident, but note it: that's the
feedback we want.

## After (10 minutes)

1. Make the support bundle:
   `python3 tooling/scripts/build_support_bundle.py --output ~/kenn-pilot/s01.zip`
2. Open the ZIP and look through `diagnostics.json` and `lifecycle-events.json`. Check there are no project or track
   names, no audio and none of the tester's questions. It should be counts and receipt IDs only.
3. Show the tester a one-line summary (changes made, undos, any incidents) and ask them to sign it off.
4. Record the session:
   `python3 tooling/scripts/record_pilot_session.py --bundle ~/kenn-pilot/s01.zip --project "<tester>, <song>" --tester "<tester>" --started-at <start time>`
   Use the same project wording every time you mean the same song: it's hashed, and different wording counts as a
   different project.
5. If it says **"Won't count yet"**, fix what it names while the tester is still there (usually a missed undo).

Keep the bundles and logs together, outside the repository. When there are ten, the aggregate command is in
`docs/runbooks/QUALIFIED_BETA_EVIDENCE_RUNBOOK.md`, section 7.
