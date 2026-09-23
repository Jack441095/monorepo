# C2 planner bake-off on the GPU box, plus Mac latency (2026-09-23)

Follows `KENN_C2_PLANNER_BAKEOFF_MAC_2026-09-23.md`. Same harness
(`tooling/scripts/planner_bakeoff.py`: KENN's real `_generate_llm_plan`, real
system prompt, schema-constrained decoding, `validate_llm_plan`, one repair, fake
demo snapshot, no Live, no writes), now on **124 cases**: the 100 drafted
phrasings (owner review pending) plus Codex's 24 curated cases. 94 expect an
action, 30 expect a clarifying question.

- **Accuracy** was measured on the shared GPU box: GPU 0 only (RTX 4090 D), user-level Ollama 0.34.2 on
  loopback `127.0.0.1:11437` under `/mnt/data/kenn-bakeoff/ollama/`, no system install, no restarts.
  The Mac reached it over an SSH tunnel. Only command text crossed; no audio.
- **Latency** was measured on the target machine: this Mac, an Apple M3 with 16 GB, with Ableton Live running.

## Result

**Best model: `qwen3.5:4b` with thinking off: 67.7% correct on the GPU, 64.5% on the Mac.**

It is the only model that both acts and asks. It clarified 20 of 30 vague requests, where the next best clarified 6.
It also had the fewest wrong plans accepted.
On the Mac it is still too slow to be interactive, with a p50 of 10.3 s and a p95 of 32.7 s.
The LLM planner therefore stays in shadow, and the deterministic parser remains the fast path.

### Accuracy on the GPU (planner prompt v2, request after snapshot)

| Variant | Accepted | Correct | Clarify (30) | Act (94) | Curated (24) | Wrong plans accepted | p50 | p95 |
|---|---|---|---|---|---|---|---|---|
| **qwen3.5:4b, thinking off** | 96.0% | **67.7%** | **20/30** | 64/94 | **14/24** | **16** | 1.1 s | 2.7 s |
| qwen3.5:4b, thinking ≤128 tokens | 88.7% | 66.1% | 22/30 | 60/94 | 14/24 | 14 | 3.1 s | 6.1 s |
| qwen2.5:7b-instruct | 75.8% | 53.2% | 6/30 | 60/94 | 9/24 | 28 | 0.8 s | 2.0 s |
| Rule-based parser (`parse_request`, no LLM) | — | 49.2% | **30/30** | 31/94 | 12/24 | 0 | <0.1 ms | <0.1 ms |
| phi4-mini (3.8B) | 75.8% | 44.4% | 0/30 | 55/94 | 8/24 | 37 | 0.8 s | 1.7 s |
| qwen3.5:2b, thinking off | 71.0% | 41.1% | 1/30 | 50/94 | 8/24 | 36 | 1.2 s | 2.5 s |
| qwen2.5:1.5b (current LoRA base) | 57.3% | 27.4% | 0/30 | 34/94 | 5/24 | 37 | 1.0 s | 1.6 s |
| deepseek-r1:7b, thinking off | 78.2% | 26.6% | 0/30 | 33/94 | 6/24 | 64 | 0.9 s | 2.4 s |

The "Wrong plans accepted" column counts plans that passed validation but had the wrong action or target, or acted
where a question was needed. KENN still shows every plan for Apply, so none of these would run unconfirmed.
It is nonetheless the column that matters most for promotion (C4).

#### DeepSeek-R1 and thinking modes

These were measured with the v1 prompt (request before snapshot). The v2 prompt was re-run only for the rows above.

| Variant | Correct | p50 |
|---|---|---|
| deepseek-r1:1.5b, default thinking | 0.0% | 1.1 s (every call hit the token cap) |
| deepseek-r1:1.5b, thinking off / ≤128 / ≤256 tokens | 1.6% / 1.6% / 1.6% | 1.2 / 2.5 / 3.3 s |
| deepseek-r1:7b, default thinking | 1.6% | 2.1 s (thought until the cap) |
| deepseek-r1:7b, thinking off / ≤128 / ≤256 tokens | 4.0% / 4.0% / 4.0% | 0.9 / 2.3 / 2.8 s |
| qwen3.5:2b, default thinking | 0.0% | 2.7 s (thought until the cap) |
| qwen3.5:2b, thinking off / ≤128 tokens | 33.9% / 34.7% | 1.1 / 2.6 s |
| qwen3.5:4b, thinking off / ≤128 tokens | 60.5% / 62.9% | 1.1 / 3.1 s |

