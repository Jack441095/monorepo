# Discarded engine transport tokens — 3 October 2026

Code commit: `a334088c` (`Revoke discarded engine transport proposal confirmations`).

The engine discarded stale play/stop shortcut replies without retiring their confirmation token. Cancellation before issuance left a new hidden token usable; replacement while the stream was suspended left an older card usable. Each existing delivery guard now revokes the exact token for its owning chat. Newer cards and other chats remain usable.

Changed files:

- `apps/backend/src/kenn/core/chat_answer.py`: retire the transport shortcut token at the payload discard guard and the three stream discard guards.
- `apps/backend/src/kenn/tests/test_stream_request_delivery.py`: 32 cases through the public answer surfaces, using actual transport proposal issuance and confirmation consumption with Fake Live. These cover play/stop, cancellation/replacement, suspension after metadata/token, and chat isolation.

## Verification

Commands ran from `products/kenn`, with one CPU-heavy job at a time.

Red regression:

```sh
KENN_LIVE_BACKEND=fake PYTHONPATH='apps/backend/src:tooling' apps/backend/.venv/bin/python -m pytest -q --tb=line -p no:randomly apps/backend/src/kenn/tests/test_stream_request_delivery.py -k discarded_engine_transport -o cache_dir=/private/tmp/kenn-engine-token-red-20261003
```

Result before the fix: **12 failed, 20 passed, 254 deselected in 0.23 s**. All failures left a discarded token consumable.

Scoped command:

```sh
KENN_LIVE_BACKEND=fake PYTHONPATH='apps/backend/src:tooling' apps/backend/.venv/bin/python -m pytest -q --tb=short -p no:randomly apps/backend/src/kenn/tests/test_stream_request_delivery.py apps/backend/src/kenn/tests/test_stream_cancel_work.py apps/backend/src/kenn/tests/test_answer_upgrades.py apps/backend/src/kenn/tests/test_confirmation_revocation.py apps/backend/src/kenn/tests/test_confirmation_replay.py apps/backend/src/kenn/tests/test_confirmation_cancellation_routes.py apps/backend/src/kenn/tests/test_session_clear_revokes_pending_confirmations.py apps/backend/src/kenn/tests/test_server_smoke.py -o cache_dir=/private/tmp/kenn-engine-token-scoped-pass-20261003
```

Result: **469 passed, 2 warnings in 6.93 s**.

Full suite, required because the shared answer entry point changed:

```sh
KENN_LIVE_BACKEND=fake KENN_LLM_CACHE=0 PYTHONPATH='apps/backend/src:tooling' apps/backend/.venv/bin/python -m pytest -q --tb=short -p no:randomly apps/backend/src/kenn/tests -o cache_dir=/private/tmp/kenn-engine-token-full-20261003
```

Result: **4,074 passed, 12 skipped, 5 warnings, 1 pre-existing failure in 84.79 s**. The failure is `test_personal_path_gate.py::test_the_shipped_tree_has_no_personal_path_or_remote_host`. Diagnostic output remains private. The scoped diff check passed.

## Limits and research decision

This closes the transport shortcut's token-ownership gap. Raw dispatch proposal paths still need audit. It does not remove retained proposal records, undo an already-consumed action, abort inference, or close the interval between the final owner check and delivery.

The deep-research speed shortlist remains experiments to measure on the M3 / 16 GB. At about 13 tok/s, 220–280 output tokens require 17–21 s of decoding. This change establishes no decode-speed gain or latency-gate recovery. No model run, index rebuild, dependency installation, setting change or real Live soak occurred. Output-length and brief-style trials remain disabled pending Jack's decision; keep-alive is unchanged.

C1, C2 and C3 remain unticked. The useful accepted-answer gate on both surfaces with Live open is still failed. No plan tick is claimed by this receipt.
