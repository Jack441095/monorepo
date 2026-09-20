# KENN general-intelligence sprint

## Goal

Move KENN from a collection of capable audio tools toward a dependable Ableton
colleague: aware of the current session, able to reason through multi-step
production goals, honest about uncertainty, and unable to bypass confirmation.

This work does not include UX. It also does not equate model fluency with
intelligence; success is measured on grounded Ableton trajectories and verified
outcomes.

## Current diagnosis

KENN already has unusually strong foundations for an assistant:

- a sanitized, fingerprinted `SessionContext`;
- deterministic Ableton intent and identity resolution;
- typed, confirmation-gated proposals with stale checks and readback;
- specialist analysis, generation, retrieval, reflection, and session-memory
  components;
- held-out command, knowledge, and safety evaluations.

The principal missing layer is deliberation. The orchestrator routes many
requests through regex classification, while the local 1.5B model is primarily
used to phrase grounded answers. Neither currently builds and evaluates a
coherent plan across session observations, specialist tools, uncertainty, and
follow-up evidence.

## Architecture

```text
producer goal
    -> versioned SessionContext / Ableton world model
    -> deliberative planner (shadow first)
    -> strict plan validator
    -> typed specialist calls and read-only observations
    -> confirmation-gated Live proposal
    -> readback receipt
    -> episodic outcome + producer feedback
```

The planner is not an executor. Its output contains capability choices,
dependencies, rationale, and expected evidence only. Exact Live values remain
the responsibility of the existing narrow proposal services.

## Delivery sequence

1. **Typed deliberative contract — implemented on the intelligence branch.**
   Context-bound plans, explicit dependencies, evidence expectations, bounded
   step kinds, stale-snapshot rejection, and zero execution authority.
2. **Hybrid shadow planner — implemented on the intelligence branch.** Models
   emit only a compact semantic sketch. KENN deterministically supplies session
   binding, action kinds, linear dependencies, evidence requirements, safety
   flags, provider identity, and timestamps before strict validation; no step is
   dispatched. Hard policy refusals, disconnected writes, and unresolved target
   identities are handled by a deterministic preflight rather than delegated to
   model judgment.
3. **Trajectory evaluator — implemented on the intelligence branch.** Score
   plan validity, capability selection, ordering, clarification, refusal, and
   compactness instead of prose similarity.
4. **Ableton world-model expansion — foundation implemented.** `SessionContext`
   now sanitizes clips, scenes, routing, sends, return tracks, master-chain
   identity, selection, and five-minute observation freshness alongside the
   existing device capability profiles. Deeper clip contents and arrangement
   timeline observations remain future read-only additions.
5. **Event-driven awareness — ingestion/delta foundation implemented.** A
   read-only `SessionWorldModel` now converts successive snapshots into bounded
   semantic events and defensive context copies. The remaining work is wiring
   Live Object Model observers into that boundary without model calls on the
   audio thread.
6. **Layered memory — task, preference, and outcome foundations implemented.**
   Validated plans persist in a separate assistant-task ledger and can resume
   after restart. Steps advance only with kind-appropriate typed evidence; Live
   steps require a verified applied receipt, and only compact evidence identity
   is retained. Production-profile memory accepts only allow-listed preferences
   explicitly present in a user statement. Production episodes require both a
   completed receipted task and an explicit keep/revise/reject verdict. Both are
   bounded, advisory, independently forgettable, and cannot override safety or
   current observed state. Deeper project facts remain a later memory slice.
7. **Model bake-off in shadow mode — local baseline collected.** A sealed
   ten-case Ableton trajectory set covers inspection, diagnostic ordering,
   ambiguity, disconnects, refusal, missing identity, generated/rendered asset
   follow-up, preference grounding, and needless-action avoidance. The runner
   emits provider-neutral compact prompts and scores contract validity, task
   checks, aggregate quality, and safety pass rate. A local
   `qwen2.5:7b-instruct` hybrid run passed all 10 cases and all six
   safety-critical cases. A separate 12-case adversarial set now covers poisoned
   track/device metadata, poisoned preference memory, confirmation and policy
   bypasses, duplicate identities, negated changes, unavailable services, and
   positive controls; its post-fix run passed 12/12 and 10/10 safety cases. The
   remaining bake-off work is repeated runs, longer multi-turn attacks, and at
   least one stronger reasoning model. MiniMax is one candidate, not a dependency
   or assumed winner. The GPU-ready `scripts/run_deliberative_bakeoff.py` now
   runs both suites repeatedly across multiple model tags, retains every run,
   and refuses to recommend any model with less than 100% contract and safety
   performance. See `docs/KENN_GPU_MODEL_BAKEOFF.md`.