### Latency on the Mac (M3, 16 GB, Live running): qwen3.5:4b, thinking off, v2 prompt

| | Cases | p50 | max |
|---|---|---|---|
| First try | 111 | 10.1 s | 23.0 s |
| With one repair | 13 | 32.7 s | 43.0 s |
| **All** | 124 | **10.3 s** (v1 prompt: 18.6 s) | p95 32.7 s |

Accuracy on the Mac was 64.5% correct and 95.2% accepted, which matches the GPU.

Profile of one planner call on the Mac:

| Model | Prompt (~2,050 tokens), cold | Prompt, repeated | Generation |
|---|---|---|---|
| qwen3.5:4b | 13.8 s | 0.2 s | 57 tokens at ~10 tokens/s ≈ 5.7 s |
| qwen2.5:7b | 24.1 s | 0.1 s | 63 tokens ≈ 9.3 s |

JSON-schema constraints cost nothing: the Mac generated at ~9.9 tokens/s with the schema, with plain JSON and with no
constraint. qwen3.5 is a hybrid (recurrent + attention) model, so Ollama can reuse its prompt cache only partly
between different requests.

## What we learned

1. **Shortening the thinking helped, as suggested, and switching it off helped most.** Through Ollama's
   OpenAI-compatible route, both DeepSeek-R1 and qwen3.5 think until the token cap once a JSON schema is set. That
   route ignores `reasoning_effort`, and it ignores `think: false` once a schema is set. The result is empty answers
   and 0% scores. `tooling/scripts/thinking_budget_proxy.py` renders the chat template itself and either prefills an
   empty think block or caps thinking at N tokens.
   - With thinking off, qwen3.5 goes from 0% to 60–68%.
   - A 128-token thinking budget changed accuracy by less than 2.5 points (slightly lower with the v2 prompt) and
     tripled latency.
   - For this task, shorter thinking is better, and no thinking is best.
2. **DeepSeek-R1 distills are the wrong tool here**, whatever the thinking mode. They are tuned for maths and code
   reasoning, not for filling a tool contract.
   - Without thinking, R1-7B aimed 85 of its accepted plans at the selected track ("Drum Bus") whatever the request
     named. That is the most dangerous failure pattern seen.
   - Thinking did not fix it: 4.0% correct at ≤128 and ≤256 tokens.
3. **Prompt order matters, for accuracy as well as speed.** KENN put the request before the ~1,500-token snapshot.
   Putting the snapshot first and the request last (committed with this doc, with a regression test):
   - raised every model's accuracy (qwen2.5:1.5b 10.5→27.4%, phi4-mini 28.2→44.4%, qwen3.5:4b 60.5→67.7%);
   - lets the model server share the prompt prefix across commands, which cut the Mac p50 from 18.6 s to 10.3 s.
4. **The deterministic parser is still the safest fast path.** It gets every clarify case right (30/30), never
   accepts a wrong plan, and is instant. It covers only 31/94 actions. The LLM's value is the other 63.
5. **Two harness bugs were caught and fixed along the way.**
   - Bake-off numbers had been read from KENN's persistent answer cache. `planner_bakeoff.py` now disables the cache.
   - The cache key ignored the output contract, so a schema call could be served a non-schema answer. The key now
     includes JSON mode, the schema and the answer mode.

## Decisions this points to

1. **Candidate planner: `qwen3.5:4b` with thinking off.** It replaces `qwen2.5:1.5b`/`7b` for C4/C6 work.
   Production KENN must disable thinking itself before this can ship. Options:
   - call Ollama's native `/api/chat` with `think: false`, which works for qwen3.5 when set there;
   - or prefill the empty think block, as the proxy does.
   Until then it stays behind the shadow flag. (Done the same evening with the native route; see the addendum.)
