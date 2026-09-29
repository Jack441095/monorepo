# KENN north star: an expert production partner inside Ableton Live

**Written:** 2026-09-24 · **Owner:** Jack · **Status:** proposal for owner sign-off (brain decided 25 Sept: local only)

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
3. **Private by default:** audio never leaves the Mac, and neither does any text. The brain is a local model (owner
   decision, 25 Sept); there is no hosted provider.
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
| Conversation, explanation, multi-step reasoning | **The brain: local Qwen3 8B** (decision below) | Needs broad knowledge and real reasoning |
| Drafting knowledge notes, labelling training data | Box models (GPU notes model) | Cheap, offline, reviewed before use |

Options that were weighed (25 Sept: the owner chose A, local only):

| Option | Strengths | Costs and risks |
|---|---|---|
| **A. Larger local model** (8–14B, fine-tuned on KENN's knowledge and tools) | Private, offline, no per-use cost | Weaker reasoning; needs a strong Mac; slower (today's 4B is already 6–10 s); ongoing training work |
| **B. Hosted frontier model** (e.g. Claude through the API, with KENN's tools and retrieval) | Best reasoning and conversation now; improves without our training | Per-use cost; needs internet; privacy and terms review; latency depends on the network |
| **C. Hybrid (recommended)** | B for conversation and planning when online and opted in; A-class local model for private or offline use and commands | Two paths to test; a router decides |

**Decision (owner, 25 Sept): A, local Qwen only.** KENN's value is its tools, knowledge and safety model, and those stay
the same whichever brain drives them. Nothing leaves the Mac: no hosted model, no hosted budget, no opt-in to design.
The model layer's OpenAI-compatible endpoint stays in the code but is not used. Qwen3 8B was picked on 25 Sept (see
Stage 1). The cost of this choice is speed: on a 16 GB Mac with Live open the 8B is too slow for chat, so chat shows
the template first and swaps the model's answer in when it is ready.

## Stages

Each stage ends at a measured gate. Stages overlap where they don't depend on each other.

### Stage 0 — Private beta (now → ~4 weeks)

See `KENN_BETA_PLAN_2026-09-24.md`. Exit: qualified gate 14/14, 3 testers onboarded.

### Stage 1 — Conversational KENN (beta weeks 1–6)

- [x] Brain decision made — **owner, 25 Sept: local Qwen only** (option A). KENN stays fully on the Mac: no hosted model,
      nothing sent off the machine. The existing Ollama provider behind the model router serves it
      (`KENN_LLM_PROVIDER_<TASK>=ollama`, per-task switches `KENN_LLM_ENABLED_<TASK>`).
- [x] Choose the conversation model: compare local Qwen sizes on KENN's chat checks (quality on the GPU box, speed on
      the Mac), then fine-tune the winner on KENN's notes and answer style on the box
  > 25 Sept, **decided: Qwen3 8B** (owner delegated the choice). Same pass rate as 14B on KENN's checks (78/84; its own
  > answers 40/42 vs 42/43), a third faster (p50 2.8 s vs 3.8 s; 14B's p95 was 4.96 s, over the 4 s target), and
  > ~5 GB in memory vs ~9 GB, which matters on a 16 GB M3 running Live, KENN and the 2.8 GB planner. On the Mac as
  > `kenn-brain-qwen3-8b`; Mac speed measured after the soak. A style LoRA trained on KENN's own accepted answers
  > made things worse (model answer used 36/84 vs 40, p95 9.7 s vs 3.4 s), so plain 8B stays; see the review doc.
  > 25 Sept, first comparison on KENN's real answer path (84 chat questions, box GPU 0, thinking off; tool
  > `tooling/scripts/evaluate_chat_brain.py`): template 79/84 (0.16 s); Qwen3.5 4B 78/84, its answer used on 37
  > (36 pass), p50 3.8 s; **Qwen3 8B 78/84, used on 42 (40 pass), p50 2.8 s**; **Qwen3 14B 78/84, used on 43 (42 pass),
  > p50 3.8 s**. The model answers pass the same content checks as the template, so the choice is about how they read:
  > side-by-side review for the owner in `docs/reviews/KENN_BRAIN_ANSWERS_REVIEW_2026-09-25.md`. Two fixes came out of
  > it: the eval now bypasses KENN's semantic answer cache, and KENN adds the sources itself when a model's answer
  > leaves out "Sources:" (good 8B answers were being thrown away for that). Next: speed of 8B on the owner's M3/16 GB
  > (after the soak), then a KENN-style fine-tune of the winner on the box.