8. **Diagnostic production loops — causal state machine implemented.** Existing
   symptom-specific hypotheses are now ranked from typed session evidence and
   tested one at a time. Explicit producer observations, measurements, or
   verified receipts can support, contradict, or leave a hypothesis
   inconclusive. Only supported hypotheses yield an advisory recommendation;
   the next deliberative step still asks before creating any exact Live
   proposal. Coverage includes low-end masking, vocal intelligibility,
   headroom, dynamics, stereo/phase, arrangement energy, and other established
   diagnostic families. The loop is now exposed through two read-only MCP tools:
   an assistant can start a diagnosis from a fresh Ableton context, record one
   typed observation, and receive the next bounded conversational step. A
   changed session fingerprint stops continuation and requires a fresh diagnosis.
9. **Multi-turn task continuation — persistence and coordination foundations
   implemented.** The
   assistant-task ledger resumes validated plans after restart and advances
   steps only from kind-appropriate evidence. Diagnostic calls now carry their
   typed loop between assistant turns. A safe coordinator now exposes exactly
   one typed next-step directive, rejects new work after a session fingerprint
   change, pauses on user/job/confirmation boundaries, and recognizes task
   completion only after ledger-accepted evidence. It never emits an execution
   payload or grants execution authority. The MCP facade can now start/resume a
   task from a caller-supplied validated plan or build one itself through
   `plan_assistant_task`: fresh context, deterministic preflight, constrained
   loopback Ollama sketch, host hydration, validation, persistence, and one
   safe next-step directive. It can fetch and record a fresh inspection itself,
   record an explicit producer
   response, bind a proposal to the active task step, and complete that step from
   the direct apply receipt or a receipt resolved by ID from KENN's session-scoped
   journal. Caller-asserted receipt objects are not accepted. Assistant-memory
   sync failure after a successful apply never hides the real Live receipt. The
   world model now advertises asynchronous services only when their availability
   was actually observed. AudioGen render jobs can be queued against the active
   generation step, retain one immutable server-issued job identity, and advance
   only after KENN fetches a completed job itself. A matching server-reported
   failure now terminates the task explicitly without marking the step complete;
   a failed or unrelated job cannot leave the assistant waiting forever or swap
   the bound identity. Plans may now name a future generated-asset review only
   when it directly depends on an earlier generation step. When that exact job
   completes, compact context-domain identities allow the task to rebind and
   continue into review only if Live state, service availability, measurements,
   profile memory, audition evidence, and every unrelated job remain unchanged.
   A real read-only MCP-path smoke against the running companion and local
   `qwen2.5:7b-instruct` produced and persisted one `inspect_live` task with
   `execution_authorized=false`; no Live write or permanent test ledger was
   created.
   The preferred `plan_assistant_goal` entry point now routes supported symptom
   language into the existing causal diagnostic loop before generic model
   planning. A kick/bass coexistence request therefore starts one ranked,
   evidence-first hypothesis test rather than asking a small model to invent a
   diagnosis or prematurely promise a parameter change.
   The remaining integration work is to connect AutoMix renders, diagnostic
   loops, and audition feedback to the same task boundary.
10. **Supervised pilot.** Promote only capabilities whose shadow trajectories,
    real-Live qualification, recovery behavior, and human usefulness pass their
    gates. Writes always retain exact confirmation and readback.

## Intelligence evaluation set

The first sealed set should include at least these families:

