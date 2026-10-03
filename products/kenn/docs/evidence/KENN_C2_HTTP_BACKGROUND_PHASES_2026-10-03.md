# C2 HTTP background phases, 3 October 2026

C2 stays open. Five existing diagnostic questions exercised the real HTTP template/upgrade handlers on Fake Live with the model enabled. Only **1/5 (20%)** received an accepted upgrade within 15 seconds of the initial POST. Four upgrades were eventually accepted. This is a warm, selected-set diagnostic with Live closed, not the Live-open release gate or a controlled speed comparison. C1, C2 and C3 remain unticked.

## Source and command

Measured checkout: `ee8d3f30` on `fix/review-critical-2026-10-02`. No production changes were made for this measurement. The scratch collector wraps `server.answer_payload`, routing and retrieval, and captures provider usage inside each worker thread. It starts `server.Handler` in a loopback HTTP server with isolated scratch chat/database/runtime stores. It does not call server startup, prewarm or rebuild the index.

Command from `products/kenn`, one CPU-heavy job at a time:

```sh
KENN_LLM_ENABLED=1 KENN_LLM_PROVIDER=ollama KENN_LLM_MODEL=kenn-brain-qwen3-8b KENN_LLM_CACHE=0 KENN_LLM_BACKGROUND=1 KENN_LIVE_BACKEND=fake KENN_USE_MLX=0 KENN_LLM_CRITIQUE=0 KENN_LIVE_LLM_ENABLED=0 AUDIO_TOO_LLM_ENABLED=0 PYTHONPATH="apps/backend/src:tooling" apps/backend/.venv/bin/python /private/tmp/kenn-http-background-phases-final-20261003/run.py > /private/tmp/kenn-http-background-phases-final-20261003/run.log 2>&1
```

Result: exit 0; five terminal upgrades, no pending worker overlap. Scratch `receipt.json` contains numeric measurements and Mac snapshots. Model candidates and delivered prose remain in scratch only. Collector SHA-256: `a79b2ab471a82439c4a11587c882e96385ede39c38ce37c06aef462d79fac74e`; numeric receipt SHA-256: `3aabc21420c4bcf89274418850c68f4459015680691abf6000bf4cf865e4fd7f`.

The command used `KENN_LLM_CRITIQUE=0`, which is not the reflection module's switch: that switch is `KENN_CRITIQUE_LLM_ENABLED`. Do not treat the former as configuration verification. Captured calls show one rewrite per background answer and no critique/provider calls in the foreground for these five questions. Other configurations and unknown-route questions are not qualified here.

An earlier collector attempt in `/private/tmp/kenn-http-background-phases-20261003` failed with `KeyError: session_id` after two generations. Removing the key from shared rows broke the next iteration; the final collector copies rows instead. Earlier timings are excluded. Those generations could have warmed Ollama's prefix cache before this pass, so the final pass is not an independent cold baseline.

## Native phases and delivery

All five background rewrites completed normally with `stop`, response-cache hits false, thinking off and the production 384-token ceiling unchanged. Native nonstream responses do not report first-token timing; generation TTFT remains **unknown**. HTTP template latency is not model TTFT. The earlier [stream/payload phase harness](KENN_C2_MODEL_PHASES_AND_OUTPUT_CAP_2026-10-03.md) reports stream TTFT separately.

| Case | Template HTTP s | Terminal HTTP s | Accepted | Prompt / output tokens | Prefill s | Decode s | Decode tok/s | Background retrieval ms |
| --- | ---: | ---: | --- | --- | ---: | ---: | ---: | ---: |
| bass-processing | 0.709 | 16.057 | yes | 1144 / 266 | 0.077 | 15.118 | 17.60 | 7.14 |
| sidechain-release-time | 0.062 | 9.144 | yes | 1087 / 156 | 0.067 | 8.817 | 17.69 | 26.33 |
| reverb-send | 0.060 | 15.212 | yes | 1097 / 228 | 2.436 | 12.630 | 18.05 | 18.91 |
| gain-staging | 0.045 | 12.576 | no | 1066 / 186 | 2.092 | 10.325 | 18.01 | 15.28 |
| streaming-loudness | 0.038 | 15.518 | yes | 1006 / 233 | 2.082 | 12.818 | 18.18 | 9.78 |

Foreground routing took 0.10–0.25 ms; foreground retrieval took 16–451 ms. The first request included a 164 ms index load. Background routing took 0.04–0.09 ms; repeated retrieval took 7–26 ms. Native warm model loads took 0.8–5.1 ms. No foreground provider calls occurred. Cached prompt-token counts were 646–1143, with no prompt-cache reset.

