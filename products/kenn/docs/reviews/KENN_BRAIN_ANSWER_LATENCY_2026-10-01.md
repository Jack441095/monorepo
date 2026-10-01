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
at 6-16 tok/s on the GPU, and KENN makes more than one model call per answer. Measured: median 60.2 s,
p95 89.5 s, 24% of attempts accepted.

**On one RTX 4090 the gate is met: 3.75 s p95 with 43% of answers landing**, and the two defects that
were capping it are fixed. The remaining gap on the Mac is not closable by this hardware at this model size.

The one thing that already met the gate on the Mac is the path the producer sees: with
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

## Live open vs Live closed, measured properly (1 Oct)

This is the separation the North Star says nobody has, so it was measured last, with the owner closing and
opening Live and the same code on both sides. Four runs, 30 questions each, `KENN_LLM_BACKGROUND=1`:

| Run | Accepted | Swap p50 | Swap p95 | Template p50 |
|---|---|---|---|---|
| Live **open**, post-fix | 10/30 | 40.3 s | 47.4 s | 0.27 s |
| Live **closed**, run 1 | 12/30 | 41.4 s | 47.0 s | 0.43 s |
| Live **closed**, run 2 | 14/30 | 39.8 s | 46.7 s | 0.43 s |
| Live open, pre-fix (for reference) | 5/30 | 81.4 s | 105.3 s | 0.12 s |

**Live costs 40.3 s open against 41.4 s and 39.8 s closed. That difference is smaller than the 1.6 s
run-to-run spread between two identical closed runs.** Live is not competing for the resource the answer waits
on: Ollama decodes on the GPU via Metal, and Live's cost is CPU. Measured as such, Live sat at 39.8% of a core
when first checked and **57.5%** when it was reopened for this test — a large and variable tax on the CPU that
does not reach the GPU decode loop.

An earlier reading of this section claimed Live *did* cost about 2x (81 s open against 41 s closed). That was
wrong, and the reason is worth recording because it is the same trap twice: the 81 s figure came from the run
**before** the thinking fix, so it differed from the 41 s in two ways at once — Live state *and* the fix. The
controlled-load experiment had already contradicted it at 0.95x, and I read that as "Live is not the reason"
while still quoting the confounded 2x elsewhere. One change at a time, and when a number is surprising, distrust
it before believing it.

So the answer to "the model is slow, or Live is competing" is: **the model is slow.** 40 s with or without Live,
against a 4 s gate.

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

## The box GPU: the gate is reachable off the Mac (1 Oct, later the same day)

The North Star has carried "or serving the brain from the box GPU (2.8 s) for the owner's own use" since 25
Sept, with no receipt behind the 2.8 s. Measured properly, on an RTX 4090 (GPU 0, one of the two GPUs
AGENTS.md authorises for KENN work; 2-7 untouched), same index, same 30 questions, same `qwen3` model at the
same Q4_K_M quantisation, reached over an SSH tunnel:

| | Mac M3 (local ollama) | Box, 1x RTX 4090 | Ratio |
|---|---|---|---|
| Raw decode, 300 tokens | 40.6-47.9 s eval, 6.3-7.4 tok/s | **2.12 s eval, 141.3 tok/s** | **~20x** |
| Streaming path, 30 questions | 60.2 s median, 89.5 s p95 | **5.2 s median, 7.5 s p95** | **~12x** |
| Background swap, template on screen | 0.12 s p50, 0.96 s p95 | **0.12 s p50, 0.76 s p95** | - |
| Background swap, when it lands | 81.4 s p50, 105.3 s p95 | **5.8 s p50, 6.0 s p95** | **~15x** |

So the answer to the question Stage 1 was blocked on is: **p95 <= 4 s is not reachable on this Mac, and is
nearly reachable on one 4090.** 5.2 s median and 7.5 s p95 against a 4 s gate -- the same prompt the Mac
takes 60 s to answer. Getting the last 1.5 s is now a model-size question rather than a hardware one, which
is a very different place to be: Qwen3 4B or a 1.7B on the same 4090 lands inside the gate, and D3 already
schedules that comparison.

**The acceptance rates are not comparable and must not be read as a regression.** Box 5/30 accepted on
streaming, Mac 7/30; box 2/30 on the swap, Mac 5/30. The two models have different digests at the same Q4_K_M
quantisation: the Mac's `kenn-brain-qwen3-8b` is a KENN-curated build, the box ran stock `qwen3:8b`. A stock
model grounding itself against KENN's notes will cite things the curated one does not. Only the timing columns
are a like-for-like comparison; the acceptance columns are "how often this particular model lands", and
running the curated model on the 4090 is the obvious next measurement.

