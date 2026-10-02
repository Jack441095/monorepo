# A2 route map: who owns each write and request path — 2 October 2026

Working record for A2 in [KENN_PLAN.md](../../KENN_PLAN.md). It is a source-read inventory
(two read-only passes over the tree, a direct trace of the ambient guardian, and the fixes listed
below), not a runtime trace. Every bypass or duplicate owner it found has a fixture and a fix; the
open list at the bottom holds observations that are not write bypasses.

## Owners

- Production HTTP is the stdlib handler in `apps/backend/src/kenn/server.py`. `run_ux_backend.py`
  and `app_entry.py` both serve it.
- `routes/fastapi_app.py` is a smaller alternate ASGI app, documented as not route-parity.
  Several frontend routes 404 there, and its `/api/ask` skips the stdlib pre-routes. We left that
  as documented; making it parity is a separate decision.
- Every Live write goes through `core/live_action_service.py` (`consume_confirmation`, a token bound
  to the exact proposal plus an idempotency key). HTTP applies also check
  `action_allowed("daw_control")`. The read found no entry point (voice, plugin handoff, MCP,
  frontend, background threads) that writes without a proposal and a confirmation.

## Duplicate owners found and closed (each has its own receipt)

| Path | What was wrong | Receipt |
| --- | --- | --- |
| `/api/feedback` | FastAPI said "Feedback recorded." for any rating and stored nothing | [feedback single owner](KENN_FEEDBACK_SINGLE_OWNER_2026-10-02.md) |
| Live apply routes, `confirmation_token` vs `confirm_token` | Nine apply sites read only one spelling | [token alias](KENN_CONFIRMATION_TOKEN_ALIAS_2026-10-02.md) |
| FastAPI `/api/live/command` | Separate copy of the command logic | [command owner](KENN_FASTAPI_LIVE_COMMAND_OWNER_2026-10-02.md) |
| OSC undo | Two copies, one in `server.py` | [undo owner](KENN_OSC_UNDO_SINGLE_OWNER_2026-10-02.md) |
| Session Doctor remediate | Posted to a route neither server has, so it could never have worked | [doctor closed](KENN_DOCTOR_REMEDIATION_CLOSED_2026-10-02.md) |
| Batch parameter changes | A missing `track_index` was planned against track 0 | [batch track index](KENN_BATCH_TRACK_INDEX_2026-10-02.md) |
| Agent-tool writes | Receipts returned to the model but never journaled, so Undo could not find them | [autonomous tool receipts](KENN_AUTONOMOUS_TOOL_RECEIPTS_2026-10-02.md) |
| `tool_auto_remediate_session_issues` | Applied a batch through a self-confirming method; no caller | [dead write paths](KENN_AUTONOMOUS_DEAD_WRITE_PATHS_2026-10-02.md) |

## Open, with source symbols

None of these is a write bypass. They are carried forward, not fixed.

- Stdlib ask pre-routes (`server.py`, the Live inspection, MIDI generation and Live command
  shortcuts after `begin_turn`) have no `is_current_turn` check. They answer synchronously to the
  request that asked, so the requester always gets its own reply; the only residue is a pending
  proposal token for a card the client may have dropped, which expires. Judged low risk, not fixed.
- No concurrent-stream guard: `answer_upgrades.begin_turn` is last-writer-wins.
- `core/mcp/live_proposals.py` writes a `proposal_action` field that nothing in the backend reads.
- Still caller-less but kept: `LiveExecutor` (`core/live_executor.py`, five test files use it) and the
  `execute_autonomous` / `execute_batch_autonomous` pair in `live_action_service.py` (no caller outside
  the service since `tool_auto_remediate_session_issues` was removed). `run_agent_loop` and the
  closed-loop session methods are reachable only from each other and one test.
- Remaining track-0 fallbacks in snapshot reads: `core/session_doctor.py`,
  `core/subjective_translator.py` (and the dead `LiveExecutor`).
- `demo_feedback` is not in the tree, so `/api/feedback` answers 503 on both servers. Restoring the
  module or routing to `save_session_feedback` is Jack's call.
- `/kenn/api/admin/reload-index` has no auth; the default bind is 127.0.0.1.
- Frontend `MaskingRadar.vue` calls the remediate route that now answers 410.
- `core/ambient_guardian.py` (traced): read-only status for `/api/guardian/status`, `/api/guardian/events`
  and the session-intelligence handler. It never writes to Live. Its staged proposal comes from
  `AcousticCalibrationLoop()` built with no recipe service, so the token it shows (`guardian_...` or
  `calib_...`) is a hash made locally and never issued, and the confirmation gate would reject it.
  The only consumer found, `apps/legacy-web/app.js` `renderGuardianPill`, reads status and
  advisories and ignores the proposal. Advisory only, so left alone; do not wire an Apply button to it
  without issuing a real proposal.
- Not verified: shared default orchestrator sessions, the Thursday fallback to the legacy engine,
  unused `revoke_confirmation` imports in `routes/daw_routes.py`.

## Limits

- Source reading can miss dynamic dispatch. The "no unconfirmed write" statement is about the
  entry points inspected, not a proof.
- Nothing here was run against real Live.
