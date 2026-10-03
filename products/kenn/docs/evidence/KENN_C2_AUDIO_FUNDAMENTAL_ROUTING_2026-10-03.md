# C2 audio fundamental routing, 3 October 2026

C2 stays open. Three new engineering questions exposed a classifier error: precedence effect and balanced cabling were classified as out of scope; phantom power reached production after an unnecessary model route. Code commit `c26c286e803de16171d232e94221016bb96ca913` routes the complete audio terms directly. The repeated real-model diagnostic reached knowledge generation for all three questions on both surfaces, with no route-provider call. It did **not** establish useful answers or a speed gain. C1, C2 and C3 remain unticked.

## Bounded change and regression

Only `apps/backend/src/kenn/core/chat_routing.py` and `apps/backend/src/kenn/tests/test_route_query_model_free.py` changed in the code commit. The existing production keyword route now recognizes precedence effect, phantom power and balanced audio cables/connections, including case and whitespace variants. Arbitrary explanation requests and partial/non-audio terms retain their previous routes. Grounding, generation, style, token ceiling and residency are unchanged.

`test_audio_fundamentals_reach_knowledge_without_a_model_route` checks the production route with model routing allowed and disabled, and forbids a fallback model call. `test_audio_fundamental_routes_do_not_claim_partial_or_non_audio_terms` protects the boundary. Before the repair, the initial six regression cases failed and two existing cases passed. Removing the new route after the repair restored **12 failures and 6 passes**; the source was restored before the full suite.

From `products/kenn`, one CPU-heavy job at a time:

```sh
KENN_LIVE_BACKEND=fake PYTHONPATH="apps/backend/src:tooling" apps/backend/.venv/bin/python -m pytest -q --tb=short -p no:randomly apps/backend/src/kenn/tests/test_route_query_model_free.py apps/backend/src/kenn/tests/test_conversational_answer_grounding.py apps/backend/src/kenn/tests/test_chat_route_context.py apps/backend/src/kenn/tests/test_game_audio_routing_mobile_memory.py apps/backend/src/kenn/tests/test_answer_grounding_bypass.py apps/backend/src/kenn/tests/test_llm_grounding_pair.py -o cache_dir=/private/tmp/kenn-audio-fundamentals-scoped-20261003
```

Result: **64 passed, 2 warnings in 1.96 s**, exit 0. Full shared-router verification:

```sh
KENN_LIVE_BACKEND=fake PYTHONPATH="apps/backend/src:tooling" apps/backend/.venv/bin/python -m pytest -q --tb=short -p no:randomly apps/backend/src/kenn/tests -o cache_dir=/private/tmp/kenn-audio-fundamentals-full-20261003 > /private/tmp/kenn-audio-fundamentals-full-20261003.log 2>&1
```

Result: **3999 passed, 12 skipped, 5 warnings and 1 pre-existing failure in 87.03 s**, exit 1. The failure is `test_personal_path_gate.py::test_the_shipped_tree_has_no_personal_path_or_remote_host` against existing historical content. The known ordering-sensitive server-smoke failure did not occur. No dependencies or CI changed.

## Real-model command and measured phases

The existing `tooling/scripts/measure_model_phases.py` was called through isolated scratch wrappers. Baseline checkout: `6f592a3fd160660b12ac16663ef0704730408806`; repeated checkout: `c26c286e803de16171d232e94221016bb96ca913`. Both used the same three freshly authored questions: Explain precedence effect; Explain phantom power; Explain balanced cabling. No held-out rows were opened. The wrapper asserts all four task models use Ollama Qwen3 8B, thinking is off, the existing index is available, and keyword routes match the intended pre/post state. Chat/database/runtime/route logs are isolated under the wrapper directory.

Run from `products/kenn` with the following command for the repeated pass. The baseline used the identical environment with `/private/tmp/kenn-unknown-route-phases-20261003/run.py` and its corresponding `run.log`.

```sh
KENN_LLM_ENABLED=1 KENN_LLM_PROVIDER=ollama KENN_LLM_MODEL=kenn-brain-qwen3-8b KENN_LLM_MODEL_ROUTE=kenn-brain-qwen3-8b KENN_LLM_MODEL_PARAPHRASE=kenn-brain-qwen3-8b KENN_LLM_MODEL_FOLLOWUPS=kenn-brain-qwen3-8b KENN_LLM_CACHE=0 KENN_USE_MLX=0 KENN_CRITIQUE_LLM_ENABLED=0 KENN_LIVE_LLM_ENABLED=0 AUDIO_TOO_LLM_ENABLED=0 KENN_LIVE_BACKEND=fake PYTHONPATH="apps/backend/src:tooling" apps/backend/.venv/bin/python /private/tmp/kenn-audio-fundamentals-phases-20261003/run.py > /private/tmp/kenn-audio-fundamentals-phases-20261003/run.log 2>&1
```

Both exited 0. Each pass ran stream then payload serially. Baseline stream timely acceptance was 1/3; payload 0/3. Baseline precedence effect and balanced cabling skipped knowledge generation entirely. The one accepted stream answer was an abstention, not a useful explanation. Warm route calls cost 0.255–0.394 s; the naturally cold first route included 3.345 s model load and 1.185 s prefill. This small serial cost is not the main decode lever.

Repeated pass, current 384-token ceiling and style:

