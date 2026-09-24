# KENN north star: an expert production partner inside Ableton Live

**Written:** 2026-09-24 · **Owner:** Jack · **Status:** proposal for owner sign-off

The long-term plan for KENN's intelligence. It merges the three GLM plans
(`KENN_GLM_MEGA_PLAN.md`, `KENN_GLM_ROADMAP_2026-09-21.md`, `KENN_GLM_ABLETON_ASSISTANT_PLAN_2026-09-22.md`) and the
frontier plan (`KENN_FRONTIER_PLAN.md`) into one direction. Those stay as reference; this doc decides the order.
Stage 0 is the private beta (`KENN_BETA_PLAN_2026-09-24.md`). The GLM tracker stays the working log. Tick items here
in the same commit as the work, with the date and the evidence.

## What KENN becomes

A producer talks to KENN the way they would talk to a senior engineer sitting next to them. KENN:

- **knows Ableton Live deeply:** every device, every parameter, the manual, and how things are actually done;
- **knows this session:** tracks, devices, routing, automation, what changed and when;
- **listens:** measures the mix and the stems, and says what it hears with evidence;
- **acts safely:** proposes a change, waits for Apply, checks Live did it, and can always undo it;
- **thinks in steps:** "tighten the low end" becomes a short plan it explains, then carries out one confirmed step at a time;
- **remembers:** the project, and the producer's preferences they chose to share, both visible and deletable;
- **says what it doesn't know**, and never invents a Live state, a parameter or a source.

"Like Claude, but for KENN" means that level of conversation and reasoning, with KENN's own knowledge and tools,
inside KENN's safety model.

## Principles that do not change

1. **Deterministic code owns the dangerous parts:** Live snapshots, units and fader laws, target resolution, safety policy,
   confirmation, OSC writes, readback, receipts and undo. A model never writes to Live directly.
2. **Every claim is sourced or measured:** notes and the manual for knowledge, Live reads for session facts, analysis for
   audio. Answers cite; unknowns are said out loud.
3. **Private by default:** audio never leaves the Mac. Anything sent to a hosted model is text the user can see, and
   hosted use is opt-in.
4. **Promotion by evidence:** a model or a capability moves up (shadow → propose → default) only through a measured gate,
   never because it demos well.
5. **One product:** browser companion and the AU/VST3 plug-in share one backend and one set of receipts.

## Where KENN is today (2026-09-24)

| Capability | Today | Long-term target |
|---|---|---|
| Understands open phrasing | Rule parser 80/124 with 0 wrong plans; C6 4B fine-tune in shadow | ≥ 95% on ≥ 500 natural phrasings |
| Converses | Chat answers are templates over retrieved notes (model off for chat) | Model-written, cited, multi-turn, clarifies |
| Knows Live | 74/78 devices with an approved note; hybrid retrieval, recall@4 0.966 | Every device and parameter, grounded in the user's installed devices |
| Knows the session | 7 question kinds, change history, world model reads (returns, master, racks) | Full session model including clips, automation and routing |
| Controls Live | Mixer, focus, sends, 12 measured parameters on 9 devices, 10 insertable effects | ≥ 60 parameters on ≥ 25 devices, every change undoable |
| Thinks in steps | Deliberative planner (Qwen3-4B) qualified once on real Live; ~10 s per step | ≥ 15 qualified recipes; advice → fix → re-measure |
| Listens | Rendered captures: loudness, true peak, clipping, low end | Live capture, masking and balance with confidence |
| Remembers | Session receipts only | Project memory and opt-in preferences, viewable and deletable |
| Creates | MIDI ideas as confirmable clips | Preview → insert; audio-to-MIDI; later, generation |

## The main decision: which model is KENN's brain

KENN uses three kinds of model, each where it is strongest:

