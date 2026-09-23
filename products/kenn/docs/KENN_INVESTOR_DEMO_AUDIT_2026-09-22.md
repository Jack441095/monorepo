# KENN Investor-Demo Audit — 2026-09-22

**Scope:** Full investor-demo audit (readiness + codebase health + risks + next actions).
**Method:** Read-only inspection. No code changed, no tests run, no Live session probed.
**Plan reference:** `docs/plans/KENN_GLM_ABLETON_ASSISTANT_PLAN_2026-09-22.md` (840 lines, baseline `3bb9ebc`).
**Repo rules:** `monorepo/CLAUDE.md` — no AI attribution trailers on commits; KENN source of truth is `products/kenn/`; verify with `cd products/kenn && PYTHONPATH="apps/backend/src:tooling" python3 -m pytest -q apps/backend/src/kenn/tests`.

## Post-audit update — 2026-09-23

The body of this document is the original read-only gap audit. It is retained
as baseline evidence, but its missing/blocked labels are no longer the current
implementation status. Forty-three KENN commits after `3bb9ebc` completed the
main wiring, hardening, qualification tooling, fixture, and frontend work.

Now complete:

- Grounded session Q&A, receipt history, retrieval fallback/startup behavior,
  and evidence-labelled mix/vocal advice through the real chat surface.
- Shadow reporting, durable promotion thresholds/state, natural holdout
  assessment, evidence isolation, and bounded multi-turn resolution. The model
  correctly remains at `shadow`.
- Eleven-check demo preflight, latency budgets, sentence-level demo errors,
  safe refusals for unverifiable compound workflows, and frontend polish.
- A real eight-track Live 12 reset fixture, deterministic `Neon Proof` audio,
  hash-bound analysis files, canonical runbook, and investor FAQ.
- Automated verification: 1,410 backend tests passed with 5 skips and 4 known
  warnings; 18 frontend tests and the production build passed.
- Real-Live evidence: 11/11 mutating preflight, 10/10 bounded recipe runs,
  10/10 non-mutating script-contract runs, and one successful canonical Bass
  EQ focus/change/exact-undo sequence.

Still open before the demo can be called qualified:

1. Import all eight generated stems into the disposable rehearsal copy.
2. Re-run mutating preflight and qualify atomic EQ with `--apply` on the empty
   Synth chain.
3. Complete ten consecutive end-to-end 20-step UI rehearsals, including the
   deliberate recovery/reset drill, projector check, and 8–12 minute timing.

Current safe handoff: Live is stopped on the tracked reset fixture, not the
disposable rehearsal set. The disposable copy is byte-identical and still has
no stems. No mutation should be confirmed until the `.runtime` window path is
visibly verified.

Architecture decision: OSC remains the final transport into Ableton because
AbletonOSC is the real Live-side endpoint and provides low-latency control and
readback. MCP is complementary: it can expose KENN's safe tools to agents, but
it does not replace the Live endpoint, confirmation gate, receipts, or exact
undo.

## Executive summary

KENN has a real, safe chat-to-Live control chain worth demoing. It is **not demo-ready** on the scripted 20-step flow. The blockers are integration and wiring, not invention:

1. Session Q&A answers exist but are unreachable from `handle_command()` — Acts 1–2 of the demo fail through the normal chat path.
2. No change-history reader — "What did you change?" has no answer path.
3. `/api/ask` crashes with `SystemExit` when the retrieval index is unbuilt.
4. Mix/audio intelligence exists but is unreachable from conversational chat.
5. No pre-flight script, no demo-grade rehearsed session (`assets/demo/KENN_Live12_Demo.als` is 357 bytes), no latency budget enforcement, no top-level graceful-error wrapper on the demo path.
6. LLM planner is fully built but correctly off (`KENN_LIVE_LLM_ENABLED` off, `live_activation_allowed: False`). Shadow mode has zero data flowing.

