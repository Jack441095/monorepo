# KENN GLM Ableton Assistant — Build Prompt

Use this prompt in a fresh Claude Code session from `/Volumes/Jack_Gandy_1TB_SSD/Nite-DSP/monorepo/products/kenn`.

---

## Prompt

You are building KENN into a solid AI studio assistant for Ableton Live, targeting investor-demo quality. This is for a live demonstration to a company showing investors — every demo-path feature must be bulletproof, every error must be graceful, and the frontend must look professional. Zero crashes, zero stack traces, zero "sorry I can't do that" on the scripted flow.

KENN already has a proven, safe control chain from chat to Live via OSC — every mutation is readback-verified, confirmation-gated, and exactly undoable. The work ahead is integration, wiring, hardening, and polish — not invention from scratch.

## Current checkpoint — 2026-09-23

This prompt was written against baseline `3bb9ebc`. Forty-three KENN commits now
implement and test most of the requested integration. Treat the original
"what's broken" list below as historical scope, not current state. Do not redo
completed work; read the current runbook and live-qualification record first.

Completed and verified:

- Session Q&A, receipt history, retrieval fallback/startup handling, and
  evidence-labelled mix/vocal advice are wired through the real chat path.
- Shadow analysis, durable promotion gates/state, evidence isolation, and the
  bounded ten-exchange context preprocessor are implemented. The model remains
  at `shadow`; no active execution permission was enabled.
- The 11-check preflight, latency reporting, investor-facing error conversion,
  unsupported partial-workflow guards, and Vue demo polish are implemented.
- The eight-track Live reset fixture, deterministic rights-clear `Neon Proof`
  stems, manifest-bound analysis WAVs, FAQ, runbook, and evidence record exist.
- Verification is green: 1,410 backend tests passed (5 skipped), 18 frontend
  tests passed, and the production frontend build passed.
- Real-Live qualification includes an 11/11 mutating preflight, a 10/10 bounded
  recipe run, a 10/10 non-mutating scripted contract gate, and one successful
  canonical Bass EQ focus/change/exact-undo sequence.

Remaining release gate:

1. Open and verify `.runtime/investor-demo-audio/KENN_Live12_Demo_Rehearsal.als`;
   import the eight stems and save only this disposable copy.
2. Re-run mutating preflight and the atomic-EQ qualifier's `--apply` path on
   the disposable set.
3. Complete ten consecutive 20-step UI rehearsals, including reset, deliberate
   recovery, projector layout, and 8–12 minute timing.

Current safe handoff: Live is stopped on the tracked reset fixture, not the
disposable copy. The rehearsal copy is still byte-identical to the reset
fixture and has no imported stems. Do not confirm any mutation until Live's
window URL shows the `.runtime` rehearsal path.

### Why OSC is still used instead of MCP

OSC is the inner real-time transport because AbletonOSC already exposes Live's
control and readback surface over local UDP. MCP is an outer tool-discovery and
agent-integration protocol; it does not by itself add an endpoint inside Live,
verified state, receipts, or exact undo. KENN can expose its safe service
through MCP while retaining OSC for the final KENN-to-Live hop.

Read `docs/plans/KENN_GLM_ABLETON_ASSISTANT_PLAN_2026-09-22.md` for the full plan with codebase evidence, the demo script (Phase 5), and the demo-specific metrics. Read the CLAUDE.md at the monorepo root for repo-wide rules (notably: no AI attribution trailers on commits in this repo). Then execute the phases below in order.

### Context

**Architecture:** `server.py` (~3200 lines, BaseHTTPRequestHandler) dispatches to `live_command.py:handle_command()` (2574 lines) which calls `live_intent.py:parse_request()` (1539-line regex parser) → typed proposal → `live_action_service.py:apply()` (4083 lines) → `live_executor.py` → readback verification → durable receipt → exact undo. OSC bridge talks to Live on UDP 11000/11001.

**What works:** Mixer (volume/pan/mute/solo), track creation/rename, device insert/remove/set_parameter with readback+undo (EQ Eight, Compressor, Auto Filter, Saturator, Hybrid Reverb, Echo, Glue Compressor, Roar, Drum Buss), EQ band gain, sends, batch gain staging/grouping. 11 evidence-backed device unit profiles in `apps/backend/src/kenn/core/device_units.py`.

