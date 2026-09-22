# KENN Ableton Live GLM Qualification Report — 2026-09-21

Start commit: `1e2b7f6` (origin/main, PRs #22 and #23 merged — verified).
Branch: `kenn-qual-glm-eq-intent` (isolated worktree `workspace/worktrees/kenn/qual-glm`,
detached from origin/main; pre-existing dirty worktree untouched).
Machine-readable audit: `docs/research/results/kenn_audit_ableton_glm_qualification_2026-09-21.json`.
Raw receipts: `docs/research/results/qual-glm-2026-09-21-raw/`.

## Executive summary

- **Exact EQ request through KENN's real chat surface: PASS with measured Live readback.**
  “Add EQ Eight to track 3 and boost 500 Hz by 3 dB” resolved track 3 →
  index 2 `3-Audio`, inserted exactly one EQ Eight (verified device readback),
  auto-selected band 4B already at **500 Hz**, set gain to **+3.00 dB measured**
  (receipt `receipt-a3866de0…`, verified). Exact undo returned gain to
  **0.00 dB measured** and removed the device; final Live state is
  byte-identical to baseline. A +2 dB re-adjustment was likewise verified
  (2.00 dB measured).
- **Other stock effects:** Compressor Threshold −18 dB, Auto Filter cutoff
  1 kHz, Saturator Drive +4 dB, Hybrid Reverb 15%, Echo 10% — all applied
  through chat with measured display readbacks and verified undos, after
  qualifying three new evidence-backed unit mappings from reversible Live
  probes. Mixer volume/pan/mute/solo apply+undo verified. Duplicate-insert
  guard, ambiguity handling, invalid-input handling, and repeat-submission
  idempotency all behave correctly (fail closed, no wrong-track writes).
- **Repaired (4 commits):** EQ boost-direction parsing + compound-transparency,
  spoken hundreds/spelled-out units, OSC first-contact breaker starvation,
  display↔raw unit conversion on all planning paths, kHz handling.
  Regression tests added: intent (+8), command (+3 net), device-units (+5),
  bridge (+2).
- **Failed / blocked (honest, no mock-as-real):** session-understanding Q&A
  (7/8 clarify), multi-turn anaphora (“it”), tempo control, change history,
  musical-intelligence requests, Utility Gain (endpoint floor 0 dB),
  Limiter exact name, move/bypass/remove actions, `/api/ask` without a
  retrieval index (500, blocked-env), MCP mutations (read-only by design +
  provider absent), 5-track duplicate/clip fixture (not built — track
  creation has no undo).
- **GLM readiness:** dependable single-step Ableton operator for
  tracks/devices/params/mixer with receipts and exact undo (Phase 1
  partial). Session intelligence, musical reasoning, generation, and
  adaptive collaboration are missing or experimental. Highest-priority next
  milestone: **P0 — MCP mutation qualification + session Q&A/history**
  (roadmap `docs/plans/KENN_GLM_ROADMAP_2026-09-21.md`).

## 1. Starting point and isolation

- `git fetch origin` → `origin/main == 1e2b7f6aed3aa536bdab49fc3d6d312a88304fac`
  (matches the expected commit; main had not advanced).
- Merged PRs confirmed in main history: #23 `1e2b7f6` (selectable Ableton MCP
  backend), #22 `95e420d` (production hardening review).
- Clean isolated worktree created at `workspace/worktrees/kenn/qual-glm`
  (detached HEAD 1e2b7f6; path is git-ignored in the parent so the dirty
  worktree — `fixtures/cache_rt_stress/*.shm` modified, `Testing/`, `data/`,
  `website/` untracked — was never touched). No resets, no force-push.
- Commits on `kenn-qual-glm-eq-intent` (all human subjects, no AI trailers):
  `3194f0d`, `b4eb3f6`, `e5e357d`, `3dc80bb`.

## 2. Transport boundary (all values measured, nothing bypassed)

