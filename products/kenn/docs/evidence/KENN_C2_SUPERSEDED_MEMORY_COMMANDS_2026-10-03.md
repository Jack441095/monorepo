# C2 explicit memory command ownership, 3 October 2026

Code commit: `dfef29ab259cc3c2bd8455e8c1b25e8c2c217f66`.

An explicit preference save, forget or clear could change project memory after cancellation or a replacement turn, even though answer delivery was discarded. Both payload and stream shortcuts now pass their request owner to the memory evaluator. Persistence shares the cancellation lock; parsing and reads remain outside it. Commands in another chat retain their own ownership.

Exact files:

- `apps/backend/src/kenn/core/chat_answer.py`: forward request ownership to the shortcut and memory evaluator.
- `apps/backend/src/kenn/core/project_memory_advisory.py`: guard preference save, forget and clear writes.
- `apps/backend/src/kenn/tests/test_memory_request_ownership.py`: 18 payload/stream cases cover three commands, cancellation, replacement and other-chat isolation with real temporary SQLite stores and Fake Live.
- `apps/backend/src/kenn/tests/test_stream_request_delivery.py`: two shortcut test doubles accept the owner argument.

Commands ran from `products/kenn`, with Fake Live and no model calls. Each pytest run used a fresh cache directory.

```sh
KENN_LIVE_BACKEND=fake PYTHONPATH="apps/backend/src:tooling" apps/backend/.venv/bin/python -m pytest -q --tb=short -p no:randomly apps/backend/src/kenn/tests/test_memory_request_ownership.py -o cache_dir=/private/tmp/kenn-memory-owner-red-20261003
```

Before the fix: 12 failed, 6 passed in 0.64 s. The failures reproduced stale saves, forgets and clears on both surfaces. All six other-chat cases passed.

```sh
KENN_LIVE_BACKEND=fake PYTHONPATH="apps/backend/src:tooling" apps/backend/.venv/bin/python -m pytest -q --tb=no -p no:randomly apps/backend/src/kenn/tests/test_memory_request_ownership.py -o cache_dir=/private/tmp/kenn-memory-owner-mutation-20261003
```

Removing the request-owner guard caused the same 12 failures, with 6 passes in 0.37 s. The source was restored in a `finally` block before verification.

```sh
KENN_LIVE_BACKEND=fake PYTHONPATH="apps/backend/src:tooling" apps/backend/.venv/bin/python -m pytest -q --tb=short -p no:randomly apps/backend/src/kenn/tests/test_memory_request_ownership.py apps/backend/src/kenn/tests/test_stream_request_delivery.py apps/backend/src/kenn/tests/test_project_memory_stage4.py apps/backend/src/kenn/tests/test_assistant_profile_memory.py apps/backend/src/kenn/tests/test_session_memory_preferences.py apps/backend/src/kenn/tests/test_confirmation_cancellation_routes.py apps/backend/src/kenn/tests/test_answer_upgrades.py -o cache_dir=/private/tmp/kenn-memory-owner-restored-20261003
```

After restoration: 188 passed, 2 existing warnings in 3.37 s. The earlier scoped run also passed all 188 cases.

```sh
KENN_LIVE_BACKEND=fake PYTHONPATH="apps/backend/src:tooling" apps/backend/.venv/bin/python -m pytest -q --tb=short -p no:randomly apps/backend/src/kenn/tests -o cache_dir=/private/tmp/kenn-memory-owner-full-20261003
```

Full backend: 3765 passed, 12 skipped, 7 warnings and 1 pre-existing failure in 104.05 s. The failure is `test_personal_path_gate.py::test_the_shipped_tree_has_no_personal_path_or_remote_host`; its findings are not copied here. `git diff --cached --check` passed.

## Limits and research implications

This fixes persistence after request revocation. A write already holding the owner lock completes before cancellation can revoke it; cancellation does not undo earlier memory changes. The checks forbid retrieval and model generation, and Fake Live receives no writes. This slice does not stop inference or measure latency.

The [speed shortlist](KENN_SPEED_RESEARCH_2026-10-03.md) and [broader research](../research/KENN_PRODUCT_AND_OPEN_SOURCE_RESEARCH_2026-10-02.md#12-accelerating-the-fixed-qwen-models-follow-up-findings) still guide experiments, not speed claims. Decode/output length dominate the measurements. Cap and brief-style trials remain disabled pending Jack's decision, thinking is already off, and residency is unchanged. The same-Qwen3-8B MLX proposal remains unexecuted; no dependency or model asset was added. C1, C2 and C3 stay unticked, with the Live-open gate and audio/memory qualification still open.