No blocker requires new DSP, new models, or C. All are Python wiring + qualification + polish.

## What works (verified)

- **Control chain:** `apps/backend/src/kenn/server.py` (~3308 lines) → `core/live_command.py:2034 handle_command()` (2574 lines) → `core/live_intent.py parse_request()` (1539 lines) → `core/live_action_service.py apply()` (4083 lines) → OSC UDP 11000/11001 → readback verification → durable receipt → exact undo.
- **Wired actions:** mixer (`set_volume/pan/mute/solo`), track create/rename, `insert_device` / `set_device_parameter` / `remove_device` with readback + undo, EQ band gain, sends, batch gain-stage/group. Matches plan §Current State table.
- **Device profiles:** 11 `DeviceUnitProfile(` entries in `core/device_units.py:35-62` (Auto Filter ×2, Compressor Threshold table, Saturator, Drum Buss, Hybrid Reverb, Echo, Glue ×2, Roar ×2). Linear/log/table mappings implemented.
- **Session Q&A logic:** `core/live_session_questions.py` (144 lines) implements 7 kinds (`connection`, `track_count`, `track_identity`, `tempo_signature`, `selected_track`, `duplicate_names`, `overview`) via fresh snapshot. Read-only by construction (returns `None` for non-questions, never mutates).
- **Tests:** `apps/backend/src/kenn/tests/test_live_session_questions.py` (89 lines, 3 fns; first fn parametrizes all 7 kinds through direct call, plus `test_unrelated_chat_is_not_hijacked`). 174 entries in `tests/`. Server exposes `/api/health`, `/api/ableton/*`, `/api/admin/reload-index`, mix/session/doctor routes (`server.py:779+`).
- **Native DSP (out of demo scope):** `core/_kenn_dsp_native.cpython-313-darwin.so` (179KB) + `tooling/native/dsp_core/` + `fft_poc/` exist. `docs/research/CPP_DSP_BENCHMARK_PLAN.md` records Phase 2 native comparison passing its gate with release-default still pending. No action needed for demo.

## Gaps by phase

### Phase 1 — Make It Conversational

**1.1 Session Q&A routing — MISSING.**
`server.py:77` imports and `server.py:664-674 _maybe_handle_live_inspection()` calls `answer_live_session_question()`, but `live_command.py:handle_command()` contains no session-Q&A early return. Any question routed through the command path falls to regex parse and fails. Fix is the plan's early-return block before `parse_request()` with `answer_mode: "session_question"`, `changed: False`. Tests needed through `handle_command()`, not just direct call.

**1.2 Change history — MISSING.**
No `describe_recent_changes` in `live_action_service.py` (only `_RECEIPTS` dict writes at ~`607-681` plus `receipt_contract.py` helpers). No `change_history` kind in `_question_kind()` (`live_session_questions.py:20-38`). "What did you change?" / "undo everything" currently unhandled. Needs journal reader + kind + tests (seeded journal, limit, empty, undoable flag).

**1.3 Retrieval crash — PRESENT.**
`core/chat_retrieval.py:35-40 _load_index_bundle()` raises `SystemExit("Index not found…")` when `chunks.jsonl`/`terms.json` absent. `lru_cache(maxsize=1)` means one failure poisons the process. Needs empty-collection fallback + startup auto-build + startup log. `/api/admin/reload-index` (`server.py:1105`) already exists for the manual path.

**1.4 Shadow analysis script — MISSING.**
`tooling/scripts/analyze_shadow_logs.py` does not exist. Shadow infra in `live_command.py:2311-2330` + `_generate_llm_plan()` (`764-838`) + `validate_llm_plan()` (`180-270+`) is built but `KENN_LIVE_LLM_ENABLED` is off and `KENN_LIVE_LLM_MODE` defaults to off, so zero data flows. Script is new-file only, no runtime change.

### Phase 2 — Expand Capability