- ambiguous references and duplicate track/device names;
- requests requiring observation before recommendation;
- multi-step kick/bass, vocal, drum, and arrangement tasks;
- stale state, Live disconnects, and changed targets;
- unsupported tools and arbitrary-code/refusal probes;
- conflicting producer preferences versus measured evidence;
- delayed render/audition follow-up and task resumption;
- metadata prompt injection;
- technically plausible but causally wrong mix advice;
- needless action, where the correct result is to leave the session unchanged.

Promotion gates should include contract validity, task completion, grounded
claims, correct ordering, clarification precision, refusal precision, receipt
coverage, latency, and human preference. A model that sounds better but chooses
worse actions does not pass.

## Measured local-planner evidence — 2026-09-08

The first direct local-model experiments showed why the planner contract must
not be copied wholesale by a language model:

- `qwen2.5:0.5b` returned quickly but selected incorrect actions and invalid
  dependencies. It is not suitable as KENN's planner.
- `qwen2.5:7b-instruct` took 149.95 seconds on the session-overview case when
  asked to reproduce the full plan and failed contract validation with a score
  of 0.0.
- Compact sketch decoding plus deterministic hydration reduced the same model
  to 59.91 seconds and a valid 0.833 trajectory; removing model-owned dependency
  bookkeeping and clarifying the read-only boundary produced a 1.0 score.
- After compacting redundant context and adding deterministic policy/identity
  preflight, one full warmed-model run passed 10/10 sealed trajectories with
  100% contract validity and 6/6 safety-critical passes. Aggregate latency was
  12.25 seconds mean and 25.01 seconds p95; the six model-mediated cases ranged
  from 13.79 to 25.01 seconds while four deterministic cases completed in under
  one millisecond.

These are development measurements from one machine and individual runs, not a release
claim. The ten-case set is intentionally small. Beta promotion still requires
repeated runs, paraphrase and prompt-injection expansion, real-Live multi-turn
trials, and human usefulness review. The architectural result is stronger than
the model result: unsafe execution authority and session identity are no longer
model-owned, and a weak model can be rejected or replaced without weakening the
Ableton boundary.

The separate adversarial run initially passed 11/12 and exposed a deterministic
language bug: “do not change it” was treated as mutating because the preflight
matched `change` and `it` without understanding negation. After adding bounded
negation handling—and a regression proving a later real mutation is not erased—
one coherent rerun passed 12/12, including 10/10 safety-critical cases, with
100% contract validity, 8.39 seconds aggregate mean latency, and 23.00 seconds
p95. Model-visible context now explicitly labels all metadata as untrusted, and
host hydration rejects instruction-like model prose, executable text, URLs,
API/OSC paths, and leaked control-field names. Deterministic intent also refuses
confirmation/policy/instruction bypass language before any model call.

Repeated normal-case runs also exposed why the local 7B model is not itself a
beta claim. A later hardened ten-case run passed 9/10: the kick/bass trajectory
was safely rejected after the model placed `ask_user` before a pre-planned
proposal. After restoring the terminal-step instruction, three instruct-model
runs were contract-valid but all chose an unnecessary clarification (0.5 score),
while three coder-model runs only inspected and omitted the follow-up proposal
(0.625 score). Adding more prompt prose then caused three unavailable-action
selections, all rejected by KENN. The durable fix is host-level: constrained
decoding now exposes only context-available actions, and the unified MCP goal
router sends recognized production symptoms to KENN's deterministic causal
diagnostic workflow. This preserves honest model-variance evidence instead of
tuning the benchmark until one model appears reliable.

The action-scoped adversarial rerun then exposed one positive-control weakness:
the model asked what “that” meant despite a selected Live track. KENN now adds a
host-resolved deictic reference to planner context when the selected index maps
to an observed track. Three targeted repeats all moved to the correct
`inspect_live -> create_live_proposal` sequence. A final coherent adversarial
run with action scoping and reference resolution passed 12/12, including 10/10
safety cases and 100% contract validity, at 8.17 seconds aggregate mean and
25.27 seconds p95.

## Immediate next implementation slice

The first multi-turn recovery gap is now closed: a stale task no longer ends at
an unactionable `replan` directive. `replan_assistant_task` carries the original
goal and optional producer clarification into a fresh context-bound plan,
atomically records parent/successor lineage, and cancels the superseded active
task. It refuses to orphan an identity-bound pending confirmation or generation
job, and caps replacement chains at eight. Exact observed track names in a
clarification now resolve earlier deictic wording without weakening the
missing-target preflight.

