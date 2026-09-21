# KENN Chat Optimization Pass Receipt

Date: 2026-09-21

## Outcome

Executed the chat-focused optimization pass against the in-process answer path with the LLM disabled and the repository's current BM25 fallback. The optimized path reduced the four-query mixed workload from a 28.27 ms median to 14.84 ms, with identical source-selection digest (`3a3d7eb2cef08ea9`).

## Implemented

- Added bounded immutable caches behind the existing `tokenize`, `query_topics`, and `normalized_terms` APIs. This removes repeated regex/topic work during BM25 scoring, reranking, intent guards, and answer formatting without changing return types or ranking rules.
- Added `record_citations()` and switched answer trace handling to batch citation trust updates in one SQLite transaction. Citation counts and the capped `+0.01` trust increment were verified to match the previous per-citation implementation.

## Validation

- Focused chat/retrieval/API tests: **11 passed**.
- Broader chat and retrieval run: **82 passed**; four existing evaluation cases remain red (`bass-processing`, `reverb-send`, `group-bus-workflow`, and `wwise-mobile-ambience-memory`). These failures reproduce with an isolated database and are not caused by the caching or batched-write changes.
- Python compilation and `git diff --check`: passed.
- LLM generation was not benchmarked because the MLX engine is unavailable on this host.
- Hybrid retrieval was not promoted because the active embedding artifact is missing and the existing comparison receipt shows a quality regression.

Detailed measurements are in [chat_optimization_cache.json](./results/chat_optimization_cache.json).

## Native/C++ decision

No new C++ chat module was added. The measured hot paths are short-string classification and SQLite connection setup; a native boundary would add complexity without addressing the dominant costs. The existing C++ DSP work remains opt-in and unaffected.

No commit was created; the worktree's existing changes were preserved.
