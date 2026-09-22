# KENN Roadmap to Full GLM Coproducer Capacity — 2026-09-21

Source evidence: `docs/reports/KENN_ABLETON_GLM_QUALIFICATION_2026-09-21.md`,
audit JSON `docs/research/results/kenn_audit_ableton_glm_qualification_2026-09-21.json`,
gap matrix `docs/research/KENN_GLM_GAP_MATRIX_2026-09-21.md`.
Priorities: P0 (blocker) → P1 (dependable operator) → P2 (intelligence/generation) → P3 (adaptive/hardening).
Critical path: P0-1 → P0-2 → P0-3 → P1-1 → P1-2 → P2-1 → P2-2 → P4-1.

Item template (all fields present, condensed): problem / impact / evidence /
architecture / owner / contracts / deps / steps / tests / Live acceptance /
metric / latency / safety / rollback / effort / risk / priority / done-evidence.

## Phase 0 — Immediate blockers (P0)

### P0-1 MCP mutation qualification (Control Deck transport)
- Problem: chat mutations run on legacy OSC; the selectable MCP backend is read-only by construction and its provider cannot even start here.
- Impact: producer cannot use the supported transport for any write; OSC fallback is the only path.
- Evidence: `ControlDeckMCPBackend` write fail-closed verified; no ARM64 Node runtime; no server build; `Control_Deck` script installed but idle.
- Architecture: install Node 24 ARM64 + provider build; add a write-allowlist behind the existing qualification gate; reuse proposal/confirmation/readback/receipt layers unchanged.
- Owner: `core/live_backend.py`, `core/live_backend_factory.py`, `core/mcp_stdio.py`.
- Contracts: `kenn.live_backend_capabilities.v1` (write[] populated only post-qualification); per-tool JSON envelopes pinned.
- Deps: provider repo access; disposable 5-track fixture (§9 of report).
- Steps: (1) provider install docs + version pin; (2) read-parity suite MCP-vs-OSC on identical sets; (3) enable ONE write (device insert) with full receipt/undo; (4) expand per device.
- Tests: `test_live_backend_mcp_writes.py` (fake MCP server), allowlist/garbage-response/timeout cases.
- Live acceptance: full matrix B+C on MCP transport with readbacks; OSC parity diff empty.
- Metric: 100% of matrix B/C pass on MCP; zero substitutions.
- Latency: propose ≤300 ms p50; confirmed execution ≤1.5 s incl. readback.
- Safety: writes stay disabled until the gate suite passes on real Live; default-deny preserved.
- Rollback: env switch back to `osc`; MCP selection fails closed (already does).
- Effort: M (1–2 wks). Risk: medium (provider behavior unknown). Priority: P0. Done: MCP matrix receipts in `docs/research/results/`.

### P0-2 Session Q&A + change history on the command gateway
- Problem: 7/8 understanding questions and `What did you change?` clarify-fail (matrix A/D).
- Impact: producer cannot ask what is in the set or review what KENN did.
- Evidence: matrix A records; no session-Q&A code path exists.
- Architecture: read-only intent actions (`describe_set`, `count_tracks`, `tempo_signature`, `selected_track`, `duplicate_names`, `change_history`) answered from the fresh snapshot + receipt journal; never writes.
- Owner: `core/live_intent.py`, `core/live_command.py`.
- Contracts: `kenn.ableton_intent.v1` (new inspect actions); answers cite snapshot fields.
- Deps: none. Steps: parser patterns → resolvers → answer templates → history from journal.
- Tests: intent + command tests per question; history test with seeded journal.
- Live acceptance: matrix A 8/8 pass against readbacks; history matches journal.
- Metric: 8/8 + history exact. Latency: ≤250 ms (single snapshot). Safety: read-only; no proposals. Rollback: revert commit. Effort: S (days). Risk: low. Priority: P0. Done: matrix-A re-run receipts.

### P0-3 Restart/persistence semantics + docs
- Problem: proposals die on restart (correct) but the behavior is undocumented; journal durability unadvertised.
- Impact: producer confusion after companion restarts.
- Evidence: restart test (409 fail-closed; journal persists).
- Architecture: document + surface “re-propose after restart” in answers; add journal-backed `pending` listing (read-only).
- Owner: `core/live_receipt_journal.py`, command answers. Deps: none. Steps: docs + answer text + test.
- Tests: restart unit tests (exist; extend to journal listing).
- Live acceptance: restart drill script passes. Metric: documented + tested. Latency: n/a. Safety: no auto-re-execution ever. Rollback: revert. Effort: XS. Risk: low. Priority: P0. Done: drill receipts.

## Phase 1 — Dependable Ableton operator (P1)

