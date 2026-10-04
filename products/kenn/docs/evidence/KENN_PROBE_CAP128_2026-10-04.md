# 47-question probe with the 128-token cap, 4 October 2026

The 15 s gate is still failed, so C1, C2 and C3 stay open. Fake Live backend, **Ableton Live open the whole time** (checked at start and end, and every 10 s during the run), no code changed, no index rebuild. This is a Live-open timing, not a supervised Live qualification. A first run earlier the same night is also recorded below because Live quit a minute into it.

## Source and setup

- Code: `54743a01` on `fix/review-critical-2026-10-02`. `MAX_TOKENS_BY_MODE` is 128 for every prose mode (including `voice`) and 256 for `command`.
- Apple M3, 16 GB. `kenn-brain-qwen3-8b` (id `90a5eaf166fd`), 100% GPU, context 4096, response cache off, `KENN_LLM_BACKGROUND=1`, `KENN_CRITIQUE_LLM_ENABLED=0`, `KENN_USE_MLX=0`. The model was loaded with a one-token request before each run, so the first question did not pay the load.
- Companion started with `tooling/scripts/run_fake_live_companion.py --port 8090 --state-dir <tmp>` (temporary chats dir and DB), stopped by PID afterwards.
- Raw answers (`/tmp/kenn-probe-cap128-liveopen.jsonl`, `.review.md`) stay local and are not in git.

```sh
tooling/scripts/probe_advanced_questions.py --endpoint http://127.0.0.1:8090 --wait-upgrade 90 --output /tmp/kenn-probe-cap128-liveopen
```

## Probe against the 3 October Mac baseline

| Measure | Baseline | Cap 128, Live open | Cap 128, Live quit at 1 min |
| --- | ---: | ---: | ---: |
| Delivered by the model / by the template | 21 / 26 | 18 / 29 | 22 / 25 |
| Model attempted | 46 of 47 | 46 of 47 | 46 of 47 |
| Template rows that were a rejected upgrade | 25 of 26 | 28 of 29 | 24 of 25 |
| Unsupported measurements / fabricated sources | 0 / 0 | 0 / 0 | 0 / 0 |
| Abstentions | 0 | 0 | 0 |
| `expected_abstain_handled` | not reported | 2 of 3 | 2 of 3 |
| Forbidden names | 0 | 1 | 0 |
| Mean concept recall (keyword check, not a grade) | 0.64 | 0.63 | 0.62 |
| Final time p50 / p95 / max (all 47) | 18.2 / 26.2 / 28.2 s | 32.2 / 39.7 / 42.4 s | 28.2 / 36.2 / 52.4 s |
| Final time of the model answers p50 / min | 20.2 / 14.1 s | 32.2 / 30.2 s | 28.2 / 26.2 s |
| Finished within 15 s | 9 of 47 (model 2) | 7 of 47 (model 0 of 18) | 6 of 47 (model 0 of 22) |

The seven inside 15 s in the Live-open run are all template answers; every model answer took at least 30.2 s. Times are polled at about 2 s. `followup-drums` was the one question the model was not attempted on, as in the baseline.

Weakest categories by recall (Live open): `scope` 0.0 (2 questions), `underspecified` 0.25 (1), `dynamics` 0.47, `psychoacoustics` 0.48 (0 of 4 by the model), `robustness` 0.5 (0 of 2 by the model), `digital_and_gain` 0.55.

## What the answers look like (Live open)

- Read by hand: 17 of the 18 model answers end mid-sentence, mid-citation or on an unfinished step or heading; one ends cleanly. The Sources list is added after the cut.
- 28 of the 29 template answers were upgrades the gate rejected. The probe rows carry no rejection reason: `warnings` is empty on all 28 (and on all 24 in the first run), so the summary cannot say why the gate refused them. That needs recording before the next run.
- `lowend-fresh` was delivered by the model and names FabFilter, which the question did not. The unasked-product guard from 3 October did not reject it; we have not checked whether the cited notes mention the brand. The probe counts this as the one forbidden name.

## Machine state

| | Before | During (49 samples, 30 s apart) | After |
| --- | --- | --- | --- |
| Ableton Live CPU | 63% | 38% / 56% / 66% (min / mean / max) | 42% |
| Ollama runner CPU | 0.5% | 8.3% mean, 16.5% max | 0.3% |
| Memory free (`memory_pressure`) | 24% | 23% to 31% | 31% |
| Swap used | 1,147 MB | 768 MB to 1,509 MB | 1,485 MB |
| Wired / compressor | - | - | 7.4 GB / 3.3 GB |

Swap was already 1.1 GB when the run started and reached 1.5 GB. Ollama CPU is low because the model runs on the GPU.

## Limits and what this does not show

- One pass per condition. Run-to-run spread is large: the two cap runs differ by four model answers and 4 s at p50, so the 18 against 22 split is within noise.
- It does not show Live is what slowed things: the Live-closed run was also about 10 s slower than the baseline. Both cap runs were slower than the baseline at p50, and we do not know why; memory pressure and swap are suspects, not findings, and the baseline's memory state was not recorded.
- The cap shortens answers (and cuts most of them off) but did not move end-to-end time on the full 47, and the five-question phase result from 3 October did not carry over.
- Keyword recall is not a grade, and the 2-of-3 abstain figure is three questions.
- The 15 s gate is failed. C1, C2 and C3 stay open until the time is under 15 s on model answers and a Live-open soak has run.