**What's broken or unwired:**
- Session Q&A (`live_session_questions.py`, 144 lines, 7 question kinds) is imported in `server.py:77` and called at `server.py:674` but fails 7/8 qualification questions through the chat surface — it's not called from `handle_command()` in `live_command.py`
- The LLM planner (`live_command.py:63-838`) is fully built with shadow mode, validation, and contract gating, but `KENN_LIVE_LLM_ENABLED` is off and has zero real data flowing through it
- Audio analysis (`audio_analysis.py`, 749 lines — FFT, spectral, masking, findings), arrangement doctor, mix doctor, and stem masking are all imported in `server.py` but unreachable from the conversational chat surface
- Chat retrieval (`chat_retrieval.py`) crashes with SystemExit when the index hasn't been built
- Only 11 device profiles out of thousands of Live parameters

### Phase 1 — Make It Conversational (do this first)

**1.1 Wire session Q&A into `handle_command()`.**

In `apps/backend/src/kenn/core/live_command.py`, add a session Q&A check as the first thing in `handle_command()`, before `parse_request()`. Call `answer_live_session_question(command, service=service)` — if it returns non-None, return immediately with `answer_mode: "session_question"` and `changed: False`. This is read-only (no mutations, no proposals), so it's safe as an early return.

The 7 question kinds in `live_session_questions.py` are: connection, track_count, track_identity, tempo_signature, selected_track, duplicate_names, overview. Each returns a grounded answer from a fresh Live snapshot.

Extend `apps/backend/src/kenn/tests/test_live_session_questions.py` (currently 3 tests) to cover all 7 kinds through the `handle_command()` path, not just through direct function call.

**1.2 Add change history from receipts.**

The receipts journal in `live_action_service.py` records every mutation (proposal_id, action, track, device, parameter, before/after values, timestamp, undo_available). Add a `describe_recent_changes(limit=10)` method that reads the journal and returns a structured summary.

Add a `change_history` kind to `_question_kind()` in `live_session_questions.py` matching patterns like "what did you change", "show history", "undo everything". Wire it through the session Q&A path added in 1.1.

Write tests with a seeded journal: verify correct rendering, limit, empty journal, undo status display.

**1.3 Fix retrieval index crash.**

In `apps/backend/src/kenn/core/chat_retrieval.py`, change `_load_index_bundle()` (line 35) to return empty collections instead of raising SystemExit when no index exists. The chat pipeline should work with reduced quality (no retrieval context) rather than crashing. Add a startup check in `server.py` that logs the index state and triggers an auto-build from Training_Data_Notes if no active index version exists.

**1.4 Create shadow analysis script.**

Create `tooling/scripts/analyze_shadow_logs.py` that reads shadow comparison metadata from command logs and produces a report: total commands, schema acceptance rate, deterministic match rate, divergence samples (where LLM and regex disagreed), and novel phrasings the model handled that the regex missed. This script doesn't change any runtime code — it reads logs produced when `KENN_LIVE_LLM_MODE=shadow` is set.

### Phase 2 — Expand Capability

**2.1 Wire mix doctor into chat.**

Create `apps/backend/src/kenn/core/live_session_advice.py` with a `mix_advice_from_session()` function. Add a `mix_advice` kind to `_question_kind()` matching "how does my mix sound", "check my low end", "any masking issues", "analyze my session". Route through the session Q&A early return in `handle_command()`.

When audio capture is available, run `audio_analysis.py:analyze_wav()` and format findings as conversational advice with severity, confidence, and suggested listening tests. When no audio is available, fall back to arrangement-level advice from `arrangement_doctor.py:analyze_timeline()`.

This must be advice only, not execution. KENN presents findings with evidence. If the producer wants to act ("OK, cut 3dB at 200Hz"), that goes through the normal command pipeline with confirmation.

**2.2 Add multi-step recipe patterns to the deterministic parser.**