Audition revision is now connected to assistant-task continuation. The prior
contract incorrectly classified `revise_audition` as a queued generation job,
although the implemented AudioGen route immediately returns a confirmation-only
MIDI clip proposal. It is now a `live_proposal` step: MCP resolves feedback by
session and `feedback_id`, binds the server-issued proposal action identity to
the task, waits for explicit confirmation, and accepts completion only from the
matching verified MIDI receipt. Caller-supplied feedback cannot replace the
stored listener evidence.

Diagnostic continuation is now server-authoritative as well. Previously the
MCP client returned the entire loop and structural validation could not prove
that its hypothesis text, ordering, status, or result history was what KENN had
issued. Diagnostic loops now persist in a bounded SQLite ledger and advance by
compare-and-swap. An echoed loop must exactly match the stored state, stale Live
context is rejected before consuming an observation, and MCP no longer accepts
caller-constructed measurement or receipt evidence. Explicit producer
observations remain supported; machine evidence must be resolved by KENN.

Multi-turn recovery now has its own deterministic qualification artifact and
release-gate integration. `scripts/qualify_assistant_recovery.py` exercises
eight persisted trajectories: stale-context replanning, successor lineage,
pending-confirmation preservation, receipt replay rejection, queued-job
identity mismatch, evidence-scoped generation rebinding, diagnostic restart,
and concurrent diagnostic replay. The current result is 8/8 overall and 7/7
safety-critical, with `execution_authorized=false`. The qualified intelligence
gate now runs this alongside the 15 hard chat cases, retrieval comparison, and
six session-grounded advice cases; all four receipts must pass.

The first structural Live capability beyond track/device edits is now wired
through the same intelligence boundary: append-only audio and MIDI track
creation with optional naming, exact topology binding, explicit confirmation,
idempotency, and `has_midi_input` readback. The command-planning training seed
now includes varied named/unnamed requests plus refusals for middle insertion
and unsupported return-track creation. This is still synthetic/fixture evidence
until a disposable real-Live qualification can prove creation and a separately
approved restoration path; it is not yet part of the qualified support matrix.

The next assistant-like control is now wired as a deliberately narrow compound
trajectory: append a qualified `Hybrid Reverb` or `Echo`, resolve its real
post-insertion `Dry/Wet` parameter index, set an absolute percentage, verify
both reads, and remove the newly inserted device if the parameter step fails
while the chain is still exact. Natural-language aliases such as `add reverb to
hi hat at 25% dry wet` are covered, and the LLM plan validator cannot invent the
new device or parameter index. The current-source service has now passed its
disposable real-Live combined qualification on `3-Audio`, including apply,
parameter readback, replay rejection, identity-bound undo, and final chain
restoration; the privacy-safe receipt is `.runtime/evidence/real-live-device-setup-20260909.json`.
The running companion was intentionally not restarted during the soak, so the
reloaded HTTP-route smoke check remains a follow-up before beta promotion.

The GPU bake-off now reuses each model's exact hydrated plans in five persisted
context-change and identity attacks. Promotion requires a passing recovery
receipt for every repeat, in addition to 100% static contract and safety rates.
Run those repeated trials on the GPU host to measure model variance without
heating the development Mac. AutoMix is explicitly excluded by the current public-beta
tool registry, and the MCP context correctly does not advertise offline-render
creation; do not add an assistant completion route until that service is
promoted with a server-issued queue identity and typed receipt. Exercise the
persisted diagnostic and deliberative workflows through longer context-change,
replay, and recovery trajectories against a real Ableton session. Compare at
least one stronger reasoning model when available. Model
fluency remains replaceable; grounded state, causal tests, receipts, and
resumption are the core assistant behavior.

The first end-to-end bake-off run through the new aggregate runner preserved
the local 7B variance: 9/10 normal holdout, 12/12 adversarial, 100% contract
validity, and no recommended model because one holdout safety-critical rubric
case added an unnecessary clarification (5/6). Aggregate mean latency was
11.45 seconds per case. This is the baseline to beat on the GPU host; the
runner's loopback-only transport and no-redirect policy prevent benchmark
prompts from being sent to an arbitrary endpoint.

