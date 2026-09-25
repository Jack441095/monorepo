# KENN natural phrasings: the Stage 1 command gate (25 Sept 2026)

Stage 1 gate: **≥ 95% correct on ≥ 500 natural phrasings**. This is where that stands, and how far the numbers can
be trusted.

## What was measured

`tooling/scripts/score_natural_phrasings.py` sends each phrasing through `handle_command` on the demo set (fake
Live: Kick, Snare / Clap, Hi-Hats, Drum Bus, Bass, Synth at −14 dB; Lead Vocal and FX Print at 0 dB; Compressor on
Drum Bus and Lead Vocal, EQ Eight on Bass; returns A-Reverb and B-Delay). That's the same gateway the app uses:
rule parser, corrections, recipes, the subjective translator. Nothing touches Live. Each result is:

- **right**: expected action, track, value (fader dB, pan, on/off) and name (locator, rename, new track)
- **asked**: KENN asked when it could have acted. Safe, but it counts against the 95%.
- **wrong**: KENN proposed something that wasn't meant, or acted where it should have asked

A "wrong" is the one that matters: press Apply on it and you get a change you didn't ask for.

## The three sets

| Set | Rows | Written by | Labelled by | Role |
|---|---|---|---|---|
| `natural_holdout.jsonl` + `natural_holdout_candidates.jsonl` | 505 | 124 earlier + 381 drafted by Claude | Claude | development |
| `natural_blind_qwen14b.jsonl` | 210 | Qwen3 14B (box), asked for varied producer wording | Claude, before scoring | blind, then development |
| `natural_blind_qwen8b.jsonl` | 171 | Qwen3 8B (box), "typed in a hurry mid-session" | Claude, before scoring | blind, then development |

The Qwen labels were unreliable ("mute the kick" labelled `on: false`), so every row was relabelled by what a
producer means, before any scoring. The rules:

- "can you…?" is a request.
- "a bit" or "a touch" asks.
- A negative bare number on a fader is dB.
- "comp" with no parameter asks.
- A pan with no amount asks.
- A request naming two things asks.

Rows that also appear in the planner's training data were removed. The two blind files and the candidates are on the
training builder's exclusion list (`NATURAL_HOLDOUTS`).

## Results

**First, and only, blind run** (saved before any fix; `workspace/tmp/kenn-ops/phrasings/*_FROZEN.json`):

| Set | Right | Asked | Wrong |
|---|---|---|---|
| Qwen3 14B, 210 | **71.9%** (151) | 51 | 8 (7 real, 1 scorer bug) |
| Qwen3 8B, 171 | **70.2%** (120) | 44 | 7 |

**After fixing what they found** (all three sets are now development data):

| Set | Right | Asked | Wrong |
|---|---|---|---|
| 505 development | 95.4% | 23 | 0 |
| Qwen3 14B, 210 | 94.3% | 12 | 0 |
| Qwen3 8B, 171 | 79.5% | 35 | 0 |

**Reading it straight:** on wording it hasn't seen, the rule parser gets about **70%** right. It reaches 95% once
it has been tuned on a set. Both blind sets landed within two points of each other, so ~70% is the real starting
point, not a fluke. The rule parser alone won't reach the gate on fresh wording. The next step is the local planner
where the rules ask; that measurement is in progress (below). Zero wrong plans on all three sets matters as much as
the 95%.

## Wrong plans the blind sets found (all fixed, each with a regression test)

1. "put 40% of the bass on reverb" / "add 25% of the drums bus to delay" / "can you add a reverb send to the lead
   vocal?" **inserted a Reverb or Echo device** on the track instead of setting its send. So did "put 30 on delay for
   the vox". A percentage, or a bare number next to reverb/delay, now means a send; with no amount it asks.
2. "rename the track with no devices to main synth" **renamed the Synth**, because "synth" is in the *new* name. The
   track is now found only in the words before "to".
3. "play the drums" / "stop the bass" **started or stopped the whole set**. Play and stop naming a track now ask
   ("did you mean solo/mute the drums, or the whole set?").

The development set found three more, also fixed:

- "bring the vocal up a hair" became a two-track recipe that also **cut the Synth** (the subjective translator's
  "bring the vocal up" pattern).
- "put a marker called Build here" named the locator "Build here".
- "mute the FX Print" was refused as a device mute because of the "fx".

## Relabelled after the first run (owner to confirm; each row carries a `note`)

These rows first expected an action. KENN asks, by design:

- **Vocal or FX Print up 1–2 dB.** Both sit at 0 dB in the demo set, and KENN asks before any fader goes above 0 dB.
- **"kick −3 dB".** Ambiguous: a level or a change.
- **"pan the hats left and the snare right".** No amount given.
- **Compressor ratio in x:1.** Not measured in Live yet.

In the other direction, four rows moved from "asks" to an action:

- "solo the drums" / "mute all the drums" now expect the Drum Bus.
- "glue the drums together" / "compress the drums more" now expect the Glue Compressor proposal on the Drum Bus.

## What this doesn't show

- **The labels are mine, not the owner's.** The gate says "curated". Someone who isn't me should read the rows,
  especially the `note`s, and correct them.
- **It's one demo set.** Track names with numbers, groups, or two tracks with similar names aren't covered.
- **It's typed text only.** Voice transcripts will be messier.