In `live_intent.py`, add regex patterns for the 5 most common multi-step requests:
- Insert device + set parameter(s): "add a compressor to vocals and set threshold to -20"
- Create send + set send level: "create a return with reverb and send vocals to it at -10"
- Insert EQ + set band gains: "add an EQ and boost 3dB at 5kHz"
- Gain stage + rename: "balance all the drums and call the group 'Drums'"
- Solo + analyze: "solo the bass and check the low end"

Each pattern should decompose into the existing action primitives and go through `apply_batch_proposal` or sequential `apply()` calls with per-step verification.

### Phase 3 — Trust the Model

**3.1 Staged LLM promotion.**

Extend `_model_contract_gate` in `live_command.py` with promotion stages. Add a `PROMOTION_THRESHOLDS` dict defining:
- shadow → propose: ≥500 comparisons over ≥14 days, schema acceptance ≥98%, deterministic match ≥90%
- propose → active: ≥1000 proposals, user acceptance ≥95%, zero safety violations

Track promotion state in a durable JSON file alongside the shadow logs.

**3.2 Multi-turn session context.**

Create `apps/backend/src/kenn/core/session_context.py` with a per-session ring buffer (last 10 exchanges) tracking: last discussed track/device, last proposed action, confirmation/rejection status, current topic. Add anaphora resolution before parsing: "it" → last discussed entity, "louder/softer" without target → last discussed parameter, "again" → repeat last action, "undo" without target → undo last receipt.

This sits between user input and `parse_request()` — a context-aware preprocessor. The parser itself doesn't change.

### Phase 4 — Demo Readiness (do after Phases 1-2)

**4.1 Create the pre-flight check script.**

Create `tooling/scripts/demo_preflight.py` that verifies: Live connected (OSC ping < 100ms), demo session loaded (expected track names match), server healthy, retrieval index loaded, DAW control enabled, session Q&A working, device control working, audio analysis working, undo round-trip succeeds, frontend reachable, latency < 500ms. Each check individually runnable, clear pass/fail with failure reason. Full suite under 30 seconds.

**4.2 Error handling hardening.**

Audit every code path on the demo script (see Phase 5 in the full plan for the 20-step demo script) for graceful degradation. No demo attendee should ever see a stack trace, a raw error code, or a silent failure. Every failure mode gets a sentence-level English response:
- OSC timeout: "Ableton Live isn't responding — check the connection"
- Device not found: "I can see the track but I can't find that device — here's what I see: [list]"
- Unknown command: "I'm not sure what you're asking. I can help with: [capability list]"
- Parameter out of range: "That value is outside the safe range. The range is [min] to [max]."

Wrap the entire `handle_command()` path in a top-level exception handler that converts any unhandled exception to a structured error response.

**4.3 Latency optimization.**

Profile the command path end-to-end. Target budget: parse < 50ms, OSC snapshot < 200ms, execution < 100ms, readback < 200ms, frontend update < 100ms = total < 650ms. If any step exceeds its budget, investigate: socket reuse for OSC, caching snapshots with staleness checks, parallelizing readback with response sending.

**4.4 Frontend polish.**

The Vue frontend must be demo-grade: clean layout (no debug panels or raw JSON), chat bubbles with confirm/reject/undo buttons, status bar (Live connection, session name, track count), mix advice panel with severity badges, dark theme matching Ableton's aesthetic, smooth animations on state changes, good projector/large-screen layout.

### Working rules

- Run the test suite after each phase: `cd apps/backend && python -m pytest src/kenn/tests/ -q`
- Every new function gets tests. Every behavioral change gets a test that proves it works through the real code path, not just the isolated function.
- Don't change the proposal/confirmation/undo safety model. Don't bypass readback verification. Don't auto-execute without confirmation.
- The LLM planner changes are infrastructure only (shadow logging, analysis scripts, promotion thresholds). Don't flip `live_activation_allowed` to True or set `KENN_LIVE_LLM_MODE=active`.
- Keep session Q&A and mix advice as read-only early returns — they must never create proposals or trigger mutations.
- Commit after each sub-phase (1.1, 1.2, 1.3, etc.) with a clear message describing what changed and why. No AI attribution trailers per the repo CLAUDE.md rule.
- **Demo quality bar:** Every feature on the demo script path must work 10 consecutive times without error before it's considered done. If a feature can fail silently, add explicit error handling. If a response could confuse a non-technical investor, rewrite it.
