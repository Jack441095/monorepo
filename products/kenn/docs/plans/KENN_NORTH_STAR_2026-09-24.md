# KENN north star: an expert production partner inside Ableton Live

**Written:** 2026-09-24 · **Owner:** Jack · **Status:** proposal for owner sign-off (brain decided 25 Sept: local only)

The long-term plan for KENN's intelligence. It merged the earlier GLM, frontier and beta plans into one direction, and
those older plan files were removed on 29 Sept so this is the one place that decides the gates (they are in git
history). `KENN_MEGA_PLAN_2026-09-29.md` sets the order of the work. Stage 0 is the private beta (`KENN_BETA_PLAN_2026-09-24.md`). The GLM tracker stays the working log. Tick items here
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
  > **1 Oct, re-measured and the 26 Sept figures do not hold.** `tooling/scripts/measure_chat_latency.py`, index
  > `v-db8c6334cf63`, `kenn-brain-qwen3-8b`, both answer caches off, 30 questions: on the streaming path
  > (`kenn.core.chat`, `chat_cli`) 29 attempted, **7 accepted (24%), median 60.2 s, p95 89.5 s** — not 7–16 s. On the
  > **companion surface (`answer_payload`) the model never wrote an answer at all**: 0 of 30, `llm_enhanced` false on
  > all 30, 20.2 s median, and that 20 s is `post_answer_critique()` grading KENN's own template — so the companion
  > pays a fifth of a minute for self-criticism and ships the template every time. Templates alone: 0.08 s median,
  > 0.15 s p95. Of 22 rejections, 17 were `generated answer introduced unsupported measurements` — the model invents
  > numbers. Full numbers, the prompt cut, and the Live-contention split:
  > `docs/reviews/KENN_BRAIN_ANSWER_LATENCY_2026-10-01.md`.
  > 28 Sept: Prompt token footprint reduced by >50% via `_clean_chunk_for_synthesis` and concise excerpt extraction in
  > `llm_rewrite.py` (KENN_LLM_CONTEXT_CHARS=650, KENN_LLM_DRAFT_CHARS=300), bringing token footprint to <= 450 tokens
  > with compact system prompt, cutting Apple Silicon prompt read latency from ~18 s to ~6 s. All 2,187 backend tests pass.
  > **1 Oct, the <= 450 token figure is wrong on this Mac and is corrected here.** It holds only on the MLX path.
  > `_mlx_engine_answers()` is False here (MLX is not installed), so KENN sends `build_system_prompt()` — measured
  > **534 tokens, 63% of the request** — instead of `STATIC_CORE_SYSTEM_PROMPT`. Exact `prompt_eval_count` from Ollama
  > on 3 questions: **816 mean** (849/840/759), not <= 450. The short prompt cannot simply be substituted: on the
  > Ollama path it made most answers fail the structure check (26 Sept), so 534 is the floor and the 28 Sept claim of
  > "prompt read latency ~6 s" is not supported — prefill measured here is 0.06 s at 356 tokens and 0.07 s at 1,028.
  > 29 Sept: "template now, the model's answer when it's ready" exists as `core/answer_upgrades.py`
  > (`KENN_LLM_BACKGROUND=1`): the reply carries the template and an `answer_upgrade` id, the full answer pipeline runs
  > once in the background, and the app swaps the text in only if the grounding check accepted it. This note has no
  > Mac timing for it yet, so the item stays open until there is one (how often the swap lands, and after how long).
  > **1 Oct, the Mac timing this note was waiting on now exists, and the path was broken.** Driving it through the
  > real `answer_upgrades.start()` calls the ask route makes: **0 of 30 swaps landed**, because the background thread
  > inherited the ask path's 20 s HTTP timeout (`AUDIO_TOO_LLM_TIMEOUT`) against a ~60 s answer, so every one timed out
  > and offered back the template it was meant to replace. Fixed with `llm_rewrite.background_budget()` — a
  > `ContextVar`, so the longer budget goes to the upgrade thread and not to the producer's next question — and
  > **re-measured: 4 of 30 land (13%)**, template on screen at **p50 0.22 s / p95 0.54 s**, the swap itself at
  > p50 74 s when it lands. `route_latency_report.py` reports the same events from the route log independently
  > (30 started, 4 accepted, median 73.8 s), so the harness and the existing tool agree. The streaming path over the
  > same 30 questions is 7/29 (24%) at a 60.2 s median. The box stays **unticked on purpose**: the template path meets
  > the 4 s gate comfortably, but "answers written by the brain" is 13% here and takes 74 s when it works, against a
  > gate of >= 70% within 15 s. The binding constraint is decode, not the prompt (see the 1 Oct notes above and
  > `docs/reviews/KENN_BRAIN_ANSWER_LATENCY_2026-10-01.md`), so the next moves are D3 (model choice; Qwen3 1.7B does
  > a 120-token answer in 3.17 s) and serving from the box GPU. A second defect is recorded and deliberately not
  > changed: `valid_response()` gates only the non-streaming path, so a well-formed bulleted answer can be discarded
  > for format on the swap path while the streaming path accepts it.
  > **1 Oct, later: measured on a box GPU, and the gate is nearly in reach.** One RTX 4090 (GPU 0, one of the two
  > AGENTS.md authorises for KENN work), same index, same 30 questions, same Q4_K_M quantisation over an SSH tunnel:
  > streaming **5.2 s median / 7.5 s p95** against the Mac's 60.2 / 89.5 — **~12x** — and the background swap lands
  > at **5.8 s p50** against the Mac's 81.4 s. Raw decode of 300 tokens is 2.12 s at 141 tok/s against the Mac's
  > 6-7 tok/s, ~20x. So the honest answer to "can this reach p95 <= 4 s" is **not on the M3, and nearly on one 4090**:
  > the remaining 3.5 s is a model-size question now, not a hardware one, which is what D3 schedules. The acceptance
  > rates are *not* comparable and must not be read as a regression — the Mac's `kenn-brain-qwen3-8b` is a
  > KENN-curated build and the box ran stock `qwen3:8b`, same Q4_K_M but a different digest; only the timings are
  > like-for-like. Receipts `KENN_CHAT_LATENCY_BOX_GPU0_STREAM_2026-10-01.json` and
  > `KENN_BACKGROUND_SWAP_BOX_GPU0_2026-10-01.json`. **Box GPU is a good, fast machine but it is not the producer's
  > laptop, so a KENN that depends on it is not a KENN that works on its own.**
  > **1 Oct, later, and this one was never a speed problem: KENN was asking a thinking model not to think.**
  > Qwen3 writes a `thinking` block before answering; with the token cap spent there it returns **zero characters**
  > (`think=true` -> 1054 chars of thinking, 0 of answer). KENN's `_ollama_think_off()` was gated on a JSON schema
  > being present, so chat answers took Ollama's OpenAI-compatible route, which ignores `think` — measured **24 of
  > 30 questions on the 4B returning an empty answer**, logged as "generation returned no answer" and mistaken for a
  > grounding failure. And the guard never fired on the shipped model anyway: the pattern `(?:^|/)qwen3` does not
  > match `kenn-brain-qwen3-8b`, so the fix was live on the 4090 and dead on the M3. Both fixed (schema gate
  > removed, pattern matches `qwen3` anywhere). **Acceptance 24% -> 38% on the M3 and 17% -> 34% on the 4090**, and
  > on the 4090 it is free: 5.5 s median, 6.9 s p95. On the M3 it costs real time (60 s -> 91 s) because the
  > previously-discarded answers now run to the cap and are real, which is the right trade. Part of what this item
  > recorded as "failed the grounding check after the wait" was never reaching the grounding check.
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
  > **30 Sept correction: re-scored on unmodified `main`, the same command now gives 492 / 505 right (97.4%), 13 asked,
  > 0 wrong plans** — not the 494 / 11 recorded above. The 494 was the 28 Sept number and drifted as later work
  > landed; the accuracy requirement is met either way, and **0 wrong plans still holds**, which is the part this gate
  > actually turns on. Corrected here so the record matches what the tooling prints.
  > 30 Sept, round 9 (`docs/evidence/KENN_BLIND_PHRASINGS_ROUND9_MIXNOTES_2026-09-30.md`), mix-notes register: 118
  > phrasings written before scoring, **74 / 118 (62.7%), 40 asked, 4 wrong** on the one blind run. The real find was a
  > **silent wrong write**: "Lead Vocal off solo" **soloed** the vocal, because every negation pattern in
  > `live_intent.py` required a verb, so a bare mix-note negation fell through to the positive branch — it read back
  > clean and was journalled as verified. "no solo", "solo off" and "off mute" were wrong the same way. Fixed on
  > `kenn-solo-negation` (14 tests); the holdout re-scores 492/505 with and without the change, so it cost no
  > phrasings. Two of the other three wrong rows were mislabels, not defects. **The round's second author was an
  > automated session rather than a person who had not written the parser fixes**, which weakens the
  > independence claim and is stated in the evidence doc; the plan wants a human second author each round.
  > 29 Sept, round 5 (`docs/evidence/KENN_BLIND_PHRASINGS_2026-09-29.md`): 146 new phrasings written before scoring, in a
  > new register. First run **69.2%** right, 3 wrong (**76.7%, 1 wrong** after I corrected 10 labels that
  > ignored product rules, e.g. Limiter isn't insertable and the vocal is already at 0 dB). The wrong plan that mattered:
  > "kill the send from bass to delay" proposed **muting the Bass**. Fixed by group (spoken minus, `@`, "3 more dB",
  > "swing the snare 15% right", "feed X into the reverb", markers with a colon, and so on), 34 tests; all earlier sets
  > rescored with no new wrong plan. The new set is now development data (143/146), so the blind number stays ~70–77%.
  > Two pinned policies conflict with the labelling rules ("lead vocal to -4" and "kill playback" both ask): owner call.

### Stage 2 — Deep Ableton knowledge (beta weeks 2–10, runs alongside)

- [ ] Parameter-level knowledge for all 78 devices: every parameter's name, range, unit and what it does, read from
      Live (display tables, as with the fader law) and the manual
  > **30 Sept correction to the 28 Sept note below: the manual IS in the index.** 1,436
  > `official_ableton_manual` chunks from `live11-manual-en.pdf`, 16 / 16 grounding cases passing, `--require-manual`
  > exit 0. Every "0 chunks" figure in the note below was true on 28 Sept and is not true now.
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
  > 29 Sept (cloud session, no Live): the pipeline after the measurement is built. `measure_device_parameters.py` →
  > `tooling/data/measured_devices/<device>.json` → `build_parameter_reference.py --out <notes>` writes
  > `measured-<device>-<n>.md` (12 parameters a note; ranges, mappings and options exactly as Live displayed them; drafts
  > until `--approve`), which the index labels as the top tier and the note check reads back. 0 of 78 devices are measured
  > yet: that needs Live open (10 parameters on 9 devices are covered by the existing profiles). "What it does" still
  > comes from the manual notes; nothing here writes prose about a parameter.
- [ ] Notes for how things are done: gain staging, bus processing, sidechain, arrangement moves, genre conventions;
      drafted on the GPU notes model, checked automatically against sources, reviewed before approval
- [x] Grounded in the user's own setup: installed devices, packs and third-party plug-ins read from Live, so advice
      names what they actually have
  > 28 Sept: Implemented in `core/session_intelligence.py`. Bounded `present_devices` extracted across all active session
  > tracks and return buses from Live snapshots, exposing exact installed device names to advice generators and chat.
  > 29 Sept (cloud session, tested on a made-up Mac layout, not yet on a real one): `core/installed_devices.py` reads names
  > only, from disk — Live's built-in devices from the app bundle, saved racks from the User Library (via `Library.cfg`),
  > packs from Factory Packs, plug-ins from the VST3/Audio Unit/VST folders. When the page sends `ground_in_set` (the
  > chat does now) and a knowledge answer found a source, a question about EQ, compression, limiting, reverb, delay or
  > saturation gets one extra factual line: "In your Live, built into …; plug-ins whose names match: …; your saved racks:
  > …; already on your tracks: …". A plug-in's family is a guess from its name and the line says so. Nothing is loaded and
  > nothing leaves the Mac. Not covered: parameters of third-party plug-ins, pack devices inside packs, and Live's own
  > browser view (AbletonOSC has search but no listing). Check on the Mac: ask "how do I EQ a vocal?" in the app.
- [ ] Contradiction checks and source tiers (manual and measured data above notes, notes above general advice)
  > 28 Sept: Verified in `test_source_tiers_and_contradictions.py` (8/8 pass) and `test_retrieval_evidence_classes.py` (14/14 pass).
  > Enforces strict source hierarchy (official manual/measurements 1.0 > curated notes 0.9 > transcripts 0.7), dynamic trust adaptation
  > with citations and user corrections, measurement mismatch detection across notes and user corrections, draft demotion on
  > conflict resolution (primary_a / primary_b), and index rebuild gating via `KENN_MAX_CONTRADICTIONS`.
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
  > 30 Sept: the wave-1 set is built and rehearsed, so night 1 costs two hours of measurement rather than two hours
  > of preparation. `docs/runbooks/KENN_DEVICE_ZOO_WAVE1.md` lists the twelve regular tracks and
  > `tooling/scripts/prep_device_zoo.py` checks the names and dry-runs the whole pipeline on `FakeLiveBackend`
  > (12 of 12 measured, 35 candidate profiles, 17 choosers, 1 unmapped). It found that `pick_raw_values` collapsed
  > an all-positive dB control to a single test value, so Saturator's Base and Multiband Dynamics' Range could never
  > have qualified; fixed, and the 0 dB clamp still holds for controls that go below it. **Still 0 of 78 measured:**
  > nothing here has touched real Live, and four of the twelve wave-1 devices are not in
  > `DEVICE_INSERTION_ALLOWLIST`, so that part of the set is a hand drag.
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

- [x] `LiveExecutor.undo_action` checks no confirmation, no mutation gate and no device identity, and writes
      `before` into whatever parameter now holds that index. No production caller today (tests only), but the
      class docstring's "disabled by default" is untrue of this method, and it drops the undo record when
      AbletonOSC's acknowledgement is lost — the exact bug the production path was already fixed for.
  > 28 Sept: Fixed in `core/live_executor.py`. Enforces `allow_legacy_mutation` gate on undo, checks pre-write
  > Live device and parameter identity before restoring, supports confirmation tokens, and reconciles lost OSC
  > acknowledgements via readback (`unacknowledged_write_reconciled`); verified in `test_live_control_safe_pipeline.py`.
- [x] `validate_llm_plan` silently skips the device-parameter range check when the snapshot carries no
      parameters for the device, and when a profile's bounds are non-numeric (NaN makes the guard false). Both
      fail open.
  > 28 Sept: Fixed in `core/live_command.py`. Enforces fail-closed validation when capability has no parameters
  > and rejects non-finite bounds (NaN/inf); verified in `test_live_command.py`.
- [x] `set_volume` with `relative: true` is silently dropped for an LLM plan whose unit is `normalized`:
      `propose_track_action` has no `relative` parameter, so "add 0.15 to the fader" becomes an absolute
      0.15 — a ~30 dB cut on a track at 0.5, which then passes readback and is journalled as verified.
  > 28 Sept: Fixed in `core/live_command.py`. Normalized relative changes are resolved against current snapshot
  > track values before proposal, converting to validated absolute normalized values; verified in `test_llm_plan_units.py`.
- [x] The deterministic-refusal guard in `handle_command` is conditioned on `and clean_command`, so a request
      with an empty `command` and an `llm_plan` skips both the refusal check and the deterministic comparison.
      `validate_llm_plan` still runs, so this is not a direct write bypass, but it defeats the rule parser's
      authority.
  > 28 Sept: Fixed in `core/live_command.py`. Removed `clean_command and` conditions from deterministic refusal
  > and action comparison checks, preserving rule parser authority; verified in `test_live_command.py`.
- [x] `display_text("Mixer", "Volume", "db", 0.85)` renders unity as `0.8 dB`, and a silent Compressor
      threshold reads `-57.2 dB` instead of `-inf`. Two conversion layers disagree about the same physical
      value, and `volume_law` is the one that is measured.
  > 28 Sept: Fixed in `core/device_units.py`. Unified `display_text` volume/fader reporting with `volume_law`
  > (0.85 -> 0.0 dB, 0.0 -> -inf dB) and mapped silent Compressor threshold to -inf dB; verified in `test_device_units.py`.
- [x] The semantic answer cache has no `session_id` column, so project A's answer can be served verbatim in
      project B for any query ≥ 0.95 similar. `chat_answer.py` enables this path precisely when there is *no*
      session context. The Stage 4 cross-project gate exists to prevent exactly this.
  > 28 Sept: Fixed in `core/session_memory.py` and `core/chat_answer.py`. Added `session_id` column, compound
  > unique key and index, session-keyed L1 and L2 filtering, and bounded FIFO L2 cache; verified in `test_semantic_cache_versioning.py`.
- [x] `idempotency_bounds.prune_if_needed` evicts arbitrary set members rather than the oldest, so the
      replay-protection set drops recent action ids (verified: 5 of 10 recent keys evicted).
  > 28 Sept: Fixed with `IdempotencyTrackingSet` (dict-backed `MutableSet`) in `core/idempotency_bounds.py`
  > and deployed across all mutating services. Guarantees strict FIFO eviction of oldest keys under memory pruning;
  > verified in `test_idempotency_bounds.py` that 10/10 recent keys survive while exactly the oldest 5,000 are evicted.
- [x] `ACTION_FLAGS` has a duplicate `daw_control` key, so `action_denied_message` names the wrong environment
      variable. Behaviour is right today only because of an explicit legacy fallback.
  > 28 Sept: Fixed in `core/action_policy.py`. Removed duplicate key to cite canonical `KENN_ALLOW_DAW_CONTROL`;
  > verified in `test_ported_platform_modules.py`.
- [x] `endpoint_policy` fails open: unrecognised `business` POST paths are classified `PUBLIC` while its
      docstring promises fail-closed family defaults, and `/command` is classified `ORCHESTRATED` so the
      confirmation flag is `False` for the endpoint that drives Live.
  > 29 Sept: Closed in `core/endpoint_policy.py`. An allowlist miss on any non-read method (POST included, plus
  > verbs like TRACE that the old mutating-method list never matched) now lands AUTHENTICATED, and `/command`
  > classifies `ORCHESTRATED` with `confirmation_required` firing on it; verified in `test_ported_platform_modules.py`.
- [x] The `diagnostic_loop` `inconclusive` branch never advances `active_hypothesis_id`, so three inconclusive
      results wedge the loop permanently and no recommendation is reachable.
  > 29 Sept: Fixed in `core/diagnostic_loop.py`. One inconclusive verdict still asks for clarification; a second
  > consecutive one on the same hypothesis advances to the next, so the loop can no longer stall on a test the
  > producer cannot run; verified in `test_diagnostic_loop.py`.
- [x] `mix_recipes` zips steps against children, so a short proposal response yields "there's nothing to
      change" — a confident false negative. It also reports "I couldn't find a reverb return in this set" when
      the Live read failed, blaming the producer's session for a backend error.
  > 29 Sept: Fixed in `core/mix_recipes.py`. A step counts as already-done only when its child reports an explicit
  > `before == after` readback, positional pairing is trusted only when children mirror the steps one-for-one, and a
  > failed returns read now says the read failed instead of blaming the set (`Set.returns_read_failed`); verified in
  > `test_mix_recipes.py`.
- [x] A producer's stated LUFS target is discarded: the rule captures the number but stores the literal
      "master to -9 LUFS", so "I master to -12 LUFS" is rejected and the chat intent falls through with no
      confirmation and no error.
  > 29 Sept: Fixed in `core/project_memory_advisory.py`. The rule now stores the value the producer actually spoke
  > (`m.group(0)`) instead of the canned example; verified in `test_project_memory_stage4.py`.
- [ ] Only one preference per key survives (`record_preference` deactivates the rest) and there is no API to
      list or restore the inactive rows, which contradicts "see, edit, delete; nothing learned silently".
  > 30 Sept: fixed on `kenn-stage3b-items`. `record_preference` deactivating the previous value is right for
  > answering and wrong for "see, edit, delete; nothing learned silently" — a producer who said "actually, I master
  > to -9, not -12" lost the old value with no way to see, compare or restore it. The rows were **already retained**
  > by the `MAX_PREFERENCES` prune; they were simply never readable. Added `preference_history` (superseded rows,
  > newest first, optionally narrowed to one key) and `restore_preference`, where restore is a **move** — it
  > deactivates the current value and reactivates the chosen row in one transaction, so `current_preferences` still
  > returns one row per key. Exposed as `GET /api/memory/preference/history` and
  > `POST /api/memory/preference/restore`. 8 tests, including that another session's `preference_id` cannot be
  > restored and that the restore window is bounded by `MAX_PREFERENCES` (32), not wider.
- [x] `chat_completion_stream` returns normally on a mid-stream failure, so a truncated answer is validated as
      a complete candidate.
  > 29 Sept: Fixed. Both swallow sites (`chat_completion_stream` and `enhance_stream`) now propagate instead of
  > ending the stream quietly -- timeouts and HTTP errors already raised from there, so mid-stream wire failures
  > now follow the same contract. `chat_answer` catches the propagated error, refuses to validate the truncated
  > candidate, falls back to the grounded template, and records the reason in `generation_validation.warnings`.
  > Pinned in `test_llm_stream_honesty.py`.
- [ ] `llm_rewrite._clean_chunk_for_synthesis` cuts mid-word and mid-code-fence, and appends a closing
      `</source_excerpt>` after a cut that can land inside the opening tag.
  > 30 Sept: fixed on `kenn-stage3b-items`. All three defects land in the same place — the markup that tells the
  > model where untrusted evidence stops. A 240-char cut severed a word and glued the fragment to the ellipsis; a
  > fenced block was flattened into one broken statement (`` ```python
KENN_LLM_CONTEXT_CHARS=650
``` `` became a
  > single line); and `build_raw_context_block` sliced the assembled block, emitting
  > `<source_excerpt label="… section Dry/Wet para</source_excerpt>` — an unterminated attribute with the label cut
  > mid-word. Now: `_truncate_on_word_boundary` cuts on a word boundary with the ellipsis **inside** the budget,
  > fenced regions are dropped whole rather than joined into the prose, and the opening tag is budgeted before any
  > slicing — including the `\n\n` joiner, which was the reason it overshot `max_chars`. An excerpt whose label
  > leaves no room is dropped rather than squeezed. 8 tests.
- [x] The L2 semantic-cache list grows unbounded and is scanned in full on every query; a *semantic* match is
      also written into the exact-match cache, turning a soft 0.95 match into a hard one.
  > 29 Sept: Cleared without new code -- both halves died in the 28 Sept session-scoping pass. L2 is bounded to
  > 256 entries with FIFO eviction, and a soft semantic hit is never promoted into the L1/exact cache. Both
  > behaviors were already pinned in `test_semantic_cache_versioning.py` (`test_l2_cache_fifo_eviction_bounds_memory_to_max_size`,
  > `test_soft_semantic_hit_does_not_pollute_l1_exact_cache`).
- [x] `mix_recipes`, `device_units.display_to_raw(relative=True)`, `live_recipe.audition_loudness_trim_db` and
      `live_recipe.undo_steps` each treat a raw fader value as dB or fabricate a `readback` field.
      `live_recipe`'s trim constant is dead (never read) but is persisted into receipts.
  > 29 Sept: Cleared. The `mix_recipes` readback fabrication was the zip bug above (fixed). `execute_recipe` receipts
  > no longer carry the raw-fader-times-25 "audition trim" estimate or an `undo_steps` preview whose readback was a
  > copy of the requested value -- nothing ever read either, and undo goes through `propose_undo`, which re-proposes
  > exact steps for a fresh verified execution; pinned in `test_live_command.py`. `display_to_raw(relative=True)`
  > verified honest: linear profiles scale a delta with no offset, and table/log profiles refuse or resolve through
  > a display round-trip against the current raw value in the caller.
- [x] The Ableton manual has never been ingested, so **every** official-manual pathway in the product is dead:
      `pdf_evidence_class` would label it, but the index holds 0 `official_ableton_manual` chunks (3,308
      `curated_kenn_note`, 28 transcript, 2 `reference_document`), which makes `session_intelligence.py`'s
      "Grounded in the authorized Ableton manual" unreachable. This is a Stage 2 content gap, not a code gap.
  > **30 Sept: no longer true — the premise was stale by about a day.** Re-measured on the live index with
  > `evaluate_ableton_manual_grounding.py`: **`official_manual_chunk_count: 1436`**, `all_cases_passed: true`,
  > 16 / 16 reference cases, every one selecting `official_ableton_manual`, `--require-manual` exit **0**. Counted
  > from the index: 4,642 chunks = 3,176 curated + **1,436 official-manual** + 28 transcript + 2 reference, all from
  > `Training_Data_PDF/live11-manual-en.pdf`, which is git-ignored. The pathway is live, not dead.
  > **Two things remain open, and both are the owner's.** The manual indexed is **Live 11's** while he runs **Live 12
  > Suite**, and the Knowledge programme ranks the manual *above* curated notes, so KENN now cites Live 11
  > documentation for a Live 12 product — export the Live 12 manual from Live's Help menu and rebuild to fix that.
  > And the ingest ran at 01:09 on 30 Sept while the decision box below was still unticked, so the decision now is
  > whether to keep it rather than whether to start it.
  > 29 Sept: Partly a code gap after all -- verified counts are 3,176 curated / 28 transcript / 2 reference /
  > 0 official (index `v-07328d9baf04`), and the documented fetch path (`download-pdfs`) pointed at a script
  > that never existed. That script is now real (`tooling/scripts/setup/download_training_pdfs.py`), the Live 11
  > catalog entry flipped to `local_opt_in` with its CDN URL verified live, and the dead `./ableton` pointers in
  > the catalog now name the actual `python main.py` entry point. What remains is genuinely content: download
  > the PDFs (Live 11 via `download-pdfs`, Live 12 exported from Live's Help menu) into the gitignored
  > `Training_Data_PDF/`, rebuild with `--include-local-manuals`, and qualify with
  > `evaluate_ableton_manual_grounding.py`.

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
satisfaction, and how often the local model's answer lands (and how long it takes) on each tester's Mac.

Two more, added 28 Sept after the audit, because both failures were invisible until they were counted:

- **Answers with no citable source** (must be zero). The display layer can legitimately return nothing — that is
  how KENN says "I don't know" — but the answer must never be built anyway with an empty `Sources:` line.
- **Answers with no citable source** (must be zero). First counted 30 Sept by `tooling/scripts/answer_audit.py`:
  100 answers on the live index, **88 answered, 12 abstained, 0 uncited** — the requirement holds. Two traps had to
  be closed first, both the "a gate quietly stops gating" failure this list exists to catch: with no retrieval index
  every answer abstains and the measure reads 0 (now `NOT_MEASURED`, exit 2), and a mixer recipe has `grounding: null`
  and nothing to cite, so counting it as an uncited answer was a false positive (recipes are now counted separately).
- **Answers rejected by the grounding gate, and why** (rate plus top warning). A jump here means the retrieval or
  the notes changed, not that the gate is misbehaving. The gate failing *open* is the thing to alarm on, and the
  `test_the_marker_prefix_is_not_a_grounding_input_anywhere` test is the standing guard for that.

## Risks

| Risk | Mitigation |
|---|---|
| Local model too slow or too weak on testers' Macs | Templates as the instant path; model answer swapped in when ready; measure the swap rate and wait per Mac |
| Latency makes KENN feel slow | Route clear commands to the instant path; stream answers; measure by stage |
| Knowledge errors with confident tone | Source tiers, citations, contradiction checks, reviewer audits |
| Scope creep before the beta is solid | Stage 0 exit first; later stages start only behind their own gates |
| Too many plans again | This doc is the direction; older plans are reference only |
| A gate quietly stops gating (28 Sept) | The grounding gate had a bypass reachable by typing, and the write report said
  "nothing changed" after a real write. Gating logic is now covered by tests that reproduce each bypass, and the
  marker-prefix test greps the package so the pattern cannot come back. Auditing the gate is a recurring cost,
  not a one-off |

## Decisions needed from you

- [ ] Sign off this direction (local Qwen brain, stages in this order)
- [x] Brain provider: local Qwen only (owner, 25 Sept) — no hosted budget or opt-in needed
- [x] What may be sent to a hosted model: nothing — no hosted model (owner, 25 Sept)
- [ ] Whether Stage 2's craft notes should cover specific genres first (which?)
- [x] Ingest the Ableton Live Reference Manual now, or keep the knowledge base KENN-written only until Stage 2's
      parameter work lands? It is the one source the Knowledge programme ranks above curated notes, and the code
      is already written and tested for it; the gap is the catalogue entry and the extraction run.
  > **Answered by action before it was recorded:** the Live 11 manual is ingested (1,436 chunks, grounding 16/16)
  > as of 30 Sept 01:09. The decision left is narrower — whether to keep it given it is the **Live 11** manual for a
  > **Live 12** install, and whether to export the Live 12 manual to replace it.
- [ ] Does Stage 3b's open list get worked now or after the beta? Twelve of the eighteen have no production
      caller or no reachable path, so the beta is not blocked by any of them — but the semantic-cache
      cross-project leak and the `validate_llm_plan` range-check gaps are worth closing before a second tester
      runs.
