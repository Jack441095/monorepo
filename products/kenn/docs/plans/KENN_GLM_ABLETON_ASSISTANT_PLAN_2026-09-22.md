# KENN GLM Ableton Assistant — Implementation Plan

**Date:** 2026-09-22  
**Baseline:** commit `3bb9ebc` (main, post-hygiene)  
**Test suite:** 1317 passed / 2 failed (network flakiness) / 5 skipped (onnxruntime)  
**Goal:** Transform KENN from a command executor with a regex brain into a solid, daily-usable AI studio assistant for Ableton Live — and bring it to investor-demo quality.

---

## Progress checkpoint — 2026-09-23

This plan records the baseline at `3bb9ebc`. The implementation has since
advanced by 43 KENN commits. Sections headed "Current State" and "What doesn't
work" below are retained as the original design evidence; this checkpoint and
the current runbook/evidence record supersede them for operational status.

| Workstream | Current status |
|---|---|
| Session Q&A and change history | Done through the real command/chat path, with fresh Live grounding and receipt-backed history |
| Retrieval startup | Done; missing data degrades safely and startup reports/builds the available index mode |
| Mix/audio advice | Done for manifest-bound low-end and vocal-clipping chat paths; remains read-only |
| Deterministic recipes | Verified bounded compressor and two-step recipe flows; rollback-safe atomic EQ is implemented; return+send, group+rename, and solo+analyze remain explicit no-change guards pending complete bridge verification |
| LLM promotion | Shadow analysis, durable thresholds/state, holdout assessment, and test-evidence isolation are done; production state remains `shadow` |
| Multi-turn context | Done with a bounded ten-exchange preprocessor and correction/anaphora tests |
| Demo preflight/errors/latency | Done; mutating real-Live preflight passed 11/11 in 9.62 seconds and post-restart read-only preflight passed 10/11 with the mutation check explicitly skipped |
| Frontend | Demo theme, Live status, action cards, advice rendering, errors, and projector-oriented layout polished; 18 tests and production build pass |
| Fixture and audio | Eight-track reset fixture plus deterministic rights-clear stems and manifest-bound analysis WAVs are built |
| Full investor rehearsal | In progress: stems imported and set qualified on 2026-09-23 (see tracker below); ten complete 20-step rehearsals remain |

### Progress tracker

Tick items here in the same commit as the work that completes them.

**Phase 1 — Conversational**
- [x] 1.1 Session Q&A through the real command/chat path
- [x] 1.2 Receipt-backed change history
- [x] 1.3 LLM shadow infrastructure + `analyze_shadow_logs.py` (production stays `shadow`)
- [x] 1.4 Retrieval graceful degradation + startup index build

**Phase 2 — Capability**
- [ ] 2.1 Device mapping sprint to 20+ profiles (currently 11 profiles across 8 devices)
- [x] 2.2 Mix doctor in chat (low-end and vocal-clipping advice, read-only)
- [ ] 2.3 Multi-step recipes: compressor, two-step, and atomic EQ done; return+send, group+rename, solo+analyze still guarded

**Phase 3 — Trust the model**
- [x] 3.1 Staged promotion thresholds and durable state (stage remains `shadow`)
- [x] 3.2 Bounded ten-exchange multi-turn context
- [ ] 3.3 Nightly real-Live regression + SLO report (no script yet)

**Phase 4 — Product surface**
- [x] 4.1 Frontend chat, proposal, receipt, and advice UI
- [ ] 4.2 Knowledge base curation + semantic index (BM25-only today)
- [ ] 4.3 Generative preview/approve/insert (roadmap)

**Phase 5 — Demo readiness**
- [x] 5.2 Eight-track reset fixture + rights-clear `Neon Proof` stems
- [x] 5.3 Eleven-check preflight
- [x] 5.4 Investor-facing error hardening
- [x] 5.5 Latency budget reporting
- [x] 5.6 Frontend demo polish
- [x] Atomic-EQ `--apply` passed on the disposable set (2026-09-23)
- [x] Kick and Synth converted to audio tracks; all eight stems placed at bar 1 via `prepare_investor_demo_rehearsal_set.py` (2026-09-23)
- [x] Mutating preflight 11/11 on the stem-loaded disposable set (2026-09-23)
- [x] Disposable set saved (`.runtime/investor-demo-audio/KENN_Live12_Demo_Rehearsal-1 Project/`); read-only reset copy kept as `KENN_Live12_Demo_RESET Project/` (2026-09-23)
- [x] Ten-run non-mutating script gate on the stem-loaded set: 10/10, 130 prompts, slowest 398.6 ms (2026-09-23)
- [x] UI Apply token mismatch fixed (browser JSON number formatting) (2026-09-23)
- [x] Chat route sends demo steps 6, 8, 9, 10, 15, 16 to the Live gateway; history scoped to session (2026-09-23)
- [x] History undo labels follow the real undo rules (pan/focus now "undoable") (2026-09-23)
- [x] Current Project card shows the selected track as focus and the full key ("C Major") (2026-09-23)
- [ ] Chat parser cannot return a pan to centre ("Pan the Synth center.")
- [x] UI starts a fresh session on every page load, so change history only covers the visible chat (2026-09-23)
- [ ] `kenn/speech/voice_copilot.py` simulates voice input (hard-coded sentence, invented +120 ms latency); label or remove before anyone demos it as real
- [ ] AbletonOSC `view.py` `get_selected_track` raises when a return/master track is selected (1.2 s timeout in KENN)
- [x] Chat undo marks the reverted card "Reverted" and removes its Undo button (2026-09-23)
- [x] A refused stale undo shows a neutral "Not undone … Nothing changed" note, never Apply (2026-09-23)
- [ ] Plain statements typed into chat get unrelated knowledge answers: retrieval rates them "high" confidence, so this needs a statement-vs-request check in the chat pipeline (after the demo; runbook forbids typing talk lines)
- [x] Low-end finding shows whole hertz ("44 Hz") (2026-09-23)
- [ ] Ten consecutive complete 20-step rehearsals (reset, recovery drill, projector layout, 8–12 min timing): **1/10** (run 1 passed 9m11s, 2026-09-23)
- [ ] Fix AbletonOSC `get_selected_track` crash when a return/master track is selected
- [ ] Push local commits (awaiting owner go-ahead; triggers the public mirror)

Latest automated baseline: `1410 passed, 5 skipped, 4 warnings` for the backend;
18/18 frontend tests and the production build pass. The 13-prompt
non-mutating script gate passed 10/10 against real AbletonOSC, and a bounded
two-step mutation recipe passed 10/10 with exact restoration.

Safe handoff: Ableton is stopped on the tracked reset fixture
`assets/demo/KENN_Live12_Demo.als`. The disposable
`.runtime/investor-demo-audio/KENN_Live12_Demo_Rehearsal.als` exists, is still
byte-identical to the reset fixture, and has no imported stems. Verify the Live
window URL points to that `.runtime` copy before any confirmation-bound change.

