# KENN State-of-the-Union Assessment & Roadmap to a GLM-Grade Ableton Live Assistant

**Date:** 2026-09-22 · **Baseline commit:** `a0e51b7` (post-cleanup main) · **Test suite:** 1317 passed / 2 failed / 5 skipped (the 2 failures are pre-existing `test_server_smoke` network flakiness — `http.client.RemoteDisconnected` in that env, not code rot; the 5 skips are `test_sample_embeddings.py` waiting on onnxruntime).

**Primary evidence base:** `products/kenn/docs/reports/KENN_ABLETON_GLM_QUALIFICATION_2026-09-21.md`, `products/kenn/docs/plans/KENN_GLM_ROADMAP_2026-09-21.md`, `products/kenn/docs/research/KENN_GLM_GAP_MATRIX_2026-09-21.md`, raw receipts `products/kenn/docs/research/results/qual-glm-2026-09-21-raw/` (12 probes), the audit JSON, plus direct code inspection cited below.

Ground rules honored: read-only investigation; every behavioral claim backed by a test in `products/kenn/apps/backend/src/kenn/tests/` or a research receipt under `products/kenn/docs/research/results/`; owner audio/corpora stay outside the repo.

---

## Part 1 — Honest Current-State Audit

### 1.1 Live control surface — what KENN can actually *do* end-to-end

**The chain is real and proven against real Live** (qualification §2, all values measured, nothing bypassed):
`server.py` command route (`ableton_command`) → `handle_command()` (`apps/backend/src/kenn/core/live_command.py:2034`) → fresh topology snapshot → `parse_request()` deterministic parser (`live_intent.py`, ~1500 lines) → intent/plan validation → typed proposal with confirmation token → `live_action_service.py` apply → `live_executor.py` → **fresh-read verification** (raw + display string) → durable receipt → exact undo.

**Wired action verbs** (verified in `live_action_service.py` / `live_executor.py`, many live-verified 2026-09-21):

| Family | Actions | Status |
|---|---|---|
| Mixer | `set_volume`, `set_pan`, `set_mute`, `set_solo` (`live_action_service.py:131-134`, executor dispatch :3118-3121) | production-ready, live-verified |
| Track ops | `create_midi_track`, `create_audio_track`, `create_return_track`, `rename_track` | live-verified (insert); **no undo for track creation** — the reason the 5-track fixture was never built |
| Devices | `insert_device`, `insert_device_with_parameter`, `set_device_parameter`, `remove_device` | live-verified with readback + exact undo (EQ Eight, Compressor, Auto Filter, Saturator, Hybrid Reverb, Echo) |
| EQ | `set_eq_band_gain`, `set_eq_band_tuning_gain` (EQ Eight only, band must resolve) | live-verified: 500 Hz +3.00 dB measured, byte-identical undo |
| Sends | `set_send` (`SUPPORTED_SEND_ACTIONS`, :143) | wired, tested |
| Batch | `gain_stage_tracks`, `group_tracks` (executor `apply_batch_proposal`) | implemented, tested in suite |
| Multi-step | typed recipes + `parse_natural_recipe` (command path :2203+) | tested-but-limited |
| Subjective | `SubjectiveTranslator` (`subjective_translator.py:46`) — "make it warmer"-style mapping | experimental |
| Questions | `answer_live_session_question` (`live_session_questions.py:41`) — 7 kinds (connection, track_count, track_identity, tempo_signature, selected_track, duplicate_names, overview) | **implemented-but-UNWIRED** (see 1.5) |

