# B6 measurement: what two changes in one sentence actually does today

**Written:** 2026-09-30 · **Task:** B6 · **Status: B6 not built.** This is the measurement that says where the work is.

Measured through the gateway (`handle_command` with a fake-backed `LiveActionService`, `allow_llm=False`), not through
`parse_request`. That distinction matters and I nearly got it wrong: the parser refuses almost every two-change
sentence, while the gateway upgrades several of them into two-step plans. Round 9 established the same thing about the
`verdict` column, so parser-only measurement under-reports what a producer is actually told.

## What already works

One confirmable plan with a step per change, both actions shown, nothing written:

```
"turn the hats down 3 dB and the kick up 2 dB"
  -> The plan, 2 changes:
     1. 'Hi-Hats' volume -14.0 dB -> -17.0 dB
     2. 'Kick' volume -14.0 dB -> -12.0 dB
     Nothing has changed yet.
```

Also working, verified the same way: `"mute the kick and mute the hats"` and `"solo the bass and turn it up 2 dB"`
(the latter resolves the pronoun *it* to the Bass and proposes `-14.0 dB -> -12.0 dB`). So the repeat-the-verb and
pronoun cases the North Star claims for Stage 1 are real. **B6's "instead of a refusal" is therefore not a from-scratch
feature** — the machinery and the wording for a two-step confirmable plan already exist and are used.

## What does not work, and which of it matters

| Request | Told | Which kind of gap |
|---|---|---|
| `"lower the bass 2 dB and raise the vocal 1 dB"` | "I didn't catch a change to make there" | **parser.** `lower`/`raise` are not volume verbs the split path knows; `_AND_SPLIT` handles `turn X down N dB`, and `raise the vocal 1 dB` alone fails `valid_volume` |
| `"make the hats quieter and the kick punchier"` | **"By how much? ... 'turn Kick down 2 dB'"** | **the serious one: a silent drop** |
| `"adjust that"` | "I didn't catch a change to make there" | missing entirely |

### The silent drop is the one to fix first

The producer said two things. KENN asks about the Kick and never mentions the Hi-Hats again. The request is not
refused — it is half-forgotten, and the reply reads as though only one thing was asked. That is the same shape as the
round-9 find ("mute the Kick, mute the hats" silently proposing one mute), and the North Star has been ruthless about
that class: a step that cannot be verified is not done, and a request that cannot be carried out should be named rather
than dropped.

The fix is narrow and belongs in the clarification: when a plain-`and` sentence has two parts and only one resolves,
the reply must name the part it did not understand, the same way `_split_plain_and` already refuses rather than
half-applying. Asking "by how much?" is correct here; asking it about the Kick **and forgetting the hats** is not.

### The parser gap is ordinary work

`lower`/`raise` need to be volume verbs in the direction-plus-amount forms the split already understands. This is the
same shape as the existing `turn X down N dB` handling, so it belongs beside it rather than in a new rule family.

### "adjust that" needs the previous exchange

It resolves against the last confirmed step, which is why it is `clarification_required` with no history. The follow-up
machinery already handles pronoun inheritance inside a recipe; "adjust that" needs the same anchoring at the turn level,
and it is the part of B6 most likely to need the frontend buttons to be useful, because "adjust" means adjusting *what*
only if something was just proposed.

## What this implies for the buttons

The two-step plan already renders as text with both steps and "Nothing has changed yet." The buttons B6 asks for are a
rendering change on top of a payload that exists, **except** for the ambiguous case: where one part is understood and
the other is not, the two buttons are not "do the first, then the second" but "tell me the amount for the hats" — so the
frontend cannot be a dumb renderer either way. Worth deciding that shape before building the buttons.