# KENN LLM-Controlled Ableton Build Prompt

You are the lead engineer for KENN, an Ableton Live plug-in product. Execute
this request in the existing repository while preserving unrelated user
changes.

Build the smallest honest end-to-end product slice for natural-language
Ableton control:

`user command → optional LLM JSON plan → deterministic validation → fresh
Live snapshot → exact proposal → explicit confirmation → Live write →
readback → receipt/undo`

Engineering rules:

1. Use C++ for all real-time audio work, meter computation, feature snapshots,
   plug-in UI responsiveness, local HTTP client code, and proposal display.
   Never call a network service, Python, filesystem, LLM, or blocking Live
   operation from `processBlock()`.
2. Keep Python for the local companion, RAG/knowledge retrieval, LLM provider
   adapters, session storage, and orchestration unless a benchmark proves a
   hot path belongs in C++.
3. The LLM is not trusted execution code. It may return only a typed,
   versioned JSON plan. Reject prose, unknown actions, invented track/device/
   parameter identities, destructive operations, missing values, and plans
   that do not match the current Live snapshot.
4. Route every Live mutation through `LiveActionService`. Do not add a direct
   OSC/UDP write shortcut. Require exact target identity, confirmation,
   expiry, stale-state checking, idempotency, readback, honest failure, and a
   receipt with undo information.
5. Treat “track 4” as the fourth user-visible track and show both its display
   number and internal Live index in the proposal. Never silently fall back to
   track 0.
6. Treat “add EQ on track 4” as unsupported until native device insertion has
   its own typed proposal and verified rollback. Return a clear capability
   response, never a hang and never a silent mutation.
7. Treat “reduce amplitude by 3 dB at 250 Hz” as an EQ-band request. Ask for
   missing track/device/band context, or implement it only as an atomic,
   explicitly confirmed compound proposal. Never guess a band or claim it was
   applied.
8. Keep the plug-in transparent by default. Local meters and local Mix Check
   must remain available with the companion stopped. All companion failures
   must be visible and bounded by short timeouts.
9. Add focused tests for normal commands, ambiguity, prompt injection,
   forged/expired/replayed confirmations, stale Live state, failed readback,
   and companion loss. Build the native plug-in and run the relevant tests.
10. Inspect the current worktree first and preserve unrelated changes. Do not
    use destructive git commands. Do not create a commit unless explicitly
    asked; if a commit is later requested, use a neutral message with no AI
    tags, co-authors, or generated-by wording.

Deliverables:

- a working command endpoint and C++ plug-in path;
- versioned command/plan/proposal response contracts;
- tests and build evidence;
- a short update to `KENN_LLM_CONTROLLED_ABLETON_PRODUCT_PLAN.md` recording
  what is implemented, what is intentionally unsupported, and the next
  measurable gate.

Before declaring success, verify the actual current files, build output, test
results, and—when Ableton is running—the real `KENN_Bridge` read-only path.
Report any unverified claim as unverified.
