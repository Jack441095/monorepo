# KENN blind phrasings, round 9: mix notes (30 Sept 2026)

**Register:** mix notes · **Cases:** 118 · **Scorer:** `tooling/scripts/score_natural_phrasings.py`, rule path, fake Live
**First run, labels as first written:** **74 of 118 right (62.7%)**, 40 asked, **4 wrong plans**
**First run, three labels corrected, still no rule change:** **77 of 118 right (65.3%)**, 38 asked, **3 wrong plans**
**After the post-hoc fixes below (non-blind):** 109 of 118 right (92.4%), 8 asked, 1 wrong

Gate: first run ≥ 85% and 0 wrong plans. Both missed. 62.7% is also below round 5 (69.2%) and round 6 (83.0%), so a
new register is still costing about a day of rule work to reach the 80s.

## The register, and why it is new

Every earlier round is somebody *speaking to* KENN: dictated, typed in a hurry, a beginner in whole sentences, a
second-language speaker, a Logic user, a long rambling message. This one is somebody pasting a **document**. A mix note
is written to be read once and obeyed later, often by someone else, so the verb is often a column heading rather than a
word:

```
KICK FADER: -18 dB
SNARE / CLAP — 16 dB
HATS → A-Reverb 30%
Lead Vocal off solo
MARKER: Pre-drop
mute the Kick, mute the hats and solo the Bass
```

That stresses three things the other registers do not: **declarative mood** (no verb at all — "Drum Bus: centre"),
**document punctuation carrying the meaning** (a colon, an arrow, a bullet, a markdown `**`), and **the pasted
revision list**, where one screen holds several requests and the product's own rule says a request naming two things asks.

## Who wrote it, and what that costs the evidence

**The second author for this round was an automated session, not a person who did not write the parser fixes.** The plan
asks for a human second author. That weakens the independence claim in two specific ways, and both should be read
before the number is: the register boundary was chosen by the same process that knows where the parser is thin, and the
first-run number is less likely to surprise because of that prior. Read 62.7% as a floor on unfamiliar wording, not as
an unbiased estimate. A human author picking the register is still worth doing for round 10.

A second, smaller caveat: the labels are the author's, and the owner has not checked them. Three of 118 were wrong (below).

## How the cases were produced

Written in one sitting, before the parser was run on any of this wording, and committed before the scorer was run
(`41658821`), so the freeze is auditable rather than asserted. Every label is grounded in a stated product rule:

| Rule | Source |
|---|---|
| A negative bare dB on a fader is a level; a **positive** bare dB is the level-or-change ambiguity and asks | 25 Sept labelling rules, `test_blind_wording.py` |
| Live's fader is normalized; `volume_law.db_to_raw`; a fader tops out at +6 dB | `volume_law` |
| Demo set: Kick, Snare / Clap, Hi-Hats, Drum Bus, Bass, Synth at −14.0 dB; Lead Vocal and FX Print at 0.0 dB | `FakeLiveBackend` |
| KENN asks before any fader goes above 0 dB | 25 Sept evidence |
| A relative change is taken from that track's own level | `score_owner_tests.expected_value` |
| Pan is −1..1; a percentage is a fraction of full throw; a pan with no amount asks | `test_everyday_phrasings.py` |
| A percentage or bare number next to reverb/delay means a **send**; with no amount it asks | 25 Sept evidence, wrong plan 1 |
| Sends are a percentage; no send level in dB has been measured or qualified | North Star |
| Insertion allowlist is 10 devices; Limiter, Utility and Delay are not on it | `live_action_service.py` |
| A device already on the track asks rather than adding a second | round 5 |
| Only measured parameters change; a value outside a measured range is refused | `test_device_profile_files.py` |
| A request naming two things asks; the same change on several tracks is one confirmable recipe | 25 Sept rules; North Star 29 Sept |
| A question never changes anything; a statement about the set is not a request | `test_beginner_sentences.py` |

The schema matches the existing fixtures exactly. Two deviations worth naming: `expected_pan` carries the **send
fraction** on the seven send rows, because the fixture schema has no send-specific value field and leaving sends
unpinned would let a wrong send level pass; and the `notes_document_format` rows keep their document punctuation in the
query text rather than normalising it away, which is the point of the register.

Three labels were corrected after the first run and the set was re-scored with **no rule change at all**, so the two
numbers bracket the label errors and nothing else.

**One note on the history, for anyone auditing this.** A concurrent session working in this worktree committed the
parser fixes and a write-up together in a single commit whose text claimed "rule changes in this round: none". That
commit was split so the fixes (`b2961010`) and the write-up are separate, and two claims in the earlier draft that were
wrong — that the multi-track recipe was a label error rather than a dropped request, and the 505-holdout count — are
corrected above. **No first-run number moved**: `41658821` and `38fd60dd` predate any parser change and are untouched.

