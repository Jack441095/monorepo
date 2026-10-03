# C3 generation history and model rerun, 3 October 2026

Implementation commit: `e72681534a5ac127e4a2b05a90d60f40d5b691f0`.

C3 remains open. The six existing five-turn conversations were rerun before this change, and every delivered answer was read. The run exposed an accepted export answer about the previous drum reverb: retrieval had dropped the old subject, but generation still received that conversation. The fix aligns generation with retrieval on both chat surfaces while retaining typed measurement packets and recognised uploaded-analysis context. Production prompts, output limits, grounding rules, model assets and residency are unchanged. C1 and C2 also remain unticked.

## Files and behavior

- `apps/backend/src/kenn/core/chat_answer.py`: `_history_for_answer` retains the full conversation for follow-ups. When retrieval drops history, it retains only existing typed evidence or recognised mix-review context. Stream answer-mode selection, template construction and model generation use that filtered history; payload generation does too.
- `apps/backend/src/kenn/tests/test_history_boundaries.py`: `test_generation_drops_old_reverb_on_export_but_keeps_it_for_a_followup` covers stream/payload, a new subject/follow-up, and chat-only/attached-evidence inputs. It inspects the real synthesis messages at the model boundary. Existing plugin and uploaded-analysis smoke tests protect evidence retention.

## Thirty-turn model rerun before the fix

Code commit: `62bd7a33be68c46dde7cad1a6e34e02ddb4a6dd6`. Index: `v-db8c6334cf63`, unchanged. Cases SHA-256: `3a59faff5f16e4f4bfbbd76c517adba2bbd31fe5fcbd74452c717b64ba3af691`. Runner SHA-256: `d33e0783c6c5e4a897496ff568bbbc95434da30a4e7f7f571df68b13476020e4`.

The private wrapper invokes the existing conversation runner and observes provider usage with `scripts.measure_model_phases`. It captures candidates and delivered answers for local reading. Those files contain model prose and remain outside git. Wrapper SHA-256: `9de40bc5407b80e41678a83f3e23e83336116842a22532ca7f30a72f99946b23`.

Command, from `products/kenn`:

```sh
KENN_LLM_ENABLED=1 KENN_LLM_PROVIDER=ollama KENN_LLM_MODEL=kenn-brain-qwen3-8b KENN_LLM_CACHE=0 KENN_USE_MLX=0 KENN_CRITIQUE_LLM_ENABLED=0 KENN_CHATS_DIR=/private/tmp/kenn-c3-history-rerun-20261003/chats KENN_DB_PATH=/private/tmp/kenn-c3-history-rerun-20261003/kenn.db KENN_LIVE_BACKEND=fake PYTHONPATH="apps/backend/src:tooling" apps/backend/.venv/bin/python /private/tmp/kenn-c3-history-rerun-20261003/run.py
```

Result: **30 turns, 21 answer-generation attempts, 10 accepted, 3 accepted within 15 seconds, zero runner errors**, exit 0. This includes clarification and action turns, so 3/30 is not an eligible-knowledge gate percentage. Backend acceptance did not establish usefulness: the export answer passed guards while answering the previous topic. Three later snare answers echoed instructions; the limiter/action conversation also produced topic and intent mismatches. Other attempts were rejected for unsupported measurements or insufficient evidence overlap. The guitar correction reached the production route instead of the Live translator but its candidate was rejected for unsupported measurements. Cancellation avoided retrieval, and requests for nonexistent analysis stayed behind the missing-analysis guard.

There were 21 rewrite calls: 11 completed and 10 interrupted by guards. Interrupted calls have unknown phase metrics, not zero-cost phases. A separate route call completed. For the 11 completed rewrites:

| Provider phase | Minimum | Median | Maximum |
| --- | ---: | ---: | ---: |
| Prefill | 2.567 s | 4.254 s | 9.950 s |
| Decode | 5.579 s | 11.648 s | 23.907 s |
| Decode rate | 14.22 tok/s | 17.51 tok/s | 18.10 tok/s |

These measurements support the research's instruction to separate prefill, decode and rejected work. They do not demonstrate an engine speedup. Native prefix caching was active even with the application response cache disabled.

Mac state, 01:06:59–01:11:30 UTC: Apple M3, 16 GiB, Ollama 0.34.4, Qwen3 8B Q4_K_M, reported 5.4 GB resident at 100% GPU with 4096-token context. Calendar, ChatGPT, Clock, FindMy, Flux, Home, Mail, Notes, Ollama, Siri AI, Stocks, Visual Studio Code and Weather appeared in the application inventory; Codex was active but omitted by that inventory. Live was absent. Reported swap use moved from 10636.69 to 10153.25 MiB, with 11264 MiB allocated. Background work and thermal state were uncontrolled. Thinking was off; the 384-token ceiling and 30-minute keep_alive were unchanged. One heavy job ran at a time; no index rebuild.

## Verification of the history fix

All commands ran sequentially from `products/kenn` with Fake Live and fresh pytest caches.

Initial valid regression command:

```sh
KENN_LIVE_BACKEND=fake PYTHONPATH="apps/backend/src:tooling" apps/backend/.venv/bin/python -m pytest -q --tb=short -p no:randomly apps/backend/src/kenn/tests/test_history_boundaries.py -k generation_drops -o cache_dir=/private/tmp/kenn-pcache-generation-red2-20261003
```

