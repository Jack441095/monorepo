# C2 model phases and output-cap diagnostic, 3 October 2026

C2 stays open. The release gate remains failed on both surfaces: at least 70% of eligible knowledge requests must deliver an accepted model answer within 15 seconds **with Live open**. These runs used Fake Live with Live closed, five selected questions per surface and one pass per condition. No production answer-style or residency setting changed.

## Source and commands

Measurement commit: `d37583b9eca3f5ad7567f5f5fd19b08f6b4e2b84` (harness introduced in `daaa0417beea03d5f981b401ec070b92d819d93b`). The subsequent receipt commit also makes the harness's read-only git metadata lookup run from the monorepo root; it does not change generation or measurements.

Both commands ran sequentially from `products/kenn`, baseline first, with no other foreground CPU-heavy engineering job:

```sh
KENN_LLM_ENABLED=1 KENN_LLM_PROVIDER=ollama KENN_LLM_MODEL=kenn-brain-qwen3-8b KENN_LLM_CACHE=0 KENN_USE_MLX=0 KENN_CRITIQUE_LLM_ENABLED=0 KENN_LIVE_BACKEND=fake PYTHONPATH="apps/backend/src:tooling" apps/backend/.venv/bin/python tooling/scripts/measure_model_phases.py --runtime-dir /private/tmp/kenn-model-phases-baseline-verified-20261003
KENN_LLM_ENABLED=1 KENN_LLM_PROVIDER=ollama KENN_LLM_MODEL=kenn-brain-qwen3-8b KENN_LLM_CACHE=0 KENN_USE_MLX=0 KENN_CRITIQUE_LLM_ENABLED=0 KENN_LIVE_BACKEND=fake PYTHONPATH="apps/backend/src:tooling" apps/backend/.venv/bin/python tooling/scripts/measure_model_phases.py --output-cap 128 --runtime-dir /private/tmp/kenn-model-phases-cap128-20261003
```

Each invocation creates fresh scratch session/database storage before importing KENN. Numeric `receipt.json` and candidate/delivered samples in `answers.jsonl` remain in those temporary directories; no model prose is committed. There was an initial instrumentation baseline whose payload counter incorrectly used stream-only metadata. That pass is excluded. The counter was fixed and regression-tested before the fresh baseline above and before any cap experiment. Payload acceptance uses the actual `llm_enhanced` flag; stream acceptance uses the final grounding verdict, not the provisional flag. Every eligible selected question remains in the denominator, including rejected or never-attempted answers.

Shared inputs:

- Five case IDs: `bass-processing`, `sidechain-release-time`, `reverb-send`, `gain-staging`, `streaming-loudness`, from the existing question corpus; stream first, then payload, with a fresh session per question.
- Question-set SHA-256: `502d9c5bcec3605ef5959b0792b171f13f01f91e76ca0cc84eec2838d83aec4f`.
- Measured harness SHA-256: `2beccba09d63b9d2e58038019f894ca2f076a84baa3616159fa82bb222cb26e3`.
- Existing index `v-db8c6334cf63`; no rebuild.
- Ollama 0.34.4; `kenn-brain-qwen3-8b`, digest `90a5eaf166fdda7e95441577e6ae96ebacf3248772a4366d1199b7b6ac0b0405`, parent `Qwen3-8B-Q4_K_M.gguf`, Q4_K_M, 8.2B parameters. Active context 4096, model reported 100% GPU.
- Rewrite, route, paraphrase and followups all enabled on that Ollama model with 20-second timeout; rewrite context 1200 characters. Thinking already off, unchanged. Response caching off; warm residency and Ollama prompt/KV cache were not reset.
- Baseline output limit 384; capped run temporarily limits ordinary rewrite output to 128. Prompts, grounding, action/structured output and other task limits unchanged. Temporary wrappers restore the original functions when the harness exits.

## Observed delivery and phases

| Condition | Stream accepted | Stream accepted within 15 s | Payload accepted | Payload accepted within 15 s |
| --- | ---: | ---: | ---: | ---: |
| Baseline | 3/5 | 2/5 (40%) | 3/5 | 2/5 (40%) |
| Cap 128 | 4/5 | 4/5 (80%) | 3/5 | 1/5 (20%) |

All five questions attempted generation on each surface. Stream improves by two timely answers in this selected sample; payload loses one. This does not establish a repeatable cap benefit or qualify the Live-open gate. Bass acceptance changed only on stream, which could reflect generation variation; it does not demonstrate improved grounding.