**Parsed-but-not-executable / missing** (gap matrix #6, qualification §7): tempo change, move/bypass/remove *track*, delete ops (correctly refused — destructive), clip launch/creation from chat, automation, scene ops (scene names are read for parsing only), change history.

### 1.2 Unit/parameter semantics — the honesty layer

`core/device_units.py` carries **11 evidence-backed profiles across 7 devices** (Auto Filter Resonance/Frequency-log, Compressor Threshold 20-point measured table, Saturator Drive, Drum Buss Drive, Hybrid Reverb Dry/Wet, Roar Drive/Dry/Wet). Every profile is "confirmed by reversible real-Live probes" (file docstring); conversions run on all three planning paths (deterministic, LLM, relative round-trip — hardened further in commit `4d93241` fixing the raw-vs-display range gate).

That is **~11 parameters out of thousands** in Live's device universe — the single hardest ceiling on assistant breadth. The qualification process exists and works (`tooling/scripts/qualify_ableton_live_device.py`, `qualify_ableton_live_mutations.py`, `qualify_ableton_live_recipe.py`; the 2026-09-21 session qualified 3 new mappings via reversible probes in one evening). It is **semi-automated**: scripts drive the probes, but human judgment gates each new profile. Known edges: Utility Gain fails at the endpoint floor (0 dB), Limiter exact-name resolution — both documented in the report.

### 1.3 The LLM layer — built, gated, switched off

- The planner LLM is **off by default**: `KENN_LIVE_LLM_ENABLED` gates everything (`live_command.py:771,1022,2314`); the deterministic regex parser owns the chat path. The report and gap matrix (#19) call this "experimental."
- The machinery is complete and serious: `LLM_COMMAND_SYSTEM_PROMPT` + versioned plan schema, read-only planner snapshot (`_llm_planner_snapshot`, `live_command.py:663+`), `validate_llm_plan` as the mechanical contract, shadow/active modes.
- **LoRA pipeline**: `tooling/scripts/build_kenn_command_corpus.py` (48 reviewed seed records → deterministic synthetic expansion, 576+ rows at 4×3), `build_kenn_command_training.py` (tracked artifact, holdout-safety check `assert_no_holdout_overlap`), `train_kenn_command_lora.py` (Qwen2.5-1.5B base), `run_kenn_command_pilot.py` (preflight-only by default, 192 rows), `evaluate_kenn_command_lora.py`.
- **The contract gate** (`run_kenn_command_pilot.py:31-58`) requires **100% schema acceptance AND 100% deterministic-interpretation match on holdout**, and even then `live_activation_allowed` is hard-coded `False` with three further requirements (human review, real-Live qualification, guarded path). Correctly paranoid. Is 48 seeds / 576 synthetic rows enough for open-ended phrasing? **No** — enough to prove the pipeline, not to generalize; synthetic variants share the same underlying label distribution, so "100% match" measures schema fidelity, not language coverage.
- **GLM's place**: GLM was used as the *evaluator/driver* of the qualification (the raw probes are GLM-driven chat calls). Strategically, GLM-class API models are the natural **parser/planner brain** with KENN's gate layer as the safety envelope; the local LoRA is the offline/latency fallback. Today neither is active on the command path.

### 1.4 Reliability gates — tested vs. convention

| Gate | Evidence | Status |
|---|---|---|
| Confirmation tokens, idempotency, receipts journal persisting across restart | gap matrix #7, #8; live-verified incl. restart test | **production-ready, tested** |
| Readback verification on every mutation (raw + display) | #9; live-verified | **production-ready, tested** |
| Exact undo (identity-bound, verified revert) | #10; live-verified for insert/params/mixer | tested-but-incomplete (clip/return undo untested) |
| Stale-version rejection, duplicate-insert guard, duplicate-name refusal | #5; live-verified | production-ready |
| Default-deny `KENN_ALLOW_DAW_CONTROL` (403 verified), destructive-verb refusal | #7, #23 | tested |
| Rate limiting | #21 — trips at 60/60s under bursts, no pacing logic | tested-but-crude |
| MCP write path fail-closed | report (write refused by construction) | tested fail-closed; **mutation path unqualified (P0-1)** |
| Live-restart recovery mid-write; chaos (kill Live during write, UDP drop) | #25, roadmap P6-1 | **untested — convention only** |

### 1.5 Surfaces — alive vs. stale

- **`server.py`**: alive and dense — `ableton_command`/`ableton_live_inspection` routes, DAW-command handler, automix/session-intelligence/doctor/racks routes, Ableton ping/watchdog/capabilities. But `/api/ask` **500s without a generated retrieval index** (`load_chunks` SystemExit — gap matrix #18; report §9-4). Routes are hand-rolled `do_GET`/`do_POST` dispatch — a maintenance risk worth noting.
- **MCP**: `ControlDeckMCPBackend` selectable (PR #23), read-only by construction, provider not installed (no ARM64 Node 24 build) — the qualified transport is OSC.
- **Chat pipeline / `/api/ask`**: blocked in qual env (index).
- **`live_session_questions.py`**: implemented with 3 tests on main, **but nothing calls it** — zero imports in `server.py`/`live_command.py`. This is P0-2 half-built and dangling on a branch-merge; the qualification's 7/8 session-Q&A failures still reproduce on the live chat surface.
- **M4L, desktop companion, vscode_extension**: present in tree; none exercised in the qualification; treat as dormant until a qualification receipt says otherwise.

---

## Part 2 — Gap Analysis vs. the GLM-Assistant Goal

**Definition** (from the gap matrix): open-ended producer intent → grounded Live understanding → multi-step typed plans → safe execution → exact undo, with audio/MIDI/musical reasoning, generation, and learning.

Enumerated gaps, in impact order:

1. **The brain is a regex** (areas 1, 2, 3). A ~1500-line deterministic parser means every new phrasing family is hand-coded (QLM-01/02/05 were exactly this class of repair). No anaphora ("make *it* louder"), no correction ("no, the *other* vocal"), no multi-turn context — the gateway is stateless per call. GLM-the-model is precisely the tool for this; what's missing is *wiring and trusting it inside the gate*.
2. **Parameter coverage is ~11 profiles** (§1.2). Musicians' requests are dominated by devices KENN can't honestly touch yet (Utility, Limiter, EQ band frequency/Q ranges beyond the one profile, Glue Comp, Delay, sidechain…). The honest answer today is "I don't have a verified mapping" — correct behavior, poor coverage.
3. **Session Q&A unwired** — the module exists (`live_session_questions.py`), tests exist, integration doesn't. Cheapest big win available.
4. **No change-history/memory surface** ("What did you change?" — receipts exist in the journal; no reader/answer path).
5. **Musical reasoning absent** (areas 11–14): audio analysis, mix-doctor/masking engines, generative MIDI, AudioGen all exist *in-tree* but are unreachable from the Ableton surface. KENN has an unusually large stock of already-built intelligence that it can't talk to.
6. **Transport duplication** (roadmap P0-1): chat writes run on legacy OSC; the supported MCP transport is read-only. Two transports to qualify forever unless this resolves.
7. **Evaluation loop is manual**: qualification receipts are excellent but episodic; there's no continuous corpus→gate→live regression harness (P6-1).
8. **Safety for irreversible ops**: delete/bounce/save are refused outright — right for now, but a GLM assistant eventually needs a classified, confirmed path for at least save-set.

---

## Part 3 — Phased Roadmap (opinionated)

**Sequencing argument first:** *the highest-leverage next move is wiring the existing intelligence (Q&A module, receipts, GLM planner-in-shadow) into the gated command path — not expanding `device_units.py`.* Reasons: (a) the gap matrix shows more "reachable-but-unwired / implemented-but-unqualified" (areas 15–19) than any other state — KENN's bottleneck is integration, not invention; (b) mapping expansion is linear manual labor with a human in the loop, while Q&A + LLM-shadow activation unlock conversational competence immediately; (c) the model contract gate currently has **zero live data flowing through it** — it can't be trusted or improved until a real model runs shadow mode daily. Mapping breadth (P1) remains the top *breadth* investment and follows immediately.

### P0 — Correctness & integration (1–2 weeks)
| Item | Work | Done-evidence |
|---|---|---|
| **P0-A Wire session Q&A** | Call `answer_live_session_question` in `handle_command` before intent parsing (read-only early return, like the recipe path); route the 8 matrix-A questions | Matrix-A re-run receipt, 8/8 + `test_live_session_questions` extended to cover each kind through the command path |
| **P0-B Change history from receipts** | Read-only `describe_recent_changes` backed by the receipts journal (`live_action_service` journal reader + answer template) | "What did you change?" answered from journal; seeded-journal test |
| **P0-C LLM shadow activation** | Enable `KENN_LIVE_LLM_ENABLED=shadow` behind the existing plumbing; log plan-vs-deterministic diffs to a receipts file | Weekly shadow report: schema-accept %, deterministic-match %, divergence samples |
| **P0-D MCP provider install** | Node 24 ARM64 + provider build + read-parity suite OSC-vs-MCP (`test_live_backend_mcp_writes.py` per roadmap P0-1) | Read-parity diff empty; then ONE write (device insert) with full receipt/undo |

### P1 — Dependable operator (breadth of verified mappings)
- Automate the probe→profile loop: `qualify_ableton_live_device.py` should emit a draft `DeviceUnitProfile` + verification transcript for human sign-off; target +8–12 profiles/sprint (Utility, Glue Comp, Delay, EQ band Q/frequency ranges…). Receipt per profile.
- Qualify `set_tempo`, `set_scene`, gain-stage/group on the chat path (batch machinery exists; needs matrix receipts).
- Fix the `/api/ask` blocked-env: build the index or scope retrieval out of the Ableton surface explicitly (report §9-4).
- 5-track fixture with duplicate names + clips (blocked only on track-creation undo — add create-track undo via reverse delete with confirmation, or accept fixture-as-disposable-set).

### P2 — Model quality (make the GLM the planner, inside the gate)
- Turn the contract gate's `live_activation_allowed: False` into a **staged promote**: shadow → propose-only-with-human-confirm → active, each stage requiring N days of shadow stats + human review + live qualification matrix. Extend `_model_contract_gate` with stage thresholds (e.g., ≥98% deterministic match on *held-out natural phrasing*, not synthetic variants — add a natural-language corpus: transcript-derived phrasings, not paraphrases of existing labels).
- Multi-step planner: let the LLM emit compound plans (insert+tune already exists as `follow_up`; generalize to N-step recipes validated step-wise by `validate_llm_plan`).
- Model routing: GLM for parsing/planning; local LoRA as offline fallback; both behind the same contract gate.

### P3 — Conversation, memory, learning
- Multi-turn session context (anaphora, corrections) on top of P0-A/P0-B — proposals already carry session_id; add a bounded conversation state.
- Preference store (roadmap P5-1): opt-in, isolated, citable.
- Wire mix-doctor/masking into chat *as advice* (advice ≠ execution; evidence-cited answers only — roadmap P2-3).

### P4 — Product surface & hardening
- Generative MIDI/AudioGen preview→approve→insert through the existing proposal machinery (roadmap P4-1).
- SLOs + nightly real-Live regression + chaos suite (roadmap P6-1): propose p95 ≤500 ms, verified-execution ≥99%, undo success 100% — all three already met in single-session measurements; the work is making them *continuous*.

---

## Part 4 — Do This Week (ordered by leverage)

1. **Wire `answer_live_session_question` into `handle_command`** (P0-A). ~1 day. *Acceptance:* the 8 matrix-A questions return grounded answers through the real chat route; receipt re-run archived under `products/kenn/docs/research/results/`; `test_live_session_questions` extended for command-path integration.
2. **Enable LLM shadow mode** (P0-C) on the dev machine with a recurring session. ~0.5 day + observation. *Acceptance:* shadow receipts show per-call schema-accept/deterministic-match rates; first weekly divergence report exists. This is what eventually *feeds* the contract gate with real data.
3. **Strengthen the contract gate** (sprint's gate item): extend `_model_contract_gate` to (a) track a natural-phrasing holdout set distinct from synthetic variants, (b) implement the staged `live_activation_allowed` promotion with explicit thresholds. *Acceptance:* unit tests for each blocker path; a shadow-report summary in the gate output.
4. **Add one new verified device mapping via `qualify_ableton_live_device.py`** (mapping-coverage item): Utility Gain (also fixes the known endpoint-floor defect) or Glue Compressor. *Acceptance:* reversible probe transcript + new profile in `device_units.py` + `test_device_units.py` cases + live readback receipt.
5. **`change_history` from the receipts journal** (P0-B). ~1 day. *Acceptance:* "What did you change?" answered from journal with proposal IDs; seeded-journal unit test.

Items 1, 2, 5 together retire the qualification's biggest honest failure ("session-understanding Q&A, multi-turn anaphora") and start the data flywheel for item 3; item 4 buys honest breadth; all five are small, individually testable, and produce receipts — the same discipline that made the 2026-09-21 qualification trustworthy.