| Job | Model | Why |
|---|---|---|
| Clear commands ("hats down 2 dB") | Rule parser, then the small local planner | Instant, offline, exact |
| Conversation, explanation, multi-step reasoning | **The brain: decision below** | Needs broad knowledge and real reasoning |
| Drafting knowledge notes, labelling training data | Box models (GPU notes model) | Cheap, offline, reviewed before use |

Options for the brain:

| Option | Strengths | Costs and risks |
|---|---|---|
| **A. Larger local model** (8–14B, fine-tuned on KENN's knowledge and tools) | Private, offline, no per-use cost | Weaker reasoning; needs a strong Mac; slower (today's 4B is already 6–10 s); ongoing training work |
| **B. Hosted frontier model** (e.g. Claude through the API, with KENN's tools and retrieval) | Best reasoning and conversation now; improves without our training | Per-use cost; needs internet; privacy and terms review; latency depends on the network |
| **C. Hybrid (recommended)** | B for conversation and planning when online and opted in; A-class local model for private or offline use and commands | Two paths to test; a router decides |

**Recommendation: C, hybrid.** KENN's value is its tools, knowledge and safety model, and those stay the same whichever
brain drives them. Starting hosted gets real conversational quality in front of testers quickly; the local path keeps
KENN private-first and gives a fallback. KENN's model layer already supports local Ollama and OpenAI-compatible hosted
endpoints; a hosted Claude provider would be added the same way.

**Decide before Stage 1 (owner):** hosted provider and budget per tester per month; whether hosted is on by default or
opt-in (recommend opt-in); what may be sent (recommend: the question, retrieved note excerpts and a session summary;
never audio, never file paths).

## Stages

Each stage ends at a measured gate. Stages overlap where they don't depend on each other.

### Stage 0 — Private beta (now → ~4 weeks)

See `KENN_BETA_PLAN_2026-09-24.md`. Exit: qualified gate 14/14, 3 testers onboarded.

### Stage 1 — Conversational KENN (beta weeks 1–6)

- [ ] Brain decision made; provider added behind the model router with per-task switches (as `KENN_LLM_ENABLED_<TASK>`)
- [ ] Chat answers written by the brain from retrieved notes, with citations; templates stay as the offline fallback
- [ ] One router: rule parser → local planner → brain; every route logged with timing
- [ ] Multi-turn context: anaphora ("do that on the snare too"), corrections ("no, the other one"), clarifying questions
- [ ] Safety unchanged: the brain can only call typed tools; writes still go proposal → Apply → readback → receipt
- [ ] **Gate:** ≥ 95% correct on ≥ 500 natural phrasings (curated holdout grown from 24); human-review packet passes with
      two reviewers; p95 answer latency ≤ 4 s online; zero writes without Apply in shadow logs

### Stage 2 — Deep Ableton knowledge (beta weeks 2–10, runs alongside)

- [ ] Parameter-level knowledge for all 78 devices: every parameter's name, range, unit and what it does, read from
      Live (display tables, as with the fader law) and the manual
- [ ] Notes for how things are done: gain staging, bus processing, sidechain, arrangement moves, genre conventions;
      drafted on the GPU notes model, checked automatically against sources, reviewed before approval
- [ ] Grounded in the user's own setup: installed devices, packs and third-party plug-ins read from Live, so advice
      names what they actually have
- [ ] Contradiction checks and source tiers (manual and measured data above notes, notes above general advice)
- [ ] **Gate:** retrieval recall@4 ≥ 0.95 on a fixture grown to ≥ 300 questions; answer accuracy ≥ 90% on a
      parameter-level quiz scored by reviewers; no uncited factual claims in a 100-answer audit

### Stage 3 — Agentic co-producer (beta weeks 6–16)

- [ ] Device qualification factory: every insertable device measured and end-to-end tested per parameter
      (D1 in the tracker), growing from 10 devices to ≥ 25 and ≥ 60 parameters
- [ ] Multi-step tasks from the deliberative planner (qualified once on real Live, 24 Sept): plan shown first, each step
      confirmed, one receipt per step, undo per step or for the whole task
- [ ] Advice → fix → re-measure: each audio finding offers a confirmable change and measures again after Apply
- [ ] ≥ 15 qualified recipes (e.g. "clean up the low end", "make room for the vocal", "set up parallel drums")
- [ ] Planner promotion only through `live_llm_promotion.py` (≥ 500 comparisons, ≥ 14 days, ≥ 98% schema, ≥ 90% agreement)
- [ ] **Gate:** recipes pass on real Live with exact undo; per-step latency ≤ 3 s; zero unauthorised writes across
      the pilot

### Stage 4 — Memory and personalisation (after Stage 1)

- [ ] Project memory: decisions, references, what was tried, kept per Live set
- [ ] Opt-in producer preferences ("I like my vocals bright", "I master to -9 LUFS"), always cited when used
- [ ] Memory view in the UI: see, edit, delete; nothing learned silently
- [ ] **Gate:** testers can find and delete any memory; memory-using answers cite the memory; no cross-project leaks

### Stage 5 — Creation (after Stage 3)

- [ ] MIDI ideas → preview → insert (drums, bass, chords) with undo
- [ ] Audio-to-MIDI and reference-driven suggestions
- [ ] Audio generation only as a separate, opt-in provider, labelled clearly
- [ ] **Gate:** owner listening review; everything inserted is undoable and labelled as generated

## Knowledge programme

| Source | Trust | How it enters KENN |
|---|---|---|
| Ableton Live Reference Manual | High | Section extraction → GPU notes model drafts → automatic term checks → review → index |
| Live itself (display tables, parameter lists, the user's devices) | Highest for facts | Read-only measurement scripts; stored as data, not prose |
| KENN-written craft notes | Medium | Drafted, checked against cited sources, reviewed |
| Third-party material (videos, articles, other vendors' docs) | Only with rights | Not imported until licensing is cleared (e.g. the Dan Worrall notes stay out) |
| User's own sessions | Private | Used live for that user only; never exported or trained on |

Quality is measured, not assumed: the retrieval fixture, the reviewer packet and a parameter quiz run on every index
promotion, and a promotion that regresses is rolled back (the index keeps the previous version).

## Model programme

- **Training data:** owner-written and owner-reviewed commands, shadow-log disagreements that the owner labels, drafted
  seeds marked as drafts. No user audio, no private sessions.
- **Sealed evaluation sets** that training never sees; results recorded per run (as the C6 and bake-off evidence is today).
- **Cadence:** retrain the local planner when the labelled set grows ~20% or a failure pattern appears; re-run the
  bake-off; promote only through the gate.
- **Hardware:** training and heavy evaluation on the GPU box (GPU 0 by default, following the box rules); the Mac runs
  quantised models for users.

## Measures reported every month

Understanding (natural phrasings), answer quality (reviewer scores), retrieval recall, latency by stage (planning,
OSC round trip, readback, analysis), unauthorised writes (must be zero), undo success (must be 100%), tester
satisfaction, and hosted cost per tester.

## Risks

| Risk | Mitigation |
|---|---|
| Hosted model cost or terms change | Router with a local fallback; per-tester budget; cost in the monthly report |
| Latency makes KENN feel slow | Route clear commands to the instant path; stream answers; measure by stage |
| Knowledge errors with confident tone | Source tiers, citations, contradiction checks, reviewer audits |
| Scope creep before the beta is solid | Stage 0 exit first; later stages start only behind their own gates |
| Too many plans again | This doc is the direction; older plans are reference only |

## Decisions needed from you

- [ ] Sign off this direction (hybrid brain, stages in this order)
- [ ] Brain provider, monthly budget per tester, opt-in versus default
- [ ] What may be sent to a hosted model (recommendation above)
- [ ] Whether Stage 2's craft notes should cover specific genres first (which?)