### Transport decision: OSC inside, MCP outside

OSC remains the KENN-to-Live transport because AbletonOSC supplies the actual
in-DAW endpoint and low-latency local control/readback semantics. MCP is useful
for advertising KENN's tools to agents and external clients, but it does not
replace the Live-side bridge or KENN's proposal, readback, receipt, and exact-
undo logic. The MCP facade can wrap the safe KENN service; OSC still performs
the final Live hop.

---

## Demo Context — Why This Plan Exists

This build is targeting a live demonstration to investors. That changes priorities in specific ways:

**What investors need to see:**
1. KENN controlling Ableton Live in real time — voice/text command → visible, audible result in the DAW
2. Conversational intelligence — not just commands, but understanding ("How does my mix sound?", "What did you change?", "Make it warmer")
3. The safety model — confirmation before execution, exact undo, readback verification. This is a differentiator, not a limitation: "KENN won't break your session"
4. Audio intelligence unique to KENN — mix analysis, masking detection, arrangement advice. No other AI assistant has this
5. Reliability — zero crashes, zero wrong actions, zero "sorry I can't do that" on the demo script

**What this means for the build:**
- Every demo-path feature must be **bulletproof on the scripted flow**, not just passing tests. That means a rehearsed demo script with a known Live session, tested end-to-end before every showing.
- Error handling must be graceful everywhere — no stack traces, no silent failures, no confusing error messages. If something is outside KENN's capability, the response must be honest and articulate ("I don't have a verified mapping for Wavetable's filter yet — I can adjust volume, pan, and the devices I've been qualified on").
- Latency matters. Command → audible result should be under 1 second. The audience is watching the DAW react.
- The frontend must look professional. Investors judge products by their surface. The Vue frontend needs to be polished enough that it doesn't undermine the technology behind it.
- A **pre-flight check script** must exist that verifies the entire demo environment (Live connected, OSC responsive, server healthy, index loaded, all demo commands parse correctly) before walking into the room.

**What we don't need for the demo:**
- Full device coverage (11 profiles + a focused expansion to the demo-relevant devices is enough)
- LLM active mode (shadow mode collecting data is the honest, impressive story — "we're building the data flywheel to promote the model safely")
- Production deployment infrastructure
- Multi-user, multi-session

---

## Current State — Honest Assessment

### What works today

KENN has a real, proven control chain from chat to Ableton Live:

```
server.py command route
  → handle_command() in live_command.py (2574 lines)
    → fresh topology snapshot from Live via OSC (UDP 11000/11001)
      → parse_request() deterministic regex parser (live_intent.py, 1539 lines)
        → typed proposal with confirmation token
          → live_action_service.py apply (4083 lines)
            → live_executor.py dispatch
              → fresh-read verification (raw + display string)
                → durable receipt → exact undo
```

This chain has been live-qualified against real Ableton sessions. Every mutation is verified by readback, every action is undoable, every proposal requires explicit confirmation. The safety model is mature and correct.

**Wired actions that work end-to-end (live-verified):**

| Family | Actions | Notes |
|--------|---------|-------|
| Mixer | `set_volume`, `set_pan`, `set_mute`, `set_solo` | Production-ready |
| Track ops | `create_midi_track`, `create_audio_track`, `create_return_track`, `rename_track` | No undo for track creation |
| Devices | `insert_device`, `set_device_parameter`, `remove_device` | Readback + exact undo verified (EQ Eight, Compressor, Auto Filter, Saturator, Hybrid Reverb, Echo) |
| EQ | `set_eq_band_gain`, `set_eq_band_tuning_gain` | EQ Eight only, band must resolve |
| Sends | `set_send` | Wired and tested |
| Batch | `gain_stage_tracks`, `group_tracks` | Implemented, test suite coverage |

**Evidence-backed device unit profiles (11 profiles, 7 devices):**

| Device | Parameter | Mapping | Calibration |
|--------|-----------|---------|-------------|
| Auto Filter | Resonance | linear | 0-100% |
| Auto Filter | Frequency | log | 20-20kHz |
| Compressor | Threshold | table | 20-point measured calibration (-57.2 to +6.0 dB) |
| Saturator | Drive | linear | -36 to +36 dB |
| Drum Buss | Drive | linear | 0-100% |
| Hybrid Reverb | Dry/Wet | linear | 0-100% |
| Echo | Dry Wet | linear | 0-100% |
| Glue Compressor | Attack | discrete | 7 steps (0.01-30 ms) |
| Glue Compressor | Ratio | discrete | 3 steps (2/4/10) |
| Roar | Drive | linear | 0-48 dB |
| Roar | Dry/Wet | linear | 0-100% |

Each profile was confirmed by reversible real-Live probes. The `display_to_raw()` and `raw_to_display()` functions in `device_units.py` handle three mapping strategies: linear interpolation, logarithmic (for frequency knobs), and piecewise-linear table interpolation (for non-linear controls like Compressor Threshold).

### What doesn't work

**The brain is a 1539-line regex parser.** `live_intent.py`'s `parse_request()` is a deterministic pattern matcher. Every new phrasing family requires hand-coded regex. There is no:
- Anaphora ("make *it* louder")
- Correction ("no, the *other* vocal")
- Multi-turn context (the gateway is stateless per call)
- Open-ended natural language understanding

**Session Q&A is wired in server.py but not in the command path.** The `live_session_questions.py` module (144 lines) handles 7 question kinds (connection, track_count, track_identity, tempo_signature, selected_track, duplicate_names, overview). It's imported at `server.py:77` and called at `server.py:674` via `_maybe_handle_live_inspection()`. But the September 21 qualification showed 7/8 session Q&A failures through the chat surface — the routing between the inspection path and the normal chat path has gaps.

**The LLM planner exists but is switched off.** A complete shadow/active LLM planning system is built into `live_command.py`:
- `LLM_COMMAND_SYSTEM_PROMPT` (lines 63-153) instructs the model to return structured JSON plans
- `_llm_planner_snapshot()` (lines 700-761) enriches Live snapshots with parameter profiles for model context
- `_generate_llm_plan()` (lines 764-838) calls the configured LLM with schema validation and one retry
- `validate_llm_plan()` (lines 180-270+) enforces field exclusivity, action allowlisting, and recursive recipe validation
- Shadow mode (lines 2319-2330) logs LLM plans alongside deterministic results without affecting execution

All of this is gated behind `KENN_LIVE_LLM_ENABLED` (env var, default off). The runtime provider is Ollama (local, `http://127.0.0.1:11434/v1`) with a fallback to `gpt-4o-mini`. The LoRA pipeline targets `Qwen/Qwen2.5-1.5B-Instruct` as the base model.

The contract gate in `run_kenn_command_pilot.py` (lines 33-56) requires 100% schema acceptance AND 100% deterministic-interpretation match on holdout, and even then `live_activation_allowed` is hardcoded `False` with three further human requirements. The gate is correctly paranoid but has **zero real data flowing through it** — it can't be evaluated or improved until shadow mode runs daily.