Result: **2 failed, 2 passed, 18 deselected**, 0.28 s. The two new-subject cases exposed history in generation; follow-ups retained it correctly. Attached-evidence cases were then added.

Final scoped command:

```sh
KENN_LIVE_BACKEND=fake PYTHONPATH="apps/backend/src:tooling" apps/backend/.venv/bin/python -m pytest -q --tb=short -p no:randomly apps/backend/src/kenn/tests/test_history_boundaries.py apps/backend/src/kenn/tests/test_streamed_generation_prefix_guard.py apps/backend/src/kenn/tests/test_generation_outcome_log.py apps/backend/src/kenn/tests/test_evidence_window_alignment.py apps/backend/src/kenn/tests/test_llm_stream_honesty.py apps/backend/src/kenn/tests/test_server_smoke.py -o cache_dir=/private/tmp/kenn-pcache-generation-evidence-green2-20261003
```

Result: **117 passed**, 4.21 s, exit 0.

Final full backend command:

```sh
KENN_LIVE_BACKEND=fake PYTHONPATH="apps/backend/src:tooling" apps/backend/.venv/bin/python -m pytest -q --tb=short -p no:randomly apps/backend/src/kenn/tests -o cache_dir=/private/tmp/kenn-pcache-generation-evidence-full-20261003
```

Result: **3619 passed, 12 skipped, 1 failed, 7 warnings**, 103.67 s, exit 1. The pre-existing failure is `test_personal_path_gate.py::test_the_shipped_tree_has_no_personal_path_or_remote_host`: the unchanged handoff note contains a machine-specific checkout path.

An initial filter dropped attached evidence and caused two plugin smoke failures. A HEAD-source control, loaded privately without editing the checkout, passed both plugin tests; they were actual regressions, not pre-existing failures. The final filter preserves their evidence and both pass in scoped and full runs. The full HEAD control also hit the known personal-path failure and a companion-owner timeout; that timeout did not recur in the final full run. An accidentally broad product-level collection found nine unrelated legacy/vendored collection errors before the explicit backend scope was restored.

## Original export question replay after the fix

The private replay uses the original export question and its recorded reverb history, sequentially through the public stream and payload APIs. The source SHA-256 was `bf000707f27877d6001f684f6150a3bcfc4d49dcd5d28d0651cff8dbb8fb054c`, matching the implementation committed above; the replay ran before that commit was made. Model prose remains in private scratch.

```sh
KENN_LLM_ENABLED=1 KENN_LLM_PROVIDER=ollama KENN_LLM_MODEL=kenn-brain-qwen3-8b KENN_LLM_CACHE=0 KENN_USE_MLX=0 KENN_CRITIQUE_LLM_ENABLED=0 KENN_CHATS_DIR=/private/tmp/kenn-c3-generation-boundary-20261003/chats KENN_DB_PATH=/private/tmp/kenn-c3-generation-boundary-20261003/kenn.db KENN_LIVE_BACKEND=fake PYTHONPATH="apps/backend/src:tooling" apps/backend/.venv/bin/python /private/tmp/kenn-c3-generation-boundary-20261003/replay.py
```

Result: exit 0. Both answers were read, stayed on stem export and passed existing acceptance checks. They covered export format, common length, naming and master-limiter handling. This is a topic-correctness observation, not independent approval of every explanatory claim.

| Surface | Total | Delivered first token | Prompt/output tokens | Prefill | Decode | Decode rate | Cached prefix tokens |
| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| Stream | 19.499 s | 4.072 s | 1067 / 277 | 2.604 s | 15.465 s | 17.91 tok/s | 612 |
| Payload | 14.211 s | Not exposed | 1067 / 247 | 0.058 s | 14.045 s | 17.59 tok/s | 1066 |

Both provider calls completed with `stop`, application-cache misses, and `used_history=false`. The payload followed the stream with a nearly fully cached prefix and a different output length; this is not a controlled comparison between surfaces. The old wrong-topic stream answer was faster, so it must not be counted as an improvement target.

Mac state, 01:32:47–01:33:21 UTC: same hardware, runtime, applications and resident model; Live absent. Swap use moved from 11136 to 10944 MiB with 12288 MiB allocated. This substantial background memory use cannot establish Live/audio behavior or cold-load cost.

## Limits and next work

The thirty-turn suite has not been rerun in full after this fix. The focused replay checks one previously failed topic boundary; deterministic tests cover both surfaces and evidence retention. No two-track choices, project switching, UI delivery, scheduled Live soak or held-out human quality qualification occurred. The remaining instruction echoes, action-intent mismatches and unsupported-measurement rejections remain open. Grounding must not be relaxed to increase acceptance.

The [C2 phase/cap receipt](KENN_C2_MODEL_PHASES_AND_OUTPUT_CAP_2026-10-03.md) and [brief-style/runtime proposal](KENN_C2_BRIEF_STYLE_AND_RUNTIME_PROPOSAL_2026-10-03.md) retain the speed research as a test shortlist. The cap truncates useful answers; the soft brief instruction loses acceptance and a workflow setting. Neither was adopted. keep_alive and any MLX/dependency/model-asset experiment still need Jack's decision. No plan tick is earned.
