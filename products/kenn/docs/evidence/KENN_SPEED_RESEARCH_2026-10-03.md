# Speed research for the local model, 3 October 2026

A web deep-research run (103 agents, claims checked by three verifiers each) on making Qwen3 8B faster on an M3 / 16 GB
with a DAW open. Every number below came from someone else's hardware, so this is a shortlist of things to test on our
Mac, not a result. Nothing here has been run by us.

## The sum that matters

We decode at about 13 tok/s and answers are 220 to 280 tokens, so decoding alone is 17 to 21 s. Prefill and prompt
cache tuning cannot get us under 15 s. We need roughly 1.5x decode speed, shorter answers, or both.

## Worth testing, in order

1. **Thinking off at the request level.** Ollama's `think: false` on `/api/chat` turns the reasoning phase off for Qwen3
   with no Modelfile change and no new files (Ollama blog, 30 May 2025). Prompt directives (`/no_think`) were not
   supported by the verifiers, so use the parameter. Check on Ollama 0.34.4 that no reasoning tokens come back. We already
   do this: `_ollama_think_off` in `llm/llm_rewrite.py` sends `think: false` for `kenn-brain-qwen3-8b`, so there is
   nothing to gain here.
2. **Keep the model loaded.** Ollama unloads after 5 minutes idle. `keep_alive` per request, or `OLLAMA_KEEP_ALIVE`,
   avoids a cold reload during a session. The cost is about 5 GB held while Live is open. Trade-off for Jack to pick.
3. **Shorter answers.** Capping output length is the only lever in this list that does not need a new engine, and at
   13 tok/s every 50 tokens is about 4 s. This touches answer style, not grounding, but it is Jack's call.
4. **MLX instead of GGUF.** The only close comparison found: Qwen3.5 9B on an M3 Ultra 256 GB, 107.5 tok/s with mlx-lm
   against 77.8 for llama.cpp Q4_K_M (about 38% more decode), but Ollama's MLX build prefilled far slower on that test.
   Three other MLX-vs-llama.cpp claims (4 to 30%) were refuted, so the gap on a small dense model is contested. Needs a
   new runtime and an MLX-format Qwen3 8B file, so it needs Jack's OK. Compare on our Mac, Qwen3 8B only, with our
   1,100-token prompt, prefill and decode reported separately.
5. **Speculative decoding.** Lossless, but only when the draft matches. Best analogue: Llama 3.1 8B with a 1B draft in
   MLX, 1.71x on an M3 Pro 36 GB. A badly matched draft (30% acceptance) was 73% slower on CUDA. Ollama's built-in
   multi-token prediction does not apply to Qwen3 8B. Needs a draft model file (Qwen3 0.6B or 1.7B) and a runtime that
   supports it, so it needs Jack's OK, and 16 GB with Live open is tighter than any machine tested.

## Small and not worth chasing yet

- KV cache `q8_0` saves about 0.3 GB at a 4096 context and shows no speed gain. Keep 4096.
- Ollama's huge default context only hurts on big Macs; our 4096 already avoids it.

## Not answered

Memory pressure, wired-memory limits and what drops audio in Live were refuted or unverified. Only a test on our own Mac
with Live open can answer that, on a session Jack schedules.
