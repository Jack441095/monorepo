# Query-rewriting trial on the device-purpose fixtures, 16 October 2026

Run on `feature/reference-review-grade` at `924d2843` plus `tooling/scripts/trial_query_rewrite.py`
(uncommitted when the run started, committed with this note). It answers the C3 item "Query-rewriting
trial (15 Oct research)". Result: **no adoption case on this evidence.** One local call per question
helped one fixture a little and did nothing on the other, and as a follow-up resolver it was worse than
what chat routing already does.

## What ran

Each fixture case is scored four ways with the same rank rule as `evaluate_retrieval_modes.py`
(recall@4, MRR, top-1). Retrieval is untouched; only the query string changes.

| Condition | Query handed to retrieval |
|---|---|
| `raw` | the fixture question, as asked |
| `rewrite` | one `kenn-brain-qwen3-8b` call turns the question into a retrieval query (no history) |
| `followup_history` | the fixture question is the previous turn; one of six fixed elliptical follow-ups ("and how do I set that up?") is the new one; the query is `search_query_with_history`, i.e. today's production path |
| `followup_rewrite` | same turns, but the model resolves the follow-up against the previous question |

Greedy decoding (temperature 0, seed 0), 64-token cap, thinking off, 1 minute keep-alive per call and an
explicit unload at the end (`ollama ps` was empty afterwards). One of the 750 rewrite calls returned an empty reply and fell back to the unchanged input (`rewrite_fallbacks: 1` in the receipt), which scores as the raw query. Fixtures:
`device_purpose_sealed_holdout.json` (150 cases scored of 150) and `device_purpose_sealed_qwen8b.json`
(225 of 228; the same three skips the scorer always reports). The `latency_ms` fields in the underlying rows are a constant 0.0 and are not measured. Receipt with ids and ranks only:
[results](../../tooling/evaluation/results/KENN_QUERY_REWRITE_TRIAL_2026-10-16.json).

## Results (BM25 only, recall@4)

| Fixture | raw | rewrite | followup_history | followup_rewrite |
|---|---|---|---|---|
| holdout (150) | 0.307 | 0.367 | 0.280 | 0.307 |
| qwen8b (225) | 0.227 | 0.227 | 0.227 | 0.191 |

Per-case wins and losses against the paired baseline (hit in one, miss in the other at rank 4):

| Fixture | rewrite vs raw | followup_rewrite vs followup_history |
|---|---|---|
| holdout | +20 / -11 | +20 / -16 |
| qwen8b | +16 / -16 | +12 / -20 |

Cost: about 1.5 s per rewrite call on the already-resident 8B (437 s for 300 calls on the holdout, 733 s
for 450 on the other), on top of an answer that already runs 10 s or more.

## What this does and does not show

- **Retrieval here was BM25 only.** The 14 Oct index in this checkout has no embeddings and
  `sentence_transformers` is not installed, so the shipped hybrid path (the one behind the 0.616 → 0.736
  receipt) cannot run. These figures are not comparable with that receipt, and a rewrite may help or hurt
  differently once dense retrieval is back. The trial stays open for a rerun on a hybrid index.
- The follow-ups are six templates cycled by case position, not producer turns. The trial shows whether a
  rewrite recovers a topic the history already carries; it says nothing about a real topic change.
- One model, one pass, one prompt. No prompt tuning was done, deliberately: the prompt was written once
  before any fixture was scored.
- The holdout gain (+9 net cases) is the only positive signal. The same prompt gives +0 net on the other
  fixture, so a fair reading is "noise-sized and fixture-dependent".

## Decision

Do not add a rewrite call to chat routing on this evidence. Rerun `trial_query_rewrite.py` unchanged once
an index with embeddings exists; adopt only if hybrid recall@4 rises on both fixtures with no larger loss
column than win column.