| Item | Evidence |
|---|---|
| Selected backend | `osc` — explicit fallback. MCP was requested first and evaluated, not skipped. |
| MCP backend state | `ControlDeckMCPBackend`: read-only by construction; every mutation method raises (`set_track_volume`, `set_device_parameter` verified fail-closed). No provider process exists, so no mutation could be attempted, let alone counted. |
| MCP provider identity | `ableton-control-deck`; `Control_Deck` Remote Script IS installed in Live's User Library, but no MCP server build exists locally and no ARM64 Node runtime exists (`/usr/local/bin/node` is x86_64 and fails to exec), so `KENN_LIVE_MCP_COMMAND` has no valid value. |
| Misconfiguration behavior | `create_live_backend(..., KENN_LIVE_BACKEND=control-deck-mcp)` without a command raises at startup — never silently falls back to OSC. Verified. |
| Allowlist | `ableton_status, get_live_set, get_track, list_devices, get_device_parameters`; out-of-allowlist call (`drop_tables`) rejected with `MCPTransportError`. Verified. |
| Timeout | `KENN_LIVE_MCP_TIMEOUT_SECONDS` default 8 s; offline probe fails fast with structured error. Verified with bogus command. |
| Live connection | AbletonOSC UDP 127.0.0.1:11000/11001; Ableton Live 12 Suite (PID 36389). |
| Live Set identity | Disposable default set: 4 tracks (`1-MIDI`, `2-MIDI`, `3-Audio`, `4-Audio`), 120 BPM 4/4, stopped, no devices, no clips observed. |
| Chat→orchestrator→MCP path | `POST /api/ableton/command` → `handle_command` (deterministic_snapshot_boundary, LLM disabled) → `LiveActionService` → backend client. Every mutation in this report went through this path with proposal → confirmation → execution → readback → receipt. No direct tool invocations are counted as chat proof. |
| Component versions | Worktree HEAD `3dc80bb` (over origin/main `1e2b7f6`); Python 3.13.7; AbletonOSC Remote Script (bundled); Control_Deck + KENN_Bridge scripts present in User Library (unused by tests). |
| Write gate | `KENN_ALLOW_DAW_CONTROL=1` exported only for the swap window; default-deny verified (HTTP 403 + policy message without it). |

## 3. Safety boundary

- Baseline snapshot captured before any mutation (`baseline-osc-session.json`):
  4 tracks, volumes 0.85, pans 0, unmuted/unsoloed, tempo 120, stopped.
- Operator authorized disposable testing and a companion-swap window (stale
  archive companion dropped all POSTs with empty replies and owned UDP 11001,
  so no chat/mutation could reach Live through it).
- Transport stayed stopped on every readback. Baseline restored exactly after
  every mutation via identity-bound undo; final state identical to baseline
  (verified by full session read).
- The required 5-track fixture (Drums/Bass/Synth/Vocal/FX Return, duplicate
  names, clips) was NOT built: track creation is append-only with explicitly
  no undo, so building it would permanently alter the operator's set. Recorded
  as a remaining manual step (§9). All name-based tests therefore clarify-fail
  honestly on this fixture (evidence, not gaps in the safety logic).

## 4. End-to-end matrix results

Counts: 110 machine-readable records across 4 runs (51 + 33 + 13 + 13).
Per-test rows, latencies, and notes are in the audit JSON (`record_verdicts`).

### A. Connection and session understanding — FAIL (honest)
Only narrow inspect patterns answer (`List the devices on track 3` →
“Track '3-Audio' has 0 device(s)”, 104 ms, matches readback; `What is on
track 3` likewise). “Are you connected?”, “Describe this Live Set”, “How
many tracks?”, “What is track 3?”, tempo/time-signature, selected track,
and duplicate-name questions all clarify-fail: the command gateway has no
session-Q&A capability. No wrong answers were given anywhere.

### B. Exact EQ command — PASS (real Live, measured)
Full lifecycle through the real chat surface (session `qual-glm-eq7/eq8`,
all timings recorded):
1. `Add EQ Eight to track 3 and boost 500 Hz by 3 dB.` → `insert_device`,
   track 2 `3-Audio`, confirmation-gated, nothing changed; tuning follow-up
   surfaced transparently (179 ms).
