# Post-routing conversation diagnostic, 3 October 2026

Measured commit: `3163d276a34259d726623059bfdd1d18b914ef64` (limiter implementation `7be9d57e2b1439bb1464b3bc128e7fca45dfe1b8`). This receipt adds evidence only; no model, answer style, grounding, residency or qualification setting changes.

## Command and machine

Ran once, sequentially, from `products/kenn`, 02:04:40–02:08:10 UTC:

```sh
KENN_LLM_ENABLED=1 KENN_LLM_PROVIDER=ollama KENN_LLM_MODEL=kenn-brain-qwen3-8b KENN_LLM_CACHE=0 KENN_USE_MLX=0 KENN_CRITIQUE_LLM_ENABLED=0 KENN_CHATS_DIR=/private/tmp/kenn-c3-post-routing-rerun-20261003/chats KENN_DB_PATH=/private/tmp/kenn-c3-post-routing-rerun-20261003/kenn.db KENN_LIVE_BACKEND=fake PYTHONPATH="apps/backend/src:tooling" apps/backend/.venv/bin/python /private/tmp/kenn-c3-post-routing-rerun-20261003/run.py > /private/tmp/kenn-c3-post-routing-rerun-20261003/run.log 2>&1
```

Exit 0. The private wrapper invokes the existing thirty-turn conversation runner and records provider phase telemetry. Raw prompts, model prose and session identifiers stay outside git.

- Cases SHA-256: `3a59faff5f16e4f4bfbbd76c517adba2bbd31fe5fcbd74452c717b64ba3af691`.
- Runner SHA-256: `d33e0783c6c5e4a897496ff568bbbc95434da30a4e7f7f571df68b13476020e4`.
- Private wrapper SHA-256: `7abb4efffce951e26c7be0bd2aa75cbf6ad6e4461b0c2b39b5fa1a8c0908d5f0`.
- Index `v-db8c6334cf63`, unchanged. No index rebuild.
- Apple M3, 16 GiB; Ollama 0.34.4; Qwen3 8B Q4_K_M, digest `90a5eaf166fdda7e95441577e6ae96ebacf3248772a4366d1199b7b6ac0b0405`.
- Ollama residency 5.4 GB, 100% GPU, context 4096. Thinking off, output ceiling 384, context excerpt 1200 characters, keep_alive 30m; task timeouts 20 s. Application response cache disabled; native prefix caching remains active.
- Calendar, ChatGPT, Clock, FindMy, Flux, Home, Mail, Notes, Ollama, Siri AI, Stocks, Visual Studio Code and Weather were running. Codex was also active. No Live process. Caffeinate was active; no overlapping CPU-heavy engineering job.
- Swap used 11967.12 → 11430.69 MiB; allocated 13312 → 12288 MiB. Thermal state and background activity were uncontrolled. This does not measure Live audio or identify the cause of swap usage.

## Results and native phases

Six conversations, 30 turns, 20 answer attempts, 8 accepted, 4 accepted within 15 s, zero runner errors. Commands and clarifications are included, so neither 4/30 nor 4/20 is the eligible knowledge gate. Twelve rewrite attempts were interrupted by the grounding guard; their unreturned phase metrics remain unknown.

For the eight completed rewrite calls, min / median / max:

| Metric | Min | Median | Max |
| --- | ---: | ---: | ---: |
| Prefill, s | 0.061 | 2.486 | 6.621 |
| Decode, s | 10.389 | 11.316 | 17.878 |
| Decode, tok/s | 16.164 | 17.605 | 18.015 |

Completed outputs contained 177–321 tokens; prompts contained 998–1637 tokens. All eight ended with `stop`, with no application cache hit. One additional route call completed in 0.436 s (205 prompt / 4 output tokens, 0.066 s prefill, 0.162 s decode); it is excluded from rewrite statistics.

Elapsed and first-token time below are observed by the diagnostic runner, including fallback or clarification delivery. First-token time does not necessarily mean the first accepted model token. Dashes are missing or inapplicable metrics, never zero-cost phases.

| Conversation.turn | Route | Attempt / accepted | Elapsed s | First token s | Prefill s | Decode s | Decode tok/s |
| --- | --- | --- | ---: | ---: | ---: | ---: | ---: |
| 1.1 | production | 1 / 1 | 14.356 | 3.437 | 2.438 | 10.944 | 18.001 |
| 1.2 | ableton | 1 / 0 | 6.579 | 4.558 | - | - | - |
| 1.3 | ableton | 1 / 0 | 5.063 | 4.377 | - | - | - |
| 1.4 | production | 1 / 0 | 1.798 | 1.229 | - | - | - |
| 1.5 | out_of_scope | 0 / 0 | 0.670 | 0.670 | - | - | - |
| 2.1 | ableton_controller | 0 / 0 | 0.025 | 0.025 | - | - | - |
| 2.2 | production | 1 / 0 | 3.141 | 2.084 | - | - | - |
| 2.3 | production | 1 / 0 | 6.354 | 4.927 | - | - | - |
| 2.4 | production | 1 / 0 | 6.843 | 0.936 | - | - | - |
| 2.5 | production | 1 / 0 | 5.066 | 2.596 | - | - | - |
| 3.1 | production | 1 / 1 | 12.946 | 2.583 | 2.423 | 10.389 | 17.519 |
| 3.2 | production | 1 / 1 | 15.473 | 0.279 | 0.061 | 15.234 | 17.526 |
| 3.3 | production | 1 / 1 | 14.713 | 3.268 | 2.429 | 11.490 | 18.015 |
| 3.4 | ableton | 0 / 0 | 0.027 | 0.027 | - | - | - |
| 3.5 | ableton | 0 / 0 | 0.058 | 0.058 | - | - | - |
| 4.1 | clarify | 0 / 0 | 0.001 | 0.001 | - | - | - |
| 4.2 | production | 1 / 1 | 20.651 | 2.815 | 2.646 | 17.878 | 17.955 |
| 4.3 | production | 1 / 0 | 9.539 | 5.472 | - | - | - |
| 4.4 | production | 1 / 0 | 10.212 | 6.742 | - | - | - |
| 4.5 | production | 1 / 1 | 18.853 | 6.905 | 6.621 | 11.994 | 16.342 |
| 5.1 | production | 1 / 0 | 7.529 | 3.023 | - | - | - |
| 5.2 | ableton_controller | 0 / 0 | 0.012 | 0.012 | - | - | - |
| 5.3 | ableton | 1 / 0 | 13.268 | 5.600 | - | - | - |
| 5.4 | ableton | 1 / 0 | 6.645 | 5.903 | - | - | - |
| 5.5 | ableton | 0 / 0 | 0.000 | 0.000 | - | - | - |
| 6.1 | no_analysis | 0 / 0 | 0.012 | 0.012 | - | - | - |
| 6.2 | no_analysis | 0 / 0 | 0.007 | 0.007 | - | - | - |
| 6.3 | clarify | 0 / 0 | 0.003 | 0.003 | - | - | - |
| 6.4 | production | 1 / 1 | 13.731 | 2.820 | 2.535 | 10.950 | 16.164 |
| 6.5 | production | 1 / 1 | 15.723 | 4.623 | 4.521 | 11.141 | 17.683 |

