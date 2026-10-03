# C2 cancelled stream work and research priorities, 3 October 2026

Code commit: `4e2d834db45857f2b2d786e0dd52c83901715a92`.

The stream checked ownership after advancing its raw generator. A request cancelled or replaced while suspended at metadata could therefore start model generation; one suspended at a token could read another provider chunk. The stream now checks before advancing, keeps the check after advancement for cancellation during a read, and closes the raw generator before reporting discarded delivery. Final cleanup also closes it when the consumer stops.

Exact files:

- `apps/backend/src/kenn/core/chat_answer.py`: check ownership before raw stream advancement and close on exit.
- `apps/backend/src/kenn/tests/test_stream_cancel_work.py`: 24 cases through the public stream and actual native Ollama/OpenAI provider parsers with stubbed transport. They cover cancellation, replacement, other-chat isolation and unbound requests at metadata, token and in-flight read boundaries, including cleanup before discarded metadata and interrupted usage records.

Commands ran from `products/kenn`, on Fake Live without model generation, dependencies or index work. Each run used a fresh pytest cache directory.

```sh
KENN_LIVE_BACKEND=fake PYTHONPATH="apps/backend/src:tooling" apps/backend/.venv/bin/python -m pytest -q --tb=short -p no:randomly apps/backend/src/kenn/tests/test_stream_cancel_work.py -o cache_dir=/private/tmp/kenn-stream-cancel-work-red-20261003
```

Before the fix: 8 failed, 16 passed in 0.25 s. Cancelled/replaced requests opened the provider after metadata or read an extra chunk after a token. Other-chat, unbound and in-flight discard cases passed. The first fixed run passed all 24 in 0.24 s.

```sh
KENN_LIVE_BACKEND=fake PYTHONPATH="apps/backend/src:tooling" apps/backend/.venv/bin/python -m pytest -q --tb=short -p no:randomly apps/backend/src/kenn/tests/test_stream_cancel_work.py -o cache_dir=/private/tmp/kenn-stream-cancel-work-final-mutation-20261003
```

Removing only the check before advancement restored 8 failures, with 16 passes in 0.15 s. The source was restored in a `finally` block. The final test also checks that cleanup has completed when discarded metadata arrives.

```sh
KENN_LIVE_BACKEND=fake PYTHONPATH="apps/backend/src:tooling" apps/backend/.venv/bin/python -m pytest -q --tb=short -p no:randomly apps/backend/src/kenn/tests/test_stream_cancel_work.py apps/backend/src/kenn/tests/test_stream_request_delivery.py apps/backend/src/kenn/tests/test_provider_cache_ownership.py apps/backend/src/kenn/tests/test_answer_upgrades.py apps/backend/src/kenn/tests/test_llm_stream_honesty.py apps/backend/src/kenn/tests/test_streamed_generation_prefix_guard.py apps/backend/src/kenn/tests/test_llm_usage_telemetry.py apps/backend/src/kenn/tests/test_chat_stream_weak_retrieval.py -o cache_dir=/private/tmp/kenn-stream-cancel-work-final-scoped-20261003
```

Final scoped result: 198 passed in 2.43 s. An earlier scoped run exposed two iterator test doubles without `close`; cleanup now follows the public wrapper's optional-close convention. The restored scoped run also passed all 198.

```sh
KENN_LIVE_BACKEND=fake PYTHONPATH="apps/backend/src:tooling" apps/backend/.venv/bin/python -m pytest -q --tb=short -p no:randomly apps/backend/src/kenn/tests -o cache_dir=/private/tmp/kenn-stream-cancel-work-full-20261003
```

Full backend: 3789 passed, 12 skipped, 7 warnings and 1 pre-existing failure in 91.77 s. The failure is `test_personal_path_gate.py::test_the_shipped_tree_has_no_personal_path_or_remote_host`; its findings are not copied here. `git diff --cached --check` passed.

## Research scan and decisions

The [speed shortlist](KENN_SPEED_RESEARCH_2026-10-03.md) reports external hardware. The [broader research](../research/KENN_PRODUCT_AND_OPEN_SOURCE_RESEARCH_2026-10-02.md#5-architecture-implications) calls for stopping future cancelled work, preserving request ownership, measuring full delivery and qualifying useful answers separately from model throughput. Those are experiment inputs, not local results.

| Candidate | Local evidence and next decision |
| --- | --- |
| Prevent cancelled work | This regression proves that a suspended stale request no longer starts or advances provider work on resumption. It measures no wall-clock gain and proves no server-side inference abort. |
| Shorter answers | [Cap trial](KENN_C2_MODEL_PHASES_AND_OUTPUT_CAP_2026-10-03.md): baseline accepted within 15 s was 2/5 on each surface; a 128-token trial gave 4/5 stream and 1/5 payload, with truncation. [Brief-style trial](KENN_C2_BRIEF_STYLE_AND_RUNTIME_PROPOSAL_2026-10-03.md) gave 3/5 stream and 1/5 payload and lost useful detail. Both remain disabled for Jack's decision. |
| Decode runtime | Recent local completed calls measured approximately 17–18 tok/s, with decode still the dominant stage. The exact Qwen3 8B lineage / approximately 1,100-token prompt / M3 16 GB [MLX comparison proposal](KENN_C2_BRIEF_STYLE_AND_RUNTIME_PROPOSAL_2026-10-03.md) is written but unexecuted. Dependencies and assets require Jack's approval; external speed factors cannot justify a switch. |
| Improve accepted-answer quality | Missing useful advice and grounding rejections in the diagnostic samples limit acceptance even when delivery is timely. Preserve grounding and answer completeness; use reproducible diagnostic cases for repairs and an independent held-out qualification for quality claims. Keep the sealed C4 set sealed. |
| Model residency | Keeping approximately 5 GB resident avoids cold reloads but competes with Live for memory. Keep the existing setting until Jack chooses; fake-Live measurements cannot settle audio dropout or memory pressure with Live open. |
| Prefill and prompt reuse | Native phases separate this cost from decode. A stable full-policy prefix is an experiment only when measured prefill warrants it; it cannot alone overcome the shortlist's 17–21 s decode budget. No grounding instructions were shortened. |
| Thinking, KV and speculative decoding | Thinking is already disabled at request level. Keep context 4096 and current KV policy; the shortlist establishes no KV speed gain. A speculative draft adds assets/runtime and needs approval, with no proven fit for this Mac's memory budget. |

## Limits

The tests stop future generator advancement after ownership revocation. They cannot interrupt a blocking provider read already underway, demonstrate that Ollama releases its model slot, or stop payload inference. Discarded metadata still reports `inference_aborted: false`; interrupted calls retain unknown native phases if no terminal response arrived. Closing transport is not proof of backend cancellation.

No real Live session was touched. Production answer style, output cap, grounding, residency, model assets and runtime are unchanged. No model prose or private audio is committed. C1, C2 and C3 remain unticked: accepted model answers within 15 s on at least 70% of eligible requests with Live open are still unqualified on both surfaces.
