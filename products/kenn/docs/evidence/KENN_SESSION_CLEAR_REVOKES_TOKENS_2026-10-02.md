# Clearing a session revokes its pending Apply tokens — 2 October 2026

A3 slice. It supports [KENN_PLAN.md](../../KENN_PLAN.md). It comes from a read-only trace of project
switching and Apply/Undo against an in-flight chat, recorded below.

## Reproduced defect and changed behavior

`/api/session/clear` (stdlib `server.py` and the shared `routes/chat_routes.py` handler that FastAPI
uses) dropped the cached answer upgrades and the session memory, but not the session's pending
confirmation tokens. A chat could be cleared, the user could start over, and the old Apply card
stayed good for the rest of its 300 second window. The chat "cancel" path already calls
`revoke_session_confirmations`; the clear route now does too, in both servers. Other sessions' tokens
are untouched.

## Verification

From `products/kenn/apps/backend/src`:

```sh
../.venv/bin/python -m pytest -q -p no:randomly kenn/tests/test_session_clear_revokes_pending_confirmations.py
../.venv/bin/python -m pytest -q -p no:randomly kenn/tests
```

- Scoped: 4 cases (two routes, each with a revoke case and a leave-other-sessions-alone case). Before
  the fix the revoke case failed on both the stdlib server and FastAPI; the other-session case passed.
  After the fix all four pass, along with the 24 existing clear-route and answer-upgrade cases.
- Full backend: 3,538 passed, 12 skipped, no failures (124.42 s), the earlier 3,534 plus the four new cases.

## Findings from the trace (not changed)

All verified by reading source, none reproduced.

- No set or project identity exists anywhere in the Live action layer. The only scope key is the client's
  `session_id`. A token or an Undo receipt issued under one set can be used under another if the same
  session id is sent and the target (track index, name, value or device order) still matches. Undo's
  stale checks compare values, not which set is loaded. Adding set identity to the confirmation scope is
  a larger change and needs a decision on where the identity comes from.
- `session_context._LIVE_CONVERSATIONS` (undo links, last command) is not cleared by the clear route.
- `begin_turn` does not revoke tokens, so a proposal from a superseded turn stays applicable until it
  expires. The apply and undo routes do not look at `answer_upgrades`, and nothing serialises a Live write
  against a chat turn. Staleness protection comes from the execute-time Live state checks.
- Reasoning traces store the raw user query in SQLite under the git-ignored `chats/` directory, capped
  at 1,000 rows. Redaction of pasted audio paths was not checked. Superseded or cancelled turns still
  write a trace and bump trust scores.

## Limits

- The test proves the token is revoked and unusable, not that the frontend calls the clear route when a
  Live set changes. Whether it does was not checked.
- Nothing was run against real Live.

## Exact changed files

Paths are relative to `products/kenn`.

- `apps/backend/src/kenn/routes/chat_routes.py`: import and one call in `handle_session_clear`.
- `apps/backend/src/kenn/server.py`: the same call in the legacy clear branch.
- `apps/backend/src/kenn/tests/test_session_clear_revokes_pending_confirmations.py` (new, 4 cases).
- `docs/evidence/KENN_SESSION_CLEAR_REVOKES_TOKENS_2026-10-02.md`: this receipt.
- `KENN_PLAN.md`: A3 sub-bullet.