2. Confirmed → applied in 760 ms, receipt `receipt-cfc75479…`, verified,
   readback devices `[EQ Eight]`; independent session read confirms device 0
   `EQ Eight` on track 2.
3. `Boost 500 Hz by 3 dB on track 3.` → auto-selected band **4B**
   (already at 500 Hz), +3 dB, confirmed → applied (451 ms),
   receipt `receipt-a3866de0…`, verified, `readback_display 3.00 dB`.
4. Independent display readbacks: param 41 = **500 Hz**, param 42 =
   **3.00 dB** (raw 0.5083 / 3.0, min/max observed). Tolerances: exact.
5. Undo gain → verified, measured **0.00 dB**. Undo insertion (removal
   proposal) → verified, track devices `[]`. Final session == baseline.
6. Variations: spoken numbers (`On track three, boost five hundred hertz by
   three decibels` → parses, asks for band only if unresolved), `+2 dB`
   re-adjust verified at 2.00 dB, duplicate insert refused
   (“already contains EQ Eight”), `Boost 500 Hz by 3 dB.` (no track) and
   synth-referencing variants clarify-fail safely.

### C. Other stock effects — PARTIAL (all honest)
- Insert + verified undo: Compressor, Auto Filter, Saturator, EQ Eight
  (exact browser resolution confirmed by readback; no substitutions).
- Params with measured readbacks: Threshold **−18.0 dB** (raw 0.4 via new
  table), cutoff **1.00 kHz** (raw 0.5663 via new log map; kHz path),
  Drive **4.0 dB** (raw 0.5556 linear), Hybrid Reverb **15 %**, Echo
  **10 %**. Each undone with verified revert (0.00 dB / 10.0 kHz / 0.0 dB /
  50 % defaults).
- Utility: inserts exactly, but has no Gain knob — `Output` endpoint exposes
  **0..+35 dB only**, so reductions below 0 dB are impossible: blocked with
  exact cause. Limiter: no exact stock name resolves (refuses rather than
  substituting Convolution/Align/Color variants). Bypass/move/remove-device:
  unqualified or refused by the destructive-action boundary — all fail
  closed with specific messages.

### D. Mixer and transport — PARTIAL
Volume/pan/mute/unmute/solo: applied + verified + undone via receipts (all
pass). Tempo (`Set the tempo to 124 BPM`) fails closed — tempo intent does
not exist in the parser (missing capability, P1). `What did you change?`
fails — no change-history surface (P1).

### E. Multi-turn context — FAIL (safe)
The gateway is stateless per call: `it`/`that` anaphora, `Make that 2 dB
instead`, `Actually put it at 650 Hz`, correction (`No, I meant the synth`),
and undo-by-reference (`Undo the EQ work`) all clarify-fail. Nothing was
written to the wrong track or device at any point.

### F/G. Ambiguity, identity, invalid input — PASS (fail-closed)
Unknown tracks (`track 9`), unknown devices (`Phasertron`), unknown params,
out-of-range volume, band-less EQ (asks for band only where downstream
cannot resolve), and repeat submission (second confirm rejected
“already executed”) all behave correctly. Stale-state guards
(rename/reorder/delete between proposal and confirm) are code-enforced and
unit-covered; live duplicate-name races need the absent 5-track fixture.
Rate limiter (60 mutations/60 s/IP) returned 429s during unpaced scripted
runs — protective but chat-noisy; paced runs were unaffected.

### H. Undo and recovery — PARTIAL
Every applied mutation was undone through its identity-bound receipt with a
verified second readback. Restart test: pending proposals do NOT survive
backend restart (post-restart confirm → HTTP 409 fail-closed, must
re-propose); receipts persist via the JSONL journal. Live-restart and
fixture recovery remain manual steps.

### Musical intelligence — FAIL (absent surface)
`Suggest three ways to improve this mix…` clarify-fails on the command
gateway, as do all open-ended mix requests. No audio/MIDI/arrangement
reasoning is wired to chat. (Deliberate: no canned “intelligence” was
substituted; see gap matrix areas 11–15.)

