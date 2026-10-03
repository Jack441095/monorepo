# HTTP checkpoint ownership, 3 October 2026

Code commit: `f267c4bf`.

A cancelled or replaced HTTP revision could still replace the next turn's listening checkpoint. An old checkpoint reply could clear or rate the newer checkpoint. Both storage operations now run through the existing request-owner lock on `/api/ask` and `/kenn/api/ask`. A storage operation already in progress finishes before cancellation can revoke its owner; subsequent operations from the revoked turn are skipped. Other chats and current turns retain their checkpoint behavior.

Exact files:

- `apps/backend/src/kenn/server.py`: guard incoming checkpoint consumption and outgoing revision checkpoint attachment.
- `apps/backend/src/kenn/tests/test_http_checkpoint_ownership.py`: 36 HTTP regressions using temporary SQLite storage, including four concurrent cancellation cases.
- `apps/backend/src/kenn/tests/test_stream_request_delivery.py`: move the checkpoint test stub's cancellation to the preceding request boundary. Production checkpoint storage does not re-enter the owner lock.

## Verification

Commands ran from `products/kenn`, on Fake Live, with fresh caches and one CPU-heavy job at a time.

```sh
KENN_LIVE_BACKEND=fake PYTHONPATH="apps/backend/src:tooling" apps/backend/.venv/bin/python -m pytest -q --tb=short -p no:randomly apps/backend/src/kenn/tests/test_http_checkpoint_ownership.py -o cache_dir=/private/tmp/kenn-http-checkpoint-red3-20261003
```

Before the fix: 16 failed and 16 passed in 1.45 s. Failures reproduced the two stale writes only for cancelled/replaced same-chat turns. Four concurrency cases were added afterward. An initial broader run exposed a test stub invalidating its own owner while inside the storage lock; that fixture was corrected before the final runs.

```sh
KENN_LIVE_BACKEND=fake PYTHONPATH="apps/backend/src:tooling" apps/backend/.venv/bin/python -m pytest -q --tb=short -p no:randomly apps/backend/src/kenn/tests/test_http_checkpoint_ownership.py apps/backend/src/kenn/tests/test_stream_request_delivery.py apps/backend/src/kenn/tests/test_stream_cancel_work.py apps/backend/src/kenn/tests/test_answer_upgrades.py apps/backend/src/kenn/tests/test_server_smoke.py -o cache_dir=/private/tmp/kenn-http-checkpoint-scoped3-20261003
```

Scoped result: 340 passed in 6.50 s. Temporarily removing the incoming guard produced 14 failures and 22 passes in 1.33 s; removing the outgoing guard produced six failures and 30 passes in 1.37 s. Each mutation ran the 36 checkpoint cases with its own fresh cache. Source was restored before the full suite.

```sh
KENN_LIVE_BACKEND=fake PYTHONPATH="apps/backend/src:tooling" apps/backend/.venv/bin/python -m pytest -q --tb=short -p no:randomly apps/backend/src/kenn/tests -o cache_dir=/private/tmp/kenn-http-checkpoint-full-20261003
```

Full result: 3983 passed, 12 skipped, five warnings and one pre-existing failure in 86.10 s. The failure is `test_personal_path_gate.py::test_the_shipped_tree_has_no_personal_path_or_remote_host`; historical findings are not copied here. `git diff --cached --check` passed before the code commit.

## Research and limits

The [broader research](../research/KENN_PRODUCT_AND_OPEN_SOURCE_RESEARCH_2026-10-02.md#scoped-context-and-jobs) requires persistence to retain request ownership. This closes the checkpoint gap identified in the [HTTP shortcut receipt](KENN_C2_SUPERSEDED_HTTP_SHORTCUTS_2026-10-03.md). The lock covers checkpoint storage and pure text classification, without model generation or network delivery. It does not undo a completed write or shortcut action, retire service proposal tokens, abort inference or close the final-check/network-write race. Knowledge payload and stream checkpoint guards already existed.

The [speed research](KENN_SPEED_RESEARCH_2026-10-03.md) remains an experiment shortlist. This change supplies no measured decode-speed gain. The cap and brief-style experiments stay disabled pending Jack's decision; grounding, thinking, output ceiling and keep-alive residency remain unchanged. No model files, dependencies, private audio, model prose or index rebuild were added.

C1, C2 and C3 stay unticked. The 70% accepted-within-15-s gate has not passed on both surfaces with Live open. Memory pressure and audio dropouts remain for Jack's scheduled soak.
