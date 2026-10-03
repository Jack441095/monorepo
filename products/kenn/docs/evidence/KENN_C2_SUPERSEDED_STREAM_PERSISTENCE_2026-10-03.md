# C2 superseded stream persistence receipt — 3 October 2026

Code commit: `8d814a6f8948f790827fa2132eea5dd31547ee17` on `fix/review-critical-2026-10-02`.

The stream consumer discarded stale metadata, but the producer could already have saved citation counts and a reasoning trace. Cancellation or a replacement turn after the last token, including during critique, reproduced this on template and model streams. An unrelated chat retained its own writes.

## Change

- `apps/backend/src/kenn/core/chat_answer.py`: pass the stream's session and request owner into `_critique_and_save_trace`; check ownership under the existing lock for each citation/trace save. Critique runs outside that lock. Existing session persistence remains guarded.
- `apps/backend/src/kenn/tests/test_stream_request_delivery.py`: add `test_superseded_stream_cannot_save_reasoning_traces_or_citation_counts`, with template/model, cancel/replacement/other-chat and last-token/during-critique cases. The test checks discarded delivery and persistence isolation, and verifies that critique runs outside the owner lock while writes run inside it.

## Commands and results

All commands ran from `products/kenn`, one CPU-heavy job at a time, using the existing virtual environment and Fake Live. Each run used a fresh cache directory.

Before the fix, the six-case regression failed in four cases and passed in two (47 deselected, 0.51 s, exit 1):

```sh
KENN_LIVE_BACKEND=fake PYTHONPATH="apps/backend/src:tooling" apps/backend/.venv/bin/python -m pytest -q --tb=short -p no:randomly apps/backend/src/kenn/tests/test_stream_request_delivery.py -k superseded_stream_cannot_save -o cache_dir=/private/tmp/kenn-stream-persistence-red2-20261003-0355
```

After the fix, that command with cache directory `/private/tmp/kenn-stream-persistence-green-20261003-0400` passed all six cases (47 deselected, 0.25 s, exit 0). The final regression expands those cases to both ownership-revocation timings.

Scoped verification passed: **88 passed in 4.31 s**, exit 0.

```sh
KENN_LIVE_BACKEND=fake PYTHONPATH="apps/backend/src:tooling" apps/backend/.venv/bin/python -m pytest -q --tb=short -p no:randomly apps/backend/src/kenn/tests/test_stream_request_delivery.py apps/backend/src/kenn/tests/test_streamed_generation_prefix_guard.py apps/backend/src/kenn/tests/test_answer_upgrade_context.py -o cache_dir=/private/tmp/kenn-stream-persistence-scoped-20261003-0402
```

Full backend verification: **3680 passed, 12 skipped, 1 failed, 7 warnings in 103.83 s**, exit 1.

```sh
KENN_LIVE_BACKEND=fake PYTHONPATH="apps/backend/src:tooling" apps/backend/.venv/bin/python -m pytest -q --tb=short -p no:randomly apps/backend/src/kenn/tests -o cache_dir=/private/tmp/kenn-stream-persistence-full-20261003-0405
```

The failure is pre-existing: `test_personal_path_gate.py::test_the_shipped_tree_has_no_personal_path_or_remote_host`. Its existing handoff/legacy path findings remain unresolved; no private findings are reproduced here. The ordering-sensitive `test_main_chat_can_combine_explicit_mix_review_and_plugin_evidence` passed in this run. Scoped `git diff --check` passed.

## Research follow-through and limits

Read both the 3 October speed shortlist and section 12 of the broader product/open-source research. External throughput figures remain experiment leads, not evidence for this M3 / 16 GB. The latest local HTTP diagnostic accepted 1/5 upgrades within 15 s with Fake Live; repeated retrieval was 7–26 ms against 8.8–15.1 s of decode. That supports prioritizing decode speed and answer length over repeated retrieval. See [the measured phases and Mac state](KENN_C2_HTTP_BACKGROUND_PHASES_2026-10-03.md).

The isolated cap and brief-style trials exposed quality costs and remain disabled for Jack's decision. Thinking is already off. The existing keep_alive setting remains unchanged: residency holds about 5 GB while avoiding a cold reload, with memory pressure and audio dropouts unqualified until an owner-scheduled Live soak. The exact Qwen3 8B MLX comparison remains a proposal requiring approval; no runtime, dependency, draft model or model file was added.

This receipt establishes a stream persistence correction with stubbed providers and fixtures. It does not establish a decode speed gain, model-answer quality gain or a Live-open gate pass. Payload foreground ownership and provider response-cache writes are outside this regression's scope, so the parent superseded-request persistence clause remains open. Each save checks ownership independently; a write already holding the owner lock completes before cancellation obtains that lock. No model prose or private audio is committed. Grounding, production answer style, token ceiling and residency are unchanged. **C1, C2 and C3 remain unticked.**