**2.1 Mix doctor in chat — MISSING.**
`core/live_session_advice.py` does not exist. `audio_analysis.py` (749 lines, intentionally stdlib-only: `math`/`struct`/`wave`/`array`, `DEFAULT_FFT_SIZE=16384`, `MAX_FFT_WINDOWS=4`) plus `arrangement_doctor.py`, `mix_doctor.py` are imported in `server.py` (`404`, `526-527`, `903-911`) but unreachable from chat. Needs `mix_advice` kind + `mix_advice_from_session()` with audio→`analyze_wav()` path and arrangement fallback. Constraint holds: advice-only, execution stays behind proposal/confirm.

**2.2 Multi-step recipes — PARTIAL.**
`parse_natural_recipe` (`live_command.py:2203+`), recursive `validate_llm_plan`, `apply_batch_proposal`, and `tooling/scripts/qualify_ableton_live_recipe.py` exist. The 5 deterministic patterns (device+param, send+level, EQ+bands, gain-stage+rename, solo+analyze) are not in `live_intent.py`. Needs regex → existing primitives with per-step verification.

Device sprint (plan §2.1, 11→20+ profiles) is deferred by task scope, not done. Qualification tooling (`qualify_ableton_live_device.py`) exists.

### Phase 3 — Trust the Model

**3.1 Promotion ladder — MISSING.**
No `PROMOTION_THRESHOLDS` in `live_command.py` or pilot script. `tooling/scripts/run_kenn_command_pilot.py:52` still hardcodes `live_activation_allowed: False` (correct — do not flip). No durable promotion-state JSON, no `natural_holdout.jsonl`. Infrastructure-only work; shadow→propose→active gates from plan §3.1 stand.

**3.2 Multi-turn context — NAME CLASH, LOGIC MISSING.**
`core/session_context.py` exists (707 lines) but is a bounded provenance-aware context composer (`SCHEMA = "kenn.session_context.v1"`, caps like `MAX_TRACKS=256`, `MAX_CONTEXT_AGE_SECONDS=300`). Zero anaphora handling (`grep anaphora` = no hits anywhere in `core/`). The planned ring-buffer preprocessor ("it" → last entity, "louder" → last param, "again", bare "undo", corrections) does not exist. Decide: extend this file or create a separate `conversation_anaphora.py`-style module to avoid overloading the existing schema.

**3.3 Continuous regression — MISSING (out of task scope).**
No `tooling/scripts/nightly_regression.py`, no `slo_report.py`. Golden benchmark runner exists at `tooling/evaluation/benchmark/run_golden_benchmark.py`.

### Phase 4 — Demo Readiness

**4.1 Pre-flight — MISSING.**
`tooling/scripts/demo_preflight.py` does not exist. Related scripts (`record_demo_live.py`, `demo_plugin_live.py`, `notes_server_preflight.sh`, `kenn_demo_doctor.py` in legacy) are not the 11-check <30s gate the plan specifies (OSC ping, session names, server, index, DAW gate, Q&A, device, audio analysis, undo round-trip, frontend, latency).

**4.2 Error hardening — PARTIAL.**
`handle_command()` has ~39 `except` clauses but no single top-level converter guaranteeing sentence-level English on every demo-path failure (OSC timeout, device-not-found with visible list, out-of-range with min/max, unknown-command with capability list). `server.py:2573` inspection call site also needs coverage. No stack-trace leak audit done.

**4.3 Latency — UNMEASURED.**
No profile data. Budget from plan stands: parse <50ms, snapshot <200ms, exec <100ms, readback <200ms, frontend <100ms, total <650ms. Suspects if over budget: UDP socket reuse, snapshot caching with staleness check, parallel readback + response.

**4.4 Frontend — EXISTS, POLISH UNKNOWN.**
`apps/frontend/` (Vue 3 + TS, Pinia, vue-i18n, Vitest) with `KennChatBody/Input/History`, `KennActionCard`, `AbletonWorkspace`, `mix-review/`, `studio/` components. Demo-grade bar (no debug panels/JSON, confirm/reject/undo buttons, status bar, severity badges, Ableton dark theme, projector layout) not verified without running it.

