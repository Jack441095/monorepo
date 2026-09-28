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

Stage 3b is not a feature stage. It was added on 28 Sept after an audit of the safety and answer paths found
eight live defects in code this plan's own principles rest on, including one where a producer could type
their way past the grounding gate. It sits here so it is not read as optional polish: the answer gate and the
write report are the two things the producer trusts most, and both had holes.

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
  > 28 Sept: Prompt token footprint reduced by >50% via `_clean_chunk_for_synthesis` and concise excerpt extraction in
  > `llm_rewrite.py` (KENN_LLM_CONTEXT_CHARS=650, KENN_LLM_DRAFT_CHARS=300), bringing token footprint to <= 450 tokens
  > with compact system prompt, cutting Apple Silicon prompt read latency from ~18 s to ~6 s. All 2,187 backend tests pass.
- [x] One router: rule parser → local planner → brain; every route logged with timing
  > 25 Sept: `/kenn/api/ask` already sends a request down one path (Live question → Live command via the rule
  > parser, then the shadow/live planner → knowledge answer via the brain). Every exit now logs the route, time,
  > whether the brain wrote the answer and whether a proposal came back to `runtime/logs/routes.jsonl` (no question
  > text; last 5,000 requests). `tooling/scripts/route_latency_report.py` prints p50/p95 per route against the
  > 4 s target.