### P1-1 Tempo + move + bypass + remove-device (exact) actions
- Problem: tempo/move/bypass missing; remove refused even with exact undo (matrix C/D).
- Impact: routine requests fail despite safe implementations existing nearby.
- Evidence: clarify/refuse records; removal executor already exists for undo.
- Architecture: tempo intent (no track binding) + `propose_tempo_action` with readback/undo; move-device order proposal with before/after chain fingerprint; bypass via Device-On param where qualified per device; user-facing removal reusing the exact removal proposal + undo payload (still confirmation-gated, still refuses fuzzy targets).
- Owner: `core/live_intent.py`, `core/live_action_service.py`, `core/live_command.py`.
- Contracts: `kenn.ableton_action_proposal.v1` extensions (action `set_tempo`, `move_device`, `remove_device`).
- Deps: P0-2 patterns. Steps: intents → proposals → executors → readbacks → undos.
- Tests: per-action propose/apply/undo/idempotency tests (fake + table-driven).
- Live acceptance: `Set tempo 124`, `Move EQ before Compressor`, `Bypass Compressor on track 2`, `Remove the effect` (exact, confirmed) with readbacks + undos.
- Metric: 4/4 with measured readbacks. Latency: ≤1.5 s executions. Safety: confirmation always; stale-chain rejection; no fuzzy removal. Rollback: revert. Effort: M. Risk: low-medium. Priority: P1. Done: receipts.

### P1-2 5-track fixture + duplicate/stale-race live drills + Utility/Limiter closure
- Problem: duplicate-name/stale-state paths unit-covered only; Utility floor and Limiter naming unresolved live.
- Impact: identity safety unproven under realistic conditions.
- Evidence: fixture gap §3/§9 of report; probe data for Utility Output (0..35 dB floor).
- Architecture: disposable fixture builder script (track names incl. duplicates, clips, pre-loaded device) + drill runner (rename/reorder/delete between propose and confirm; duplicate-targeted commands must clarify).
- Owner: `tooling/scripts/` + docs. Deps: P1-1 (move/remove needed for drills).
- Tests: drill assertions in `test_live_control_*`.
- Live acceptance: full A–H re-run on fixture; Utility reduced via Output where ≥0 dB else honest block; Limiter resolved to an exact stock name or documented absent.
- Metric: zero wrong-target writes across drills. Latency: n/a. Safety: fixture disposable; baseline diff empty at end. Rollback: n/a (docs/tooling). Effort: S–M. Risk: low. Priority: P1. Done: drill receipts.

### P1-3 Conversational context (anaphora + correction) on chat
- Problem: matrix E fully clarifies (`it`, `Make that…`, corrections).
- Impact: multi-turn workflows unusable; producer repeats full context every turn.
- Evidence: matrix E records; gateway stateless.
- Architecture: session-scoped resolver memory (last track/device/param/value per session_id, TTL-bounded, exact-identity only — never index-only); correction intent revises pending proposal or undo+reapply; all resolutions surfaced in answers (“using track 3 `3-Audio` from your last message”).
- Owner: `core/chat_context.py`, `core/live_command.py`.
- Contracts: `kenn.chat_reference.v1` (session_id → identities + timestamps).
- Deps: P0-2. Steps: memory store → resolver hooks → correction flow → expiry tests.
- Tests: scripted E-dialogue tests incl. correction and expiry.
- Live acceptance: matrix E 8/8 + correction scenario with no stray devices.
- Metric: context-retention accuracy 100% on scripted dialogues; zero cross-track leakage. Latency: +≤50 ms. Safety: references expire; never resolve across sessions; confirmations still required. Rollback: revert. Effort: M. Risk: medium. Priority: P1. Done: dialogue receipts.

## Phase 2 — Session intelligence (P2)

### P2-1 Normalized Live Set model (arrangement, roles, clips, harmony, descriptors)
- Problem: planner sees tracks/devices/mixer only; no clips/notes/sections/key/roles/descriptors (areas 4, 11–14).
- Impact: musical reasoning and generation have nothing grounded to reason over.
- Evidence: snapshot shape; gap areas 4/11/12/13/14 missing.
- Architecture: `core/live_set_model.py` building a versioned normalized model (tracks, groups, routing, clips + MIDI notes, tempo/meter, key/scale, device chains + automation refs, audio descriptors, history) from batched OSC reads with freshness stamps; read-only; Q&A and planners consume it.
- Owner: new `core/live_set_model.py` + bridge batch readers.
- Contracts: `kenn.live_set_model.v1` (JSON schema + versioning).
- Deps: P0-2, P1-2. Steps: schema → readers → builders → golden-file tests on captured snapshots.
- Tests: golden model tests; large-session perf test (200+ tracks simulated).
- Live acceptance: model dump matches a 16+ track set incl. clips/notes within tolerance; read time budget met.
- Metric: field coverage vs schema 100%; read ≤5 s on 16-track set. Latency: cached ≤250 ms. Safety: read-only; PII-free. Rollback: revert. Effort: L (3–4 wks). Risk: medium. Priority: P2. Done: model goldens + acceptance dump.

## Phase 3 — Musical reasoning (P2)