The first work-GPU comparison is now complete and retained. An existing
Qwen3-4B checkpoint completed three repeats of both sealed suites but was not
eligible for promotion: 4/10 normal and 6/12 adversarial on every repeat, 0.45
aggregate pass rate, failed recovery qualification, and 4.31-second mean
latency. Most rejected generations chose plausible semantic steps but violated
the compact JSON contract; one invented an unavailable action. This is useful
beta evidence because KENN rejected every malformed plan before persistence or
execution, and it gives the intelligence sprint a concrete decoder/contract
target instead of an anecdotal model preference.

The Qwen3.5-27B-FP8 checkpoint loaded but could not perform inference because a
required FP8 kernel package was absent from the existing host runtime. That is
an environment incompatibility, not a model-quality result. The no-service GPU
runner now fails the whole comparison on missing inference dependencies rather
than recording dozens of synthetic model failures. No host component was
installed or restarted. The next meaningful model experiment is a
provider-neutral schema-constrained decode using already-approved runtime
components, followed by the exact same sealed matrix and recovery gate.

That provider-neutral reduction is now implemented and measured. Models may
return semantic steps only; KENN adds only missing constant/empty sketch
boilerplate and still rejects incorrect supplied values, wrappers, unavailable
actions, unsafe prose, and malformed steps. On the identical Qwen3-4B repeated
GPU matrix, aggregate score improved from 0.45 to 0.8458 and mean pass rate from
0.45 to 0.7666. Normal runs improved from 4/10 to 7/10 and adversarial runs from
6/12 to 10/12 on all three repeats. The model remains ineligible: minimum
contract validity is 0.90, minimum safety pass rate 0.8333, and recovery fails
when one required plan is rejected for choosing an unavailable action. This
turns the next intelligence target from generic JSON compliance into specific
semantic weaknesses—over-clarification and context-invalid action choice—while
retaining the same strict beta gate.

Those two weaknesses are now resolved at their correct ownership boundaries.
Request-scoped action meanings removed unavailable-action selection. KENN's
deterministic preflight now exclusively owns clarification; after it establishes
that identity and intent are sufficient, the replaceable model cannot insert
`ask_user` into an executable trajectory. This is not silent plan repair: the
model still chooses every semantic action and strict hydration still rejects
anything outside the context.

The resulting Qwen3-4B V5 run passed all three repeats of both sealed suites:
10/10 normal, 12/12 adversarial, 100% contract and safety rates, and 5/5 model-
plan recovery attacks per repeat. Aggregate score/pass rate was 1.0 at 3.112
seconds mean latency, making it the first model configuration recommended by
the repeated GPU aggregator. This closes the synthetic planner qualification
gap. It does not close the beta programme: the configuration still needs
real-Live multi-turn trials, deployment/resource qualification, and human
usefulness review before becoming KENN's default planner.

The qualified V6 rerun now binds that result to eight exact source/evaluation
inputs with SHA-256 hashes and is checked by a dedicated qualified-beta release
gate. It reproduced 10/10 normal, 12/12 adversarial, and 5/5 recovery attacks
on all three repeats. The refreshed 66-case run passed a newly enforced latency
gate at 3.145 seconds sample-weighted mean and 12.659 seconds maximum suite p95,
against ceilings of 5 and 15 seconds respectively. The tracked artifact is
`evaluation/results/KENN_DELIBERATIVE_MODEL_BAKEOFF.json`; stale planner,
evaluator, runner, recovery, or sealed-suite content now makes the release gate
fail. The 100-case human-review packet was regenerated after the planner-core
change and remains honestly marked pending independent review.

Stale assistant tasks now report bounded context-change categories in their
read-only next-step directive. Replanning can therefore distinguish Live-world
drift from new measurements, SLO audio classification, audition feedback,
producer memory, or asynchronous job evidence without exposing the prior raw
session or allowing the model to reinterpret it. Coordinator and MCP focused
checks pass, and the field remains informational with `execution_authorized:
false`.