## Reading all thirty delivered answers

- Limiter insertion now reaches the existing honest refusal in 0.012 s, with no answer-model call. The prior diagnostic spent 9.63 s generating knowledge for that command. This is a routing correction, not decode acceleration.
- Export stays on the new topic; the acoustic correction reaches knowledge routing. Cancellation and missing-analysis replies remain deterministic. The initial vocal-mud question still reaches the controller, and some named drum-reverb follow-ups still ask for an instrument unnecessarily.
- Twelve generated answers introduce unsupported numeric settings and are rejected. Several fallbacks repeat a full workflow rather than answering the specific follow-up. Threshold context is retained, but the retrieved/fallback advice concerns master distortion rather than the corrected drum bus.
- Acceptance does not establish usefulness. The accepted mono-check advice changes the mix by disabling stereo effects and centring tracks; it does not describe checking the unchanged mix summed to mono. Accepted snare guidance describes sound design instead of making an existing snare bigger. Streaming-target and phase advice also need applicability review.
- No delivered instruction echo appeared in this run. Previous echoes remain an unresolved qualification failure; one rerun does not prove a repair.

The prior diagnostic had 21 attempts, 10 accepted and 3 timely; this one has 20, 8 and 4. Routing, model sampling, native prefix warmth and Mac state differ. There is no paired speed or quality improvement claim.

## Research decisions

The [speed shortlist](KENN_SPEED_RESEARCH_2026-10-03.md) remains external hardware evidence. Our median decode rate here is 17.605 tok/s, but the old 13 tok/s observations remain valid for their runs; no engine change caused a proved gain. Even almost fully cached export prefill leaves 15.234 s of decoding. Prefix work can help individual long prompts but cannot remove that output cost.

The isolated [128-token cap](KENN_C2_MODEL_PHASES_AND_OUTPUT_CAP_2026-10-03.md) and [brief-style experiment](KENN_C2_BRIEF_STYLE_AND_RUNTIME_PROPOSAL_2026-10-03.md) did not qualify both surfaces and had quality costs. Production style remains unchanged for Jack's decision. Keep_alive holds roughly 5.4 GB and is renewed by the existing ping; cold-reload benefit and Live-open memory/audio cost remain unmeasured. Residency is unchanged.

The [product research, section 12](../research/KENN_PRODUCT_AND_OPEN_SOURCE_RESEARCH_2026-10-02.md#12-accelerating-the-fixed-qwen-models-follow-up-findings) points to output/cache contract drift and evidence applicability. A response-cache contract audit can be verified offline without changing budgets or grounding. Cache was disabled here, so it cannot explain these measured failures. MLX and speculative decoding require Jack's approval for runtime/assets; the exact Qwen3 8B comparison proposal is already written and remains unexecuted. No dependencies, downloads or new model files.

C1, C2 and C3 remain unticked. This is a streaming diagnostic, not payload/UI delivery or a held-out qualification run. Two-track choices, project switching, Live-open timing and supervised audio soak remain open.

## Scoped verification

The receipt and plan entry were checked with the existing routing, history and phase-harness tests; the exact command and result are recorded below before committing. The last full backend run on the measured code was 3635 passed, 12 skipped and one pre-existing failure: `test_personal_path_gate.py::test_the_shipped_tree_has_no_personal_path_or_remote_host`, due to the unchanged handoff note. No suppression or unrelated edit.

```sh
KENN_LIVE_BACKEND=fake PYTHONPATH="apps/backend/src:tooling" apps/backend/.venv/bin/python -m pytest -q --tb=short -p no:randomly apps/backend/src/kenn/tests/test_limiter_command_routing.py apps/backend/src/kenn/tests/test_history_boundaries.py apps/backend/src/kenn/tests/test_measure_model_phases.py -o cache_dir=/private/tmp/kenn-pcache-post-routing-receipt-20261003
```

Result: **59 passed**, 1.22 s, exit 0. `git diff --check` passed. Only this receipt and the unticked C3 plan progress entry were explicitly staged, committed and pushed to `fix/review-critical-2026-10-02`.
