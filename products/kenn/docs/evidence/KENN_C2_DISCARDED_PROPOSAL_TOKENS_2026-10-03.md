# Discarded HTTP proposal tokens — 3 October 2026

Code commit: `758a88c8` (`Revoke confirmation tokens when superseded HTTP proposals are discarded`).

An HTTP shortcut can issue a confirmation token after cancellation has revoked the chat's earlier cards. The reply was discarded, but its hidden token remained usable. The delivery guard now revokes that reply's exact token for its owning session. It leaves newer cards and other chats usable.

Changed files:

- `apps/backend/src/kenn/server.py`: revoke the discarded shortcut's token before returning cancelled metadata.
- `apps/backend/src/kenn/tests/test_stream_request_delivery.py`: 32 cases covering both ask endpoints, MIDI and command proposals, cancellation/replacement timing, and chat isolation with real confirmation issuance and consumption.

## Verification

Commands ran from `products/kenn`, with fake Live and one CPU-heavy job at a time.

Red regression:

```sh
KENN_LIVE_BACKEND=fake PYTHONPATH='apps/backend/src:tooling' apps/backend/.venv/bin/python -m pytest -q --tb=line -p no:randomly apps/backend/src/kenn/tests/test_stream_request_delivery.py -k discarded_proposal_revokes -o cache_dir=/private/tmp/kenn-shortcut-token-red-20261003
```

Result before the fix: **12 failed, 20 passed, 222 deselected in 1.35 s**.

Scoped command:

```sh
KENN_LIVE_BACKEND=fake PYTHONPATH='apps/backend/src:tooling' apps/backend/.venv/bin/python -m pytest -q --tb=short -p no:randomly apps/backend/src/kenn/tests/test_stream_request_delivery.py apps/backend/src/kenn/tests/test_stream_cancel_work.py apps/backend/src/kenn/tests/test_answer_upgrades.py apps/backend/src/kenn/tests/test_confirmation_revocation.py apps/backend/src/kenn/tests/test_confirmation_replay.py apps/backend/src/kenn/tests/test_confirmation_cancellation_routes.py apps/backend/src/kenn/tests/test_session_clear_revokes_pending_confirmations.py apps/backend/src/kenn/tests/test_server_smoke.py -o cache_dir=/private/tmp/kenn-shortcut-token-scoped-pass-20261003
```

Result: **437 passed, 2 warnings in 6.75 s**. An earlier command named a nonexistent `test_confirmation.py`; it collected no tests. The command above uses the actual confirmation test files.

Full suite, required because the HTTP entry point changed:

```sh
KENN_LIVE_BACKEND=fake KENN_LLM_CACHE=0 PYTHONPATH='apps/backend/src:tooling' apps/backend/.venv/bin/python -m pytest -q --tb=short -p no:randomly apps/backend/src/kenn/tests -o cache_dir=/private/tmp/kenn-shortcut-token-full-20261003
```

Result: **4,042 passed, 12 skipped, 5 warnings, 1 pre-existing failure in 84.87 s**. The failure is `test_personal_path_gate.py::test_the_shipped_tree_has_no_personal_path_or_remote_host`, also present before this change. Diagnostic output remains private. The scoped diff check passed.

## Limits and research decision

This closes a token-ownership gap in HTTP shortcut delivery. It does not remove retained proposal records, undo an already-consumed action, abort inference, or close the interval between the final owner check and writing the reply. Engine shortcut token ownership still needs audit.

The speed shortlist remains candidate experiments from other hardware. At about 13 tok/s, 220–280 output tokens require 17–21 s of decoding. Token retirement does not demonstrate a decode-speed gain or recover the latency gate. No model run, index rebuild, dependency installation, setting change or real Live soak occurred. Output-length and brief-style trials remain disabled pending Jack's decision; keep-alive is unchanged.

C1, C2 and C3 remain unticked. The useful accepted-answer gate on both surfaces with Live open is still failed. No plan tick is claimed by this receipt.