## The wrong plans

Four on the first run. Three after three labels were corrected. Listed individually, because 0 wrong plans is the gate
and a wrong plan is worse than a miss.

| id | phrasing | KENN proposed | what it is |
|---|---|---|---|
| blind-r9-033 | `Lead Vocal off solo` | `set_solo Lead Vocal = true` | **genuine defect — the request was inverted. Fixed.** |
| blind-r9-103 | `mute the Kick, mute the hats and solo the Bass` | a 2-step recipe: mute Kick, solo Bass | **genuine defect — the hats were silently dropped. Fixed.** |
| blind-r9-061 | `set the vocal compressor knee to 3 dB` | `set_device_parameter Knee = 3.0` | **unresolved — an owner's decision, not a fix.** |
| blind-r9-072 | `ADD: Delay on the Lead Vocal` | `insert_device Echo` | label error on my side, not a defect |

### blind-r9-033: the request was inverted

Asked to take a track **off** solo, KENN soloed it. Every negation rule in `live_intent.py` wanted a verb in front
(`turn`, `switch`, `take`), so the bare mix-note state fell through to the positive branch. `Lead Vocal solo off` and
`hats out of solo` were wrong the same way. This is the worst class of parser bug there is: the write lands, reads back
cleanly and is journalled as verified, so nothing downstream can notice that it is the opposite of what was asked.

### blind-r9-103: a request was silently dropped

This is the round's most serious find, and it is bigger than the row that exposed it. The line asks for three things.
KENN proposed a two-step recipe: **mute the Kick** and **solo the Bass**. "Mute the hats" was not in the plan, and the
answer never mentioned it. A producer who presses Apply gets two of the three requests and has no way to know.

The mechanism is plain: a comma list that repeats the verb (`mute the Kick, mute the hats`) is not the shape
`_SECOND_ACTION` guards, so the single-command parse read the first clause and stopped. `mute the Kick, mute the hats`
on its own proposed a single mute of the Kick, with a reply of "I can mute 'Kick'".

### blind-r9-061: the value written is not the value asked for

The Compressor `Knee` has no qualified profile — 20 profiles cover 9 devices and none of them is a Knee. KENN nevertheless
proposes writing 3.0, because `_display_unit_error` only checks a profile for the `ms` and `ratio` units and returns
early for everything else, so a `db` request on an unmeasured control is written straight through. On real Live the raw
control is 0..1, so 3.0 clamps and the producer asking for 3 dB gets Live's maximum knee.