### Chat quality — PARTIAL
Concise producer-facing answers; exact proposals; honest clarification;
measured (never assumed) results; no claims of hearing audio. Gaps:
`/api/ask` returns 500 without a retrieval index (blocked-env, pre-existing);
no session Q&A/history; 429s when unpaced. Proposal latency ~104–180 ms;
confirmed executions ~450–760 ms including verification.

## 5. Latency summary
110 records with per-call ms. Median ≈ low-hundreds ms; max single call
under ~2 s (insertion with browser search + verification). Rate-limit
429s only during unpaced bursts; paced (≥2 s) runs clean. Full distribution
in the audit JSON.

## 6. Defects found and repaired (all with regression tests)
- **QLM-01** EQ boost verbs unrecognized; compound insert+tune silently
  dropped tuning → verb family + sign, freq-first pattern, `follow_up`
  channel in proposal answers.
- **QLM-02** Spoken hundreds/spelled units never normalized; spacing bug
  glued words mid-sentence → hundred handling, hertz/decibel/kHz lookahead,
  spacing-preserving replacement.
- **QLM-03** Fresh breaker-enabled OSC client stayed offline forever
  (first contact + every multi-batch snapshot starved) → attempt-once
  semantics, transport-success state updates, first-contact + fast-fail
  tests. (This defect blocked the entire backend on every fresh start.)
- **QLM-04** Display-unit params compared against raw ranges on all three
  planning paths → measured table/log/linear profiles (Threshold 20-pt
  table, Filter 20 Hz–20 kHz log, Drive linear −36..+36), conversion on
  deterministic + LLM + relative (round-trip) paths, raw-domain doubles.
- **QLM-05** kHz/spelled-out units lost in device-parameter parsing →
  alternations + Hz normalization on both intent paths.
- Test-double fidelity fix: Threshold doubles moved to production raw
  domain (0.55 ↔ −12 dB, 0.0..1.0) with `raw_to_display`-backed displays.
- Full relevant suites green: 299 passed (command/intent/units/pipeline/
  action-service/backend/stdio/qualification/runner/bridge).

## 7. What was NOT repaired (by design — roadmap)
Tempo intent, change history, anaphora/memory, session Q&A, musical
reasoning, Utility floor, Limiter naming, move/bypass/remove actions,
`/api/ask` index, MCP provider + mutation qualification, 5-track fixture.
Each has a P0–P3 item with acceptance criteria in the roadmap.

## 8. Capability truth map (today, evidenced)
Production-ready: typed proposals, confirmation gating, idempotent confirm,
receipts, exact undo, readback verification, Compressor/EQ/Reverb/Echo/Auto
Filter/Saturator insert+qualified params, mixer controls, fail-closed
ambiguity/invalid handling, offline/MCP-unavailable behavior.
Tested-but-incomplete: Frequency/Gain EQ tuning (band must resolve),
relative mapped-param changes.
Implemented-but-unqualified: Control Deck MCP reads (provider absent).
Missing: §7 list. Mocked: nothing presented as real. Broken at start,
repaired: QLM-01…05.

## 9. Remaining manual steps
1. Save the disposable Live Set under a test name; build the 5-track
   fixture (Drums/Bass/Synth/Vocal/FX Return, duplicate names, MIDI+audio
   clips, one pre-loaded device) and re-run matrices A/E/F against it.
2. Toggle Live's AbletonOSC control surface (or restart Live) so the
   restored stock companion (PID 64851, new path
   `Products/Kenn/archive/…/server.py`) reconnects — it serves health OK
   but reads offline after tonight's client churn; Live itself verified
   responsive (tempo 120.0 via raw probe) and the set pristine.
3. Install ARM64 Node 24 + build the Control Deck MCP server, then run the
   MCP mutation-qualification suite (roadmap P0-1).
4. Build the chat retrieval index (`python main.py build`) to unblock
   `/api/ask`, or scope it out of the Ableton surface.
5. Review + push `kenn-qual-glm-eq-intent` (4 commits, ready, unpushed) and
   open a PR (do NOT merge without authorization).