One configuration note, because it cost a wasted run: `KENN_LLM_BASE_URL` must include the `/v1` suffix
(KENN's own default is `http://127.0.0.1:11434/v1`). Without it every request 404s and the harness reports
0 attempts in 0.46 s, which reads like a spectacular result and is in fact a total failure. The second
failure was mine too: an SSH tunnel on local port 11434 silently did not bind, because that port is the
Mac's own ollama -- so it was measuring the Mac and calling it the box. The box tunnel is on 21434.

## The biggest finding of the day: KENN was asking a thinking model to answer immediately

Chasing why the 4B was *slower* than the 8B on the 4090 (7.4 s against 5.2 s, and 24 of 29 returning
nothing at all) turned up a defect that had been live the whole time, on both machines.

Qwen3 is a reasoning model. With thinking on, it writes a `thinking` block first, and with a 200- or
1200-token cap it will spend the entire budget there and return **zero characters of answer**:

```
think=true   content=0ch  thinking=1054ch  eval_tok=200   # 4B
think=true   content=0ch  thinking= 954ch  eval_tok=200   # 8B
think=false  content=989ch thinking=0ch     eval_tok=200   # 4B
```

KENN does not send `think: false` on the chat path. `_ollama_think_off()` was gated on
`json_schema is not None`, so prose answers went to Ollama's OpenAI-compatible route, which **ignores**
`think` entirely. Every chat answer was therefore paying for a block of reasoning that was then thrown away.
`enhance()` got an empty string, returned `None`, and KENN fell back to the template — logged as
`generation returned no answer`, which reads like a grounding failure and is not one at all.

Worse, the guard that was supposed to catch this never fired on the model KENN actually ships. The pattern
was `(?:^|/)qwen3`, which requires `qwen3` at the start of the name or after a slash, so it matched stock
`qwen3:8b` and **never matched `kenn-brain-qwen3-8b`**, the curated build on the owner's Mac. The fix was live
on the GPU box and dead in production.

Fixed both: the schema gate is gone, and the pattern matches `qwen3` anywhere in the name. `KENN_LLM_THINK=on`
still opts back into reasoning, and a schema still routes the planner's structured calls. Same 30 questions:

| | Accepted (of 29 attempts) | Median | p95 |
|---|---|---|---|
| M3, default | 7 (24%) | 60.2 s | 89.5 s |
| **M3, thinking off** | **11 (38%)** | 91.1 s | 117.1 s |
| 4090, default | 5 (17%) | 5.2 s | 7.5 s |
| **4090, thinking off** | **10 (34%)** | **5.5 s** | **6.9 s** |

**Acceptance roughly doubles on both machines.** On the 4090 it costs nothing at all: 5.5 s median, 6.9 s p95.
On the M3 it is genuinely slower — 60 s to 91 s — and that is the correct trade, because the answers that used
to be discarded empty now run to the cap and are real. A grounded answer at 91 s beats a template at 60 s every
time; it just makes the M3 less usable, not more.

This is the part of Stage 1 that was never a speed problem at all. A meaningful slice of what the North Star
recorded as "the rest failed the grounding check after the wait" was a thinking model being asked not to think,
and never getting to the grounding check at all.

## The gate is met on one 4090: 3.5 s p95 with 43% of answers landing

With thinking off and the brain served from a single RTX 4090, the same 30 questions through the real
`KENN_LLM_BACKGROUND=1` path (`answer_upgrades.start()`, the calls the ask route makes):

| | Template on screen | Swap lands | Landing rate | Answer on screen |
|---|---|---|---|---|
| M3, before any fix | 0.22 s p50 | 81.4 s p50 | 4-5 of 30 | 0.24 s p50, 74.4 s p95 |
| **4090, thinking off** | **0.23 s p50, 0.76 s p95** | **2.5 s p50, 3.5 s p95** | **13 of 30 (43%)** | **0.76 s p50, 3.75 s p95** |

**p95 answer latency 3.75 s against a 4 s gate.** `route_latency_report.py`, reading the route log this wrote,
independently reports 30 started, 13 accepted (43%), median 2.5 s, p95 3.1 s — so the harness and the existing
tool agree, and the number is not an artifact of the new script.

Both halves of Stage 1's item now hold at once, and neither was true at the start of the day: answers are
written by the brain, cited, and landing under the latency the producer will actually wait through. The
templates remain the offline fallback, and the path that guarantees that is unchanged.

Two caveats, stated plainly. The landing rate is 43%, not the Track D target of 70% within 15 s — but at
2.5 s the *time* half of that target is met with room to spare, and the shortfall is grounding quality, which
is the next piece of work rather than a latency one. And this is a shared GPU box, not the producer's laptop: a
KENN that needs it is not a KENN that works on its own. On the M3 the same code gives 38% at 91 s, which is a
better answer than before and still not 4 s.

Remaining rejections on the 4090, from the route log: 12 unsupported measurements, 3 fabricated source
citations, 1 claiming it changed the Live set. The last one is the safety property working — the model
asserted it had modified the session and the grounding check refused it.

## D3's answer: a smaller model is not the lever

The obvious way to close the last 3 s on a GPU is a smaller model, so `qwen3:4b` was measured too, with
thinking off. It is **worse**, and for an instructive reason:

| Model | Tokens to finish a chat answer | Streaming median | Accepted |
|---|---|---|---|
| qwen3 8B | **105** | 5.5 s | 10/29 |
| qwen3 4B | **2157** | 7.1 s | 0/29 |

The 4B does not write a shorter answer, it writes a *twenty-times longer* one. At KENN's 1200-token cap
(`DEFAULT_MAX_TOKENS`) it is truncated mid-answer every time, so 27 of 29 came back empty and the run
reported 0% accepted. Raising the cap does not rescue it: 2157 tokens at the 4B's ~105 tok/s is about 20 s,
worse than the 8B's 5.5 s. The 8B is both faster and more concise here, and the North Star's 25 Sept
conclusion that 8B stays is confirmed rather than overturned.

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
