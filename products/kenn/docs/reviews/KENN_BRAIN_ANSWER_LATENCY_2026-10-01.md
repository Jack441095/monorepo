# KENN brain answer latency on the owner's M3 (1 Oct 2026)

Settles Track D1 and D2 for the M3 / 16 GB, and corrects three numbers the North Star had
carried since 26-28 Sept. Everything below was measured on this machine with Ollama on
`127.0.0.1:11434` and Ableton Live 12 open. Nothing was written to Live.

Tool: `tooling/scripts/measure_chat_latency.py`, index `v-db8c6334cf63` (4,642 chunks),
model `kenn-brain-qwen3-8b` (Qwen3 8B, 5.0 GB).

## The short answer

**D2 cannot reach p95 <= 4 s on this Mac for a brain-written answer, and Live is not the reason.** The
prompt was never the cost: prefill is ~60 ms of a ~60 s answer, and cutting the prompt by 22% moved the
median by 3 s one way and p95 by 1 s the other, which is run-to-run noise. Decoding is 300 output tokens
at 10-16 tok/s on the GPU, and KENN makes more than one model call per answer. Measured: median 60.2 s,
p95 89.5 s, 24% of attempts accepted.

The one thing that does meet the gate is the path the producer actually sees: with
`KENN_LLM_BACKGROUND=1`, **the template is on screen in 0.22 s median / 0.54 s p95**, and the model's
answer, when it is accepted at all (13%), arrives at 74 s. That path was dead until today — it accepted
0 of 30 because the background thread inherited the ask path's 20 s HTTP timeout against a 60 s answer.
Fixed and measured below.

## D1 - the numbers

30 knowledge questions each, both caches off (`KENN_LLM_CACHE=0` and the semantic answer
cache dropped before every question), nothing else running on the box:

| Surface | Asked | Brain attempted | Accepted | Median | p95 |
|---|---|---|---|---|---|
| `answer_payload_stream` (kenn.core.chat, chat_cli) | 30 | 29 | **7 (24% of attempts)** | **60.2 s** | **89.5 s** |
| - accepted answers only | | | 7 | 64.5 s | 96.0 s |
| `answer_payload` (browser companion) | 30 | **0** | **0** | 20.2 s | 20.4 s |
| templates only (no model) | 10 | - | - | 0.08 s | 0.15 s |

Receipts: `tooling/evaluation/results/KENN_CHAT_LATENCY_M3_STREAM_2026-10-01.json`,
`..._COMPANION_2026-10-01.json`, `..._PROMPT_CUT_2026-10-01.json` (the last is the cut, not a
template run).

The North Star recorded "7-16 s an answer through the companion, KENN used its answer 1 time
in 6". Neither number reproduced, and the second half of that claim is wrong in a way worth
knowing: **on the companion surface the model never wrote an answer at all** — 0 of 30, and
`llm_enhanced` was false on all 30 even though all 30 found their sources. Generation is
gated by `should_use_llm_rewrite()` on retrieval confidence, which those questions do not
clear, so what the companion spends its 20 s on is `post_answer_critique()` asking the model
to grade KENN's own deterministic template. The companion pays a fifth of a minute for
self-criticism and ships the template every time. Brain answers happen only on the streaming
path, which is why measuring only the companion measures nothing.

Rejection reasons across the 22 rejections: `generated answer introduced unsupported
measurements` on 17, `generated answer is below the quality threshold` on 7. The model's
failure mode is inventing numbers, not being slow or ungrounded in general — which is worth
knowing because it is fixable in the prompt, and the accepted answers cluster in the short
factual questions.

One question (`muddy-low-mids`) never reached the model at all, retrieval confidence below the
gate. It is counted in "asked" and not in "attempted".

## D2 - the prompt, before and after

Exact `prompt_eval_count` from Ollama, no character estimates:

Same 30 questions, streaming surface, one change at a time:

| | Prompt tokens | system | user | Accepted | Median | p95 |
|---|---|---|---|---|---|---|
| Before (`CONTEXT_CHARS=650`, `DRAFT_CHARS=300`) | **816** (849/840/759) | 534 | 318 | 7/29 (24%) | 60.2 s | 89.5 s |
| After (`CONTEXT_CHARS=300`, `DRAFT_CHARS=0`) | **637** (631/641/639) | 534 | 106 | 9/29 (31%) | 56.8 s | 90.4 s |

A first 10-question pass suggested the cut *halved* the accepted rate (2/10 to 1/10) and that
we should reject it on those grounds. That was noise: at 30 questions the cut is level to
slightly better, 7/29 to 9/29, with "unsupported measurements" down from 17 to 13. Two runs
apart on a 10-question sample is not a 10% swing worth acting on. The cut neither helps nor
hurts the answer quality.

