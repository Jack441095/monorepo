# Generated MIDI clip owner, 3 October 2026

Code commit: `6db2815` on `fix/review-critical-2026-10-02`; baseline `90530a0`.

`Handler._maybe_handle_midi_generation` in `server.py` filed a clip proposal under
the owner `"chat"` whenever `/api/ask` arrived without a usable session ID. Every
unnamed caller therefore shared one owner, so one could dismiss or apply another's
pending clip. Reproduced on fake Live through the real `/api/ask` route: an anonymous
"Write a 4-bar chord progression in D minor" returned a registered token and
`requires_confirmation: true`.

The handler now answers "A KENN session ID is required to prepare a clip." with no
proposal or token when the owner is empty. Missing, blank, non-string and over-128
IDs all reach it as empty after the route's existing normalization. A named chat
(padding stripped) still gets its proposal, owned by that chat alone.

Files, relative to `apps/backend/src/kenn`: `server.py`,
`tests/test_midi_generation_chat.py` (two tests, five anonymous forms plus a named
owner whose token another chat and the old `chat` owner cannot revoke).

## Verification

Environment: Claude Cloud container, throwaway venv outside the repo (see the
[autonomous token receipt](KENN_A2_AUTONOMOUS_CONFIRMATION_TOKENS_2026-10-03.md)),
fake Live only. The five anonymous cases failed before the change (proposal issued
under the shared owner) and pass after.

Scoped command, from `products/kenn`:

```sh
KENN_LIVE_BACKEND=fake PYTHONPATH='apps/backend/src:tooling' python -m pytest -q --tb=short -p no:randomly apps/backend/src/kenn/tests/test_midi_generation_chat.py apps/backend/src/kenn/tests/test_orchestrator_autonomous.py apps/backend/src/kenn/tests/test_orchestrator_session_ownership.py apps/backend/src/kenn/tests/test_confirmation_cancellation_routes.py apps/backend/src/kenn/tests/test_session_clear_revokes_pending_confirmations.py apps/backend/src/kenn/tests/test_http_checkpoint_ownership.py -o cache_dir="$(mktemp -d /tmp/kenn-cloud-scoped-XXXXXX)"
```

Result: **165 passed, 1 warning.** Full backend: **4014 passed, 137 skipped, 10 failed**,
the same ten as on a clean checkout (nine cloud-environment gaps plus the known
`test_personal_path_gate.py` failure). Not comparable to the Mac's counts.

## Limits

Other fallbacks were read and left alone: `plugin_handoff.py`'s `plugin-local` keys
plugin parameter state and issues no confirmation; the `default_session` defaults
in `autonomous_agent.py` tool functions and `live_executor.py` were not traced to
a public route here. No real Live, model or Live-open run; C1, C2 and C3 stay open.