**Parameter coverage is ~11 profiles out of thousands.** Musicians' requests are dominated by devices KENN can't honestly touch yet. The qualification tooling (`qualify_ableton_live_device.py`, `qualify_ableton_live_mutations.py`, `qualify_ableton_live_recipe.py`) works and is semi-automated, but each new profile requires a human-in-the-loop session with Live open.

**The audio analysis intelligence is unreachable from chat.** KENN has substantial audio analysis capability already built:
- `audio_analysis.py` (749 lines): stdlib-only WAV analysis with FFT, spectral peaks, 5-band energy, 40-band LTAS, pink-noise reference, clipping/mono/masking/harshness detection
- `arrangement_doctor.py`: timeline segmentation (INTRO/VERSE/BUILDUP/DROP/BRIDGE/OUTRO), energy curves, transition automation recipes (HPF sweeps, pre-drop cutouts, impact enhancers)
- `mix_doctor.py`: session-level mix analysis via `get_latest_report()` and `audit_session()`
- Stem masking analysis via `stem_masking_context_turn` and `attach_stem_masking_evidence`

These are imported in `server.py` (lines 404, 526-527, 903-911) but none are wired into the conversational chat surface. A producer can't ask "how does my low end sound?" and get KENN's analysis back through the assistant.

**The retrieval/knowledge system crashes without a built index.** `chat_retrieval.py`'s `_load_index_bundle()` loads `chunks.jsonl` and `terms.json` from the active version directory. If the index hasn't been built, `/api/ask` hits a `SystemExit` from `load_chunks`. The index is built from Training_Data_Notes via BM25 (with optional embedding when the all-MiniLM ONNX model is present), but this build step is not automatic.

---

## The Core Thesis

**KENN's bottleneck is integration, not invention.**

The codebase contains:
- A proven, safe control chain to Ableton Live
- A complete LLM planner with shadow mode, validation, and contract gating
- Session Q&A with 7 question kinds and tests
- Audio analysis with spectral, masking, and arrangement intelligence
- A retrieval knowledge base with hybrid BM25/embedding search
- A LoRA fine-tuning pipeline with corpus generation and evaluation
- 1,487 test files across backend, OSC, packages, and tooling
- A Vue 3 + TypeScript frontend with Pinia state management
- MCP transport with facade and stdio client

Most of this intelligence **can't talk to each other through the chat surface.** The work ahead is wiring, qualifying, and trusting — not building from scratch.

---

## Phase 1 — Make It Conversational

**Duration:** 1-2 weeks  
**Goal:** KENN answers questions about the Live session, remembers what it did, and starts learning from real usage via LLM shadow mode.  
**Evidence of completion:** All 8 qualification matrix-A questions pass through the real chat route; "What did you change?" returns grounded answers from the receipts journal; shadow mode produces its first weekly divergence report.

### 1.1 Fix Session Q&A Routing

**Problem:** `live_session_questions.py` handles 7 question kinds but the qualification showed 7/8 failures through the chat surface. The module is called from `server.py:674` via `_maybe_handle_live_inspection()`, but this only triggers when the request hits the inspection route — not when it goes through the normal command path in `handle_command()`.

**Current flow (broken):**
```
User asks "How many tracks do I have?"
  → server.py routes to /api/ask (chat) or /api/ableton (command)
    → if /api/ableton: _maybe_handle_live_inspection() → answer_live_session_question() ✓
    → if /api/ask: goes to chat pipeline → retrieval → no session awareness ✗
    → if routed to handle_command() directly: no session Q&A check ✗
```

**Target flow:**
```
User asks "How many tracks do I have?"
  → handle_command() checks session Q&A FIRST (read-only early return)
    → answer_live_session_question() returns grounded answer ✓
  → Falls through to intent parsing only if Q&A returns None
```

**Implementation:**

In `live_command.py`'s `handle_command()`, add session Q&A as the first check before intent parsing. This is architecturally correct because:
- Session questions are read-only (no mutations, no proposals)
- The `answer_live_session_question()` function already returns `None` for non-questions, making the fallthrough clean
- It uses the same `LiveActionService` snapshot mechanism as the command path

```python
# Early in handle_command(), before parse_request():
from kenn.core.live_session_questions import answer_live_session_question

session_answer = answer_live_session_question(command, service=service)
if session_answer is not None:
    return {
        "status": "ok",
        "route": "ableton_command",
        "answer_mode": "session_question",
        "changed": False,
        **session_answer,
    }
```

**Testing:**
- Extend `test_live_session_questions.py` beyond its current 3 tests to cover all 7 question kinds through the `handle_command()` path
- Re-run the 8 matrix-A qualification questions and archive receipts under `docs/research/results/`
- Verify that non-question commands still fall through correctly (the existing `test_unrelated_chat_is_not_hijacked` test covers this pattern)

**Files to modify:**
- `apps/backend/src/kenn/core/live_command.py` — add session Q&A early return
- `apps/backend/src/kenn/tests/test_live_session_questions.py` — extend to command-path integration

### 1.2 Add Change History from Receipts

**Problem:** Producers ask "What did you change?" or "Undo everything" and KENN has no answer. The receipts journal exists and is durable (every mutation writes a receipt with proposal ID, action, before/after values, and timestamp), but there's no reader or answer path.

**What exists:**
- `live_action_service.py` maintains a receipts journal (every `apply()` call writes a receipt)
- Receipts contain: proposal_id, action, track, device, parameter, before_value, after_value, timestamp, undo_available
- The journal survives server restarts (file-backed)
- Exact undo is already implemented per-receipt (identity-bound, verified revert)

**Implementation:**

Create `describe_recent_changes()` in `live_action_service.py` that reads the journal and returns a structured summary:

```python
def describe_recent_changes(self, limit: int = 10) -> dict:
    """Summarize the N most recent mutations from the receipts journal."""
    recent = self._journal[-limit:]
    if not recent:
        return {
            "status": "no_changes",
            "answer": "I haven't made any changes to this session yet.",
            "changed": False,
        }
    
    lines = []
    for r in reversed(recent):
        lines.append(f"- {r['action']} on {r['track']}: "
                     f"{r.get('before_display', '?')} → {r.get('after_display', '?')} "
                     f"({'undoable' if r.get('undo_available') else 'not undoable'})")
    
    return {
        "status": "inspected",
        "answer": f"Here are my last {len(recent)} changes:\n" + "\n".join(lines),
        "changes": recent,
        "changed": False,
    }
```

Wire this into the session Q&A system by adding a `change_history` kind to `_question_kind()` in `live_session_questions.py`:

```python
# In _question_kind():
if re.search(r"\b(what did you|changes?|history|undo)\b.*\b(change|do|made|make)\b", q, re.I):
    return "change_history"
```