Prefill and decode use Ollama terminal durations, independently of total chat latency. Decode rate is completion tokens divided by native decode duration. Generation TTFT starts at the completion function; delivered TTFT starts at chat entry. Payload uses a nonstream response, so its TTFT is unknown. Prefix-guard interruptions lack native terminal phase metrics; those costs stay unknown, not zero.

### Baseline

| Surface / case | Total s | Prompt / output tokens | Prefill s | Decode s | Decode tok/s | Generation / delivered TTFT s | Accepted | Completion |
| --- | ---: | --- | ---: | ---: | ---: | --- | --- | --- |
| stream / bass-processing | 7.518 | unknown (interrupted) | unknown | unknown | unknown | 3.283 / 3.867 | no | unknown |
| stream / sidechain-release-time | 10.868 | 1087 / 148 | 2.412 | 8.274 | 17.888 | 2.525 / 2.636 | yes | stop |
| stream / reverb-send | 15.104 | 1097 / 224 | 2.431 | 12.506 | 17.912 | 2.462 / 2.634 | yes | stop |
| stream / gain-staging | 5.870 | unknown (interrupted) | unknown | unknown | unknown | 2.301 / 2.397 | no | unknown |
| stream / streaming-loudness | 9.357 | 1006 / 165 | 0.059 | 9.149 | 18.036 | 0.156 / 0.247 | yes | stop |
| payload / bass-processing | 15.411 | 1144 / 221 | 2.857 | 12.420 | 17.794 | unknown / unknown | no | stop |
| payload / sidechain-release-time | 12.054 | 1087 / 159 | 2.887 | 9.000 | 17.667 | unknown / unknown | yes | stop |
| payload / reverb-send | 15.637 | 1097 / 220 | 2.951 | 12.578 | 17.491 | unknown / unknown | yes | stop |
| payload / gain-staging | 13.180 | 1066 / 181 | 2.539 | 10.516 | 17.212 | unknown / unknown | no | stop |
| payload / streaming-loudness | 10.299 | 1006 / 172 | 0.065 | 10.115 | 17.004 | unknown / unknown | yes | stop |

### Cap 128

| Surface / case | Total s | Prompt / output tokens | Prefill s | Decode s | Decode tok/s | Generation / delivered TTFT s | Accepted | Completion |
| --- | ---: | --- | ---: | ---: | ---: | --- | --- | --- |
| stream / bass-processing | 10.474 | 1144 / 128 | 2.444 | 7.531 | 16.997 | 2.531 / 2.969 | yes | length |
| stream / sidechain-release-time | 10.605 | 1087 / 128 | 2.882 | 7.606 | 16.829 | 2.925 / 3.042 | yes | length |
| stream / reverb-send | 11.398 | 1097 / 128 | 2.983 | 8.227 | 15.558 | 3.017 / 3.215 | yes | length |
| stream / gain-staging | 6.289 | unknown (interrupted) | unknown | unknown | unknown | 2.845 / 2.955 | no | unknown |
| stream / streaming-loudness | 9.113 | 1006 / 128 | 0.069 | 8.825 | 14.505 | 0.220 / 0.339 | yes | length |
| payload / bass-processing | 13.437 | 1144 / 128 | 3.511 | 9.746 | 13.134 | unknown / unknown | no | length |
| payload / sidechain-release-time | 15.419 | 1087 / 128 | 3.812 | 11.426 | 11.203 | unknown / unknown | yes | length |
| payload / reverb-send | 17.641 | 1097 / 128 | 4.299 | 13.182 | 9.710 | unknown / unknown | yes | length |
| payload / gain-staging | 18.192 | 1066 / 128 | 4.126 | 13.879 | 9.223 | unknown / unknown | no | length |
| payload / streaming-loudness | 13.603 | 1006 / 128 | 0.091 | 13.317 | 9.611 | unknown / unknown | yes | length |

Completed baseline calls decoded at 17.00–18.04 tok/s. During the cap run stream decode fell from 17.00 to 14.50 tok/s, then payload from 13.13 to 9.22 tok/s. These are observations, not a diagnosis of thermal or memory effects. The cap changes token count, not engine throughput. At 13 tok/s, 128 tokens still require about 9.85 seconds of decode plus prefill and delivery; 220–280 tokens require about 17–22 seconds of decode alone. Saving prefill cannot remove that decode cost.

Prompt counts were 1006–1144 on completed calls. Reported cached prompt counts were 667–711 for most questions and 1005 for streaming loudness. That question's prefill was only 0.059–0.091 seconds, illustrating warm-prefix reuse, not a newly tuned cache. Completed warm load durations were approximately 0.9–6.7 ms; cold reload was not measured.

