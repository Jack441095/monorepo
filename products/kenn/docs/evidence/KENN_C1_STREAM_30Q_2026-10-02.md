# Thirty-question stream baseline — 2 October 2026

Recorded source: `7539ec106fd53afca502f4980677633fab304418`. The
[numeric receipt](KENN_C1_STREAM_30Q_2026-10-02.json) is the raw output of one run. It covers the **stream**
surface only, so it is part of C1, not all of it. It follows the
[five-question capture](KENN_QWEN_SMALL_CURRENT_PATH_2026-10-02.md) and uses the same runner.

## Conditions

Apple M3, 16 GiB. Ollama 0.34.4, `kenn-brain-qwen3-8b:latest` (digest `90a5eaf166fd`, Q4_K_M, 4,096-token context,
100% GPU). Index `v-db8c6334cf63`. LLM generation was turned on for the run with the Ollama provider and that model, as in the five-question
capture; it is not on in the shipped config. `KENN_LLM_CACHE=0`, so no
response-cache hits (the receipt agrees: 0). The runner clears the semantic cache between questions. FakeLive, with
chats and the database in a temp directory, so no real Live and no writes to Live.

We did not look at `/api/ps` before the run started, so we can't say whether the model was resident for the first
question. The first row's first token took 11.0 s against a median of 3.4 s, which fits a cold load, but that is a
guess. Nothing else heavy was running; `caffeinate` kept the Mac awake.

The 30 questions are the first 30 in the runner's default cases file (27 uncategorized, 3 production), run once, in
order.

## Results

| | median | p95 |
| --- | ---: | ---: |
| Completion, all 30 | 18.9 s | 28.5 s |
| Completion, accepted answers (22) | 20.5 s | 27.4 s |
| First delivered token, all 30 | 3.39 s | 8.90 s |

- 29 of 30 questions went to the model. The one that didn't (`muddy-low-mids`) found no sources and answered from
  the template in 0.04 s.
- 22 of the 29 generated answers were accepted (76%). 7 were rejected, 0 runner errors, 0 provider failures.
- The rejected answers were stopped mid-stream. Six were unsupported measurements (`120hz`, `100hz`/`60hz`, `-0.1db`,
  `-0.3db`, `-6db`, `0.5hz`) and one claimed it had changed the Live set. Each reason appeared once.
- Rejected rows are not slow rows: their median completion is 11.7 s against 20.5 s for accepted ones, because the
  stream is cut. Their first token still arrives (median 3.8 s), so a user can see text that is then replaced.
- The gate in the plan is p95 <= 4 s. This path is nowhere near it: even the median first token is 3.4 s and the
  median completion is about 19 s.

First token and completion are separate columns on purpose. A first token can come from the template fallback, and
partial text can arrive before a rejection, so a delivered token does not mean a good answer.

## Where the time goes

Ollama's own timings exist for the 22 completed calls only. The 7 interrupted calls returned none, and we leave them
unknown rather than guess.

| Per completed call | median | max |
| --- | ---: | ---: |
| Model load | 2.7 ms | 11 ms |
| Prompt evaluation (prefill) | 3.2 s | 7.5 s |
| Generation | 16.8 s | 23.8 s |
| Prompt tokens | 1,076 | 1,140 |
| Completion tokens | 220 | 282 |
| Prompt tokens served from Ollama's cache | 667 | 711 |

Every completed call ended with reason `stop`. Generation is the bulk of it: 220 tokens in 16.8 s is about 13
tokens a second. Prefill is a fifth of the wall time even with roughly 60% of the prompt cached. The model was
already loaded for all of these, so load time is not the problem once it is warm.

## What this does not cover

- Only the stream surface. The plan also wants separate foreground and background runs.
- One run, so no repeat to say how much of the spread is noise.
- No admission/queue, retrieval, verification, polling or displayed-result timing, and no memory pressure, swap or
  audio dropout readings. Live-open against Live-closed needs Jack present, so it was not attempted.
- Model-cold against warm is not separated (see above).
- The questions come from the default cases file, not a held-out set. No quality comparison was made, so this says nothing
  about whether the answers are good, only how long they take and how often the checks stop them.
- C1 stays unticked.
