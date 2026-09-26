# Chat routing: Live or the notes (26 Sept 2026)

**Why:** testing the tester guide in the app's own chat, "Do that on the snare too" got a notes page about snare drums.
The phrasing scorer never saw this, because it sends each phrasing straight to the command gateway; the chat decides
before that. `tooling/scripts/measure_chat_routing.py` now measures the chat itself: it starts a fake-Live KENN on a
spare port and sends every labelled request (1,072 that should change Live) and every retrieval question (481 that
shouldn't) through `/kenn/api/ask`.

| | Before (main `c648e1a`) | After (`kenn-after-soak`) |
|---|---|---|
| Requests that reach Live | 654 / 1,072 (61.0%) | 1,016 / 1,072 (94.8%) |
| Knowledge questions taken over by Live | 44 / 481 | 3 / 481 |
| Server errors | 2 | 0 |
| Rule path (phrasing scorer) | 1,639 / 1,751 right, 1 wrong | 1,642 / 1,751 right, 1 wrong (the disputed "-1 pan" row) |

**What changed:**
- The chat used to hand a message to Live only if it opened with a known command verb, so "can you solo the hats?"
  and "bump the synth up 1 dB" got the notes. Now the rule parser decides (`core/chat_live_router.py`), on the cached
  look at the set: if it reads a Live change, the command gateway answers.
- Asking how stays with the notes wherever it sits in the message ("My drums rumble. What's a quick way to clean them
  up?"), including a wish with a condition ("more depth, but not muddy"). The orchestrator uses the same rule, which
  stopped 33 how-to questions coming back as proposals (a Glue Compressor for rumbly drums, the Synth turned down for
  muddy vocals).
- Mid-change follow-ups, corrections and short replies reach Live ("do that on the snare too", "no, I meant the kick",
  "3 dB"), and so does KENN's own question when it can't do one ("that would take the vocal above 0 dB").
- Narrower matchers: "tempo" anywhere no longer answers "the current tempo is 120 BPM"; "which key I press" isn't the
  song's key; "every note I play" isn't transport Play; "a tremolo that pulses to the beat" isn't a request to write
  drums; swing on a drum pattern doesn't write a bassline.
- Answers read as a tester reads them: "I can mute 'Hi-Hats'", "rename 'Synth' to 'Pads'", a compressor threshold
  "from 0.00 dB to -20.0 dB" (it said "from 0.85 db to 0.362 db"), recipes step by step in dB and %, and "'Synth' is
  already centred" instead of a proposal to change nothing. The phrasing scorer counts "already there" as right only
  when what KENN understood matches the label (1,642 right, unchanged).
- The two 500s: Live's numeric root note (0 = C) crashed the MIDI generator; the session doctor's audit read fields
  its issues don't have. Both fixed, and a 500's error text now goes to the local log.

**The 56 requests still missed** are phrasings the rule parser can't do either (0 of them become a proposal through
the command gateway), so they are phrasing coverage, not routing. The 3 questions still taken over are borderline
("fix muddy low mids in a mix" reads as a command).

**On real Live** (demo set, branch companion at `e3afe8b`): 32 of 32 through the chat, with the set restored exactly:
the whole tester guide including every follow-up, correction and reply row (main had 17 of 26), plus "can you solo the
hats?", "bump the synth up 1 dB", "Send the synth to A-Reverb 30 percent", "could you mute the drum bus please", and
a how-to question about rumbly drums staying with the notes.