**Testing:**
- Unit test with a seeded journal: verify correct rendering, limit, empty journal, undo status
- Integration test through `handle_command()`: "What did you change?" returns journal summary
- Verify "undo everything" is correctly classified as a change_history question, not an action

**Files to modify:**
- `apps/backend/src/kenn/core/live_action_service.py` — add `describe_recent_changes()`
- `apps/backend/src/kenn/core/live_session_questions.py` — add `change_history` kind
- `apps/backend/src/kenn/tests/test_live_session_questions.py` — add journal-backed tests

### 1.3 Enable LLM Shadow Mode

**Problem:** The LLM planner has zero real data flowing through it. The contract gate can't be evaluated or improved without real-world divergence data. The 48-seed / 576-synthetic-row LoRA corpus measures schema fidelity, not language coverage.

**What exists (fully built, switched off):**

1. **System prompt** (`LLM_COMMAND_SYSTEM_PROMPT`, `live_command.py:63-153`): Instructs the model to return a single JSON object with schema `kenn.ableton_llm_plan.v1`. Actions limited to the same set the deterministic parser handles. Model receives the full Live snapshot enriched with parameter profiles.

2. **Shadow infrastructure** (`live_command.py:2311-2330`): When `KENN_LIVE_LLM_MODE=shadow`, the LLM plan is generated and compared against the deterministic parser's intent, but the deterministic intent always controls execution. The comparison is logged in metadata.

3. **Validation** (`validate_llm_plan`, `live_command.py:180-270+`): Checks schema version, field exclusivity (e.g. `steps` only on `recipe`, `clarification` only on `clarify`), action allowlist, recursive recipe validation, snapshot-grounded track/clip indices.

4. **Provider config** (`llm_rewrite.py`): Default provider Ollama (`http://127.0.0.1:11434/v1`), fallback `gpt-4o-mini`. Per-task model override via `KENN_LLM_MODEL_COMMAND`.

**Implementation:**

This is primarily configuration and observation, not code:

1. **Install Ollama on the dev machine** if not present, pull a suitable model (Qwen2.5-7B-Instruct or similar — larger than the 1.5B LoRA base, small enough for local M-series inference)
2. **Set environment variables:**
   ```bash
   export KENN_LIVE_LLM_MODE=shadow
   export KENN_LLM_MODEL_COMMAND=qwen2.5:7b-instruct
   ```
3. **Use KENN normally for a week.** Every command will generate a shadow LLM plan alongside the deterministic parse, logged in metadata.
4. **Create a shadow analysis script** (`tooling/scripts/analyze_shadow_logs.py`) that reads the shadow comparison logs and produces a weekly report:
   - Total commands processed
   - Schema acceptance rate (did the model return valid JSON?)
   - Deterministic match rate (did the model agree with the regex parser?)
   - Divergence samples (where did they disagree, and who was right?)
   - Novel phrasings the model handled but the regex missed
   - Failure modes (hallucinated track names, invented actions, wrong parameter values)

**The shadow data is the foundation for everything in Phases 2 and 3.** Without it, the contract gate has no signal, the LoRA fine-tuning has no real-world distribution to learn from, and there's no evidence base for trusting the model with execution.

**Acceptance criteria:**
- Shadow receipts appear in the metadata of every command processed
- First weekly divergence report exists with real data
- No shadow processing affects the user-facing execution path (the deterministic parser always wins in shadow mode)

**Files to modify:**
- New: `tooling/scripts/analyze_shadow_logs.py`
- Config only: environment variables on the dev machine

### 1.4 Fix Retrieval Index Auto-Build

**Problem:** `/api/ask` crashes with `SystemExit` when the retrieval index hasn't been built. The knowledge base side of the assistant is completely blocked.

**What exists:**
- `chat_retrieval.py:35`: `_load_index_bundle()` loads `chunks.jsonl` and `terms.json` from the active version directory
- `kenn.retrieval.index_store.active_version_dir` manages versioned index directories
- The index is built from Training_Data_Notes via BM25 (with optional all-MiniLM ONNX embedding)
- `/api/admin/reload-index` endpoint exists for manual rebuilds (`server.py:1108`)

**Implementation:**

1. **Graceful degradation:** Change `_load_index_bundle()` to return empty collections instead of raising `SystemExit` when no index exists. The chat pipeline should still work with reduced quality (no retrieval context) rather than crashing.

2. **Auto-build on startup:** In `server.py`'s initialization, check if an active index version exists. If not, trigger an index build from Training_Data_Notes (BM25-only, no model download needed). This is the same operation the `/api/admin/reload-index` endpoint performs.

3. **Startup log:** Print the index state (version, chunk count, whether embeddings are available) at server start so operators know what's loaded.

**Files to modify:**
- `apps/backend/src/kenn/core/chat_retrieval.py` — graceful degradation
- `apps/backend/src/kenn/server.py` — auto-build check on startup

---

## Phase 2 — Expand What It Can Do

**Duration:** 2-3 weeks  
**Goal:** KENN can operate on the most-requested devices, gives mix advice grounded in actual audio analysis, and handles common multi-step workflows.  
**Evidence of completion:** 20+ device profiles qualified; mix-doctor advice reachable from chat; `/api/ask` works without manual index builds.

### 2.1 Device Mapping Sprint

**Problem:** 11 profiles across 7 devices means KENN can't honestly touch most of what producers ask about. The honest answer "I don't have a verified mapping for that" is correct behavior but poor coverage.

**What exists:**
- Semi-automated qualification tooling (`qualify_ableton_live_device.py`) that drives reversible probes via KENN's HTTP companion endpoints
- Three mapping strategies (linear, log, table) already implemented in `device_units.py`
- A proven workflow: the September 21 session qualified 3 new mappings in one evening

**Target devices (priority order based on producer request frequency):**

| Priority | Device | Parameters | Mapping Type | Estimated Effort |
|----------|--------|-----------|-------------|-----------------|
| 1 | **Utility** | Gain, Width, Mid/Side | linear | 1 session (fix known endpoint-floor defect at 0 dB) |
| 2 | **EQ Eight** | Band Frequency, Band Q | log, linear | 1 session (extends existing EQ Eight gain profile) |
| 3 | **Compressor** | Attack, Release, Ratio, Knee | table or discrete | 1-2 sessions (non-linear knobs need measured tables) |
| 4 | **Limiter** | Gain, Ceiling | linear | 1 session (fix known exact-name resolution edge) |
| 5 | **Delay** | Dry/Wet, Feedback, Time | linear, discrete | 1 session |
| 6 | **Reverb** | Dry/Wet, Decay, Size | linear | 1 session |
| 7 | **Auto Pan** | Amount, Rate | linear | 0.5 session |
| 8 | **Gate** | Threshold, Return, Hold | table | 1 session |
| 9 | **Corpus** | Dry/Wet, Resonance | linear | 0.5 session |
| 10 | **Wavetable** | Filter Frequency, Resonance | log, linear | 1 session |

