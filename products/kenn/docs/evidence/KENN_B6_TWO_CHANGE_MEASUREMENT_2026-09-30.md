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
| `"lower the bass 2 dB and raise the vocal 1 dB"` | "I didn't catch a change to make there" | **not a gap — the request is impossible.** The fixture's Lead Vocal sits at **+0.00 dB**, so raising it has nowhere to go. `raise` is a volume verb and works on every other track (`raise the bass 1 dB` → 0.52495). See the correction below. |
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

### The `lower`/`raise` "gap" was my mistake, and the behaviour is right

I first wrote this up as a parser gap: `lower` and `raise` not being volume verbs the split path knows. That is
**wrong**, and the reason it looked wrong is worth recording. Splitting the sentence gives two halves, the second of
which fails:

```
'raise the vocal 1 dB'  -> action=set_volume  missing=['valid_volume']  value=None
```

`valid_volume` reads like a missing rule. It is not: the fixture's Lead Vocal is at **+0.00 dB** (raw 0.8500, unity),
so a 1 dB raise has nowhere to go. Every other track is at -14.00 dB and raises fine:

```
'raise the bass 1 dB'   -> missing=[]  value=0.52495
'raise the kick 1 dB'   -> missing=[]  value=0.52495
```

So the whole sentence is correctly refused: one of the two changes cannot be made. Round 9 hit exactly this and I
recorded it then as a *label* error ("the vocal is already at 0 dB"). I should have recognised it here instead of
reaching for a missing rule. **The refusal is right; the sentence is impossible.**

What it does show is a reply worth having: KENN says "I didn't catch a change to make there" when one change was fine
and the other was impossible. That is closer to the silent-drop problem above than to a parser gap — the producer is
told nothing about either half.

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

## Addendum, 30 Sept: the buttons are blocked on a broken card, not on missing data

I assumed the frontend had nothing to bind to. It has plenty — the problem is it renders a two-step plan as **"Track "**.

`KennChatHistory.vue:80` renders `KennActionCard` for any message with a `proposal`, and passes the whole proposal
object. For a recipe that object has no `track_name` and no `track_index`:

```
proposal has track_name  : False
proposal has track_index : False
proposal.steps          : 2
```

`KennActionCard.vue:10` is then

```vue
{{ proposal.track_name || `Track ${proposal.track_index != null ? proposal.track_index + 1 : ''}` }}
```

which with neither present renders the literal string **"Track "**. The plan text is fine — it is in `answer` as "The
plan, 2 changes: …" — so what a producer sees today is a correct sentence above an action card with no track name on
it, and a working Apply button. Verified 30 Sept against `FakeLiveBackend`; not verified in a browser, because I cannot
see one.

Everything the buttons need is already in the payload. Each step carries `action_id`, `action`, `before`, `after`,
`before_db`, `after_db`, `parameter`, `reason` and `evidence` — so `Hi-Hats -14.0 dB -> -17.0 dB` can be rendered
per step, which is the thing B6 actually wants ("Do the first, then the second?").

So the frontend work is: a `KennRecipeCard.vue` that iterates `proposal.steps`, and a branch in `KennChatHistory` to
prefer it when `proposal.action === 'recipe'`. That fixes the empty card as a side effect. **I have not written it** —
a Vue component I cannot look at is not something to land on a claim that it works.
