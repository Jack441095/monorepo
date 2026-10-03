# C2 abstentions and retrieval gap, 3 October 2026

C2 remains open. The [speed research](KENN_SPEED_RESEARCH_2026-10-03.md) is a shortlist of experiments on other hardware, not an M3 result. At 13 tok/s, 220–280 output tokens require about 17–21 s of decoding alone. Prefill and prompt-cache work cannot remove that floor. The available levers remain measured decode acceleration, shorter useful answers, or both. No production style, grounding, runtime or residency setting changed here.

Code commit `93e18f99831f1057bad56725c8e100a9d25d0328` changes only `tooling/scripts/measure_model_phases.py` and `apps/backend/src/kenn/tests/test_measure_model_phases.py`. The harness keeps the existing raw acceptance figures and adds a per-response `abstained` flag, `accepted_abstentions`, `accepted_non_abstaining_within_15_seconds` and `non_abstaining_fraction`. It recognizes the existing explicit abstention prefix at the start of a line, including case/whitespace variants and a bare prefix. It does not copy the missing fact or answer prose into numeric receipts.

Non-abstaining does not establish useful, correct or supported advice. Those counts still need private answer review. `release_gate_evaluated` remains false; the required Live-open gate was not run. Honest abstentions remain valid grounding outcomes, but cannot establish that a requested explanation was useful.

## Scoped verification

From `products/kenn`, fake Live, one job at a time:

```sh
KENN_LIVE_BACKEND=fake PYTHONPATH="apps/backend/src:tooling" apps/backend/.venv/bin/python -m pytest -q --tb=short -p no:randomly apps/backend/src/kenn/tests/test_measure_model_phases.py apps/backend/src/kenn/tests/test_measure_chat_latency.py apps/backend/src/kenn/tests/test_conversational_answer_grounding.py apps/backend/src/kenn/tests/test_llm_grounding_pair.py -o cache_dir=/private/tmp/kenn-abstention-count-restored-20261003
```

Result: **65 passed in 0.54 s**, exit 0. Initial six behavior cases failed before the change. Forcing abstention detection to false restored **7 failures and 17 passes in 0.11 s**; the source was restored before the scoped command above. The integration fixture checks both surfaces, raw acceptance, abstention separation and prose isolation. No full-suite rerun for this tooling-only change. The preceding shared-router full run had **3999 passes, 12 skips and one pre-existing personal-path gate failure**, documented in the [routing receipt](KENN_C2_AUDIO_FUNDAMENTAL_ROUTING_2026-10-03.md).

## Recount of the existing private run

Reclassified the already captured final deliveries from `/private/tmp/kenn-audio-fundamentals-phases-20261003/answers.jsonl` using `answer_outcome`, then applied `gate_counts` to the original timing/acceptance rows. No new model generation, cache reset, index build or Mac-state comparison. Original run code: `c26c286e803de16171d232e94221016bb96ca913`; original command, native timings and Mac state are in the routing receipt.

| Surface | Eligible / attempted | Raw timely accepted | Accepted abstentions | Timely accepted non-abstaining |
| --- | ---: | ---: | ---: | ---: |
| Stream | 3 / 3 | 2 / 3 | 2 | 0 / 3 |
| Payload | 3 / 3 | 0 / 3 | 0 | 0 / 3 |

Private review of all six candidates/deliveries already found **zero useful explanations on either surface**. The numeric recount is `/private/tmp/kenn-audio-fundamentals-phases-20261003/abstention-recount.json`, SHA-256 `a6e28f227c09fa28e8fc62ec12ca94a8889288473e41555a35556241622a3093`. Updated harness SHA-256: `2e5d4df51c0a2ce0d1797788090cd2fafad4e4f5e983d72a839df01808577edf`. Private model prose remains outside git.

## Existing-index diagnosis

An offline read of the current index `v-db8c6334cf63` loaded 4642 chunks and searched the same three questions with `chat_retrieval.search`, `display_results`, `results_are_weak` and `intent_guard_status`. It completed in 0.815 s, exit 0, using fake Live and the same Python/PYTHONPATH. No model or index rebuild ran.

Exact concept-pattern matches across indexed title/text/tags: **0** for precedence effect; **2** for phantom power; **1** for balanced audio cabling/connections. This does not rule out aliases such as Haas effect, or establish the adequacy of those sparse mentions. Displayed results instead selected reverb/delay and chain order for precedence effect, soundstage and minimalism for phantom power, and bass/low-end notes for balanced cabling. All three had no recognized query topics, `results_are_weak=False` and `intent_guard_status=not_needed`.

This narrows the remaining quality problem to sparse concept coverage and unrelated retrieval/fallback selection. Direct routing now reaches generation, but cannot supply missing evidence. The next investigation should inspect existing aliases, exact passages and ranking before proposing a corpus or retrieval change. No grounding rule was relaxed and no training/index content was edited.

## Research decisions and limits

The [cap trial](KENN_C2_MODEL_PHASES_AND_OUTPUT_CAP_2026-10-03.md) and [brief-style trial](KENN_C2_BRIEF_STYLE_AND_RUNTIME_PROPOSAL_2026-10-03.md) remain disabled pending Jack's answer-style decision. Their improvements did not hold across both surfaces and answer quality declined. Thinking is already off. The current 30-minute residency retains about 5 GB against avoiding cold reloads; changes require Jack, and memory pressure/audio continuity remain open until his Live-open soak.

The exact MLX comparison proposal remains Qwen3 8B lineage only, the roughly 1100-token KENN prompt, separate prefill/decode measurements on this M3/16 GiB, paired cold/warm repeats and private quality review. It has not been executed. No MLX switch, speculative draft, model download, dependency installation or CI/permission change. These three engineering questions are not a held-out qualification set. C1, C2 and C3 stay unticked.