**Process per device:**

1. Open Live with a session containing the target device
2. Run `qualify_ableton_live_device.py` — it resolves the parameter by Live's own name, applies a test value, verifies readback, restores via confirmed inverse
3. Review the probe transcript and approve the calibration data
4. Add the new `DeviceUnitProfile` to `EVIDENCE_BACKED_PROFILES` in `device_units.py`
5. Add corresponding test cases to `test_device_units.py` (round-trip conversion accuracy)
6. Archive the qualification receipt under `docs/research/results/`

**Target:** 20+ profiles covering the top 10 devices. This is ~8-10 evening sessions with Live open, producing verified receipts for each new mapping.

### 2.2 Wire Mix Doctor into Chat

**Problem:** KENN has a substantial audio analysis engine that producers can't reach through the assistant. The `audio_analysis.py` module (749 lines) performs spectral analysis, masking detection, and generates findings with confidence scores and suggested listening tests. The `arrangement_doctor.py` segments timelines and generates transition recipes. The `mix_doctor.py` provides session-level analysis. None of this is accessible from the conversational chat surface.

**What exists:**
- `audio_analysis.py` — FFT, spectral peaks, 5-band energy, 40-band LTAS, pink-noise reference comparison, clipping/mono/masking/harshness detection. Each finding includes confidence, severity, evidence, and a `suggested_listening_test`.
- `mix_doctor.py` — `get_latest_report()` and `audit_session()` for session-level analysis
- `arrangement_doctor.py` — timeline segmentation, energy curves, transition automation recipes
- `stem_masking_context_turn` and `attach_stem_masking_evidence` in server.py imports
- Mix review pipeline via `audio_analysis.mix_review.mix_review` (imported at `server.py:404`)

**Implementation:**

Add a `mix_advice` question kind to the session Q&A system. When a producer asks "How does my mix sound?" or "Check my low end" or "Any masking issues?", route to the mix doctor:

1. **Extend `_question_kind()` in `live_session_questions.py`** with mix/masking/analysis patterns
2. **Create `mix_advice_from_session()` in a new `live_session_advice.py`** that:
   - Captures audio from the current Live session (if available via the existing stem export path)
   - Runs `audio_analysis.py`'s `analyze_wav()` on the capture
   - Formats the findings as conversational advice with evidence
   - Returns structured advice with severity, confidence, and suggested listening tests
3. **Fall back to arrangement-level advice** when no audio capture is available:
   - Use `arrangement_doctor.py`'s `analyze_timeline()` on the session's clip/scene structure
   - Provide structural feedback ("Your intro is 16 bars — consider whether that's too long for streaming platforms")

**Critical constraint:** This must be advice, not execution. KENN presents findings with evidence and suggested listening tests. It does not automatically apply corrections. The existing proposal/confirmation boundary stays intact — if a producer wants to act on advice ("OK, cut 3dB at 200Hz"), that goes through the normal command pipeline with confirmation.

**Files to modify:**
- New: `apps/backend/src/kenn/core/live_session_advice.py`
- `apps/backend/src/kenn/core/live_session_questions.py` — add `mix_advice` kind
- `apps/backend/src/kenn/core/live_command.py` — route mix advice through the session Q&A early return

### 2.3 Qualify Multi-Step Recipes

**Problem:** The recipe system (`parse_natural_recipe` in `live_command.py:2203+`) exists and is tested, but coverage is limited. Multi-step workflows like "add a compressor to the vocals and set the threshold to -20dB" require both `insert_device` and `set_device_parameter` to execute in sequence.

**What exists:**
- `validate_llm_plan()` supports recursive recipe validation (1-3 steps)
- `qualify_ableton_live_recipe.py` qualification script for two-step recipes
- The executor handles `apply_batch_proposal` for gain staging and grouping

**Implementation:**

1. **Define the 10 most common multi-step patterns** from producer workflows:
   - Insert device + set parameter(s)
   - Gain stage multiple tracks
   - Create send + set send level
   - Insert EQ + set band gains
   - Insert compressor + set threshold + set ratio
   - Rename track + insert device
   - Solo track + capture analysis + unsolo
   - Group tracks + rename group

2. **Qualify each pattern** using `qualify_ableton_live_recipe.py` with real Live sessions

3. **Add recipe patterns to the deterministic parser** so common multi-step requests work without the LLM

4. **Ensure the LLM planner's recipe validation** covers all qualified patterns (the `validate_llm_plan` recursive check already exists; verify coverage)

**Files to modify:**
- `apps/backend/src/kenn/core/live_intent.py` — add multi-step regex patterns
- `apps/backend/src/kenn/core/live_command.py` — recipe execution integration
- `tooling/scripts/qualify_ableton_live_recipe.py` — run for each new pattern

---

## Phase 3 — Trust the Model

**Duration:** 2-4 weeks  
**Goal:** The LLM planner is promoted from shadow to active-with-confirmation, giving KENN real natural language understanding inside the existing safety envelope.  
**Evidence of completion:** LLM planner handles open-ended phrasing with ≥95% acceptance rate on natural-language holdout; multi-turn context works; continuous regression catches regressions before they ship.

### 3.1 Staged LLM Promotion

**Problem:** The contract gate (`run_kenn_command_pilot.py:33-56`) requires 100% schema acceptance and 100% deterministic match on holdout, and `live_activation_allowed` is hardcoded `False`. The gate is correctly paranoid but there's no path from shadow to active.

**The promotion ladder:**

```
OFF (current)
  ↓ Set KENN_LIVE_LLM_MODE=shadow
SHADOW (Phase 1.3)
  — Observes only. Deterministic parser always wins.
  — Collect ≥500 shadow comparisons over ≥2 weeks.
  ↓ When: schema acceptance ≥ 98%, deterministic match ≥ 90%
PROPOSE-WITH-CONFIRM
  — LLM plan shown to user as "I think you want X — confirm?"
  — Deterministic parser still executes if user confirms.
  — LLM divergences logged for review.
  ↓ When: ≥1000 proposals, user acceptance ≥ 95%, zero safety violations
ACTIVE-WITH-FALLBACK
  — LLM plan executes if validated, with deterministic as fallback.
  — Any validation failure falls back to deterministic.
  — All executions still require user confirmation (existing token system).
```

**Implementation:**

1. **Extend `_model_contract_gate`** with staged thresholds:
   ```python
   PROMOTION_THRESHOLDS = {
       "shadow_to_propose": {
           "min_comparisons": 500,
           "min_days": 14,
           "schema_acceptance_pct": 98,
           "deterministic_match_pct": 90,
       },
       "propose_to_active": {
           "min_proposals": 1000,
           "user_acceptance_pct": 95,
           "safety_violations": 0,
       },
   }
   ```