The [2 October stubbed upgrade-path measurement](KENN_UPGRADE_PATH_REPEATED_WORK_2026-10-02.md) already found about 25 ms of repeated work per question. This real-model pass supports its scale, not a new optimization claim. Current `route_query` honors `allow_llm=False`; the historical plan observation about an unguarded route-classification call must not be read as the current implementation. These recognized questions do not prove the unknown-route branch.

Only sidechain met timely acceptance; a fast rejected answer still fails the delivery criterion. Read all five private candidates. Gain staging was rejected by existing checks. Accepted reverb wording confused send/return monitoring, and accepted loudness advice still contained problematic blanket targeting and peak guidance. Automated acceptance is not human workflow correctness. No grounding check was relaxed, and no model prose is reproduced here.

## Mac state and research decisions

Snapshots: 03:40:10–03:41:19 UTC, 3 October 2026. Apple M3, 16 GiB; Ollama 0.34.4, resident model ID `90a5eaf166fd`, 5.4 GB, 100% GPU, context 4096; existing index `v-db8c6334cf63`. Live was absent. The application process inventory found Calendar, ChatGPT, Clock, FindMy, Flux, Home, Mail, Notes, Ollama, Siri AI, Stocks, Visual Studio Code and Weather. Codex was conducting the measurement. The inventory does not assign CPU load to applications or cover every service.

Swap used: 13365.75 → 13181.75 MiB. With 16 KiB pages, wired pages: 456341 → 458254; compressor occupancy: 192991 → 211397. No thermal, incremental memory attribution or audio-dropout telemetry was collected. Background load and warm-cache order were uncontrolled. Polling every 50 ms measures terminal availability more closely than the UI's normal 2-second polling interval; it is not a UI delivery measurement. This isolated server also omits normal application startup/keep-warm behavior.

Re-read the [speed shortlist](KENN_SPEED_RESEARCH_2026-10-03.md) and [broader fixed-model research](../research/KENN_PRODUCT_AND_OPEN_SOURCE_RESEARCH_2026-10-02.md#12-accelerating-the-fixed-qwen-models-follow-up-findings). Their external hardware numbers remain hypotheses. Priorities from our measurements:

- Thinking is already off. Repeated retrieval is milliseconds; decoding is seconds. Do not claim a 1.5x engine gain from prefill/cache tuning.
- The [128-token cap](KENN_C2_MODEL_PHASES_AND_OUTPUT_CAP_2026-10-03.md) and [brief-style trial](KENN_C2_BRIEF_STYLE_AND_RUNTIME_PROPOSAL_2026-10-03.md) remain disabled: neither gave reliable improvement across both surfaces, and quality declined. Jack decides answer style.
- Residency holds about 5 GB alongside a future Live session to avoid an unmeasured cold reload. Current 30-minute request residency and 240-second keep-warm pings remain unchanged. Jack decides; Live memory pressure and audio continuity remain open.
- The existing exact Qwen3 8B / approximately 1,100-token [MLX comparison proposal](KENN_C2_BRIEF_STYLE_AND_RUNTIME_PROPOSAL_2026-10-03.md) remains a proposal. No MLX runtime, speculative draft, dependency or model file was installed or downloaded. External Qwen3.5/M3 Ultra and Llama/M3 Pro results do not establish our M3/16 GiB throughput.
- Correct answer context and cache identity remain useful quality work, but those repairs have not demonstrated faster decoding. No sealed held-out ranking rows were opened.

## Scoped verification

After generation finished, from `products/kenn`:

```sh
KENN_LIVE_BACKEND=fake PYTHONPATH="apps/backend/src:tooling" apps/backend/.venv/bin/python -m pytest -q --tb=short -p no:randomly apps/backend/src/kenn/tests/test_measure_model_phases.py apps/backend/src/kenn/tests/test_measure_chat_latency.py apps/backend/src/kenn/tests/test_llm_usage_telemetry.py apps/backend/src/kenn/tests/test_answer_upgrade_context.py -o cache_dir=/private/tmp/kenn-http-phase-scoped-20261003-0344
```

Result: **75 passed in 3.65 seconds**, exit 0. Only this receipt and an unticked plan progress entry change; no full-suite repeat for documentation. The preceding full backend run had 3668 passed, 12 skipped and the pre-existing `test_personal_path_gate.py::test_the_shipped_tree_has_no_personal_path_or_remote_host` failure against existing handoff content. The known ordering-sensitive server-smoke failure did not occur in that run. No plan qualification tick is earned.
