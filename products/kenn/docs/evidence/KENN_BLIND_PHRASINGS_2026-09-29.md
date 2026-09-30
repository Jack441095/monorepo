# KENN blind phrasings, round 5 (29 Sept 2026)

A fresh set of 146 phrasings, written in one sitting before any scoring and before reading the parser, to see what the
rules do on wording they have not been tuned on. Same scorer and demo set as `KENN_NATURAL_PHRASINGS_2026-09-25.md`
(`tooling/scripts/score_natural_phrasings.py`, rule path, nothing touches Live).

The set is `tooling/data/natural_blind_drafted_2026-09-29.jsonl`. It was drafted by the assistant that fixed the parser, not by a Qwen model on the
box (the box wasn't reachable from that session), so it shares an author with the labels. It covers registers the earlier
sets didn't: a reason before the request ("the synth is fighting the vocal, can you pull it down like 3 dB"), shorthand
("hats @ -17dB"), sloppy typing ("vocal upp 2 db"), and studio verbs ("shut the hats up", "swing the snare 15% right"),
plus 30 requests that should ask. **The labels are the drafter's; the owner has not checked them.**

## First run (frozen, before any fix)

Saved as `tooling/data/natural_blind_drafted_2026-09-29_first_run.json`.

| | Right | Asked | Wrong |
|---|---|---|---|
| Labels as first written | **69.2%** (101/146) | 42 | 3 |
| Labels after review (below) | **76.7%** (112/146) | 33 | 1 |

This is the same ~70% the three Qwen sets gave: a new register, the same gap.

## What it found

The wrong plan that mattered: **"kill the send from bass to delay" proposed muting the Bass.** The mute slang ("kill",
"nuke") fired on a request that was about a send. It now sets that send to 0% (test:
`test_killing_a_send_never_mutes_the_track`).

Two more wrong plans were label errors on my side, not parser errors (see the review), and one was a fix that broke
something: writing "minus six" as "-6" early in the parse changed how "…minus six—actually pan it 20% right" was read
(it set the volume). It is now only done when the number ends the request. A second rename rule I wrote guessed where
the track name ended ("name the lead vocal Main Vox" became "vocal Main Vox"); it now needs "as" or "to".

Most of the 42 asks were wording, fixed as a group rather than one phrase at a time:

- **Levels:** `@` for "at", "minus eight" (spoken, no unit), "zero dB", "sitting around", "should live at", "for now",
  "fader down to", "put X on -16", a leading "let's".
- **Changes:** "3 more dB on the kick", "quieten the hats by four dB", "X too loud, down 3", "upp".
- **Pan, mute, solo, arm:** "swing the snare 15% right", "synth over to the left, 30 percent", "shut the hats up",
  "I need to hear just the vocal", "stop soloing the hats", "get the vocal armed".
- **Sends, markers, names, transport:** "feed the synth into the reverb at 50%", "hats to the b-delay about 15 percent",
  "turn the vocal reverb send down to 10%", "set a marker: Breakdown", "new locator, name it Pre-drop", "the fx print
  should be called Bounce", "relabel the hats as Shaker", "pause it there".
- **Reads and focus:** "which tracks do I have", "list the effects on the drum bus", "open up the vocal compressor",
  "I want an EQ Eight on the kick".

## Label review (owner to confirm)

After the first run I re-read every row that failed against facts about KENN I hadn't allowed for. Ten labels changed;
each row in the file carries `label_review` with the old label and the reason.

| Phrasing | Was | Now | Why |
|---|---|---|---|
| snare clap -12; fx print -30 dB; drums bus -5, please | level | asks | a level or a change; KENN asks which |
| nudge the vocal up 1.5 dB; vocal upp 2 db | change | asks | Lead Vocal is at 0 dB, KENN never sets above 0 dB |
| put a limiter on the drum bus; stick Utility on the fx print | insert | asks | neither is on the insertion allowlist (a plain "Limiter" resolves to Color Limiter in Live) |
| slap a compressor on the lead vocal | insert | asks | the vocal has a Compressor; KENN asks which one you mean |
| back the vocal compressor threshold off by 2 dB | parameter | asks | "back off" a compressor can mean either direction of the threshold |
| solo the synth and the vocal | asks | recipe | two solos in one confirmable recipe is what was asked |
| put reverb on the vocal | asks | insert | see the decision below |

## Second run (after the fixes)

**143/146 (97.9%), 0 wrong**, but the set is now development data: I fixed what it found, so this number says the rules
cover these phrasings, not that they cover unseen ones. The honest blind number is the first run: **69.2% as labelled,
76.7% after label review.**

The three still asked:

- "lead vocal to -4 please" asks because a bare "X to -N" with no verb and no unit asks (pinned by
  `test_everyday_phrasings.py` and `test_live_intent_natural.py`). The labelling rules in the 25 Sept evidence say a
  negative bare number on a fader is dB. The tests and the labelling rule disagree.
- "name the lead vocal Main Vox" asks: the name has no separator, so where "lead vocal" ends is a guess.
- "kill playback" asks: `test_live_intent_natural.py` pins it as not acting (the test wants it not to become a mute).
  Stopping the transport is the obvious reading; the pin is older than this check.

Every earlier set was rescored with the new rules: 1,110 → 1,256 rows in total, 92.3% right, 95 asked, 2 wrong (the two
mixed requests from the beginner set that were already wrong: "…by 3 dB. Can you show me the hats track?", "I want to
solo the synth track. Can you go there?"). Qwen 14B 94.3%, Qwen 8B 95.9% (was 96.5%), beginner 75.0%, all with 0 new
wrong plans. One row moved from right to asked and was put back ("let's hear it": my "let's" lead-in stripped its verb).

## Decisions for the owner

1. **Bare "X to -N", and "kill playback".** Should "lead vocal to -4" set the level? The labelling rule says yes; the pinned tests say ask. Likewise "kill playback" is pinned as not acting.
2. **"Put reverb on the vocal".** A device on the track, or a send to A-Reverb? Today it proposes a Hybrid Reverb device
   (undoable, behind Apply), as "add reverb to vox" already did in the development labels. The alternative is to ask.
3. **Labels.** All the blind sets need someone other than their drafter to check the labels before the gate can count them.

## What this does not show

The gate is ≥ 95% on ≥ 500 natural phrasings, on wording the rules haven't seen. Round 4 says ~77% on a new author's
wording before fixes. Rules-first with the small planner as a fallback lifted the earlier sets by 5–14 points, but the
current planner (run 11) needs the box to re-run and wasn't reachable this session.

## Round 6 (112 phrasings, written before scoring)

New set: `tooling/data/natural_blind_drafted_round6_2026-09-29.jsonl`, first run frozen in `..._first_run.json`. It leans
on wording round 5 didn't cover: hedged requests ("would you mind…", "any chance you could…"), tracks by number or
"called", "X on" for unmute, and chained "solo the bass, then pan it".

First run: 83.0% as labelled, 86.6% once four rows were relabelled after review (each has a `label_review` note; I had
labelled the producer's intent wrong, not KENN). 0 wrong plans. After the rewrites in `live_intent.py` it reads 109 of
112 (97.3%), still 0 wrong, and the nine earlier sets score the same as before. The three left ask on purpose: "the sixth
one" can mean an option KENN just listed, and "call the bass Sub Bass" has no clear name boundary.

This is the same drafter tuning against their own set, so the 97% is not a gate number. Someone else still has to write
and label a fresh set.