2. **Add a natural-language holdout set** distinct from synthetic variants. Sources:
   - Real shadow-mode divergence samples (novel phrasings the regex missed)
   - Transcripts from actual producer sessions (ask-to-record workflow)
   - Music production forums: how producers actually phrase requests
   
   The current 48-seed corpus shares the same label distribution across all synthetic variants. A natural holdout must include:
   - Incomplete sentences ("louder vocals")
   - Colloquial phrasing ("crank the bass", "turn it up a bit")
   - Ambiguous requests ("make it bigger")
   - Multi-intent sentences ("solo the drums and turn up the reverb send")
   - Corrections mid-sentence ("set the volume to— actually the pan")

3. **Track promotion state durably** — a JSON file alongside the shadow logs recording current stage, when it was entered, and the evidence that qualified it.

**Files to modify:**
- `apps/backend/src/kenn/core/live_command.py` — staged mode logic
- `tooling/scripts/run_kenn_command_pilot.py` — promotion threshold checks
- New: `tooling/data/natural_holdout.jsonl` — natural-language test corpus

### 3.2 Multi-Turn Context

**Problem:** The command gateway is stateless per call. Producers can't say "make it louder" (referring to the last thing discussed) or "no, not that one" (correcting a misresolution). Proposals already carry `session_id` but there's no conversation state.

**Implementation:**

Add a bounded session context to `live_command.py`:

1. **Session memory** — a per-session ring buffer (last 10 exchanges) tracking:
   - What track/device was last discussed
   - What action was last proposed/executed
   - Whether the last proposal was confirmed or rejected
   - The current "topic" (the entity the producer is talking about)

2. **Anaphora resolution** — before parsing, resolve pronouns and implicit references:
   - "it" → last discussed track/device
   - "that" → last proposed action target
   - "louder/softer/more/less" without a target → last discussed parameter
   - "again" → repeat last action
   - "undo" without target → undo last executed action (already supported via receipts)

3. **Correction handling** — detect correction patterns and re-parse:
   - "no, the other one" → re-resolve with exclusion of last match
   - "I meant track 3" → override the track resolution
   - "not the compressor, the EQ" → override the device resolution

This sits between the user input and `parse_request()` — a context-aware preprocessor that enriches the command string before the parser sees it. The parser itself doesn't need to change.

**Files to modify:**
- New: `apps/backend/src/kenn/core/session_context.py` — ring buffer + anaphora resolution
- `apps/backend/src/kenn/core/live_command.py` — context enrichment before parsing

### 3.3 Continuous Regression

**Problem:** The qualification process is excellent but episodic. There's no continuous harness that catches regressions between sessions.

**What exists:**
- 1,317 passing backend tests
- Qualification scripts that drive real Live probes
- Golden benchmark runner at `tooling/evaluation/benchmark/run_golden_benchmark.py`
- Multiple benchmark scripts (audio analysis, chat, masking, mix review, native kernels, MLX)

**Implementation:**

1. **Nightly fixture test** — a script that:
   - Opens a known Live session (the 5-track fixture, once it exists)
   - Runs the top 20 most common command patterns
   - Verifies readback on every mutation
   - Confirms undo restores the original state
   - Produces a pass/fail report with timing data

2. **SLO tracking** — define and measure:
   - Command-to-response latency: p95 ≤ 500ms (already met in single-session measurements)
   - Verified execution rate: ≥ 99% (mutation + readback match)
   - Undo success rate: 100% (revert matches original state exactly)
   - Session Q&A accuracy: 100% (grounded in Live snapshot, no hallucination)

3. **Shadow divergence alert** — if the LLM shadow mode shows a >10% divergence rate increase week-over-week, flag for review before promoting the model.

**Files to modify:**
- New: `tooling/scripts/nightly_regression.py`
- New: `tooling/scripts/slo_report.py`

---

## Phase 4 — Product Surface

**Duration:** 2-4 weeks (can overlap with Phase 3)  
**Goal:** KENN feels like a polished studio assistant, not a command-line tool.  
**Evidence of completion:** The Vue frontend provides a responsive chat experience; the knowledge base answers Ableton workflow questions; generative features (MIDI/AudioGen) are accessible through proposals.

### 4.1 Frontend Chat Experience

**What exists:** A Vue 3 + TypeScript SPA (`apps/frontend/`) with Vite, Vue Router, Pinia state management with persistence, vue-i18n for internationalization. Source structure: `App.vue`, `api/`, `components/`, `composables/`, `views/`, `router/`, `styles/`, `locales/`, `mocks/`, `utils/`. Tests use Vitest.

**Work:**
- Connect the frontend to the session Q&A and change history endpoints
- Display proposals with confirmation/rejection UI (not just text responses)
- Show receipt history (what KENN has done, with undo buttons)
- Display mix advice findings with severity indicators and suggested listening tests
- Show device parameter state visually (current value, range, what KENN can control)

### 4.2 Knowledge Base

**What exists:** The retrieval pipeline uses hybrid BM25 + embedding search over Training_Data_Notes. The `/api/ask` route serves knowledge-grounded answers. The `/api/admin/reload-index` endpoint rebuilds the index.

**Work:**
- Curate the Training_Data_Notes corpus for Ableton-specific knowledge (effects chains, mixing techniques, arrangement patterns, genre conventions)
- Add Live device documentation (what each parameter does, typical ranges, common use cases)
- Build the embedding index with the all-MiniLM ONNX model for semantic search
- Wire knowledge retrieval into the mix advice path (when KENN suggests "try cutting at 200Hz", link to the knowledge base entry on low-end mixing)

### 4.3 Generative Features (Preview-Approve-Insert)

**What exists:**
- AudioGen capabilities in-tree (the Audio_Too lineage)
- MIDI generation capability
- The proposal/confirmation machinery

**Work:**
- "Generate a drum pattern for this section" → MIDI generation → proposal with audio preview → confirm → insert as clip
- "Create an ambient pad" → AudioGen → proposal with audio preview → confirm → insert as audio clip
- These go through the same proposal/confirmation/undo boundary as everything else — no unsupervised generation

---

## Phase 5 — Demo Readiness

**Duration:** 1 week (after Phases 1-2 are complete; can overlap with Phases 3-4)  
**Goal:** A rehearsed, bulletproof investor demo with zero failure modes on the scripted path.  
**Evidence of completion:** The demo script runs end-to-end 10 times consecutively with zero errors; the pre-flight check passes on cold boot; the full demo fits in 8-12 minutes.

### 5.1 Demo Script — The Narrative

The demo tells a story: a producer working in Ableton Live with an AI assistant that understands their session, controls the DAW safely, and gives intelligent mix advice. The script should hit these beats:

**Act 1 — "KENN knows your session" (2 min)**
1. Open Ableton Live with the demo session (a polished 8-16 track mix — real music, not test tones)
2. "How many tracks do I have?" → KENN answers from the live snapshot
3. "What's selected?" → Grounded answer
4. "Describe this session" → Overview with track names, tempo, time signature
5. "Any duplicate track names?" → Demonstrates awareness of the session topology

