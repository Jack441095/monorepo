# C2 shortcut stream ownership, 3 October 2026

Code commit: `ad40311cc0b19922e7f400053bfaf2a63d2edf2f`.

A greeting, status reply or transport proposal stream could pause after metadata, then emit stale answer text after cancellation or a replacement turn. The shortcut now rechecks its owner after each yield. Cancellation acknowledgements still deliver their own reply because they intentionally revoke their owner. No generation or Live write was added.

Exact files:

- `apps/backend/src/kenn/core/chat_answer.py`: check shortcut ownership between stream events.
- `apps/backend/src/kenn/tests/test_stream_request_delivery.py`: 24 greeting/status/play/stop cases cover cancellation, replacement and other-chat isolation after metadata or token delivery; the existing cancellation acknowledgement test also checks its token.

Commands ran from `products/kenn`, on Fake Live, without model calls. Each pytest run used a fresh cache directory.

```sh
KENN_LIVE_BACKEND=fake PYTHONPATH="apps/backend/src:tooling" apps/backend/.venv/bin/python -m pytest -q --tb=short -p no:randomly apps/backend/src/kenn/tests/test_stream_request_delivery.py -k shortcut_stream_discards -o cache_dir=/private/tmp/kenn-shortcut-delivery-red-20261003
```

Before the fix: 16 failed, 8 passed, 70 deselected in 0.36 s. The failures reproduced stale tokens after metadata and missing discarded metadata after the last token. The eight other-chat cases passed.

```sh
KENN_LIVE_BACKEND=fake PYTHONPATH="apps/backend/src:tooling" apps/backend/.venv/bin/python -m pytest -q --tb=no -p no:randomly apps/backend/src/kenn/tests/test_stream_request_delivery.py -k shortcut_stream_discards -o cache_dir=/private/tmp/kenn-shortcut-delivery-mutation-20261003
```

Removing the new check after metadata caused 8 failures, with 16 passes and 70 deselections in 0.19 s. The original source was restored in a `finally` block before the following verification.

```sh
KENN_LIVE_BACKEND=fake PYTHONPATH="apps/backend/src:tooling" apps/backend/.venv/bin/python -m pytest -q --tb=short -p no:randomly apps/backend/src/kenn/tests/test_stream_request_delivery.py apps/backend/src/kenn/tests/test_confirmation_cancellation_routes.py apps/backend/src/kenn/tests/test_chat_status_observations.py apps/backend/src/kenn/tests/test_transport_shortcut_reasons.py apps/backend/src/kenn/tests/test_provider_cache_ownership.py apps/backend/src/kenn/tests/test_answer_upgrades.py -o cache_dir=/private/tmp/kenn-shortcut-delivery-restored-20261003
```

After restoration: 204 passed, 2 warnings in 2.21 s. The earlier scoped run also passed all 204 cases.

```sh
KENN_LIVE_BACKEND=fake PYTHONPATH="apps/backend/src:tooling" apps/backend/.venv/bin/python -m pytest -q --tb=short -p no:randomly apps/backend/src/kenn/tests -o cache_dir=/private/tmp/kenn-shortcut-delivery-full-20261003
```

Full backend: 3747 passed, 12 skipped, 7 warnings and 1 pre-existing failure in 104.21 s. The failure is `test_personal_path_gate.py::test_the_shipped_tree_has_no_personal_path_or_remote_host`; its findings are not copied here. `git diff --cached --check` passed.

## Limits and research implications

This covers delivery between shortcut stream events. Already emitted bytes cannot be retracted. It does not cancel inference, revoke an already applied action or establish ownership of every explicit-memory write. The other-chat checks use Fake Live and forbid retrieval/model calls.

The [speed research](KENN_SPEED_RESEARCH_2026-10-03.md) remains a shortlist, not a measured speed gain. Decode speed and output length dominate the existing measurements; previous cap and brief-style trials lost quality and remain pending Jack's decision. Thinking is already off. Residency stays unchanged, and the proposed same-Qwen3-8B MLX comparison has not run. No dependency or model asset was added. C1, C2 and C3 stay unticked: the Live-open accepted-answer gate and memory/audio qualification remain open.