It also does not help latency, which is the only reason to have considered it: median moved
3.4 s and p95 moved 0.9 s in opposite directions, i.e. within run-to-run variation, against
an expected gain of about 0.01 s from the 179 tokens saved.

**Where the remaining budget actually goes.** The 28 Sept note claimed the pass took the
footprint to <= 450 tokens. That figure is only true on the MLX path. `_mlx_engine_answers()`
is False here (MLX is not installed), so KENN sends `build_system_prompt()` - **534 tokens,
63% of the request** - rather than `STATIC_CORE_SYSTEM_PROMPT`. The short prompt cannot be
used on the Ollama path because it made most answers fail the structure check (26 Sept). So
816 is the real footprint, and the floor is 534 no matter how short the excerpts get.

Cutting excerpts and dropping the draft removed 22% of the tokens and the user part fell
318 -> 106 tokens. That is real, and it is the only part of D2 that works — but it buys
nothing, because prefill is 0.06 s at 356 tokens and 0.07 s at 1,028 tokens. A 179-token
saving is worth about 0.01 s of a 60 s answer. Prompt reuse between turns (the other half of
D2) cannot help a path that is 99.9% decode.

So D2 is measured and answered, and the answer is no: not on this Mac, not with this model.
The prompt is 1% of the cost. The 534-token system prompt that cannot be shortened without
breaking the structure check is 1% of the cost. The other 99% is the GPU writing hundreds of
tokens at 10-16 tok/s.

## Live open vs Live closed

The separation the North Star wants, as far as it can be had without quitting the owner's DAW.

- **Live open, idle, is not free**: `ps` CPU-time delta over a 5 s window puts Live at
  **39.8% of one core**, continuously, with nothing playing.
- **A Live-sized load costs the model nothing.** Re-running a 300-token generation with a
  synthetic load of the same size: 31.0 s idle -> 29.3 s loaded, **0.95x, i.e. inside noise**.
  Ollama decodes on the GPU via Metal; Live's 39.8% is CPU. The two do not contend for the
  resource the answer is waiting on.

So the hypothesis "Live is competing for the machine" is refuted as the driver. What is left
is the model itself. The true Live-closed half still needs someone to close Live at a natural
break; that is a 10-second owner action and it is the one thing here we did not do, because it
is not ours to do.

## Why 4 s is out of reach on this box

An answer is 2-3 sequential model calls (generation, then critique, plus validation), each
outputting hundreds of tokens at 9.7-16.4 tok/s measured here:

| Model | 120-token answer |
|---|---|
| Qwen3 8B | 11.31 s |
| Qwen3 4B | 6.90 s |
| Qwen3 1.7B | 3.17 s |
| Qwen2.5 1.5B | 2.60 s |

p95 <= 4 s is only reachable with a 1.5-1.7B model, a short answer, and fewer sequential
calls - not with 8B. The two levers that would actually move it are D3 (model choice) and
serving from the box GPU (2.8 s p50 measured on the box, 25 Sept). D2 is not one of them.

## The background swap could not work at all, and why (found and fixed 1 Oct)

The 29 Sept note asked for "Mac timing for `KENN_LLM_BACKGROUND=1` (how often the swap lands, and after
how long)". Driving the real path -- `answer_upgrades.start()` on the same calls `server.py:3019` makes --
gave **0 swaps landed out of 30**, against 7/30 on the streaming path. Two real defects, in order.

**1. The upgrade inherited the ask path's 20 s HTTP timeout.** `AUDIO_TOO_LLM_TIMEOUT` defaults to 20 s
(`llm_rewrite.py:248`), which is right for the ask path: someone is watching a spinner and needs a fast
fallback into the template. But `answer_upgrades` runs on its own thread *after* the template is already on
screen, so there is nobody to fail fast for -- and an answer on this box takes ~60 s. Every upgrade timed
out inside `enhance()`, which returned `None`, and the swap offered back the same template the producer was
already looking at. A 60 s answer against a 20 s ceiling cannot land by construction.

Fixed with `llm_rewrite.background_budget()`: a `ContextVar` (not a global -- the upgrade runs on its own
thread while the next question is answered on the request thread, so a global would hand the 120 s budget
to the ask path too and put a two-minute spinner back in front of someone who already has an answer) that
raises the ceiling for the calls made inside it. Seven tests in `test_answer_upgrade_timeout.py` pin both
halves: the ask path still fails fast at 20 s, the upgrade runs at 120 s, the budget is per-thread, and it
restores itself after an exception. Measured after the fix: **0/30 -> 4/30 landed**, so the timeout was
masking a second problem rather than being the whole of it.