**Act 2 — "KENN controls the DAW safely" (3 min)**
6. "Turn up the vocals 3dB" → Proposal with confirmation → visible fader move in Live → readback
7. "Pan the synth hard left" → Same flow, visible panner move
8. "Add an EQ Eight to the bass" → Device insertion, visible in Live's device chain
9. "Boost 3dB at 200Hz on the bass EQ" → Parameter change with verified readback
10. "Undo that" → Exact revert, visible and audible
11. "What did you change?" → Change history from receipts journal

**Act 3 — "KENN understands audio" (2 min)**
12. "How does my low end sound?" → Mix analysis with spectral findings, masking candidates, suggested listening tests
13. "Check the vocals for clipping" → Targeted analysis with confidence and severity
14. Show the findings in the frontend with severity indicators

**Act 4 — "The safety model" (2 min)**
15. "Delete track 3" → KENN refuses destructive operations (explains why)
16. "Set the master volume to maximum" → KENN flags this as potentially dangerous, asks for confirmation
17. Show the confirmation token system — nothing executes without explicit approval
18. Show the receipts journal — full audit trail of every action
19. Show exact undo — every action is reversible

**Act 5 — "Where we're going" (1 min, narrative only)**
20. LLM shadow mode running — building the data flywheel to move from regex parsing to natural language understanding
21. The qualification pipeline — semi-automated device profiling, expanding coverage with evidence
22. The LoRA fine-tuning pipeline — training a local model on real usage data
23. Generative features on the roadmap — MIDI generation, AudioGen, all through the same safety envelope

### 5.2 Demo Session Fixture

Create a purpose-built Ableton Live session for the demo:

- **8-16 tracks** across a real mix: drums, bass, synth, vocals, FX sends, master
- **Named tracks** with clear, readable names (not "Audio 1", "Audio 2")
- **Devices already loaded** on key tracks: EQ Eight on bass, Compressor on drums, Reverb on a send — so KENN can show parameter control immediately
- **A deliberate mix issue** for the analysis demo: slightly hot low end, a near-clipping peak, a mono compatibility issue — things KENN's analysis will catch and articulate
- **No copyrighted material** — use original production or royalty-free stems
- **Save as a template** so it can be restored to a known state before every demo

### 5.3 Pre-Flight Check Script

Create `tooling/scripts/demo_preflight.py` that verifies the entire demo environment:

```
KENN Demo Pre-Flight Check
═══════════════════════════
[✓] Ableton Live connected (OSC ping < 100ms)
[✓] Demo session loaded (8 tracks detected, expected names match)
[✓] Server healthy (all routes responding)
[✓] Retrieval index loaded (chunk count > 0)
[✓] DAW control enabled (KENN_ALLOW_DAW_CONTROL=1)
[✓] Session Q&A working (track count returns correct number)
[✓] Device control working (EQ Eight on bass resolves correctly)
[✓] Audio analysis working (test WAV analyzes without error)
[✓] Undo system working (set+revert round-trip succeeds)
[✓] Frontend reachable (HTTP 200 on localhost)
[✓] Latency check (command round-trip < 500ms)

11/11 checks passed — ready for demo
```

Each check should be individually runnable and produce a clear pass/fail with the failure reason. The full suite should complete in under 30 seconds.

### 5.4 Error Handling Hardening

Audit every code path on the demo script for graceful degradation:

- **OSC timeout:** If Live doesn't respond within 2 seconds, return "Ableton Live isn't responding — check the connection" instead of a stack trace
- **Device not found:** "I can see the track but I can't find that device on it — here's what I can see: [device list]"
- **Parameter out of range:** "That value is outside the safe range for [parameter]. The range is [min] to [max]."
- **Unknown command:** "I'm not sure what you're asking. I can help with: [capability list]" — never a raw parse failure
- **Server error:** Any unhandled exception in the command path should be caught and returned as a structured error with a human-readable message

The principle: **no demo attendee should ever see a stack trace, a raw error code, or a silent failure.** Every failure mode has a sentence-level English response.

### 5.5 Latency Optimization

Profile the command path end-to-end and optimize for sub-1-second visible response:

- **OSC round-trip:** Measure snapshot fetch time. If > 200ms, investigate UDP socket reuse, snapshot caching (with staleness check), or partial snapshot (only the tracks relevant to the command)
- **Parse time:** The regex parser should be < 5ms. If it's slow, profile and optimize the hot patterns.
- **Readback verification:** This is the safety guarantee and cannot be skipped, but it can be parallelized — verify while sending the response, not before.
- **Frontend update:** The frontend should optimistically show "executing..." while the readback verifies, then confirm. The perceived latency is command → visible fader move, not command → verified response.

**Target latency budget:**
| Step | Budget |
|------|--------|
| Parse + plan | < 50ms |
| OSC snapshot | < 200ms |
| Execution | < 100ms |
| Readback verification | < 200ms |
| Frontend update | < 100ms |
| **Total** | **< 650ms** |

### 5.6 Frontend Polish for Demo

The Vue frontend needs to be demo-grade, not developer-grade:

- **Clean, professional layout** — no debug panels, no raw JSON, no developer tools visible
- **Chat interface** with clear message bubbles: user commands, KENN responses, proposals with confirm/reject buttons, receipts with undo buttons
- **Status bar** showing: Live connection status (green/red), current session name, track count, last action timestamp
- **Mix advice panel** that displays findings with severity badges (green/amber/red), confidence percentages, and "Try this" listening suggestions
- **Smooth animations** on state changes — fader values updating, devices appearing, undo animations
- **Dark theme** that matches Ableton's aesthetic (dark greys, accent colours for severity levels)
- **Responsive** enough to look good on a projector or large screen (the demo context)

### 5.7 Demo Rehearsal Protocol

Before every investor showing:

1. **Cold boot test:** Restart everything (Live, KENN server, frontend) and run the pre-flight check
2. **Full script run:** Execute the entire demo script top to bottom, verify every response
3. **Recovery test:** Deliberately break something (kill the server mid-command, disconnect OSC) and verify graceful recovery
4. **Reset:** Restore the demo session to its template state
5. **Final pre-flight:** Run the check script one more time
6. **Time the run:** The demo should fit in 8-12 minutes including natural pauses for explanation

---

## Risk Register

