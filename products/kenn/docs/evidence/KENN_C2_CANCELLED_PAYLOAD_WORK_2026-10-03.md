# C2 cancelled payload work, 3 October 2026

Code commit: `8f70af44144b1698bd9f56dcc8964c3124467245`.

Payload delivery already discarded cancelled or replaced answers, but retrieval could still start generation for a stale owner, and generation or metadata assembly could still start optional critique. The payload now checks its owner before generation; the shared critique helper checks before optional work. Model work stays outside the owner lock.

Exact files:

- `apps/backend/src/kenn/core/chat_answer.py`: check request ownership at the generation and critique entry boundaries.
- `apps/backend/src/kenn/tests/test_stream_request_delivery.py`: 48 public-payload cases covering cancellation, replacement, other-chat isolation and unbound requests after retrieval, generation and metadata assembly. Both foreground and read-only calls exercise template and stubbed model generation; read-only calls carry the owner registered by HTTP. Discarded replies preserve their session, plugin and correlation fields and report `inference_aborted: false`.

## Verification

Commands ran from `products/kenn`, on Fake Live with stubbed model calls and fresh pytest caches. No real model, index rebuild or other CPU-heavy job ran concurrently.

```sh
KENN_LIVE_BACKEND=fake PYTHONPATH="apps/backend/src:tooling" apps/backend/.venv/bin/python -m pytest -q --tb=short -p no:randomly apps/backend/src/kenn/tests/test_stream_request_delivery.py -k cancelled_payload_does_not_start -o cache_dir=/private/tmp/kenn-payload-cancel-work-red-20261003
```

Initial template-only regression: 8 failed, 8 passed in 0.62 s. Cancellation or replacement after retrieval still started generation and critique; after generation it still started critique. A first fixed run exposed four read-only fixture failures because those calls had no registered owner. The fixture was corrected to match HTTP, rather than changing read-only ownership semantics. All 16 then passed in 0.36 s; adding stubbed model cases gave 32 passes in 0.42 s.

```sh
KENN_LIVE_BACKEND=fake PYTHONPATH="apps/backend/src:tooling" apps/backend/.venv/bin/python -m pytest -q --tb=short -p no:randomly apps/backend/src/kenn/tests/test_stream_request_delivery.py -k cancelled_payload_does_not_start -o cache_dir=/private/tmp/kenn-payload-cancel-work-metadata-red-20261003
```

Adding cancellation during metadata assembly exposed 8 failures, with 40 passes in 0.48 s. The critique-entry guard brought all 48 to green in 0.41 s, using `/private/tmp/kenn-payload-cancel-work-metadata-green-20261003`.

Mutation checks removed one guard at a time and restored source bytes in a `finally` block:

```sh
KENN_LIVE_BACKEND=fake PYTHONPATH="apps/backend/src:tooling" apps/backend/.venv/bin/python -m pytest -q --tb=no -p no:randomly apps/backend/src/kenn/tests/test_stream_request_delivery.py -k cancelled_payload_does_not_start -o cache_dir=/private/tmp/kenn-payload-cancel-work-mutation-generation-20261003
KENN_LIVE_BACKEND=fake PYTHONPATH="apps/backend/src:tooling" apps/backend/.venv/bin/python -m pytest -q --tb=no -p no:randomly apps/backend/src/kenn/tests/test_stream_request_delivery.py -k cancelled_payload_does_not_start -o cache_dir=/private/tmp/kenn-payload-cancel-work-mutation-critique-20261003
```

Removing the generation guard restored 8 failures, with 40 passes in 0.53 s. Removing the critique guard restored 16 failures, with 32 passes in 0.39 s.

```sh
KENN_LIVE_BACKEND=fake PYTHONPATH="apps/backend/src:tooling" apps/backend/.venv/bin/python -m pytest -q --tb=short -p no:randomly apps/backend/src/kenn/tests/test_stream_cancel_work.py apps/backend/src/kenn/tests/test_stream_request_delivery.py apps/backend/src/kenn/tests/test_provider_cache_ownership.py apps/backend/src/kenn/tests/test_answer_upgrades.py apps/backend/src/kenn/tests/test_llm_stream_honesty.py apps/backend/src/kenn/tests/test_streamed_generation_prefix_guard.py apps/backend/src/kenn/tests/test_llm_usage_telemetry.py apps/backend/src/kenn/tests/test_chat_stream_weak_retrieval.py -o cache_dir=/private/tmp/kenn-payload-cancel-work-final-scoped-20261003
```

Final restored scoped result: 246 passed in 3.31 s.

```sh
KENN_LIVE_BACKEND=fake PYTHONPATH="apps/backend/src:tooling" apps/backend/.venv/bin/python -m pytest -q --tb=short -p no:randomly apps/backend/src/kenn/tests -o cache_dir=/private/tmp/kenn-payload-cancel-work-full-20261003
```

Full backend: 3837 passed, 12 skipped, 7 warnings and 1 pre-existing failure in 91.67 s. The failure is `test_personal_path_gate.py::test_the_shipped_tree_has_no_personal_path_or_remote_host`; its findings are not copied here. `git diff --cached --check` passed before the code commit.

## Research and limits

The [broader research](../research/KENN_PRODUCT_AND_OPEN_SOURCE_RESEARCH_2026-10-02.md#scoped-context-and-jobs) separates stopping future work from preventing stale delivery. This regression covers the former at two payload boundaries, complementing the [stream checks](KENN_C2_CANCELLED_STREAM_WORK_2026-10-03.md). It establishes no wall-clock gain, provider-slot release or server-side inference abort. Cancellation after an entry check can still leave already-started retrieval, generation or critique running.

The [speed shortlist](KENN_SPEED_RESEARCH_2026-10-03.md) remains external experiment input. Decode is still the dominant measured local stage; prompt reuse cannot alone solve its output budget. The cap and brief-style trials remain disabled because acceptance or useful detail declined. Same-lineage Qwen3 8B MLX comparison remains a proposal requiring Jack's approval, as do new dependencies, assets and a speculative draft. Thinking is already off; residency, context, grounding and production style are unchanged.

No real Live, model prose or private audio is involved in this commit. C1, C2 and C3 remain unticked: neither surface has qualified at least 70% accepted model delivery within 15 s with Live open. Real-Live memory pressure and audio dropouts remain for Jack's scheduled soak.
