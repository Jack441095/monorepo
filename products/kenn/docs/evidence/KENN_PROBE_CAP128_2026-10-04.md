# 47-question probe with the 128-token cap, 4 October 2026

The 15 s gate is still failed, so C1, C2 and C3 stay open. The plan's gate is 70% of eligible requests accepted within 15 s. The first three probes with the cap were slow (0 to 4 model answers inside 15 s). The fourth, run later the same morning, was fast: all 23 model answers arrived inside 15 s, but only 23 of 46 attempts were accepted (50%), under the 70% bar. We do not know why the first three were slow. Fake Live backend, no code changed, no index rebuild. Runs 2 to 4 had **Ableton Live open the whole time**; run 1 had Live quit a minute in and is kept for comparison. These are Live-open timings, not a supervised Live qualification.

## Source and setup

- Code: `54743a01` on `fix/review-critical-2026-10-02`. `MAX_TOKENS_BY_MODE` is 128 for every prose mode (including `voice`) and 256 for `command`.
- Apple M3, 16 GB. `kenn-brain-qwen3-8b` (id `90a5eaf166fd`), 100% GPU, context 4096, response cache off, `KENN_LLM_BACKGROUND=1`, `KENN_CRITIQUE_LLM_ENABLED=0`, `KENN_USE_MLX=0`. The model was loaded with a one-token request before each run.
- Companion started with `tooling/scripts/run_fake_live_companion.py --port 8090 --state-dir <tmp>` (temporary chats dir and DB), stopped by PID afterwards.
- Raw answers (`/tmp/kenn-probe-cap128*.jsonl`, `.review.md`) stay local and are not in git.

```sh
tooling/scripts/probe_advanced_questions.py --endpoint http://127.0.0.1:8090 --wait-upgrade 90 --output /tmp/kenn-probe-cap128-run3
```

## Probe against the 3 October Mac baseline

| Measure | Baseline | Run 4, Live open | Run 3, Live open | Run 2, Live open | Run 1, Live quit at 1 min |
| --- | ---: | ---: | ---: | ---: | ---: |
| Delivered by the model / by the template | 21 / 26 | 23 / 24 | 20 / 27 | 18 / 29 | 22 / 25 |
| Model attempted | 46 of 47 | 46 of 47 | 46 of 47 | 46 of 47 | 46 of 47 |
| Template rows that were a rejected upgrade | 25 of 26 | 23 of 24 | 25 of 27 | 28 of 29 | 24 of 25 |
| Unsupported measurements / fabricated sources | 0 / 0 | 0 / 0 | 0 / 0 | 0 / 0 | 0 / 0 |
| Abstentions | 0 | 0 | 0 | 0 | 0 |
| `expected_abstain_handled` | not reported | 2 of 3 | 2 of 3 | 2 of 3 | 2 of 3 |
| Forbidden names | 0 | 0 | 0 | 1 | 0 |
| Mean concept recall (keyword check, not a grade) | 0.64 | 0.62 | 0.61 | 0.63 | 0.62 |
| Final time p50 / p95 / max (all 47) | 18.2 / 26.2 / 28.2 s | 10.1 / 12.1 / 12.2 s | 30.2 / 40.3 / 90.4 s | 32.2 / 39.7 / 42.4 s | 28.2 / 36.2 / 52.4 s |
| Finished within 15 s | 9 of 47 (model 2) | 47 of 47 (model 23 of 23) | 14 of 47 (model 4 of 20) | 7 of 47 (model 0 of 18) | 6 of 47 (model 0 of 22) |

In run 4 every model answer took 10.1 to 12.2 s (15 at about 10.1 s, 8 at about 12.1 s). Times are polled at about 2 s and every answer hits the 128-token cap, so they bunch. In run 3 one question (`live-resampling`) was still pending when the 90 s wait ran out, which is the 90.4 s max and the one template row that was not a settled rejection. The four model answers inside 15 s took 10.1 to 12.1 s; the other 16 took 20 to 40 s. In runs 1 and 2 every model answer took 26 s or more. Times are polled at about 2 s.

Weakest categories by recall (run 3): `scope` 0.0 (2 questions), `underspecified` 0.0 (1), `dynamics` 0.47, `psychoacoustics` 0.48 (0 of 4 by the model), `digital_and_gain` 0.5, `robustness` 0.5 (0 of 2 by the model).

## Why the gate refused the model's answers

The probe rows cannot say: `warnings` is empty on every rejected row in all four runs, because the background path returns the template and drops the validation result. The reasons are in the route log (`.runtime/logs/routes.jsonl`, ignored by git), written by `_log_generation_outcome`. Attempts logged in the run window:

