# C2 research follow-through, 3 October 2026

C2 stays open. The speed research is a test shortlist, not evidence of a speedup on this M3 / 16 GB. This follow-through tests a complete shorter-answer instruction in the diagnostic harness only. Production answer style, the 384-token ceiling, grounding policy and residency stay unchanged. C1, C2 and C3 remain unticked; the Live-open 15-second gate is still failed.

## Research triage

Read [the speed shortlist](KENN_SPEED_RESEARCH_2026-10-03.md), [the broader product/runtime research](../research/KENN_PRODUCT_AND_OPEN_SOURCE_RESEARCH_2026-10-02.md#12-accelerating-the-fixed-qwen-models-follow-up-findings), and [our phase/cap receipt](KENN_C2_MODEL_PHASES_AND_OUTPUT_CAP_2026-10-03.md).

- Thinking is already off. No repeat implementation or thinking experiment.
- Decode dominates completed answers in our measurements. A shorter complete answer can reduce that work, whereas the earlier bare 128-token cap truncated every accepted answer. Test style separately from a cap.
- Warm-prefix reuse already appears in native telemetry. It can save prefill but cannot remove the decode budget. Do not shorten grounding instructions to chase it.
- Warm load times were milliseconds. Keeping the model resident avoids an unmeasured cold reload but cannot accelerate decode. The existing 30-minute setting and 240-second backend ping hold about 5.4 GB; a running ping can renew residency indefinitely. Jack chooses the policy. Live memory pressure and audio dropouts remain questions for his scheduled soak.
- MLX is a plausible decode experiment, with contested results on other hardware. Their ratios are not predictions for this Mac. The exact comparison proposal below requires approval for its runtime and model assets; nothing was installed or downloaded.
- Speculative decoding adds a draft/runtime and memory competition on 16 GB. Draft acceptance and total latency must be measured together; no draft was added. KV quantization, larger context, forced Metal options, extra parallel slots and a new reranker are not justified by these measurements. No index rebuild.

The broader research also makes quality part of the speed decision: count rejections and wrong advice, keep unknown telemetry unknown, and use independent held-out questions before adopting a change. This selected five-question diagnostic is not a held-out comparison.

## Isolated experiment and verification

Baseline source commit: `ad6a84a2bc5751d26082a728253803e82d1c9308`. Experiment source commit: `d6c8d9d3a67591e85544669d5113487d4815126a`.

Exact files changed for the executable experiment:

- `tooling/scripts/measure_model_phases.py`: adds opt-in `--answer-style brief`, appending an 80-word target to the final user message for ordinary rewrite calls. All system grounding and evidence messages remain intact. Required sections, citations and safeguards take precedence over the length target. The 384-token ceiling stays; simultaneous cap/style experiments are rejected. Caller-owned messages and production functions are restored/unmodified.
- `apps/backend/src/kenn/tests/test_measure_model_phases.py`: checks both surfaces, preserved system grounding and caller messages, unchanged ceiling and exclusion of other tasks, actions and structured contracts.

Both measurements ran sequentially from `products/kenn`, with fresh scratch storage and no other foreground CPU-heavy engineering job:

```sh
KENN_LLM_ENABLED=1 KENN_LLM_PROVIDER=ollama KENN_LLM_MODEL=kenn-brain-qwen3-8b KENN_LLM_CACHE=0 KENN_USE_MLX=0 KENN_CRITIQUE_LLM_ENABLED=0 KENN_LIVE_BACKEND=fake PYTHONPATH="apps/backend/src:tooling" apps/backend/.venv/bin/python tooling/scripts/measure_model_phases.py --runtime-dir /private/tmp/kenn-model-phases-style-baseline-20261003
KENN_LLM_ENABLED=1 KENN_LLM_PROVIDER=ollama KENN_LLM_MODEL=kenn-brain-qwen3-8b KENN_LLM_CACHE=0 KENN_USE_MLX=0 KENN_CRITIQUE_LLM_ENABLED=0 KENN_LIVE_BACKEND=fake PYTHONPATH="apps/backend/src:tooling" apps/backend/.venv/bin/python tooling/scripts/measure_model_phases.py --answer-style brief --runtime-dir /private/tmp/kenn-model-phases-brief-style-20261003
```

The six new cases first failed for the missing style argument. After implementation, final scoped verification from `products/kenn`:

```sh
KENN_LIVE_BACKEND=fake PYTHONPATH="apps/backend/src:tooling" apps/backend/.venv/bin/python -m pytest -q -p no:randomly apps/backend/src/kenn/tests/test_measure_model_phases.py apps/backend/src/kenn/tests/test_measure_chat_latency.py -o cache_dir=/private/tmp/kenn-pcache-brief-style-final-20261003
```

Result: **33 passed in 0.79 seconds**. No production shared module changed, so the full suite was not repeated. The last full KENN suite had 3605 passed, 12 skipped and one pre-existing failure: `test_personal_path_gate.py::test_the_shipped_tree_has_no_personal_path_or_remote_host`, against the existing handoff checkout path. That failure is not hidden or fixed by this experiment.

## Measured result and answer review

Each condition attempted all five eligible questions on each surface, with one rewrite provider call per question. Both commands exited 0. Acceptance uses the existing product validation outcome; rejected/fallback answers remain in the denominator.

| Condition | Stream accepted | Stream accepted within 15 s | Payload accepted | Payload accepted within 15 s |
| --- | --- | --- | --- | --- |
| Fresh current-style baseline | 4/5 | 2/5 (40%) | 3/5 | 2/5 (40%) |
| Brief style, same 384-token ceiling | 3/5 | 3/5 (60%) | 2/5 | 1/5 (20%) |

The diagnostic recovers one timely accepted stream answer and loses one on payload. Neither reaches 70%. All ten brief generations stopped normally, with no length-limit truncation; one baseline stream was interrupted by a measurement guard. The shorter instruction adds 70–71 prompt tokens. Completed-call decode throughput is 17.69–18.23 tok/s at baseline and 17.29–18.16 tok/s with brief style: this is less output work, not an engine speedup. It does not establish a 1.5x gain against the earlier approximately 13 tok/s observation. Conditions differ in cache/background state and generated content; one sequential pass cannot establish a causal or stable speedup.

Native prefill and decode times below come from Ollama's returned durations. Total starts at chat entry and ends at the final validated answer/fallback. Stream TTFT is shown as generation / delivered: the first starts at the completion function, the second at chat entry. Payload TTFT and interrupted native measurements remain unknown. Provider token counts of zero on the interrupted call are not evidence of zero work.

### Stream phase rows

| Condition / question | Accepted | Total s | Prompt / output tokens | Prefill s | Decode s | Decode tok/s | TTFT generation / delivered s |
| --- | --- | --- | --- | --- | --- | --- | --- |
| current / bass-processing | yes | 15.957 | 1144 / 218 | 3.103 | 12.046 | 18.098 | 3.332 / 3.941 |
| current / sidechain-release-time | yes | 11.318 | 1087 / 159 | 2.428 | 8.723 | 18.228 | 2.530 / 2.639 |
| current / reverb-send | yes | 15.261 | 1097 / 228 | 2.429 | 12.651 | 18.023 | 2.463 / 2.643 |
| current / gain-staging | no | 6.117 | unknown / unknown | unknown | unknown | unknown | 2.268 / 2.356 |
| current / streaming-loudness | yes | 11.901 | 1006 / 212 | 0.057 | 11.683 | 18.146 | 0.169 / 0.252 |
| brief / bass-processing | yes | 14.209 | 1215 / 190 | 2.808 | 10.717 | 17.729 | 2.895 / 3.524 |
| brief / sidechain-release-time | no | 11.763 | 1157 / 160 | 2.785 | 8.839 | 18.103 | 2.862 / 2.972 |
| brief / reverb-send | no | 13.007 | 1168 / 180 | 2.913 | 9.924 | 18.138 | 2.947 / 3.129 |
| brief / gain-staging | yes | 10.300 | 1137 / 134 | 2.704 | 7.380 | 18.156 | 2.861 / 2.953 |
| brief / streaming-loudness | yes | 7.854 | 1077 / 130 | 0.603 | 7.169 | 18.134 | 0.637 / 0.725 |

### Payload phase rows

| Condition / question | Accepted | Total s | Prompt / output tokens | Prefill s | Decode s | Decode tok/s | TTFT generation / delivered s |
| --- | --- | --- | --- | --- | --- | --- | --- |
| current / bass-processing | no | 15.261 | 1144 / 219 | 2.766 | 12.341 | 17.746 | unknown / unknown |
| current / sidechain-release-time | yes | 12.366 | 1087 / 171 | 2.817 | 9.440 | 18.115 | unknown / unknown |
| current / reverb-send | yes | 15.758 | 1097 / 230 | 2.889 | 12.788 | 17.986 | unknown / unknown |
| current / gain-staging | no | 11.320 | 1066 / 158 | 2.509 | 8.730 | 18.098 | unknown / unknown |
| current / streaming-loudness | yes | 9.630 | 1006 / 168 | 0.058 | 9.497 | 17.689 | unknown / unknown |
| brief / bass-processing | yes | 15.246 | 1215 / 212 | 3.316 | 11.819 | 17.938 | unknown / unknown |
| brief / sidechain-release-time | no | 12.348 | 1157 / 155 | 3.321 | 8.798 | 17.617 | unknown / unknown |
| brief / reverb-send | no | 13.532 | 1168 / 178 | 3.384 | 10.054 | 17.704 | unknown / unknown |
| brief / gain-staging | no | 10.334 | 1137 / 131 | 2.961 | 7.262 | 18.039 | unknown / unknown |
| brief / streaming-loudness | yes | 7.290 | 1077 / 123 | 0.063 | 7.113 | 17.291 | unknown / unknown |

### Quality findings and decision

Read the ten brief candidates and their delivered answers, then the matching baseline answers in scratch. No model prose is included here. The findings are qualitative inspection, not a scored held-out evaluation:

- Bass answers retain the conditional low-mid cut, harmonics step and listening check. They complete rather than truncate, but the payload answer still takes 15.246 s. The word target is soft and does not guarantee a token budget.
- Sidechain and reverb change from accepted in the baseline to rejected on both surfaces. The two stream warnings identify measurements attributed to excerpts that do not contain them. Payload records rejection without exposing that reason through this harness; do not invent it. Grounding checks stay unchanged.
- The brief reverb candidates omit the fully wet return-device setting that the baseline retains. A shorter complete sentence is not proof that a useful workflow stayed complete.
- The accepted brief gain-staging stream adds limiting/normalization/compression advice that needs source and human review. Baseline gain-staging fallback and candidates already have advice problems; this run cannot attribute the broader issue to shortening.
- Loudness remains automatically accepted, but both conditions need review of platform-specific claims and limiter/peak-unit advice. Acceptance alone does not certify correctness. The brief payload wording leaves the peak settings ambiguous rather than resolving the existing issue.

Recommendation to Jack: **do not adopt this brief instruction from this sample**. It avoids hard truncation but loses acceptance and a workflow setting. Jack retains the style decision; production has not changed. The next quality work should examine citation-to-measurement association and preservation of required workflow/safety steps with named regression examples and independent questions, rather than relaxing the guard. Any revised style needs a new isolated paired measurement and held-out quality review.

### Machine state, provenance and limits

- Apple M3, 16 GiB; Ollama 0.34.4. Model `kenn-brain-qwen3-8b`, digest `90a5eaf166fdda7e95441577e6ae96ebacf3248772a4366d1199b7b6ac0b0405`, Qwen3 8B Q4_K_M. Ollama reported 5.4 GB resident, 100% GPU, context 4096 before/after both blocks.
- Baseline snapshots: 00:49:48–00:51:53 UTC, 3 October 2026; brief: 00:54:09–00:56:05 UTC. Live was absent throughout. Codex was active; the process inventory also found Calendar, ChatGPT, Clock, FindMy, Flux, Home, Mail, Notes, Ollama, Siri AI, Stocks, Visual Studio Code and Weather. This inventory does not measure their CPU use.
- Reported used swap: baseline 10255.88 → 10272.50 MiB; brief 10256.50 → 10216.50 MiB. Background load was not controlled. These snapshots establish neither thermal throttling nor a cause of latency. No Live memory-pressure or audio-dropout conclusion.
- Same question SHA-256: `502d9c5bcec3605ef5959b0792b171f13f01f91e76ca0cc84eec2838d83aec4f`; same existing index `v-db8c6334cf63`, not rebuilt. Baseline harness SHA-256: `2b4f64f8a8779bafb7bf1b17330998f17e2176a18e97bc2edd07ff282868abcb`; brief harness: `80d13c3b3dc1b89f15b05abb41687cb8ec21c4b11a0998fac980c70168cf0ae4`.
- Rewrite/route/paraphrase/followups use the same model and 20 s task timeout, evidence context 1200 characters, thinking disabled, response cache disabled, native prompt cache and warm residency not reset. Provider loads on completed calls were milliseconds; cold reload was not tested.
- Numeric telemetry and model prose remain separately in each command's scratch directory (`receipt.json` and `answers.jsonl`). Only this numeric/qualitative receipt is committed. No private audio or session content used.
- Five selected synthetic questions, one pass per condition, fixed order, backend calls only. No independent held-out set, UI delivery, scheduled Live soak or statistical qualification. The diagnostic is not the release gate and cannot tick C1/C2/C3.

## Exact MLX comparison proposal — approval required, not executed

1. Use this Apple M3 / 16 GiB, the same existing retrieval index and Fake Live. Freeze the baseline commit, runtime settings and synthetic question set. Do not use private audio or session content. Record background apps, memory/swap/pressure and thermals if available before/after each block. Run only one heavy job at a time.
2. Baseline is Ollama 0.34.4, `kenn-brain-qwen3-8b`, digest `90a5eaf166fdda7e95441577e6ae96ebacf3248772a4366d1199b7b6ac0b0405`, Qwen3 8B parent `Qwen3-8B-Q4_K_M.gguf`. Candidate is **the same Qwen3 8B checkpoint lineage**, converted to MLX 4-bit format. Inspect the local model's full provenance first, including any adapter/custom template. Pin the original checkpoint revision, tokenizer, chat template, conversion recipe, quantization/group size and complete asset hashes. If lineage cannot be established, stop the comparison. Never substitute Qwen2.5 1.5B (the current MLX engine default), Qwen3.5 or a different-sized model.
3. Before execution, give Jack a concrete runtime/version/dependency manifest and model source/size manifest to approve. A new `mlx-lm` installation or MLX-format download/conversion is not authorized by this proposal. The candidate adapter must expose comparable phase metrics and pass existing task/grounding contracts before timing. No production backend switch. This proposal does not invent a working MLX benchmark CLI.
4. Capture the **original approximately 1,100-token KENN request** (system policy, evidence and user query) into scratch and replay identical messages to both runtimes. Hash the serialized request, record actual token counts under each tokenizer/template, and report any differences. Keep context 4096, thinking disabled, current answer style and output ceiling 384, sampling settings aligned, and response caches off. Do not combine the brief-style experiment, shorter evidence, speculative decoding or changed residency with the runtime comparison. Q4_K_M and MLX 4-bit quantization differ, so this compares two runtime/asset packages, not pure engine speed in isolation.
5. First run a decode-only diagnostic on that fixed prompt with a declared 256-token budget and identical stop handling; report tokens actually emitted and early stops. Do not bypass grounding for delivered product answers. Separately run the five diagnostic questions on stream and payload, with normal stopping and full validation. Extend to at least 30 unsealed questions, then an independent held-out set of at least 150 with missing evidence, corrections, unknown capability and workflow safety before a production decision. Do not tune against the held-out set.
6. Run three paired repetitions per condition, alternating runtime order across pairs. Keep only one model resident at a time to avoid measuring two-engine memory contention. After Jack approves residency changes for this comparison, record precisely how cold state is established; a fresh Python process is not evidence of a cold model. Measure cold-load blocks separately, then labelled warm-model/cold-prefix and warm-prefix blocks. Repeat identical cache priming for both engines and record cached-prefix counts when available. Unknown cache state stays unknown.
7. Report load time, **prefill seconds and prompt tokens separately from decode seconds and output tok/s**, generation TTFT, delivered stream TTFT, total validated-answer time and p50/p95. Payload TTFT stays unknown unless separately instrumented. Declare instrumentation boundaries for each engine and never label TTFT as completion. Include every eligible request, not just accepted/fast answers: attempted, accepted, useful/supported, rejected, interrupted, timeout and fallback counts with reasons. Keep model prose only in scratch for blind human review.
8. A candidate needs repeatable decode or end-to-end benefit and no material loss of supported/useful answers or safety. The broader research's 20% dominant-stage/p95 improvement is an experiment selection threshold, not the product gate. Roughly 1.5x decode is a workload hypothesis at 13 tok/s, not a guarantee of 15-second delivery. Only Jack's later scheduled Live-open soak can assess memory/audio and the actual gate: at least 70% of eligible knowledge requests accepted within 15 seconds on both surfaces. Fake Live results cannot tick C1/C2/C3.

No runtime, dependency, model asset, permissions, CI, production style, grounding or residency change is part of this receipt.