- [ ] Chat answers written by the brain from retrieved notes, with citations; templates stay as the offline fallback
  > 26 Sept, measured on the owner's M3 / 16 GB with Live running: Qwen3 8B takes 7–16 s an answer through the
  > companion, and KENN used its answer 1 time in 6 (the rest failed the grounding check after the wait). The prompt
  > carries ~1,400 tokens of notes, which the Mac reads at ~75 tokens/s before writing at ~17 tokens/s; Qwen3.5 4B
  > was no better in practice. Chat on this Mac is back on templates (instant). Ways forward, none built yet: fewer
  > and shorter notes in the prompt, showing the template at once and the model's answer when it's ready, or serving
  > the brain from the box GPU (2.8 s) for the owner's own use.
  > 29 Sept: "template now, model's answer when it's ready" is built and off by default
  > (`KENN_CHAT_BRAIN_DEFERRED=1`). The ask reply carries the template and a `brain_pending` job id; one background
  > worker runs the same rewrite and validation as before; the page polls `/kenn/api/ask/brain` and swaps the text in
  > only if the rewrite passed. Never for replies with a Live proposal. Each rewrite is timed in `routes.jsonl` as
  > `brain_deferred`. Tested with a stubbed model (12 backend, 3 frontend tests). Not measured: wait-to-swap on the
  > owner's M3 with Live open. Still not ticked until that run shows how often the swap lands and how long it takes.
- [x] One router: rule parser → local planner → brain; every route logged with timing
  > 25 Sept: `/kenn/api/ask` already sends a request down one path (Live question → Live command via the rule
  > parser, then the shadow/live planner → knowledge answer via the brain). Every exit now logs the route, time,
  > whether the brain wrote the answer and whether a proposal came back to `runtime/logs/routes.jsonl` (no question
  > text; last 5,000 requests). `tooling/scripts/route_latency_report.py` prints p50/p95 per route against the
  > 4 s target.
