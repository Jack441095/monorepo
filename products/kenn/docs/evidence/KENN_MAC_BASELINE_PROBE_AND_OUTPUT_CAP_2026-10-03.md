# Mac baseline probe and output-cap diagnostic, 3 October 2026

The 15 s gate is still failed, so C1, C2 and C3 stay open. Fake Live, **Ableton Live open** (84–95% CPU, about 14% of memory) the whole time, so these are Live-open timings but not a supervised Live qualification. One pass per condition, no code changed, no index rebuild.

## Source and setup

- Code: `5a6d3264` on `fix/review-critical-2026-10-02`. Index `v-db8c6334cf63`, 4,642 chunks, native embeddings.
- Apple M3, 16 GB. Ollama 0.35.1, `kenn-brain-qwen3-8b` (id `90a5eaf166fd`), 100% GPU, context 4096, thinking off, response cache off, `KENN_LLM_BACKGROUND=1`.
- Companion started from `products/kenn` with temporary `KENN_CHATS_DIR` and `KENN_DB_PATH`; stopped by PID afterwards. Phase runs happened with the companion stopped, one job at a time.
- Raw answers (`/tmp/kenn-probe-mac.jsonl`, `.review.md`) and phase `answers.jsonl` stay local and are not in git.

```sh
tooling/scripts/probe_advanced_questions.py --endpoint http://127.0.0.1:8090 --wait-upgrade 90 --output /tmp/kenn-probe-mac
tooling/scripts/measure_model_phases.py --runtime-dir <tmp>                      # baseline
tooling/scripts/measure_model_phases.py --output-cap 128 --runtime-dir <tmp>     # cap on its own
```

## Probe: 47 questions

| Measure | Value |
| --- | ---: |
| Delivered by the model / by the template | 21 / 26 |
| Model attempted | 46 of 47 (`followup-drums` not attempted) |
| Template deliveries that were a rejected upgrade | 25 of 26 |
| Unsupported measurements / fabricated sources | 0 / 0 |
| Abstentions | 0 |
| Forbidden names / repeated answers / errors | 0 / 0 / 0 |
| Mean concept recall (keyword check, not a grade) | 0.64 |
| Template time p50 / max | 0.09 s / 0.3 s |
| Final time p50 / p95 / max (all 47) | 18.2 s / 26.2 s / 28.2 s |
| Final time of the 21 model answers p50 / p95 / max / min | 20.2 s / 26.2 s / 28.2 s / 14.1 s |
| Finished within 15 s | 9 of 47 (model answers: 2 of 21) |

Times are polled at about 2 s, so they are coarse. Weakest categories by recall: `scope` 0.0, `psychoacoustics` 0.48, `robustness` 0.5. Model-delivered share was lowest in `robustness`, `scope` and `space_and_width` (0 of 2 each) and `loudness_and_mastering` (1 of 4).

Expected-abstain cases: `trap-offtopic` and `trap-third-party-plugin` were answered by the template; `plugin-bleed-1` was answered by the model.

### Specific cases

| Case | Delivered by | Final | Note |
| --- | --- | ---: | --- |
| `lowend-fresh` | template (upgrade rejected) | 14.1 s | recall 0.75, no forbidden name |
| `plugin-bleed-1` ("fab filter") | model, accepted | 14.1 s | read as a generic filter: "A Fab Filter is a type of audio processing tool…", "Open the Fab Filter in your DAW" |
| `plugin-bleed-2` | model, accepted | 16.1 s | recall 1.0, no forbidden name |

The model invented no brand the user had not named; it invented a product description once the user typed "fab filter". The forbidden-name check cannot see that, because the user supplied the brand.

Other findings from reading answers: `vague-vocals` ("i need help mixing vocals") returned only a background-vocals note (BV level, panning, 150–200 Hz high-pass); `psy-precedence` fell back to a generic delay answer with recall 0.25 and never named the precedence effect; `followup-bass` answered bass, not drums, with a 3:1–5:1 ratio.

## Phases, baseline against output cap 128

Five cases (`bass-processing`, `sidechain-release-time`, `reverb-send`, `gain-staging`, `streaming-loudness`) on stream and payload.

| Condition | Stream accepted | Stream accepted within 15 s | Payload accepted | Payload accepted within 15 s | Median total s (stream / payload) |
| --- | ---: | ---: | ---: | ---: | --- |
| Baseline | 5/5 | 2/5 | 3/5 | 1/5 | 15.9 / 15.5 |
| Cap 128 | 4/5 | 4/5 | 4/5 | 4/5 | 10.9 / 10.6 |

- Prompt: 1,006–1,097 tokens. Prefill 2.5–3.5 s, or 0.06–0.08 s on an Ollama prompt-cache hit.
- Decode: baseline 15.3–16.5 tok/s on stream and 11.7–15.4 on payload; cap 12.6–13.6 on stream and 12.3–14.5 on payload. The cap helps by emitting fewer tokens, not by decoding faster.
- Stream time to first token about 2.8–3.4 s without a prompt-cache hit, 0.2–0.8 s with one. Payload TTFT is unknown.
- Answer length: baseline 117–268 words, cap 80–100 words for the accepted ones.
- Both `gain-staging` rows under the cap were not accepted and fell back to the template. One accepted stream answer (`sidechain-release-time`) was cut mid-sentence before its Sources list ("…ter the").

## Limits

Five questions, one pass, warm residency and prompt cache not reset, Live open but no Live writes and no dropout check. Run-to-run spread is large: the 3 October Live-closed receipt (`KENN_C2_MODEL_PHASES_AND_OUTPUT_CAP_2026-10-03.md`) saw the cap lose a payload answer where this run gained four. This does not qualify the cap and it is not enabled. Keeping it is Jack's decision; if kept it should be checked on the 47-question probe first.
