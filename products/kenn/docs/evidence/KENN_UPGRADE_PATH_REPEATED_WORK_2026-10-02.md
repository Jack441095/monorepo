# What the HTTP upgrade path repeats, and what it wrongly writes twice — 2 October 2026

C2 asked us to measure the conditional repeated routing, retrieval and critique on the HTTP template/upgrade path. With
`KENN_LLM_BACKGROUND` on, `/api/ask` answers once with `allow_llm=False` and then, for questions the model can take,
runs `answer_payload` a second time in the background (`server.py`, the `answer_upgrades.start` call).

## Method

Four knowledge questions through `answer_payload` twice each, foreground then background (`record_session=False`),
on this Mac against the current local index, with the model call stubbed to return nothing and every store pointed at a
temp directory (`KENN_CHATS_DIR`, `KENN_DB_PATH`). Wrapper counters on routing, the orchestrator dispatch, retrieval,
template building, grounding, critique and the two writes. Four questions and a stubbed model: this measures what is
repeated, not what a real upgrade costs.

## What is repeated

Everything before the model runs, once more: orchestrator dispatch, `route_query`, retrieval, `build_template_answer`,
grounding and the quality report, and the critique. All of it is cheap once the index is warm. Across the four
questions the background pass spent about 58 ms in retrieval (the foreground pass spent 575 ms, mostly the first cold
call), 10 ms building templates and about 5 ms in critique and trace work. That is roughly 25 ms a question against
15 s of generation in the earlier receipts, so removing the repetition would not change latency and we have not tried.

The LLM critique pass in `post_answer_critique` is already off unless `KENN_CRITIQUE_LLM_ENABLED=1`. The 1 Oct note
that put about 20 s on critique does not apply to the default path; we have not checked how that figure was taken.

## What it wrongly wrote twice

`_critique_and_save_trace` always called `record_citations` and `save_reasoning_trace`, including for the background
answer and for the read-only MCP knowledge path, both of which pass `record_session=False`. Four upgraded questions
left 8 reasoning traces and 128 citation counts. Each question's sources were counted twice, which moves their trust
score twice, and a background answer that the next turn discards still wrote both.

## Change

`products/kenn/apps/backend/src/kenn/core/chat_answer.py`: `_critique_and_save_trace` takes `persist` and the
non-streaming path passes `record_session`. With `persist` off the critique still runs and still sets the warnings and
confidence on the answer, but nothing is written. Same harness afterwards: 4 traces and 64 citation counts, one set per
question. The streaming path is untouched.

`tests/test_answer_upgrade_context.py`: `test_a_background_answer_does_not_count_citations_or_save_a_second_trace`.
It fails on the old code and passes on the new. KENN suite: 3,552 passed, 5 skipped, 0 failed.

## Limits

The upgraded answer's own trace is no longer saved, so the stored conclusion for that question is the template's. That
matches how session memory already treats background answers, but if we want the model's conclusion saved we should
do it through `write_if_current` once the answer is delivered. The task-budget and cache-contract drift part of the
plan item is not covered here, and neither are the streaming path's write rules.
