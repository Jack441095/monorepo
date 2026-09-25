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

## The sets

| Set | Rows | Written by | Labelled by | Role |
|---|---|---|---|---|
| `natural_holdout.jsonl` + `natural_holdout_candidates.jsonl` | 505 | 124 earlier + 381 drafted by Claude | Claude | development |
| `natural_blind_qwen14b.jsonl` | 210 | Qwen3 14B (box), asked for varied producer wording | Claude, before scoring | blind, then development |
| `natural_blind_qwen8b.jsonl` | 171 | Qwen3 8B (box), "typed in a hurry mid-session" | Claude, before scoring | blind, then development |
| `natural_blind_qwen14b_beginner.jsonl` | 224 | Qwen3 14B, a beginner writing full polite sentences | Claude, before scoring | blind, then development |

The Qwen labels were unreliable ("mute the kick" labelled `on: false`), so every row was relabelled by what a
producer means, before any scoring. The rules:

- "can you…?" is a request.
- "a bit" or "a touch" asks.
- A negative bare number on a fader is dB.
- "comp" with no parameter asks.
- A pan with no amount asks.
- A request naming two things asks.

Rows that also appear in the planner's training data were removed. All blind files and the candidates are on the training
builder's exclusion list (`NATURAL_HOLDOUTS`).

## Results

**First, and only, blind run** (saved before any fix; `workspace/tmp/kenn-ops/phrasings/*_FROZEN.json`):

| Set | Right | Asked | Wrong |
|---|---|---|---|
| Qwen3 14B, 210 | **71.9%** (151) | 51 | 8 (7 real, 1 scorer bug) |
| Qwen3 8B, 171 | **70.2%** (120) | 44 | 7 |
| Qwen3 14B beginner, 224 (scored after the first two were fixed) | **65.6%** (147) | 63 | 14 |

**After fixing what they found** (all these sets are now development data):

| Set | Right | Asked | Wrong |
|---|---|---|---|
| 505 development | 96.0% | 20 | 0 |
| Qwen3 14B, 210 | 94.3% | 12 | 0 |
| Qwen3 8B, 171 | 96.5% | 6 | 0 |
| Qwen3 14B beginner, 224 | 75.0% | 54 | 2 (both mixed requests: "I want to solo the synth. Can you go there?") |

**Reading it straight:** on wording it hasn't seen, the rule parser gets **66–72%** right, three times over. The
third set was scored *after* the first two had been fixed and still came in at 65.6%: the fixes don't carry over to
a different register (full polite sentences). Tuned on a set, the rules reach ~95% on it, but more rules alone won't
reach 95% on fresh wording. Zero wrong plans matters as much as the 95%, and every blind run found some.

### The planner as a fallback (run 9b, the current shadow model)

Measured on what the rules asked about, using the gateway's own propose-stage test: only requests where the rules
found no action. Since today, that test also excludes requests where the rules asked something specific ("how
much?", "the whole set or the drums?").

| Set | Rules only | Rules, then run 9b |
|---|---|---|
| Qwen3 14B, 210 | 94.3% right, 0 wrong | 87.1% right, **17 wrong** |
| Qwen3 8B, 171 | 96.5% right, 0 wrong | 93.0% right, **7 wrong** |

Some of those "wrong" are reads the scorer counts strictly ("what's the name of the synth track?" → list tracks), or
"comp" with no parameter read as the threshold. The rest are real guesses:

- "toggle hats" → arm
- "can i hear the vocal without the synth" → **solo the Synth**
- "send the synth to reverb" → send at 100%
- "slap the clap to the left" → hard left
- renames by description ("the track with the compressor")

So run 9b shouldn't move past shadow. The next planner (run 11 is the candidate) needs clarify examples for exactly
these patterns ("toggle", "without", sends and pans with no amount, tracks described by their devices), and this
check should run before any promotion.

## Wrong plans the blind sets found (all fixed, each with a regression test)

1. "put 40% of the bass on reverb" / "add 25% of the drums bus to delay" / "can you add a reverb send to the lead
   vocal?" **inserted a Reverb or Echo device** on the track instead of setting its send. So did "put 30 on delay for
   the vox". A percentage, or a bare number next to reverb/delay, now means a send; with no amount it asks.
2. "rename the track with no devices to main synth" **renamed the Synth**, because "synth" is in the *new* name. The
   track is now found only in the words before "to".
3. "play the drums" / "stop the bass" **started or stopped the whole set**. Play and stop naming a track now ask
   ("did you mean solo/mute the drums, or the whole set?").

The third (beginner) set found inverted values and more, all fixed with tests:

4. "Could you **dis-arm** the drum bus?" **armed** it; "I want to **turn off the solo** on the drum bus" **soloed** it.
5. "How do I solo the lead vocal?" / "Is there a way to solo…?" **soloed** it. How-to questions now change nothing.
6. New names kept the rest of the sentence ("Synth Lead, can you do that?", "just Hats").
7. "rename the vocal track to 'Vox' for clarity" became the **vocal-unmasking recipe** ("vocal … clarity"); the
   subjective translator no longer fires when the rules already have an exact request.
8. "solo the drum bus and the vocal track at the same time" soloed **only the Drum Bus**.

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