| Question / surface | Total s | Accepted | Prompt / output tokens | Prefill s | Decode s | Decode tok/s | Generation TTFT s | Delivered TTFT s |
| --- | ---: | --- | ---: | ---: | ---: | ---: | ---: | ---: |
| precedence effect / stream | 6.911 | no | unknown | unknown | unknown | unknown | 2.264 | 2.590 |
| phantom power / stream | 2.717 | yes | 975 / 17 | 1.725 | 0.885 | 19.21 | 1.792 | 1.872 |
| balanced cabling / stream | 2.948 | yes | 1003 / 19 | 1.902 | 0.991 | 19.17 | 1.916 | 1.997 |
| precedence effect / payload | 13.855 | no | 1020 / 213 | 2.064 | 11.695 | 18.21 | unknown | unknown |
| phantom power / payload | 2.654 | no | 975 / 17 | 1.724 | 0.876 | 19.41 | unknown | unknown |
| balanced cabling / payload | 2.948 | no | 1003 / 19 | 1.903 | 0.992 | 19.15 | unknown | unknown |

Stream timely acceptance is **2/3**, payload **0/3**, with all six rewrites attempted. Stream precedence generation was interrupted by the existing unsupported-measurement check, so native completed token/phase metrics are unavailable; zeros in interrupted telemetry are not measured zero tokens. Nonstream provider responses do not expose TTFT. Stream TTFT can include text later rejected; it is not first accepted useful text.

Read all six private candidates and deliveries. The two accepted stream answers abstain because retrieved excerpts do not cover the questions. Payload rejects these abstentions and delivers unrelated production templates. Precedence-effect generation introduces unsupported settings and is rejected on both surfaces. **Useful explanations: 0/3 on each surface**, in both passes. This is a routing correctness repair, not a quality qualification. Missing relevant retrieval and unrelated fallback delivery remain open; no grounding rule was relaxed.

## Mac state, provenance and limits

Apple M3, 16 GiB, Ollama 0.34.4, model ID `90a5eaf166fd`, 100% GPU, context 4096, existing index `v-db8c6334cf63`. Live was absent. Baseline snapshots: 06:37:55–06:38:09 UTC. Ollama residency was initially empty and ended at 5.7 GB. Repeated snapshots: 06:49:00–06:49:32 UTC, resident model 5.7 GB before and after. We did not unload/reset the model or prompt cache. Current request `keep_alive=30m` and 240-second keep-warm setting remain unchanged.

The application inventory found Calendar, ChatGPT, Clock, FindMy, Flux, Home, Mail, Notes, Ollama, Siri AI, Stocks, Visual Studio Code and Weather. Codex was conducting the work. The inventory does not measure app CPU load or every service. Baseline swap stayed 5338.94 MiB; repeated swap stayed 5314.94 MiB. At 16 KiB pages, baseline wired pages changed 139593 → 491315 and compressor occupancy 79201 → 106886; repeated wired pages 139121 → 486955 and compressor occupancy 124836 → 111098. These snapshots do not establish incremental model memory, thermal pressure or audio continuity.

Harness SHA-256: `80d13c3b3dc1b89f15b05abb41687cb8ec21c4b11a0998fac980c70168cf0ae4`; questions SHA-256: `ee5b263ca324b2edd143ecb3684a4ece311f24bc24c3dd573d96621cb5635f50`. Baseline wrapper SHA-256: `d276fd2179463083871cddb6b37ea51baba0010d2703ce0374cc65b7589ec6cc`; numeric receipt SHA-256: `aedaeb1da907c071e59679051508427b4b988114e10af28244002123d2b73725`. Repeated wrapper SHA-256: `d17df73fa01b28ca1915fd2f8ab8b6fecf91f277c20236c71f6014d09843f26a`; numeric receipt SHA-256: `0be18dc52d20cb432dc409d32df3424ccabf8bc44cd4b47fd9f57ce7a12c8677`. Model prose remains in private scratch only.

One pass per surface, selected questions, direct chat entry rather than HTTP/UI/background delivery, different natural residency and prefix-cache states. The repair changes which questions reach generation, so before/after totals do not measure engine acceleration. No Live-open soak, memory/audio qualification, index rebuild or plan tick.

## Research follow-through

Re-read the [speed shortlist](KENN_SPEED_RESEARCH_2026-10-03.md) and [fixed-model research](../research/KENN_PRODUCT_AND_OPEN_SOURCE_RESEARCH_2026-10-02.md#12-accelerating-the-fixed-qwen-models-follow-up-findings). The shortlist's other-hardware throughput figures remain hypotheses. Removing a wrong route helps correctness and avoids a small classifier call; it does not prove the roughly 1.5x decode improvement needed at 13 tok/s for 220–280-token answers. Prefill tuning cannot remove that decode floor.

The [output-cap experiment](KENN_C2_MODEL_PHASES_AND_OUTPUT_CAP_2026-10-03.md) and [brief-style trial](KENN_C2_BRIEF_STYLE_AND_RUNTIME_PROPOSAL_2026-10-03.md) remain disabled pending Jack's style decision. Their gains did not hold across both surfaces and quality declined. Thinking is already off. Residency retains about 5 GB against avoiding a cold reload; Jack decides changes and schedules the Live-open soak. The exact Qwen3 8B / approximately 1,100-token M3/16 GiB MLX comparison remains a written proposal only. No runtime, speculative draft, dependency or model file was installed or downloaded.