### P3-1 Grounded mix/musical advice (balance, masking, dynamics, tone, groove)
- Problem: musical requests clarify-fail; no analysis→assumption→recommendation→confirm→execute→reassess loop (area 14, MUS record).
- Impact: KENN is a control surface, not a coproducer.
- Evidence: MUS clarify record; mix-doctor/masking engines unwired.
- Architecture: wire existing engines to chat via the P2-1 model; answers follow the 10-step structure (observe → analyze → assume → recommend → propose → confidence → confirm → execute → readback → reassess); never a canned preset without project evidence.
- Owner: `core/mix_doctor.py`, masking engine, command answers.
- Contracts: `kenn.musical_advice.v1` (observations, assumptions, confidence, proposed actions).
- Deps: P2-1. Steps: engine adapters → answer composer → confidence calibration → advice tests.
- Tests: advice-on-fixture tests asserting cited evidence fields.
- Live acceptance: 5 scripted requests (busier chorus, vocal clarity, kick/bass masking, width, harsh vocal) each produce evidence-cited advice; executed ones verify readbacks.
- Metric: evidence-citation rate 100%; no generic-preset answers. Latency: advice ≤5 s. Safety: advice ≠ execution; confirmations unchanged. Rollback: revert. Effort: L. Risk: medium-high. Priority: P2. Done: advice transcripts + receipts.

## Phase 4 — Generative coproduction (P2/P3)

### P4-1 Context-aware MIDI generation/editing + AudioGen handoff (P2 priority, P3 breadth)
- Problem: generative modules unwired to chat; no preview/approve/insert/revise/provenance path (areas 15, 16).
- Impact: no coproduction beyond control.
- Evidence: gap areas 15/16 reachable-but-unwired.
- Architecture: chat-invoked generation jobs (async, progress) → preview artifacts (files + metadata) → explicit approved insertion via existing proposal/confirmation/receipt machinery → revision rounds → provenance/licensing ledger.
- Owner: `core/generative_midi.py`, audiogen modules, artifact store.
- Contracts: `kenn.generation_job.v1`, `kenn.artifact.v1` (hash, source, license, parent).
- Deps: P2-1 (context), P1-3 (multi-turn revision). Steps: job API → preview UX contract → insertion proposals → ledger.
- Tests: deterministic seeded generation tests; ledger tests; insertion round-trip tests.
- Live acceptance: generate 4-bar drum variation from set context → preview → approve → notes land in clip → undo removes them.
- Metric: insertion accuracy 100% (notes match artifact); provenance complete. Latency: job progress <30 s for 4 bars. Safety: never auto-insert; licensed-source flags. Rollback: feature-flag off. Effort: XL. Risk: high. Priority: P2 (MIDI), P3 (AudioGen breadth). Done: artifact ledger + receipts.

## Phase 5 — Adaptive producer collaboration (P3)

### P5-1 Durable project memory + opt-in preferences with isolation
- Problem: no learning, no isolation (area 20).
- Impact: every session starts from zero; no style continuity.
- Evidence: area 20 missing.
- Architecture: per-project/per-producer stores, opt-in only, correction API, export/delete; answers cite when a preference influenced a proposal.
- Owner: new `core/preference_store.py`. Contracts: `kenn.preference.v1` + isolation tests.
- Deps: P1-3. Steps: store → opt-in UX → correction → isolation audit.
- Tests: isolation (cross-project leakage) tests; correction tests.
- Live acceptance: preference (e.g., “no reverb beyond 20%”) honored and cited; deletion honored.
- Metric: 0 leakage incidents; correction applied ≤1 turn. Latency: +≤50 ms. Safety: opt-in, local-only, deletable. Rollback: wipe stores. Effort: M. Risk: medium (privacy). Priority: P3. Done: audit log.

## Phase 6 — Production hardening (P3, ongoing)

### P6-1 SLOs, registries, E2E/chaos suites, telemetry-with-privacy, installer qualification
- Problem: no SLOs, no browser-level chat E2E, no chaos coverage, installer unqualified (areas 21–25 partial).
- Impact: regressions and install failures reach producers.
- Evidence: 429-noisy bursts; manual swap window; provider install gap.
- Architecture: capability manifests + model/tool registries; Playwright chat E2E against fixture Live; chaos (kill Live mid-write, drop UDP, restart backend) with reconciliation assertions; privacy-gated telemetry; installer matrix.
- Owner: `tooling/`, CI workflows, docs. Deps: P0-1, P1-2.
- Tests: the suites themselves, run in CI where Live-less, nightly where Live-attached.
- Live acceptance: green nightly real-Live regression + chaos report.
- Metric: defined SLOs (propose p95 ≤500 ms; verified-execution rate ≥99%; undo success 100%). Latency: per SLOs. Safety: chaos only on disposable sets. Rollback: per-suite. Effort: L ongoing. Risk: low. Priority: P3. Done: dashboards + reports.