**2. `valid_response()` runs only on the non-streaming path.** `enhance()` applies a structure gate
(`llm_rewrite.py:1479`) that `enhance_stream()` never calls: it requires a `Short answer:`-family header,
two `1.`/`2.`-numbered lines or a `Try this:`-family literal, and `Sources:`. The streaming path has no
structural gate at all -- only `generated_answer_validation()`. So an answer can be fully grounded, well
written and cited, and still be discarded on the non-streaming path purely for using `-` bullets instead of
numbered steps. This asymmetry is left in place and recorded here rather than changed: `valid_structure` is
a deliberate output contract shared with `answer_quality_report`, and loosening it to lift the swap rate
would be trading a real format guarantee for a number on one machine.

With the timeout fixed, the remaining 26 rejections are `generated_answer_validation` warnings, in the same
proportion as the streaming path: `unsupported measurements` on most, plus insufficient evidence overlap and
below-quality. The model states numbers that are not in the retrieved notes, and that is the gate doing its
job.

## The background swap, measured properly

Same 30 questions, `KENN_LLM_BACKGROUND=1`, template first then the model in the background, each question
asked only after the previous swap settled (`answer_upgrades` runs one answer at a time by design). Receipts:
`tooling/evaluation/results/KENN_BACKGROUND_SWAP_M3_2026-10-01.json`, with the route log it wrote.

| | Value |
|---|---|
| Template on screen | **p50 0.22 s, p95 0.54 s** |
| Swap landed | **4 of 30 (13%)** |
| Swap time, when it landed | p50 74.0 s, p95 93.9 s |
| Answer on screen (template, or template + swap) | p50 0.24 s, p95 74.4 s |
| Busy (model still writing the last answer) | 0 |

The design does what it was built for on the part that matters: **the producer sees something in 0.22 s, not
74 s**, and the Stage 1 gate of p95 <= 4 s is met on that path with room to spare (p95 0.54 s). What it does
not do is swap often -- 13% -- and when it does, the answer takes 74 s to arrive.

`route_latency_report.py`, reading the route log this wrote, independently reports the same events: 30
started, 4 accepted (13%), 26 rejected, 0 busy, accepted median 73.8 s. That is the check that the harness
and the existing tool agree, so the number is not an artifact of the new script.

The honest summary of Stage 1's item on this machine: the **template** path meets the 4 s gate comfortably,
the **brain-written answer** path is 0.22 s to first paint and then a 13% chance of a 74 s improvement. That
is a usable product, and it is not the item as written -- "chat answers written by the brain" is 13% here,
not the default.

## Two caches make this measurement reproducible

Anyone re-running this will otherwise get numbers that mean nothing:

- The **semantic answer cache** replays an identical question's events. Three questions took
  57/54/73 s on a first pass and 0.1/0.1/1.5 s on the second, with `attempted=True` throughout.
- **`KENN_LLM_CACHE`** (on by default, 512 entries, 24 h TTL, `llm_rewrite.py`) replays the
  model's response for an identical prompt. With it on, all 10 questions report
  `attempted=True` at a 0.08 s median and no model was called at all.

The script now drops the semantic cache before every question and prints the surface it used.
Run it with `KENN_LLM_CACHE=0`.

## Open gaps found on the way

- `save_reasoning_trace()` is never passed a metadata payload, so `generation_validation` and
  the top rejection warning are not persisted anywhere. The monthly "how often does the model's
  answer land" measure has no storage behind it; the numbers in this report were captured
  in-flight. `llm_usage` is empty on the streaming path too, so token counts are not available
  from KENN at runtime.
- Accepted rate is 24% on the streaming path and 13% on the background swap, against the Track D target of
  >= 70% upgrading within 15 s.
- `make_answer()` discards `validation["warnings"]` on its fallback branch -- it prints only
  `(enhanced)` or `(fallback)` and a timing -- so the reason an answer was rejected is invisible in the
  logs. Establishing the `unsupported measurements` share above meant monkeypatching the validation
  call from a harness. A `log_outcome` line per warning, as `answer_upgrades` already does for its
  accept/reject status, would make this readable without instrumentation.
- `_answer_payload_stream_raw()` reads `answer_mode` at `chat_answer.py:1397`, `:1445` and `:1453` before
  assigning it at `:1505`, with no module-level binding and no `global`, so those lines would raise
  `UnboundLocalError` if reached. They sit behind `impossible_promise_query(query)`, `route == "clarify"`
  and `route == "out_of_scope"`, none of which fire for a knowledge question, which is why nothing has
  tripped it. Not fixed here: it is a latent crash on a path this work does not exercise, and a fix
  deserves its own test.