**I did not fix this.** A comment in `live_intent.py` states the design position deliberately ("Do not infer dB for an
arbitrary device parameter... An explicit unit remains authoritative"), and `test_live_intent_natural.py` pins
"set the snare compressor output to 3 dB" as staying on the device path. Reversing that is a product decision with
collateral reach across every dB control, and it needs A3's real-Live qualification behind it rather than my judgement.
It is the first item in the owner's list below.

### blind-r9-072: my label was wrong

`_INSERT_DEVICE_ALIASES` maps a bare "delay" to **Echo**, which is on the insertion allowlist, and
`test_live_intent.py::test_plain_reverb_and_delay_insertion_aliases_are_canonicalized` pins it. The plan's A2 note that
Live's browser search resolved "Delay" to Align Delay is about the device *named* Delay, which KENN cannot target; it is
not a statement about this alias. I had both facts in front of me and picked the wrong one.

### The other two label corrections

`SNARE / CLAP — 16 dB` and `KICK - 18 dB` were labelled `set_volume`. A **positive** bare dB next to a track name is the
level-or-change ambiguity that the 25 Sept evidence already relabelled ("kick −3 dB"); only a negative bare number is
stated to be dB. Both now ask.

## What was fixed afterwards, and what it bought

Committed separately from the round (`b2961010`) so the first-run number cannot be accused of having been tuned.

1. **Un-solo wording** (`_OFF_SOLO`). "X off solo", "X solo off", "X out of solo", "X is not soloed" now rewrite to
   "unsolo X", which the rules already read. Fixes blind-r9-033.
2. **A comma list that repeats a verb** (`_COMMA_SECOND_ACTION`, plus distribution in `_split_plain_and`). Each clause now
   gets the verb, so `mute the Kick, mute the hats` is a two-step recipe naming both; and a mixed line
   (`mute, mute and solo`) asks instead of proposing half of it. Fixes blind-r9-103.
3. **Pasted mix-notes lines** (`_rewrite_notes_line`). Document bullets, markdown emphasis and a `TODO:` prefix are
   stripped; a closed set of section labels (`MARKER:`, `SHOW:`, `TEMPO:`, `NEW MIDI TRACK:`) is rewritten into the
   wording the rules own; and `TRACK: -18 dB` becomes a target. It runs **before** `_rewrite_common_phrasings`, because
   "KICK FADER: -18 dB" only becomes "KICK to -18 dB" once the colon is gone, and it is the terse-level rule that then
   reads that as a target. Every branch has to end on a form the rules already parse, and a line matching none of them
   is left alone to ask. This is the notes-register equivalent of round 5's rule work, and it is why the non-blind
   number is as high as it is.

Non-blind after: **109 of 118 (92.4%), 8 asked, 1 wrong** — the one remaining is the Knee write.

The eight still asked, left as they are rather than chased: `kick dB: -18`, `the drums bus needs 3 dB less`, `give the
Synth 2 dB more`, `vocal comp dry/wet 40%`, `CALL THE BASS: Sub`, `name the Drum Bus 'Drums'` (a quoted name with no
"as" or "to", which round 5 made ask on purpose), `marker called Bridge`, and `Bass EQ: band 2A -3 dB` (a band gain
still wants a frequency, which is worth a decision rather than a rule).

On `Kick reverb at 20%`: the first run asked; the notes rewrite now reads it as a send, which the 25 Sept rule
("a percentage next to reverb/delay means a send") says is right, so it scores as right. **My label says clarify and I am
leaving it there** — I found that rule only after the parser had changed, and relabelling to match the result is
exactly what this exercise exists to prevent. It is the fourth label for owner review.

**Collateral damage: none.** All eleven earlier sets (1,853 phrasings) were scored before and after the fixes and
**not one row's verdict moved** — same totals, same per-row verdicts. An intermediate version of the notes rewrite did
regress four send phrasings ("synth to the delay at 20 percent" and three like it) by matching them as notes lines; the
rewrite now requires a document separator, and that regression is gone. Round 9 is development data from here on.

## Held back for the owner

Seven cases are in `natural_blind_round9_mixnotes_pending_owner_2026-09-30.jsonl` and are **not scored**. They are the
policy conflicts the plan has pinned but not settled; scoring them would mean inventing the ruling.

| Case | The conflict |
|---|---|
| `Lead Vocal to -4`, `Hi-Hats to -18`, `Kick to -12` | bare "X to -N": `test_blind_wording.py` pins it as asking, the labelling rules say it is dB |
| `ADD: reverb on the Lead Vocal`, `REVERB: Lead Vocal` | a Hybrid Reverb device, or a send to A-Reverb |
| `Lead Vocal pan to -1` | a signed number −1..1 reads as Live's pan value (hard left); the 25 Sept evidence recorded the opposite reading as the drafter's label and said which is right is the owner's |
| `stop the transport` | lands on the "kill playback" conflict, pinned as not-a-mute |

## Decisions for the owner

1. **The Knee write** (blind-r9-061). Should a dB request on a control with no qualified profile be refused at parse
   time or at write time? The repo already refuses the same request in `%`, so the two paths disagree today.
2. **`Kick reverb at 20%`** — the 25 Sept send rule says a proposal is right; the round's label says clarify. Which?
3. **The two bare-dB labels** — confirm that a positive bare dB asks and a negative one does not.
4. **B2's three pinned conflicts**, plus the −1 pan, are still unsettled; seven cases are waiting on them.
5. **Labels.** Four rows now need someone other than their author to confirm before the gate can count them.

## A note on the numbers next door

The 505-phrasing curated holdout measures **491 right, 14 asked, 0 wrong (97.2%)** on this branch, not the 494 / 11 /
97.8% the North Star records from 28 Sept. The difference predates this round — the fixes above moved no earlier row —
and the gate's accuracy requirement is met either way. **0 wrong plans still holds**, which is the part that matters.

## Files

| File | What it is |
|---|---|
| `tooling/data/natural_blind_round9_mixnotes_2026-09-30.jsonl` | the 118 cases, written before scoring |
| `tooling/data/natural_blind_round9_mixnotes_2026-09-30_first_run.json` | frozen first run: 74 right, 40 asked, 4 wrong |
| `tooling/data/natural_blind_round9_mixnotes_2026-09-30_first_run_relabelled.json` | three labels corrected, no rule change: 77 / 38 / 3 |
| `tooling/data/natural_blind_round9_mixnotes_2026-09-30_after_fixes.json` | non-blind: 109 / 8 / 1 |
| `apps/backend/src/kenn/tests/test_blind_mix_notes.py` | 25 tests, one per thing the round found |
| `tooling/data/natural_blind_round9_mixnotes_pending_owner_2026-09-30.jsonl` | the 7 unscored policy conflicts |

Re-score from `products/kenn`:

```
python3 tooling/scripts/score_natural_phrasings.py tooling/data/natural_blind_round9_mixnotes_2026-09-30.jsonl --show wrong
```