## Shortened-answer inspection and Jack's decision

Read all five capped stream deliveries and all five capped payload deliveries, plus the three accepted baseline payload samples. No generated prose is reproduced here. All seven accepted capped answers terminated with `length` at exactly 128 tokens.

- Stream bass retained useful initial processing steps but cut the third step mid-sentence, omitting the listening check and explanation. Payload bass was rejected by existing grounding and delivered a longer deterministic fallback.
- Both sidechain answers retained the main release guidance, three steps and a listening check, but cut the explanation mid-sentence.
- Stream reverb cut the fourth setup step mid-sentence. Payload reverb retained four setup steps but stopped at an unfinished check heading. Both omitted later explanation.
- Stream loudness retained initial steps and a check but cut the explanation. Payload loudness cut a citation marker and retained inconsistent peak guidance; related content concerns were present in the baseline too, so acceptance is not a human correctness verdict.
- Gain staging was rejected on both surfaces and delivered the existing fallback. The experiment caps model output, not fallback length.

The core advice survives in several answers, but the unfinished steps, sentences and citation are a user-visible quality loss. Recommendation: **do not adopt the bare 128-token cap with the current answer prompt**. Jack decides whether a shorter answer style is worth a subsequent experiment. Production remains at 384 tokens. No grounding relaxation or style-prompt tuning was included, and this selected-set reading is not held-out quality qualification.

## Mac state and keep_alive trade-off

Apple M3, 16 GiB physical memory. Baseline snapshots: 00:19:54–00:21:49 UTC; cap: 00:22:05–00:24:11 UTC, 3 October 2026. Live was absent throughout. Codex was active; the application-path process inventory also found Calendar, ChatGPT, Clock, FindMy, Flux, Home, Mail, Notes, Ollama, Siri AI, Stocks, Visual Studio Code and Weather before and after both runs. This inventory does not measure their CPU load or capture every background service. No thermal or audio-dropout telemetry was collected.

Ollama reported the model resident at 5.4 GB before and after both runs. macOS swap used moved from 9876.38 MiB to 9992.44 MiB during baseline, then 9992.44 MiB to 9984.44 MiB during cap. With 16 KiB pages, wired-page counts were 164947→463415 in baseline and 489895→460876 in cap; compressor occupancy was 504541→162616 and 158264→167187 pages respectively. These snapshots do not assign pressure or slowdown to a particular process.

Current `llm/llm_rewrite.py` uses `KENN_OLLAMA_KEEP_ALIVE=30m` by default and sends it on requests. Its enabled-backend daemon also pings an empty generation every 240 seconds. While that daemon runs, idle pings can keep renewing residency, so reducing request duration alone would not guarantee idle release. Neither setting changed.

Keeping residency trades roughly 5 GB held alongside Live for avoiding cold model reload before the next answer. The 5.4 GB reported here is Ollama's resident footprint, not measured incremental macOS memory pressure. Releasing residency could free capacity during idle periods but makes the next request pay an unmeasured cold reload. Residency does not speed up the decode phase. Jack must choose the policy; a scheduled Live-open soak is still needed to assess memory pressure and audio dropouts. No unload, model download, dependency installation, alternate runtime or speculative model was attempted.

## Verification and limits

Final scoped command, from `products/kenn`:

```sh
KENN_LIVE_BACKEND=fake PYTHONPATH="apps/backend/src:tooling" apps/backend/.venv/bin/python -m pytest -q -p no:randomly apps/backend/src/kenn/tests/test_measure_model_phases.py apps/backend/src/kenn/tests/test_measure_chat_latency.py -o cache_dir=/private/tmp/kenn-pcache-model-phases-final-20261003
```

Result: **27 passed in 0.23 seconds**, 3 October 2026. Tests cover native phase arithmetic, unknown/interrupted timings, gate denominator, actual payload versus stream acceptance, temporary cap isolation and restoration, early stream closure, baseline limits and scratch-only prose. No production shared entry point changed in the C2 work, so the full suite was not repeated. The immediately preceding correction change's full suite had 3575 passed, 12 skipped and one pre-existing failure: `test_personal_path_gate.py::test_the_shipped_tree_has_no_personal_path_or_remote_host` against the existing handoff. The known ordering-dependent server-smoke failure did not occur in that run.

Only one pass per condition, fixed ordering, no fixed seed, no repeat or held-out set, warm cache retained, uncontrolled background load and Live closed. The decode slowdown confounds causal latency comparison. No gate, acceptance-quality or memory/audio qualification tick is earned. C1, C2 and C3 remain unticked.