| Risk | Impact | Mitigation |
|------|--------|-----------|
| LLM hallucinate track/device names | Executes wrong action | `validate_llm_plan()` already checks indices against snapshot; readback verification catches mismatches post-execution |
| Device parameter mapping wrong | Incorrect sound change | Every mapping is probe-verified with readback; exact undo available; the honest "I don't have a verified mapping" response is the default |
| Shadow mode latency affects command response time | Sluggish UX | Shadow runs async (doesn't block the deterministic response); local Ollama inference adds ~200-500ms in background |
| Retrieval index missing on fresh install | `/api/ask` crashes | Phase 1.4 fixes this with graceful degradation + auto-build |
| Producer gives ambiguous command | Wrong interpretation | The existing `clarify` action in the LLM planner asks for clarification; the deterministic parser refuses ambiguous inputs rather than guessing |
| Multi-turn context window grows unbounded | Memory pressure | Ring buffer capped at 10 exchanges; conversation state is per-session, not global |
| **Demo: Live crashes or freezes** | Dead demo | Pre-flight check verifies connection; demo session is a known-good template restored before each showing; recovery script reconnects within 5 seconds |
| **Demo: Off-script question from audience** | KENN gives unexpected response | The demo operator sticks to the script for live execution; off-script questions are answered verbally ("great question — that's on the roadmap") rather than typed into KENN live |
| **Demo: Slow/laggy response** | Loses audience confidence | Latency budget enforced (< 650ms end-to-end); pre-flight includes latency check; disable shadow mode during demo if it adds visible delay |
| **Demo: Frontend looks broken** | Undermines credibility | Frontend tested on the exact projector/screen setup before the meeting; dark theme, no debug panels, responsive layout verified |
| **Demo: Undo doesn't restore exactly** | Safety story falls apart | Undo round-trip is part of the pre-flight check; the demo script's undo step is rehearsed and verified every time |
| **Demo: Audio analysis returns nothing useful** | Intelligence story is empty | Demo session has deliberate mix issues (hot low end, clipping peak, mono problem) that KENN's analysis is known to catch; verified in rehearsal |

---

## Success Metrics

After all four phases, KENN should be measurable against these:

### Product Metrics (long-term)

| Metric | Target | How Measured |
|--------|--------|-------------|
| Command vocabulary | 20+ devices, 50+ parameters | Count of qualified profiles in `device_units.py` |
| Session Q&A accuracy | 100% on the 8 matrix questions | Qualification receipt re-run |
| LLM schema acceptance | ≥ 98% on natural-language holdout | Shadow divergence report |
| Command latency (p95) | ≤ 500ms | SLO report from nightly regression |
| Verified execution rate | ≥ 99% | Nightly regression pass rate |
| Undo success rate | 100% | Nightly regression undo verification |
| User confirmation acceptance | ≥ 95% (model proposes correctly) | Tracked in propose-with-confirm stage |
| Mix advice coverage | 5+ finding types (masking, mono, clipping, harshness, balance) | Integration test |
| Knowledge base recall | Top-3 retrieval relevance ≥ 80% for Ableton queries | Benchmark against curated test queries |

### Demo-Specific Metrics (gate before any showing)

| Metric | Target | How Measured |
|--------|--------|-------------|
| Pre-flight pass rate | 11/11 checks green | `demo_preflight.py` |
| Demo script success | 20/20 steps complete, zero errors | Full rehearsal run |
| Demo script timing | 8-12 minutes | Timed rehearsal |
| Cold boot to ready | < 60 seconds | Restart + pre-flight |
| Command → visible DAW response | < 1 second | Observed during rehearsal |
| Error message quality | 100% human-readable (no stack traces, no raw codes) | Deliberate fault injection on every demo-path command |
| Recovery from failure | < 10 seconds to usable state | Kill server mid-demo, time to reconnect |
| Consecutive clean runs | ≥ 10 in a row | Run demo script 10x before showing |
| Frontend visual quality | No debug artifacts, no layout breaks on projector | Tested on actual display hardware |
| Audience Q&A preparedness | Scripted answers for 20 likely investor questions | Written FAQ document reviewed |

---

## Appendix A — Key File Locations

| Component | Path | Lines |
|-----------|------|-------|
| Command handler | `apps/backend/src/kenn/core/live_command.py` | 2574 |
| Intent parser | `apps/backend/src/kenn/core/live_intent.py` | 1539 |
| Action service | `apps/backend/src/kenn/core/live_action_service.py` | 4083 |
| Session Q&A | `apps/backend/src/kenn/core/live_session_questions.py` | 144 |
| Device units | `apps/backend/src/kenn/core/device_units.py` | 193 |
| Audio analysis | `apps/backend/src/kenn/core/audio_analysis.py` | 749 |
| Arrangement doctor | `apps/backend/src/kenn/core/arrangement_doctor.py` | — |
| Mix doctor | `apps/backend/src/kenn/core/mix_doctor.py` | — |
| Chat retrieval | `apps/backend/src/kenn/core/chat_retrieval.py` | — |
| Server | `apps/backend/src/kenn/server.py` | ~3200 |
| LLM rewrite config | `apps/backend/src/kenn/core/llm_rewrite.py` | — |
| MCP facade | `apps/backend/src/kenn/core/mcp_facade.py` | — |
| MCP stdio | `apps/backend/src/kenn/core/mcp_stdio.py` | — |
| OSC bridge | `apps/backend/src/kenn/ableton_osc_bridge.py` | — |
| AbletonOSC integration | `integrations/ableton-osc/` | — |
| Qualification: device | `tooling/scripts/qualify_ableton_live_device.py` | — |
| Qualification: mutations | `tooling/scripts/qualify_ableton_live_mutations.py` | — |
| Qualification: recipe | `tooling/scripts/qualify_ableton_live_recipe.py` | — |
| LoRA corpus builder | `tooling/scripts/build_kenn_command_corpus.py` | — |
| LoRA trainer | `tooling/scripts/train_kenn_command_lora.py` | — |
| LoRA pilot | `tooling/scripts/run_kenn_command_pilot.py` | — |
| LoRA evaluator | `tooling/scripts/evaluate_kenn_command_lora.py` | — |
| Shadow analysis | `tooling/scripts/analyze_shadow_logs.py` | (new) |
| Frontend | `apps/frontend/` | Vue 3 + TypeScript |
| Tests | `apps/backend/src/kenn/tests/` | 1487 files total |

## Appendix B — Environment Variables

| Variable | Default | Purpose |
|----------|---------|---------|
| `KENN_LIVE_LLM_ENABLED` | off | Master LLM gate |
| `KENN_LIVE_LLM_MODE` | off | `off` / `shadow` / `active` |
| `KENN_LLM_MODEL_COMMAND` | (from provider) | Model for command planning |
| `KENN_LLM_MODEL` | (from provider) | Default model for all tasks |
| `KENN_ALLOW_DAW_CONTROL` | off | Master DAW write gate (403 when off) |
| `AUDIO_TOO_DEV` | off | Development mode |

## Appendix C — Existing Qualification Evidence

All qualification receipts from the 2026-09-21 session are archived under:
`products/kenn/docs/research/results/qual-glm-2026-09-21-raw/` (12 probes)

Key reports:
- `products/kenn/docs/reports/KENN_ABLETON_GLM_QUALIFICATION_2026-09-21.md`
- `products/kenn/docs/plans/KENN_GLM_ROADMAP_2026-09-21.md`
- `products/kenn/docs/research/KENN_GLM_GAP_MATRIX_2026-09-21.md`
