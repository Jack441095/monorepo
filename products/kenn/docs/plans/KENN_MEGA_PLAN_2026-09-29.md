# KENN mega plan: a general-language-model assistant for Ableton Live that works really well

**Written:** 2026-09-29 · **Owner:** Jack · **Status:** proposal for owner sign-off

How the pieces fit and what order to build them in. It sits above the other three plan files, which stay as they are:

| File | Its job |
|---|---|
| **This plan** | The whole route, the workstreams, the order, and what only you can do |
| `KENN_NORTH_STAR_2026-09-24.md` | The stage gates and the evidence log for each stage. Tick items there in the same commit as the work |
| `KENN_BETA_PLAN_2026-09-24.md` | Stage 0, the private beta |
| `KENN_GLM_FULL_ASSISTANT_TRACKER.md` | The working checklist (phases A–I) |

If two of them disagree, the north star's gates win, then this plan's order.

## 1. What "GLM" means for KENN

A **general language model** is the part that understands open wording and holds a conversation. KENN's is a local Qwen
model (Qwen3 8B for chat, a fine-tuned 4B for commands), running on the producer's own Mac. Nothing is sent off the
machine (owner decision, 25 Sept).

A language model alone is not an assistant you would trust with a session. KENN is the model **plus** the parts that keep
it honest:

- **Rules and typed actions** own every change to Live: snapshot, target, units, safety policy, Apply, OSC write,
  readback, receipt, undo. The model can suggest; it cannot write.
- **Retrieval** gives it the Live manual and KENN's reviewed notes, so it answers with sources and says when it doesn't know.
- **Measurement** gives it what Live and the audio actually show, so it doesn't invent a state.

"Works really well" is the sum of those parts being good at once. Sections 4–6 say how.

## 2. What "works really well" means: the targets

Every workstream below is measured against these. Numbers are the bar, not a claim about today.

| Area | Bar |
|---|---|
| Understands | ≥ 95% right on ≥ 500 phrasings **nobody tuned on**, with 0 wrong plans; where it can't tell, it asks one short question |
| Answers | ≥ 90% on a reviewer-scored quiz; every factual claim cited; 0 uncited claims in a 100-answer audit |
| Speed | Commands and Live questions in ≤ 0.5 s; a model-written answer ≤ 15 s after an instant one, on a 16 GB Mac with Live open |
| Controls | Every device parameter a producer touches in real units (≥ 25 devices, ≥ 60 parameters first, then all 78 devices); 100% exact undo |
| Reasons in steps | ≥ 15 recipes that pass on real Live with exact undo; a plan shown first, each step confirmed |
| Listens | Says what it hears with a measurement behind it, and re-measures after a fix |
| Remembers | Project memory and preferences the producer can see, edit and delete; nothing learned silently |
| Safe | 0 writes without Apply; 0 unauthorised writes across a pilot; nothing leaves the Mac |

## 3. Where KENN is today (from the repo, 29 Sept)

| Capability | State |
|---|---|
| Rule parser | About 90% on the sets it has been tuned on; **70–77% on fresh blind wording** (the honest number). Voice-dictation and Logic/FL-wording sets also exist. 0–1 wrong plans per round, found and fixed |
| Command planner | Fine-tuned Qwen3.5 4B ("run 11") in shadow. With the rules first it adds 9 right and **22 wrong plans** across 1,751 phrasings, so it stays in shadow; run 13 is deliberately not trained on more synthetic data |
| Chat brain | Qwen3 8B is right in quality but takes 7–16 s an answer on the owner's M3/16 GB with Live open; the chat is on instant template answers, and `core/answer_upgrades.py` swaps in the model's answer when it passes the grounding check |
| Knowledge | 77 of 78 devices have an approved note. Retrieval recall@4: **0.98** on questions that name the topic, **0.74** on "what I want" wording, 0.84 on technique questions; the sealed set is much lower (0.34–0.45), so retrieval is the weakest link |
| Knows the session | Tracks, returns, master, racks, devices, change history; 7 kinds of question; freshness shown |
| Controls Live | Mixer, focus, sends, device focus, 10 insertable effects, 14 profiled parameters on 8 devices; a device factory (measure → candidates → qualify → data files) and choosers/switches by label are built but **no device has been run through it on real Live yet** |
| Multi-step | 15 named recipes built, **none qualified on real Live yet**; the deliberative planner was qualified once |
| Listens | Rendered-file analysis (loudness, true peak, clipping, low end); no live capture yet |
| Remembers | Session receipts only |
| Ship state | Installable app and DMG; the 6-hour soak and the real-Live assistant task have receipts on one release; sign/notarize waits on a Developer ID; no testers onboarded as of the last progress note |

