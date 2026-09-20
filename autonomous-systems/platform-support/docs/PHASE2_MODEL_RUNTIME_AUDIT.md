# Phase 2 — Model Runtime Audit

Date: 2026-08-22 · READ-ONLY audit of Audio_Too; no product code modified.

## Scope inspected (OBSERVED)

- `Audio_Too/audio_too/model_runtime.py` (279 lines) — the canonical shared runtime
- `Audio_Too/audio_too/endpoint_policy.py` (adjacent policy layer)
- Call sites: `thursday/brain.py`, `thursday/response_rewrite.py`,
  `thursday/voice_output.py` (ONNX lock only),
  `studio/audio_analysis/audio_analysis/mix_review/mix_review_critique.py`,
  `studio/kenn/kenn/core/chat_answer.py`

## Findings

### Provider architecture (OBSERVED)
- `LLMProvider` Protocol: single synchronous method
  `generate(messages, timeout=10, response_schema=None, json_mode=True) -> LLMResult`
  where `LLMResult = {content: str, model: str, usage: dict}`.
- Structured output via OpenAI-style `{"name", "schema"}` json_schema response_format;
  `json_mode=False` opts out for free-form text.
- **OllamaProvider** (local-first): env `AUDIO_TOO_LLM_MODEL_ROUTE`
  (default `qwen2.5:1.5b`), `AUDIO_TOO_LLM_BASE_URL`
  (default `http://127.0.0.1:11434/v1`), temperature 0.1, background keep-alive
  pinger thread against native `/api/generate` (`THURSDAY_OLLAMA_KEEP_ALIVE`, default 30m).
- **RemoteProvider**: OpenAI-compatible fallback; env `AUDIO_TOO_LLM_MODEL`,
  `AUDIO_TOO_LLM_BASE_URL`, `AUDIO_TOO_LLM_API_KEY`.
- **EnvGatedProvider** (= module singleton `DEFAULT_LLM`): env
  `AUDIO_TOO_LLM_PROVIDER ∈ {remote|openai|ollama|""}`; default auto-resolve =
  5s reachability probe of Ollama `/api/tags`, else remote.

### Gaps vs platform requirements (OBSERVED → RECOMMENDED)
1. No privacy awareness: auto-fallback can send any prompt to the remote provider;
   nothing distinguishes PRIVATE_AUDIO/PRIVATE_PROJECT content. → Platform routing must make privacy a hard constraint, not a preference.
2. Fallback is binary and unbounded in scope (local→remote on any failure); no attempt caps, no fallback reason reporting, no circuit breaker. → Bounded fallback chain with reasons.
3. No streaming support anywhere (`stream: False` hardcoded).
4. No cost/token budgeting (usage returned but never aggregated/enforced).
5. No health/metadata abstraction beyond ad-hoc reachability probe inside EnvGatedProvider.
6. Errors are generic `RuntimeError` wrappers — no machine-readable category. (Platform `ErrorCategory.MODEL_UNAVAILABLE/MODEL_FAILURE` map cleanly.)
7. KENN has its own parallel LLM stack (`kenn/llm/kenn_lm*`) plus imports of DEFAULT_LLM in `chat_answer.py` — two stacks converging on one protocol already.
8. ONNX session init is process-global with an RLock (`ONNX_SESSION_INIT_LOCK`) — relevant for a future local runtime service.

### What to preserve (RECOMMENDED)
The single-method sync `generate` shape is simple and adequate for current call
sites. The platform executor interface should mirror it (sync-first), add
optional streaming later only if a real consumer appears.

## Adapter strategy
Wrap, don't rewrite: a platform `ModelProvider` adapter can delegate to
`LLMProvider.generate`; live wiring deferred (product repos untouched this phase).