## Demo script traceability (plan §5.1, 20 steps)

| Act | Steps | Status |
|---|---|---|
| 1 "knows your session" (1–5: count, selected, describe, duplicates) | Blocked on 1.1 | Logic exists, routing missing |
| 2 "controls safely" (6–11: volume, pan, EQ insert, EQ param, undo, history) | Partial | 6–10 wired; 11 blocked on 1.2 |
| 3 "understands audio" (12–14: low end, clipping, findings UI) | Blocked on 2.1 | Engine exists, chat path missing |
| 4 "safety model" (15–19: refuse delete, flag master-max, tokens, receipts, undo) | Partial | Tokens/receipts/undo exist; graceful-refusal wording unaudited |
| 5 "where we're going" (20–22: shadow, qualification, LoRA, generative) | Narrative only | Shadow needs 1.4 + env flags; LoRA corpus/pilot exist but idle |

Fixture gap: `assets/demo/KENN_Live12_Demo.als` (357 bytes) is not the specified 8–16-track named session with preloaded devices and deliberate mix issues (hot low end, near-clip, mono problem). Must be built and templated before any rehearsal.

## Risks (demo-weighted)

1. Off-script audience question typed live → unexpected response. Mitigate with operator discipline + unknown-command graceful fallback (4.2).
2. Live freeze / OSC timeout mid-demo → dead air. Mitigate with pre-flight + 5s reconnect + English fallback string.
3. Undo not exact on stage → safety story collapses. Mitigate by gating the script's undo step on pre-flight round-trip.
4. Audio analysis returns thin findings → intelligence story empty. Mitigate with seeded mix issues verified in rehearsal.
5. Shadow mode latency during demo → sluggish feel. Mitigate by disabling shadow for the showing (data collection is pre/post, not live).
6. `session_context.py` name clash → Phase 3.2 breaks existing consumers. Mitigate by scoping the new preprocessor separately.
7. C/native introduction before demo → segfaults, signing/arch issues, slower cold boot. Recommendation stands: no C on the demo path (see prior analysis).

## Gate before any showing (plan §Success Metrics, demo-specific)

- `demo_preflight.py` 11/11 green; full script 20/20 zero errors; 8–12 min timed; cold boot <60s; command→visible DAW <1s; 100% human-readable errors under fault injection; recovery <10s; 10 consecutive clean runs; projector-tested frontend; 20-question investor FAQ written.

## Recommended build order

1. 1.1 Q&A early return + command-path tests.
2. 1.2 Receipts reader + `change_history`.
3. 1.3 Retrieval graceful degradation + auto-build.
4. 1.4 Shadow script + `KENN_LIVE_LLM_MODE=shadow` for a week of normal use.
5. 2.2 Recipe regexes (small, high demo value) then 2.1 mix advice.
6. 3.1 Thresholds + promotion JSON; 3.2 anaphora preprocessor (resolve filename first).
7. 4.1 Pre-flight; 4.2 exception wrapper + wording audit; 4.3 profile; 4.4 frontend polish; build fixture session; rehearse 10×.

## Appendix — key paths

`apps/backend/src/kenn/core/live_command.py` · `live_intent.py` · `live_action_service.py` · `live_session_questions.py` · `device_units.py` · `audio_analysis.py` · `arrangement_doctor.py` · `mix_doctor.py` · `chat_retrieval.py` · `session_context.py` · `server.py` · `tooling/scripts/qualify_ableton_live_*.py` · `tooling/scripts/run_kenn_command_pilot.py` · `apps/frontend/src/components/` · `assets/demo/KENN_Live12_Demo.als` · `docs/research/CPP_DSP_BENCHMARK_PLAN.md`