| Outcome | Run 4 | Run 3 | Run 2 |
| --- | ---: | ---: | ---: |
| accepted | 23 | 20 | 18 |
| generated answer introduced unsupported measurements | 12 | 11 | 13 |
| generated answer has insufficient evidence overlap | 3 | 4 | 3 |
| generation returned no answer | 2 | 3 | 4 |
| generated answer names a product that nobody mentioned | 1 | 1 | 2 |
| below the quality threshold / attributes a measurement to an excerpt | 0 / 0 | 1 / 0 | 0 / 1 |

Those counts total 41, 40 and 41, short of the 46 attempts the probe saw; we have not worked out where the rest are logged. Unsupported measurements is the largest rejection in all three runs, 11 to 13 of about 40 attempts; the flagged values in run 3 were all frequencies, milliseconds and dB figures the retrieved notes did not contain.

## What the answers look like

- Read by hand: all 20 model answers in run 3 end mid-sentence, mid-citation or on an unfinished step or heading (17 of 18 in run 2). In run 4 a last-character check puts 21 of 23 in that state (a rough count; a full stop is not proof an answer finished). The Sources list is added after the cut.
- Run 2: `lowend-fresh` was delivered by the model and named FabFilter, which the question did not. The 3 October unasked-product guard did not reject it; we have not checked whether the cited notes mention the brand. In run 3 that question was answered by the template.

## Where the time goes

Runs 1 to 3 and run 4 are the same code, runner and settings, and run 4 was fast. The Ollama runner (PID started 10:30) was one process across all of them, so the model was not reloaded between the slow and fast stretches. Run 3 itself changed partway: model calls took 30 s or more until about 10:49 and about 10 s from 10:52, and everything after that, including run 4 (11:17 to 11:26), stayed at 10 to 12 s. What changed at about 10:50 is not established. A caffeinate process (`-dim`) had been started at 10:52, which looked like the cause, so we tested it:

| Block (8 different questions each) | Caffeinate | Model answers | Final p50 / max | Decode before / after |
| --- | --- | ---: | --- | --- |
| A1, 11:10 | on | 5 of 8, all inside 15 s | 10.1 / 12.1 s | 17.8 / 16.0 tok/s |
| B, 11:12 | **off** | 1 of 8 | 10.1 / 10.1 s | 16.0 / 16.1 tok/s |
| A2, 11:14 | on | 5 of 8, all inside 15 s | 10.1 / 12.1 s | 16.1 / 16.0 tok/s |

Decode was 16 tok/s with caffeinate on or off, and the off block was as fast as the on blocks, so caffeinate is not the cause of the slow stretch (at least over five minutes of back-to-back use). The decode check is a fixed 92-token request sent straight to Ollama. The one model answer in block B is a gate result (different questions), not a sign that caffeinate changes acceptance. Swap was 1.6 GB throughout.

In the slow part of the morning (run 3), of 41 timed calls about 5 took under 10 s, 4 took 10 to 20 s, 13 took 20 to 30 s and 19 took 30 s or more. So the model call is the time. A 128-token answer at the decode speeds measured earlier (12 to 15 tok/s) should take about 13 to 15 s including prefill, so most calls ran at a third of that speed or worse.

## Machine state

| | Run 3 before | Run 3 during (49 samples, 30 s apart) | Run 3 after |
| --- | --- | --- | --- |
| Ableton Live CPU | 67% | 34% / 57% / 68% (min / mean / max) | 61% |
| Ollama runner CPU | idle | 7.5% mean, 26.6% max | 0.4% |
| Memory free (`memory_pressure`) | 76% (model not yet loaded) | 25% to 36% | 28% |
| Swap used | 1,309 MB | 1,301 to 1,656 MB | 1,576 MB |
| Wired / compressor | - | - | 7.9 GB / 3.4 GB |

Run 2 ran at 23% to 31% free with swap between 768 MB and 1,509 MB. Swap was already above 1.1 GB before either Live-open run started.

## Limits and what this does not show

- One pass per condition, and run-to-run spread is large: the three runs differ by up to four model answers and about 4 s at p50, and run 3 alone had four fast model answers the others did not. Treat the model/template split as noise.
- We do not know why runs 1 to 3 were slow. It is not caffeinate (tested above), and it was not a runner restart. Memory pressure and swap are suspects, not findings; a crude check of answer time against swap in run 2 (correlation -0.24 overall, 0.59 among answers over 25 s, 7 answers at 1 GB of swap or more) was weak, and the baseline's memory state was not recorded.
- The cap shortens answers and cuts nearly all of them off. It brought every model answer under 15 s in run 4 but not in runs 1 to 3, so one fast run is not enough, and speed is only half the gate: acceptance has to reach 70% as well, and the result needs to repeat, including on a cold start and after the Mac has been used for something else.
- Keyword recall is not a grade, and the 2-of-3 abstain figure is three questions.
- The 15 s gate is failed. Run 4 was fast but accepted 23 of 46 attempts (50%) against the plan's 70%, and runs 1 to 3 were slow. C1, C2 and C3 stay open until acceptance and speed both hold on repeat runs and a Live-open soak has run, and until the cut-off answers are dealt with.