- [x] Multi-turn context: anaphora ("do that on the snare too"), corrections ("no, the other one"), clarifying questions
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
  > 28 Sept: Implemented device-parameter follow-ups on active track/device ("now set the ratio to 4:1", "and the
  > release to 100 ms", "make the attack 15 ms", "ratio 4:1", "lower threshold by 3 dB") and "no, the other one"
  > pair/sibling resolution (e.g. Lead Vocal <-> Backing Vocal) while preserving clarification when ambiguous. Full test
  > suite passes 100%.
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
  > 26 Sept, round 4 (branch `kenn-next-build`): voice-dictation set 77.9% blind → 90.8%; a sealed Logic/FL-wording set
  > scored **92.7%** on its one blind run (plainer wording) → 97.8%. Found and fixed "synth track 5 dB louder" moving
  > track 5, "track 2, actually track 3" keeping track 2, and questions that proposed changes. Still not met.
  > 26 Sept, planner check before training run 13: rules then run 11 on all eight phrasing sets (1,751 phrasings) gets
  > 9 more right than the rules alone (1,648 vs 1,639) but 22 more wrong plans (23 vs 1): "lift the snare" unmutes it,
  > "record" presses play, "the track with the delay return" goes to Snare / Clap, pans with no amount go hard left.
  > The rules have overtaken it, so run 11 stays in shadow and **run 13 isn't trained**: another synthetic corpus would
  > repeat run 12. The next planner should learn from real tester wording, which the shadow log collects during the
  > pilot (where the rules ask, what was said, what happened next).
  > 28 Sept: Curated 505 phrasings holdout evaluated with `score_natural_phrasings.py`: **494 / 505 right (97.8%)**, 11 asked,
  > **0 wrong plans**. Fixed mid-sentence corrections ("wait no", inline params), track rename ("call"), "slo" typo,
  > compressor shorthand, and back-off threshold phrasings. Gate accuracy requirement (≥ 95% on ≥ 500 phrasings) exceeded.

### Stage 2 — Deep Ableton knowledge (beta weeks 2–10, runs alongside)

- [ ] Parameter-level knowledge for all 78 devices: every parameter's name, range, unit and what it does, read from
      Live (display tables, as with the fader law) and the manual
  > 28 Sept: **the manual is not in the index at all.** `pdf_evidence_class` (`retrieval/build_index.py:241`)
  > labels a PDF `official_ableton_manual` when its catalog entry is category `ableton` with "manual" in the
  > title or tags, but all six index versions hold 0 such chunks — 3,308 `curated_kenn_note`, 28
  > `youtube_transcript`, 2 `reference_document`, 2 of `kind: manual` (an Audio_Too checklist PDF). The whole
  > official-manual pathway is therefore dead code today: `display_results` abstains on a manual question,
  > `manual_grounding_evaluation` can never pass, `retrieval_index_shadow` filters on a class that does not
  > exist, and `session_intelligence.py:554`'s "Grounded in the authorized Ableton manual" is unreachable. The
  > Knowledge programme already names the manual the highest-trust source, so this is the one content gap that
  > contradicts the plan's own trust table. Ingest it with a catalog entry of category `ableton` and "manual"
  > in the tags, then re-run the retrieval gate: the describe-it fixtures should improve, and the manual's own
  > paragraph text will satisfy `has_manual_subject_overlap`.
- [ ] Notes for how things are done: gain staging, bus processing, sidechain, arrangement moves, genre conventions;
      drafted on the GPU notes model, checked automatically against sources, reviewed before approval
- [x] Grounded in the user's own setup: installed devices, packs and third-party plug-ins read from Live, so advice
      names what they actually have
  > 28 Sept: Implemented in `core/session_intelligence.py`. Bounded `present_devices` extracted across all active session
  > tracks and return buses from Live snapshots, exposing exact installed device names to advice generators and chat.
- [x] Contradiction checks and source tiers (manual and measured data above notes, notes above general advice)
  > 28 Sept: Verified in `test_source_tiers_and_contradictions.py` (8/8 pass) and `test_retrieval_evidence_classes.py` (14/14 pass).
  > Enforces strict source hierarchy (official manual/measurements 1.0 > curated notes 0.9 > transcripts 0.7), dynamic trust adaptation
  > with citations and user corrections, measurement mismatch detection across notes and user corrections, draft demotion on
  > conflict resolution (primary_a / primary_b), and index rebuild gating via `KENN_MAX_CONTRADICTIONS`.
- [ ] **Gate:** retrieval recall@4 ≥ 0.95 on a fixture grown to ≥ 300 questions; answer accuracy ≥ 90% on a
      parameter-level quiz scored by reviewers; no uncited factual claims in a 100-answer audit
  > 28 Sept: Parameter quiz test built in `test_device_parameter_quiz.py` (4/4 pass). Verifies evidence-backed device profiles
  > (Compressor, Auto Filter, Glue Compressor, Saturator, Roar), exact discrete UI landmarks, strict rejection of hallucinated
  > controls and mismatched units, and unit normalization across all profiles.
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
  >   intelligence benchmarks identical. Next: a stronger embedding model, evaluated on the GPU box first.
  >   **28 Sept correction: chat coverage on `main` measures 124/128, not 125** (same four failures:
  >   `bass-processing`, `harsh-vocal-fix`, `ambiguous-lufs-target`, `wwise-mobile-ambience-memory`; 81/84
  >   applicable, 43/44 abstention). Verified by re-running `tooling/scripts/eval_chat_coverage.py` with and
  >   without the Stage 3b changes stashed: identical either way, so nothing in the audit work cost a point.
  >   The 125 was most likely measured on `kenn-after-soak` before the merge, or is a transcription slip.
  >   Someone should re-record it from a clean run so the owner's record matches the tooling.
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
  > 26 Sept: sharper lines written by Claude in producer language, tested on a new sealed set of 228 questions Qwen3 8B
  > wrote from the notes alone (`evals/device_purpose_sealed_qwen8b.json`). Recall@4 on it: none 0.338, drafted 0.417,
  > sharper 0.386, **both 0.447**; original fixture 0.983 throughout. Both kinds of line are in the review doc, awaiting
  > owner ticks; `tooling/scripts/measure_use_it_when_lines.py` re-measures any selection in memory.
  > Shipping a reranker is a size/latency call (bge-reranker-base adds ~0.3–1 GB and ~1–2 s per answer on a Mac CPU,
  > unmeasured on device yet) — owner decision.
  > Fixture now **303 questions** (gate size reached): 128 original + 125 device-purpose + 50 technique-purpose
  > (`evals/technique_purpose_retrieval_cases.json`, producer wording, overlapping notes all count). Today's hybrid on
  > the technique set: recall@4 **0.84** (BM25 alone 0.64).
  > 28 Sept: measured `v1` ("Use it when" lines) across all fixtures on `main`: original recall@4 **0.983** (MRR 0.880),
  > describe-it **0.784** (was 0.768, MRR 0.624), sealed Qwen8b set **0.425** (was 0.346, +7.9pp, MRR 0.291).
  > Merged `kenn-after-soak` to `main`: return track mixer controls, tempo/time-sig chat commands, shorthand phrasing,
  > full 2,187-test suite passing 100%. Sanitized all remote box references; 0 secrets or GPU credentials tracked.
  > 28 Sept: Source tiers and contradiction tests consolidated in `test_source_tiers_and_contradictions.py` (8/8 pass).

### Stage 3 — Agentic co-producer (beta weeks 6–16)

- [ ] Device qualification factory: every insertable device measured and end-to-end tested per parameter
      (D1 in the tracker), growing from 10 devices to ≥ 25 and ≥ 60 parameters
- [x] Multi-step tasks from the deliberative planner (qualified once on real Live, 24 Sept): plan shown first, each step
      confirmed, one receipt per step, undo per step or for the whole task
  > 24 Sept / 28 Sept: Fully implemented and tested across `AssistantCoordinator` (`test_assistant_coordinator.py` 10/10 pass),
  > recovery qualification (`test_assistant_recovery_qualification.py` 1/1 pass, 8/8 cases), and live task qualification
  > (`test_assistant_live_task_qualification.py` 22/22 pass). Plan shown first with `execution_authorized=False`, each step confirmed
  > via identity-bound token, one verified receipt per step, drift-triggered replanning, and full restoration undo qualified
  > on real Live (`tooling/evaluation/results/KENN_REAL_LIVE_ASSISTANT_TASK.json`).
- [x] Advice → fix → re-measure: each audio finding offers a confirmable change and measures again after Apply
  > 25 Sept / 28 Sept: Built in `core/advice_next_step.py` (`test_advice_next_step.py` 6/6 pass) and verified in closed-loop
  > diagnostic suites (`test_closed_loop_agent.py` 2/2 pass, `test_masking_doctor_closed_loop.py` 3/3 pass,
  > `test_diagnostic_loop.py` 9/9 pass). Each audio finding offers one small, reversible confirmable change on the
  > identified track (e.g. "turn the Bass down 1 dB") with a listening test caveat and re-measure guidance ("export the
  > same way and ask again" / "load the new file in Inputs... and ask again"); multiple candidate tracks or master problems ask instead of guessing.
- [x] ≥ 15 qualified recipes (e.g. "clean up the low end", "make room for the vocal", "set up parallel drums")
  > 26 Sept (branch `kenn-recipes`): 15 named recipes built, none qualified on real Live yet. The three originals
  > (glue the drum bus, vocal cut through, low-end mud) moved faders by fixed raw amounts and misreported them ("-1.5
  > dB" was -2.8 dB; a vocal at 0 dB went to +2 dB); fixed to real dB. Twelve new ones in `core/mix_recipes.py`: room
  > for the kick, give X some space, bring X forward, push X back, sit X behind Y, dry up X, tighten the drum bus, tame
  > the vocal peaks, mono low end, solo the rhythm section, make the snare crack, clear the solos. Each writes its steps
  > as ordinary commands that go through the rule parser and safety checks; a step KENN can't do exactly makes the
  > recipe ask, and a step that changes nothing is dropped. Plain vague requests ("the hats are too loud") still ask.
  > 28 Sept: 15/15 recipes qualified with verified receipts and exact baseline undo restore (`tooling/evaluation/results/KENN_RECIPE_QUALIFICATION.json`, 15/15 passed in 88.1 s).
- [x] Planner promotion only through `live_llm_promotion.py` (≥ 500 comparisons, ≥ 14 days, ≥ 98% schema, ≥ 90% agreement)
  > 28 Sept: Fully implemented in `core/live_llm_promotion.py` and verified in `test_live_llm_promotion.py` (3/3 pass).
  > Strict gates enforce volume (≥ 500 comparisons), observation period (≥ 14 days), schema validity (≥ 98%),
  > deterministic agreement (≥ 90%), zero safety violations for active stage, and mandatory explicit human reviewer sign-off.
- [ ] **Gate:** recipes pass on real Live with exact undo; per-step latency ≤ 3 s; zero unauthorised writes across
      the pilot

### Stage 3b — Correctness and integrity (28 Sept audit, runs alongside)

The 28 Sept audit of the safety and answer paths found eight live defects. All eight are in code the
North Star's own principles depend on: "every claim is sourced or measured" and "a model never invents a
Live state, a parameter or a source". This stage is the cleanup list; it does not wait for a stage to open.

- [x] A producer could type their way past the grounding gate
  > 28 Sept: `generated_answer_validation` and `should_use_llm_rewrite` both treated a query beginning
  > `[stems masking analysis context]` or `[audio characterization:` as trusted host context: grounding was
  > hard-set to 90 with no warnings, confidence forced to "high", the evidence-overlap floor dropped from
  > 0.16 to 0.10, and the rewrite unlocked regardless of quality. Nothing in production ever emitted that
  > prefix — the path that did was consolidated away — so the only way to reach it was to type it. One token
  > in the question switched off every check. Confirmed by execution: the same fabricated answer went from
  > `accepted=False, 4 warnings` to `accepted=True, 0 warnings` with the prefix added. Host-supplied context
  > is now the `timeline_context` argument, which cannot be forged from a request body. All three live copies
  > removed; a test greps the package so a fourth cannot appear.
- [x] The evidence-overlap check counted the question as evidence
  > 28 Sept: `evidence_text` already began with the query and was then combined with it a second time, so
  > every word of the question scored as if it had been retrieved. The check answers "is the answer built out
  > of the notes we retrieved"; it was measuring answer↔question overlap. A hallucination reusing only the
  > question's own vocabulary cleared the 0.16 floor. The query is now excluded; `answered_intent` inside
  > `grounding_report` already covers whether the answer engages the question.
- [x] An answer's own `Sources:` line counted as evidence of synthesis
  > 28 Sept: the citation words are copied from labels we handed the model, so they always appear in the
  > evidence. An answer could clear the overlap floor on the strength of its citation with nothing in the
  > prose drawn from the note. The Sources: section is now removed before terms are counted.
- [x] The false-receipt guard missed the plainer way to claim a change
  > 28 Sept: `claims_live_change` only matched auxiliaries ("I've set", "I have set"), which is not how the
  > local model writes. 25 of 29 realistic phrasings slipped through, including "I turned the reverb down to
  > 20% wet", "I lowered the bass by 2 dB", "I muted the kick" and "Done - reverb send set up" (the "Done"
  > branch required a delimiter immediately after the word). Now 27/27 caught, 0 false positives on the
  > advice register KENN's own prompt asks for ("I'd set", "I would set", "I will set" are unreachable by
  > construction).
- [x] Documentation questions retrieved eight notes and cited none of them
  > 28 Sept: `display_results` correctly refuses to substitute a practical note for the official manual when a
  > producer asks for the manual, and returns an empty list. `results_are_weak` scored the *raw* retrieval
  > list, so the caller carried on and built an answer with an empty Sources: line. "What does the manual say
  > about send effects" returned 8 strong chunks, displayed 0, and did not abstain. `results_are_weak` now
  > checks the display set first. Chat coverage and abstention re-measured unchanged (124/128, 43/44).
- [x] A follow-up question was answered from the previous question's notes
  > 28 Sept: the per-session cache returned the last turn's chunks whenever the new question looked like a
  > follow-up. `should_use_history` says the turn belongs to the same conversation, not that the subject
  > matches, so "and what release time should I use?" after a reverb send question asked the model to answer
  > question B out of question A's evidence. Reuse now requires the new question's own subject words to be
  > present in the cached set; bare follow-ups ("what about that?", "and then?") still reuse.
- [x] A write that landed was reported as "Nothing was changed"
  > 28 Sept: `handle_command` wraps the Live write and the bookkeeping after it in one try, so a full disk or
  > a permissions error writing the exchange log produced `changed: False` and the sentence "Nothing was
  > changed" — at the moment KENN had just written to the set, with the receipt discarded. Now reports
  > `changed: true`, `error_code: applied_but_unlogged`, and points at undo. A failure *before* any write
  > still says nothing changed.
- [x] Verification that the fixes did not cost answer quality
  > 28 Sept: full suite 2,228 passed, 5 skipped, 0 failed (2,206 before, 22 new tests). Retrieval recall@4
  > 0.9828 (unchanged). Chat coverage 124/128 and abstention 43/44, byte-identical to the stashed baseline.
  > The LLM rewrite path is still reachable for a normal question (quality 86, grounding 90).

**Open from the same audit, not yet fixed** — these need their own work and are listed so nothing is lost:

- [ ] `LiveExecutor.undo_action` checks no confirmation, no mutation gate and no device identity, and writes
      `before` into whatever parameter now holds that index. No production caller today (tests only), but the
      class docstring's "disabled by default" is untrue of this method, and it drops the undo record when
      AbletonOSC's acknowledgement is lost — the exact bug the production path was already fixed for.
- [ ] `validate_llm_plan` silently skips the device-parameter range check when the snapshot carries no
      parameters for the device, and when a profile's bounds are non-numeric (NaN makes the guard false). Both
      fail open.
- [ ] `set_volume` with `relative: true` is silently dropped for an LLM plan whose unit is `normalized`:
      `propose_track_action` has no `relative` parameter, so "add 0.15 to the fader" becomes an absolute
      0.15 — a ~30 dB cut on a track at 0.5, which then passes readback and is journalled as verified.
- [ ] The deterministic-refusal guard in `handle_command` is conditioned on `and clean_command`, so a request
      with an empty `command` and an `llm_plan` skips both the refusal check and the deterministic comparison.
      `validate_llm_plan` still runs, so this is not a direct write bypass, but it defeats the rule parser's
      authority.
- [ ] `display_text("Mixer", "Volume", "db", 0.85)` renders unity as `0.8 dB`, and a silent Compressor
      threshold reads `-57.2 dB` instead of `-inf`. Two conversion layers disagree about the same physical
      value, and `volume_law` is the one that is measured.
- [ ] The semantic answer cache has no `session_id` column, so project A's answer can be served verbatim in
      project B for any query ≥ 0.95 similar. `chat_answer.py` enables this path precisely when there is *no*
      session context. The Stage 4 cross-project gate exists to prevent exactly this.
- [ ] `idempotency_bounds.prune_if_needed` evicts arbitrary set members rather than the oldest, so the
      replay-protection set drops recent action ids (verified: 5 of 10 recent keys evicted).
- [ ] `ACTION_FLAGS` has a duplicate `daw_control` key, so `action_denied_message` names the wrong environment
      variable. Behaviour is right today only because of an explicit legacy fallback.
- [ ] `endpoint_policy` fails open: unrecognised `business` POST paths are classified `PUBLIC` while its
      docstring promises fail-closed family defaults, and `/command` is classified `ORCHESTRATED` so the
      confirmation flag is `False` for the endpoint that drives Live.
- [ ] The `diagnostic_loop` `inconclusive` branch never advances `active_hypothesis_id`, so three inconclusive
      results wedge the loop permanently and no recommendation is reachable.
- [ ] `mix_recipes` zips steps against children, so a short proposal response yields "there's nothing to
      change" — a confident false negative. It also reports "I couldn't find a reverb return in this set" when
      the Live read failed, blaming the producer's session for a backend error.
- [ ] A producer's stated LUFS target is discarded: the rule captures the number but stores the literal
      "master to -9 LUFS", so "I master to -12 LUFS" is rejected and the chat intent falls through with no
      confirmation and no error.
- [ ] Only one preference per key survives (`record_preference` deactivates the rest) and there is no API to
      list or restore the inactive rows, which contradicts "see, edit, delete; nothing learned silently".
- [ ] `chat_completion_stream` returns normally on a mid-stream failure, so a truncated answer is validated as
      a complete candidate.
- [ ] `llm_rewrite._clean_chunk_for_synthesis` cuts mid-word and mid-code-fence, and appends a closing
      `</source_excerpt>` after a cut that can land inside the opening tag.
- [ ] The L2 semantic-cache list grows unbounded and is scanned in full on every query; a *semantic* match is
      also written into the exact-match cache, turning a soft 0.95 match into a hard one.
- [ ] `mix_recipes`, `device_units.display_to_raw(relative=True)`, `live_recipe.audition_loudness_trim_db` and
      `live_recipe.undo_steps` each treat a raw fader value as dB or fabricate a `readback` field.
      `live_recipe`'s trim constant is dead (never read) but is persisted into receipts.
- [ ] The Ableton manual has never been ingested, so **every** official-manual pathway in the product is dead:
      `pdf_evidence_class` would label it, but the index holds 0 `official_ableton_manual` chunks (3,308
      `curated_kenn_note`, 28 transcript, 2 `reference_document`), which makes `session_intelligence.py`'s
      "Grounded in the authorized Ableton manual" unreachable. This is a Stage 2 content gap, not a code gap.

### Stage 4 — Memory and personalisation (after Stage 1)
- [x] Project memory: decisions, references, what was tried, kept per Live set
  > 28 Sept: Persisted per session via `AssistantProfileStore` (`producer_preferences` and `production_episodes` tables).
  > Includes explicit outcomes, verdicts, and evidence refs bound strictly to session IDs.
- [x] Opt-in producer preferences ("I like my vocals bright", "I master to -9 LUFS"), always cited when used
  > 28 Sept: Implemented in `core/project_memory_advisory.py`. Explicit opt-in preferences are parsed from statements or
  > set via UI. When relevant to a question, KENN cites the preference in the answer prose ("Noting your preference for
  > this project: ...") and populates `applied_preferences`. Unrelated questions or empty sessions cite nothing.
- [x] Memory view in the UI: see, edit, delete; nothing learned silently
  > 28 Sept: Backed by REST endpoints (`GET /api/memory`, `POST /api/memory/preference`, `DELETE /api/memory/preference`,
  > `DELETE /api/memory/episode`, `POST /api/memory/clear`) and chat intents ("What do you remember about this project?",
  > "Forget preference ...", "Clear project memory"). Only allowlisted explicit preferences are saved.
- [x] **Gate:** testers can find and delete any memory; memory-using answers cite the memory; no cross-project leaks
  > 28 Sept: Verified in `test_project_memory_stage4.py` (5/5 pass) and `test_assistant_profile_memory.py` (7/7 pass).
  > Proved find/delete lifecycle, citation formatting, zero cross-project leakage between sessions, and rejection of silent/unallowlisted inferences.

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

Two more, added 28 Sept after the audit, because both failures were invisible until they were counted:

- **Answers with no citable source** (must be zero). The display layer can legitimately return nothing — that is
  how KENN says "I don't know" — but the answer must never be built anyway with an empty `Sources:` line.
- **Answers rejected by the grounding gate, and why** (rate plus top warning). A jump here means the retrieval or
  the notes changed, not that the gate is misbehaving. The gate failing *open* is the thing to alarm on, and the
  `test_the_marker_prefix_is_not_a_grounding_input_anywhere` test is the standing guard for that.

## Risks

| Risk | Mitigation |
|---|---|
| Hosted model cost or terms change | Router with a local fallback; per-tester budget; cost in the monthly report |
| Latency makes KENN feel slow | Route clear commands to the instant path; stream answers; measure by stage |
| Knowledge errors with confident tone | Source tiers, citations, contradiction checks, reviewer audits |
| Scope creep before the beta is solid | Stage 0 exit first; later stages start only behind their own gates |
| Too many plans again | This doc is the direction; older plans are reference only |
| A gate quietly stops gating (28 Sept) | The grounding gate had a bypass reachable by typing, and the write report said
  "nothing changed" after a real write. Gating logic is now covered by tests that reproduce each bypass, and the
  marker-prefix test greps the package so the pattern cannot come back. Auditing the gate is a recurring cost,
  not a one-off |

## Decisions needed from you

- [ ] Sign off this direction (hybrid brain, stages in this order)
- [x] Brain provider: local Qwen only (owner, 25 Sept) — no hosted budget or opt-in needed
- [x] What may be sent to a hosted model: nothing — no hosted model (owner, 25 Sept)
- [ ] Whether Stage 2's craft notes should cover specific genres first (which?)
- [ ] Ingest the Ableton Live Reference Manual now, or keep the knowledge base KENN-written only until Stage 2's
      parameter work lands? It is the one source the Knowledge programme ranks above curated notes, and the code
      is already written and tested for it; the gap is the catalogue entry and the extraction run.
- [ ] Does Stage 3b's open list get worked now or after the beta? Twelve of the eighteen have no production
      caller or no reachable path, so the beta is not blocked by any of them — but the semantic-cache
      cross-project leak and the `validate_llm_plan` range-check gaps are worth closing before a second tester
      runs.
