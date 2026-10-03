# HTTP shortcut delivery, 3 October 2026

Code commit: `57674ff0aea6a52639ef8d4fdb952c057b3897fa`.

Cancelled or replaced chat turns could still deliver HTTP shortcut replies because those exits bypassed the knowledge engine's final ownership check. The final check now covers inspection, MIDI proposals, Live command proposals, non-request replies, listening checkpoint replies, explicit tools, project analysis and mix revisions on both ask endpoints. Revoked replies return a blank cancelled envelope without a proposal or confirmation token. Current turns and other chats retain their replies.

Exact files:

- `apps/backend/src/kenn/server.py`: shared final shortcut delivery check after reply augmentation.
- `apps/backend/src/kenn/tests/test_stream_request_delivery.py`: 80 HTTP cases for the eight exits, cancellation/replacement, current turns, other chats and revocation during augmentation.

## Verification

Commands ran from `products/kenn` on Fake Live with stubbed shortcuts, one CPU-heavy job at a time and fresh pytest caches.

```sh
KENN_LIVE_BACKEND=fake PYTHONPATH="apps/backend/src:tooling" apps/backend/.venv/bin/python -m pytest -q --tb=short -p no:randomly apps/backend/src/kenn/tests/test_stream_request_delivery.py -k http_shortcut_discards -o cache_dir=/private/tmp/kenn-http-shortcut-red2-20261003
```

Before the fix: 32 failed, 32 passed, 142 deselected in 2.22 s. Only revoked same-chat turns failed.

```sh
KENN_LIVE_BACKEND=fake PYTHONPATH="apps/backend/src:tooling" apps/backend/.venv/bin/python -m pytest -q --tb=short -p no:randomly apps/backend/src/kenn/tests/test_stream_request_delivery.py apps/backend/src/kenn/tests/test_stream_cancel_work.py apps/backend/src/kenn/tests/test_answer_upgrades.py apps/backend/src/kenn/tests/test_server_smoke.py -o cache_dir=/private/tmp/kenn-http-shortcut-scoped-20261003
```

Scoped result: 304 passed in 6.56 s. Temporarily disabling the new guard produced 48 failures, 32 passes and 142 deselections in 1.90 s across the 80 shortcut cases; source was restored before the full suite.

```sh
KENN_LIVE_BACKEND=fake PYTHONPATH="apps/backend/src:tooling" apps/backend/.venv/bin/python -m pytest -q --tb=short -p no:randomly apps/backend/src/kenn/tests -o cache_dir=/private/tmp/kenn-http-shortcut-full-20261003
```

Full result: 3947 passed, 12 skipped, 5 warnings and one pre-existing failure in 85.71 s. The failure is `test_personal_path_gate.py::test_the_shipped_tree_has_no_personal_path_or_remote_host`; its historical evidence findings are not copied here. `git diff --cached --check` passed before the code commit.

## Research decisions and limits

The [broader research](../research/KENN_PRODUCT_AND_OPEN_SOURCE_RESEARCH_2026-10-02.md#scoped-context-and-jobs) separates stale delivery from stopping work. This check prevents stale HTTP delivery. It does not undo shortcut work already performed, retire pending service tokens, protect revision checkpoint writes, preempt a model, cancel a tool or abort inference. The final check and network write are separate operations; no ownership lock is held across network I/O. Stream-request shortcuts retain their existing JSON response behavior.

The [speed shortlist](KENN_SPEED_RESEARCH_2026-10-03.md) supplies experiments, not target-hardware results. No latency or decode gain was measured here. Decode remains the dominant measured cost, and the cap/brief-style experiments remain disabled pending Jack's decision. Keep-alive residency, grounding, thinking and production output ceiling stay unchanged. MLX and speculative decoding remain proposals requiring approval; no dependency, model file, index rebuild, private audio or model prose was added.

C1, C2 and C3 stay unticked. Neither surface has qualified at least 70% eligible accepted model answers within 15 s with Live open. Memory pressure and audio dropouts remain for Jack's scheduled soak.