## 4. The workstreams

Each has a goal, the next concrete steps, the gate, and what it needs from you. IDs (WS1…) are used in the order below.

### WS1 Language understanding: rules first, model when unsure
**Goal:** open wording works, and when it doesn't KENN asks well instead of guessing.
- Turn **real tester wording** into the main source of fixes. The "requests KENN didn't understand" log (opt-in) plus the
  shadow log of where the rules asked and what happened next is the corpus. Nothing synthetic beats it.
- Keep one **blind round a week**: new phrasings written before anyone reads the parser, scored once, then used to fix.
  Report the first-run number every time, never the tuned one.
- Pinned policy conflicts to settle (they cost real percentage points): bare "X to -N", "kill playback", "reverb on the
  vocal" (device or send).
- Train the next planner **only on real tester data** plus owner-reviewed clarify examples, and only promote it through
  `live_llm_promotion.py` (≥ 500 comparisons, ≥ 14 days, ≥ 98% schema, ≥ 90% agreement, wrong plans ≤ the rules').
- Multi-turn: "the other one" after KENN listed exactly two matching tracks; corrections on device parameters.
**Gate:** ≥ 95% on ≥ 500 fresh blind phrasings from ≥ 3 authors, labels checked by two people, 0 wrong plans.
**Needs you:** label review; tester recruitment; the three policy calls.

### WS2 The brain: fast enough to feel like a conversation
**Goal:** a model-written, cited, multi-turn answer that arrives while the producer is still reading the instant one.
- Measure the answer upgrade on the owner's Mac (how often it lands, how long it takes) and on 8 GB / 16 GB / 32 GB
  tiers; the result decides the default per machine. To measure: start the companion with `KENN_LLM_BACKGROUND=1` and the
  chat model on, ask 30 or more knowledge questions with Live open, then run `python3 tooling/scripts/route_latency_report.py`;
  its last line gives attempts, accepted rate and the accepted answers' median and p95 seconds. Only outcomes and timings are logged.
- Cut the prompt: fewer, shorter excerpts; reuse the model's prompt cache between turns; measure tokens/s before and after.
- Try faster local paths on the GPU box first (quantisation levels, Qwen3 4B vs 8B for chat, MLX vs Ollama on the Mac),
  one change at a time against the sealed chat set (84 questions today, grow it to 200).
- Retry a **style fine-tune** of the 8B on KENN's accepted answers only once there are ≥ 500 owner-approved answers;
  the first attempt made things worse (answers used 36/84 vs 40, slower), so it needs cleaner data, not more of the same.
- Conversation quality: clarify-before-guess, short studio tone, remembers the last five turns, never states a Live
  state it hasn't read.
**Gate:** on a 16 GB M3 with Live open, ≥ 70% of knowledge answers upgrade within 15 s and pass the grounding check;
p95 of the instant answer ≤ 0.5 s; the sealed chat set ≥ 95%.
**Needs you:** Mac timing runs; GPU box reachable from the working session.

### WS3 Knowledge: from "has a note" to "knows exactly"
**Goal:** the right note is found, the number in it is true, and it names what the producer actually owns.
- **Retrieval is the biggest measurable hole.** Order of attack, each measured on a held-out half so it isn't tuned to
  the fixture: (1) the "Use it when…" lines (owner ticks pending), (2) the cross-encoder reranker (size and latency numbers
  exist for the box; measure on the Mac, then decide), (3) note wording fixes where the right note is in the top 20 but not
  the top 4.
- **Parameter-level facts from Live itself**: run the device factory, then generate the measured parameter notes
  (`build_parameter_reference.py`). Every number is what Live displayed.
- Run `check_notes_against_measurements.py` on the real notes; anything outside a measured range is fixed or drafted back.
- Craft notes for how things are done (gain staging, bus processing, sidechain, arrangement moves, the genres you choose),
  drafted on the notes model, checked against sources, reviewed before approval. Third-party material only with rights.
- Grounding in the producer's setup: the "in your Live" line (built) plus device parameters for what is installed.
**Gate:** recall@4 ≥ 0.95 on ≥ 300 questions **and** ≥ 0.80 on the sealed set; quiz ≥ 90%; 0 uncited claims in 100 answers.
**Needs you:** ticks on the drafted lines; the reranker decision; which genres first; reviewers.

### WS4 Control breadth: every device, every parameter
**Goal:** "set X to Y" works in real units for anything a producer touches, undoable and read back.
- Run the **device factory** on real Live: `measure_all_devices.py` → `build_device_profiles.py` → the qualifier (both the
  candidate qualifier and the existing hand-targeted one). First wave: EQ Eight, Compressor, Utility, Limiter, Reverb,
  Hybrid Reverb, Delay/Echo, Saturator, Auto Filter, Glue, Multiband Dynamics; then the rest of the 78.
- Choosers and switches by label, from qualified option tables (built); extend to racks' macros and to third-party
  plug-ins' *named* parameters where the host exposes them.
- New action families, each with readback and exact undo: clips (create, launch, loop, warp, gain, transpose), MIDI note
  edit, scenes, locators, tempo/signature, routing, groups, automation write, save.
- Real-Live regression: the top 50 commands and every recipe through the UI route nightly, with an SLO report.
**Gate:** ≥ 25 devices and ≥ 60 parameters qualified, then all 78 devices measured and either qualified or listed
with the reason; undo success 100%; 0 unauthorised writes.
**Needs you:** a Live session with the device zoo set; the sign-off queue for each batch.

### WS5 Listening: say what it hears, with evidence
**Goal:** advice that comes from the actual sound, and a fix that is measured again after Apply.
- Choose and prove the **live capture path** (resample track, a Max for Live device, or loopback; licence-checked).
- Per-track capture and a masking collision map with a confidence value; decide stem separation only after a licence
  check on the weights.
- Every finding gets a "Fix it" plan built from qualified controls, and a before/after re-measure line.
- Keep the wording honest: a measurement is stated as a measurement; a guess is labelled as one.
**Gate:** on a consented set of real mixes, two reviewers agree with ≥ 80% of findings; the re-measure shows the change
in ≥ 90% of applied fixes.
**Needs you:** a consented listening set; two reviewers.

### WS6 Agentic co-producer: plan, confirm, do, check
**Goal:** "tighten the low end" becomes a short plan KENN explains, then carries out one confirmed step at a time.
- Qualify the 15 built recipes on real Live, each with exact undo (after the device factory, they share the same session).
- Show the plan first, one receipt per step, undo for one step or the whole task.
- Let the deliberative planner propose recipes for wording no recipe covers, but only from steps that already exist as
  qualified controls; anything else becomes a question.
- Per-step latency ≤ 3 s.
**Gate:** recipes pass on real Live with exact undo; a pilot of ≥ 3 testers shows 0 unauthorised writes.

### WS7 Memory and personalisation
**Goal:** it remembers the project and the producer, visibly.
- Project memory per Live set (decisions, references, what was tried); opt-in preferences ("I like vocals bright", "I
  master to -9 LUFS"), cited whenever used.
- A memory view: see, edit, delete. Nothing is learned silently; nothing crosses projects.
**Gate:** testers can find and delete any memory; answers that use memory cite it.

### WS8 Creation
- MIDI ideas as previews, then insert with undo (drums, bass, chords, arps, melody); audio-to-MIDI; reference-driven suggestions.
- Audio generation only as a separate, opt-in, clearly labelled provider.
**Gate:** owner listening review; everything inserted is undoable and labelled.

### WS9 Product and reliability
- **Ship:** sign and notarize (Developer ID), the clean-account test under 15 minutes, a rollback plan, the diagnostics
  consent as built (receipts and timings only, never audio).
- **Prove:** soak on the exact release code, the chaos suite (Live killed mid-write, dropped UDP, companion restart,
  replayed tokens), per-route rate limits, the qualified beta gate at 15/15.
- **Surfaces:** push-to-talk voice into the same command path (H1), an MCP server exposing only the safe tools (H2), UI
  upgrades (session map, receipt timeline, "Fix it" buttons).
- **Pilot:** 5–10 supervised testers, at least 3 with their own projects, a feedback channel, a weekly review of what
  KENN didn't understand.

### WS10 Evaluation and honesty (runs through everything)
- Sealed sets that training never sees; results recorded per run; a first-run number on every blind round.
- Monthly report: understanding, answer quality, recall, latency by stage, unauthorised writes (must be 0), undo success
  (must be 100%), tester satisfaction, and how often the model's answer lands on each tester's Mac.
- A capability moves shadow → propose → default only through a measured gate, never because it demos well.
- One plan set: this file, the north star, the beta plan and the tracker. Older plans go to git history, not the tree.

## 5. The order

| Phase | Weeks | Theme | Workstreams | Exit |
|---|---|---|---|---|
| **1** | 1–2 | Make it real on Live | WS4 device zoo run; WS6 recipes on Live; WS9 soak, clean-account test, sign | Qualified beta gate 15/15; ≥ 25 devices qualified; 3 testers onboarded |
| **2** | 3–6 | Learn from real use; speed | WS1 tester wording loop; WS2 Mac timing and prompt cuts; WS3 reranker decision and lines | First real-wording blind round ≥ 85%; upgrade lands ≥ 70% within 15 s |
| **3** | 6–12 | Knowledge and listening | WS3 to the recall gate and the quiz; WS5 capture path and fix-and-re-measure | Recall and quiz gates; two-reviewer listening pass |
| **4** | 10–16 | Agentic and memory | WS6 gate; WS7 | Recipes pass on real Live; memory view shipped |
| **5** | 16+ | Breadth and creation | WS4 to all 78; WS8; voice, MCP | All devices measured; creation review |

Overlaps are fine where two streams don't share a dependency. Nothing in a later phase starts before the earlier
phase's gate has been reported honestly, including the bad numbers.

## 6. Risks

| Risk | What we do |
|---|---|
| The local model is too slow on smaller Macs | Instant template first (built); measure per tier; smaller quantisation; box GPU for the owner's own use |
| Phrasing accuracy stalls near 75–90% | Tester wording is the fix, not more synthetic rules; ask well; hold the planner in shadow until it beats the rules on wrong plans |
| A wrong plan reaches Apply | Deterministic validation, exact targets, readback, receipts, undo; blind rounds report wrong plans first |
| Knowledge errors with a confident tone | Source tiers, measured-range checks, citations, the 100-answer audit |
| Too many plans, too much scope | The four files above; each phase has a gate and a stop rule |
| Device work can't be verified without Live | The qualifier tests every parameter against Live's own display and restores it; nothing loads unqualified |
| A tester's set is unusual (racks, third-party) | Say what isn't covered; never guess |

## 7. What only you can do

- **Decide:** bare "X to -N"; "kill playback"; "reverb on the vocal"; the reranker; which genres first; sign this plan off.
- **Supply:** testers (5–10) and two reviewers; a consented listening set; the Developer ID; label checks.
- **Run on your Mac with Live open:** the device zoo measure and qualify; soak #4 and the recipe runs; the clean-account test;
  the answer-upgrade timing.
- **Unblock:** GPU box reachable from working sessions (or upload the notes and index); GitHub access to the org's repos.