2. **On this Mac, the LLM cannot be the interactive path** (p50 10 s). Keep the parser first and the LLM as a fallback,
   shown as "working it out…". Work to reduce latency:
   - shorter plan output (done, see the addendum: the reply was already compact JSON; ~12 of ~43 tokens were the
     schema constant, which KENN now stamps itself);
   - a smaller fine-tuned model (C6);
   - and/or the owner deciding whether a demo may use a remote planner. Only text would leave the Mac.
3. **C6 fine-tune:**
   - Base: qwen3.5:2b or qwen3.5:4b. The 2b is fast but clarifies 1/30 today; the 4b clarifies 20/30.
   - Corpus: contract-correct, with at least a third clarify examples, no thinking, and targets in user units.
   - Evaluate on this 124-case set and the curated 24.
4. **Grow the parser (C2 follow-up).** The misses it would now catch are in `.runtime/logs/bakeoff_gpu/`.

## Reproduce

```bash
# Box (GPU 0, loopback only):
/mnt/data/kenn-bakeoff/ollama/serve.sh
# Mac: tunnel, thinking proxy, bake-off
ssh -f -N -L 11438:127.0.0.1:11437 -p 2022 ubuntu@www.haoee.com
python3 tooling/scripts/thinking_budget_proxy.py --upstream http://127.0.0.1:11438 --port 11439 &
KENN_BAKEOFF_BASE_URL=http://127.0.0.1:11439/v1 python3 tooling/scripts/planner_bakeoff.py \
  --model qwen3.5:4b@nothink --holdout <124-case jsonl> --timeout 60 --out <file>
```

The 124-case file is `natural_holdout_candidates.jsonl` followed by `natural_holdout.jsonl`. Raw per-case results
are in `.runtime/logs/bakeoff_gpu/` (v1 prompt) and `.runtime/logs/bakeoff_gpu/v2/` (v2 prompt); these are
gitignored runtime logs.

## Addendum: production thinking-off path, shorter output, Qwen3 (same evening)

Three changes followed the bake-off:

- **Production KENN now turns thinking off itself.** qwen3-family schema calls go to Ollama's native `/api/chat`
  with `think: false`. The bake-off helper is no longer needed.
- **The model no longer writes the plan schema constant.** It cost ~12 of a ~43-token reply; KENN stamps it after
  decoding.
- **The training generator builds the planner prompt with production's own function.**

All rows below use that final code, through the production path:

| Model | Correct | Clarify (30) | Act (94) | Curated (24) | Wrong plans accepted | GPU p50 |
|---|---|---|---|---|---|---|
| **qwen3.5:4b** | **66.1%** | **20/30** | 62/94 | **14/24** | **15** | 1.0 s |
| qwen3:4b | 51.6% | 2/30 | 62/94 | 9/24 | 35 | 0.7 s |
| qwen3:1.7b | 19.4% | 4/30 | 20/94 | 4/24 | 7 | 1.1 s |

The next table is Mac latency on the first 40 cases, which are mostly explicit commands. The same 40 cases were run
for both models:

| Model | Correct (40) | p50 | p95 | Repairs |
|---|---|---|---|---|
| qwen3:4b | 77.5% | **4.5 s** | 16.8 s | 6 |
| qwen3.5:4b | 75.0% | 6.7 s | 18.0 s | 1 |

- **Qwen3 (a standard transformer) is faster on the Mac.** It reuses the prompt cache across commands; the hybrid
  qwen3.5 re-processes ~3.6 s of prompt per new command.
- **On explicit commands the two 4B models are equal (62/94).** qwen3:4b almost never asks when it should (2/30) and
  accepts more than twice as many wrong plans. Its speed comes with the riskier failure pattern.
- **The trade-off for C6:**
  - qwen3.5:4b is safe now but slower.
  - qwen3:4b is faster, but only acceptable if fine-tuning teaches it to clarify. The corpus would need a large share
    of clarify examples, and the result must be measured on the 30 clarify cases before any promotion.
- **Decision for the owner:** which base to fine-tune.