- [ ] Multi-turn context: anaphora ("do that on the snare too"), corrections ("no, the other one"), clarifying questions
  > 25 Sept: follow-ups for whole-track mixer changes work in the rule path, without a model: "do that on the snare
  > too", "same for the hats", "and the kick too", "now the vocal", "do the opposite on the vocal". The last command is
  > re-parsed against the current set, so "down 2 dB" applies from the new track's own level, and the result goes
  > through the normal parser and safety checks. The same track again, or two tracks at once, asks. Device-parameter
  > follow-ups and "no, the other one" still ask (next).
  > Same day: answering KENN's own questions works — "make the bass louder" → "By how much?" → "3 dB"; "pan the synth
  > left" → "30%" or "hard"; "kick -3 dB" → "at -3" (a level) or "3 dB quieter" (a change); "mute" → "the hats".
  > Short replies only, within 5 minutes, joined to the pending request and parsed normally. Found on the way: "pan
  > the synth left 30%" panned right (side before the amount was ignored) — fixed; a pan with no side now asks.
  > Same day: corrections — "no, I meant the snare", "sorry, the kick", "not the hats, the kick", "actually the
  > vocal" — move the last whole-track change to the track meant, as a new proposal. If the first change was already
  > applied it stays, and KENN says so and points at "undo". Device changes repeat too ("set the compressor
  > threshold on the drum bus to -20 dB" → "do that on the vocal"); a track without that device gets a plain "Kick
  > doesn't have that device". Still asks: "no, the other one", two tracks at once.
  > 29 Sept: two tracks at once works — "do that on the snare and the kick" (also "same for…", "the opposite on…",
  > "and the kick and the synth too", up to four tracks) is one confirmable recipe with a step per track, each relative
  > change taken from that track's own level. The same track again, a repeated name, or five tracks still ask.
  > "no, the other one" still can't be resolved (there is no exact identity to move to), but it now says what the last
  > change was and how to name the track; "no, the snare and the kick" says to use "do that on the snare and the kick".
  > What's left for this item: "the other one" after KENN listed exactly two matching tracks, and how well any of this
  > holds up with a model in the loop.
- [x] Safety unchanged: the brain can only call typed tools; writes still go proposal → Apply → readback → receipt
  > 25 Sept: checked. The brain writes prose only; it has no Live access. Live changes run only in
  > `handle_command` with a confirmed proposal; a model plan must pass `validate_llm_plan` (typed actions, exact
  > names from the current set, no hidden nested steps) and cannot override a rule-parser refusal (tests in
  > `test_live_command.py`: typed plan must match, cannot bypass refusal, shadow keeps rule authority). One gap found
  > and closed: a brain answer saying "I've turned the bass down" was a false receipt; the grounding gate now
  > throws it away and uses the template (no false hits on 122 real Qwen answers).
- [ ] **Gate:** ≥ 95% correct on ≥ 500 natural phrasings (curated holdout grown from 24); human-review packet passes with
      two reviewers; p95 answer latency ≤ 4 s online; zero writes without Apply in shadow logs
  > 25 Sept, phrasings (`docs/evidence/KENN_NATURAL_PHRASINGS_2026-09-25.md`): 505 phrasings now exist
  > (Claude-drafted, labels need the owner). Through the whole gateway: **95.4% right, 0 wrong** on them, but only
  > after tuning on them. Two fresh blind sets written by Qwen3 14B and 8B scored **71.9% and 70.2%** on first run,
  > so ~70% is where the rules really stand on unseen wording. Six wrong plans found and fixed along the way
  > (sends inserted as Reverb devices, "play the drums" stopping/starting the whole set, a rename picking the track
  > from the new name, "vocal up a hair" also cutting the Synth). Run 9b as a fallback where the rules ask made
  > things *less* safe: 18 wrong plans on one blind set, e.g. "can i hear the vocal without the synth" soloed the
  > Synth. Not met; needs fresh blind wording each round, owner-checked labels, and a planner that asks rather than
  > guesses.
  > 29 Sept, round 4 (`docs/evidence/KENN_BLIND_PHRASINGS_2026-09-29.md`): 146 new phrasings written before scoring, in a
  > new register. First run **69.2%** right, 3 wrong (**76.7%, 1 wrong** after I corrected 10 labels that
  > ignored product rules, e.g. Limiter isn't insertable and the vocal is already at 0 dB). The wrong plan that mattered:
  > "kill the send from bass to delay" proposed **muting the Bass**. Fixed by group (spoken minus, `@`, "3 more dB",
  > "swing the snare 15% right", "feed X into the reverb", markers with a colon, and so on), 34 tests; all earlier sets
  > rescored with no new wrong plan. The new set is now development data (143/146), so the blind number stays ~70–77%.
  > Two pinned policies conflict with the labelling rules ("lead vocal to -4" and "kill playback" both ask): owner call.

### Stage 2 — Deep Ableton knowledge (beta weeks 2–10, runs alongside)

- [ ] Parameter-level knowledge for all 78 devices: every parameter's name, range, unit and what it does, read from
      Live (display tables, as with the fader law) and the manual
  > 29 Sept (cloud session, no Live): the pipeline after the measurement is built. `measure_device_parameters.py` →
  > `tooling/data/measured_devices/<device>.json` → `build_parameter_reference.py --out <notes>` writes
  > `measured-<device>-<n>.md` (12 parameters a note; ranges, mappings and options exactly as Live displayed them; drafts
  > until `--approve`), which the index labels as the top tier and the note check reads back. 0 of 78 devices are measured
  > yet: that needs Live open (10 parameters on 9 devices are covered by the existing profiles). "What it does" still
  > comes from the manual notes; nothing here writes prose about a parameter.
- [ ] Notes for how things are done: gain staging, bus processing, sidechain, arrangement moves, genre conventions;
      drafted on the GPU notes model, checked automatically against sources, reviewed before approval
- [ ] Grounded in the user's own setup: installed devices, packs and third-party plug-ins read from Live, so advice
      names what they actually have
  > 29 Sept (cloud session, tested on a made-up Mac layout, not yet on a real one): `core/installed_devices.py` reads names
  > only, from disk — Live's built-in devices from the app bundle, saved racks from the User Library (via `Library.cfg`),
  > packs from Factory Packs, plug-ins from the VST3/Audio Unit/VST folders. When the page sends `ground_in_set` (the
  > chat does now) and a knowledge answer found a source, a question about EQ, compression, limiting, reverb, delay or
  > saturation gets one extra factual line: "In your Live, built into …; plug-ins whose names match: …; your saved racks:
  > …; already on your tracks: …". A plug-in's family is a guess from its name and the line says so. Nothing is loaded and
  > nothing leaves the Mac. Not covered: parameters of third-party plug-ins, pack devices inside packs, and Live's own
  > browser view (AbletonOSC has search but no listing). Check on the Mac: ask "how do I EQ a vocal?" in the app.
- [ ] Contradiction checks and source tiers (manual and measured data above notes, notes above general advice)
  > 29 Sept (cloud session, no notes or Live here): built and tested on synthetic notes, not yet run on the real 77.
  > Tiers: `core/source_tiers.py` orders measured Live data > Ableton manual > KENN note > third-party; every cited source
  > in a chat answer now carries `tier` and `tier_label`; only a generated `measured-*.md` note with a `Measured at:` date
  > can claim the measured tier. Check: `knowledge/measured_facts.py` compares numbers in approved notes with the ranges
  > Live measured (the 10 device profiles now, plus any `tooling/data/measured_devices/*.json` from
  > `measure_device_parameters.py`); a note outside the range becomes a `note_vs_measured` contradiction with the
  > measurement winning, and retires when the note is fixed. Next: run
  > `tooling/scripts/check_notes_against_measurements.py` on the Mac against the real notes; the item stays open until then.
- [ ] **Gate:** retrieval recall@4 ≥ 0.95 on a fixture grown to ≥ 300 questions; answer accuracy ≥ 90% on a
      parameter-level quiz scored by reviewers; no uncited factual claims in a 100-answer audit
  > 2026-09-24 baseline: fixture now 128 + 125 = 253 questions. The new 125 (`evals/device_purpose_retrieval_cases.json`,
  > Claude-drafted, pending owner review) describe what a producer wants without naming the device ("line up two mics
  > a few ms out of time" → Align Delay). Recall@4: **0.62** hybrid, 0.60 BM25 (0.51 counting only the device note) —
  > against 0.966 on the original fixture, where questions usually name the topic. Cause: hybrid only re-scores BM25's
  > top 60, so embeddings can't bring in a note the keywords missed. Experiment (not shipped): union of BM25 and
  > embedding candidates with reciprocal-rank fusion, embedding weight 2 → **0.74** on the new set and **0.983** on the
  > original (no regression). Shipping it needs abstention to stop relying on BM25-scale scores (an embedding-only hit
  > would be dropped as "not relevant"), and a re-run of the intelligence gate and review packet. Next levers: that
  > fusion change, a stronger embedding model than MiniLM (download/licence is an owner decision), "use it when…"
  > phrasing in device notes (checked on a held-out half so it isn't tuned to the fixture).
  > Shipped on the branch the same evening (owner: "yes, in that order"): the fusion, with every result carrying the best
  > BM25-scale score at or below its rank so the top score that decides "I don't know" is unchanged. Recall@4 0.983
  > (was 0.966) and 0.736 (was 0.616); chat coverage 125/128 (was 124), abstention 43/44 unchanged; the other four
  > intelligence benchmarks identical. Next: a stronger embedding model, evaluated on the GPU box first.
  > Embedding model test on the GPU box (downloaded there only, via the box's HF mirror; MIT licence; revisions and
  > weight hashes recorded): recall@4 on the describe-it questions, hybrid / embeddings alone —
  > MiniLM (current) **0.736** / 0.672; bge-small-en-v1.5 (133 MB) **0.760** / 0.728; bge-base-en-v1.5 (438 MB) 0.776 /
  > **0.808**. All ≈ 0.98 on the original fixture. **Decision: keep MiniLM** — bge-small wins 3 of 125 questions, and
  > even bge-base tops out near 0.81, so model size is not the route to 0.95. The gap is vocabulary: notes describe
  > devices technically, producers describe goals. Next levers: a "Use it when…" line of goal phrasing per device note
  > (tuned on half the questions, scored on the other half), then a cross-encoder reranker on the top 20.
  > 25 Sept, reranker test on the GPU box (downloaded there only, deleted after; revisions and licences recorded): the
  > fused search's top 20 re-scored per question. Recall@4 original / describe-it: today 0.983 / 0.744;
  > ms-marco-MiniLM-L-6-v2 (Apache-2.0, ~90 MB) 0.966 / 0.800; **bge-reranker-base (MIT, ~1.1 GB fp32) 1.000 / 0.808**.
  > Ceiling: the right note is in the top 20 for 100% / 87.2%, so reranking already captures most of what it can; the
  > last 13% need better candidates (note wording). "Use it when…" drafts: 0.744 → 0.760, awaiting owner review.
  > Shipping a reranker is a size/latency call (bge-reranker-base adds ~0.3–1 GB and ~1–2 s per answer on a Mac CPU,
  > unmeasured on device yet) — owner decision.
  > Fixture now **303 questions** (gate size reached): 128 original + 125 device-purpose + 50 technique-purpose
  > (`evals/technique_purpose_retrieval_cases.json`, producer wording, overlapping notes all count). Today's hybrid on
  > the technique set: recall@4 **0.84** (BM25 alone 0.64).

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
satisfaction, and how often the local model's answer lands (and how long it takes) on each tester's Mac.

## Risks

| Risk | Mitigation |
|---|---|
| Local model too slow or too weak on testers' Macs | Templates as the instant path; model answer swapped in when ready; measure the swap rate and wait per Mac |
| Latency makes KENN feel slow | Route clear commands to the instant path; stream answers; measure by stage |
| Knowledge errors with confident tone | Source tiers, citations, contradiction checks, reviewer audits |
| Scope creep before the beta is solid | Stage 0 exit first; later stages start only behind their own gates |
| Too many plans again | This doc is the direction; older plans are reference only |

## Decisions needed from you

- [ ] Sign off this direction (local Qwen brain, stages in this order)
- [x] Brain provider: local Qwen only (owner, 25 Sept) — no hosted budget or opt-in needed
- [x] What may be sent to a hosted model: nothing — no hosted model (owner, 25 Sept)
- [ ] Whether Stage 2's craft notes should cover specific genres first (which?)
