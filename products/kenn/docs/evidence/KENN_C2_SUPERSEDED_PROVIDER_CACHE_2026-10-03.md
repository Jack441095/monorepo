# C2 provider cache ownership, 3 October 2026

Code commit: `1a74b143375d22fbfb8a770375150e8866bf60ba`.

Cancelled or replaced chat requests could still save final provider text into the SQLite response cache. Payload and stream calls now carry their request owner to the cache writer. The existing owner lock covers the actual save; generation stays outside that lock. Each stream advance restores its caller's context before yielding, so interleaved streams and unbound calls cannot inherit another chat's owner. Cleanup and error paths restore context too.

Exact files:

- `apps/backend/src/kenn/core/chat_answer.py`: bind cache ownership for payload, background payload and stream execution.
- `apps/backend/src/kenn/llm/llm_rewrite.py`: apply the caller's ownership guard around the existing SQLite save.
- `apps/backend/src/kenn/tests/test_provider_cache_ownership.py`: native Ollama and OpenAI-compatible provider stubs cover cancellation, replacement, other-chat isolation, interleaving, cleanup, errors and saves under the owner lock.

All commands below ran from `products/kenn`, with Fake Live, isolated temporary SQLite files and fresh pytest cache directories. No model or Live connection was made.

```sh
KENN_LIVE_BACKEND=fake PYTHONPATH="apps/backend/src:tooling" apps/backend/.venv/bin/python -m pytest -q --tb=short -p no:randomly apps/backend/src/kenn/tests/test_provider_cache_ownership.py -o cache_dir=/private/tmp/kenn-provider-cache-red-final-20261003
```

Before the fix: 12 failed, 6 passed in 0.28 s. The failures reproduced superseded cache writes and ownership leaking across suspended streams. An earlier fixture run had three additional failures because the OpenAI stub omitted its completion reason; the qualifying red run above corrected that fixture first.

```sh
KENN_LIVE_BACKEND=fake PYTHONPATH="apps/backend/src:tooling" apps/backend/.venv/bin/python -m pytest -q --tb=short -p no:randomly apps/backend/src/kenn/tests/test_provider_cache_ownership.py apps/backend/src/kenn/tests/test_llm_cache_key.py apps/backend/src/kenn/tests/test_llm_usage_telemetry.py apps/backend/src/kenn/tests/test_llm_stream_honesty.py apps/backend/src/kenn/tests/test_llm_generation_bounds.py apps/backend/src/kenn/tests/test_stream_request_delivery.py apps/backend/src/kenn/tests/test_answer_upgrade_context.py apps/backend/src/kenn/tests/test_answer_upgrades.py apps/backend/src/kenn/tests/test_confirmation_cancellation_routes.py -o cache_dir=/private/tmp/kenn-provider-cache-scoped-20261003
```

After the fix and eight extra context/lock checks: 266 passed, 2 warnings in 5.45 s. The new file contributes 26 provider/surface cases.

```sh
KENN_LIVE_BACKEND=fake PYTHONPATH="apps/backend/src:tooling" apps/backend/.venv/bin/python -m pytest -q --tb=short -p no:randomly apps/backend/src/kenn/tests -o cache_dir=/private/tmp/kenn-provider-cache-full-20261003
```

Full backend: 3723 passed, 12 skipped, 7 warnings and 1 pre-existing failure in 92.18 s. The failure is `test_personal_path_gate.py::test_the_shipped_tree_has_no_personal_path_or_remote_host`, also present before this change. Its findings are not copied here. `git diff --cached --check` passed.

## Limits and research implications

This completes provider-cache ownership for bound public chat calls. A save already holding the lock finishes before cancellation; anonymous calls retain their existing cache behavior. Provider stubs cover native Ollama and OpenAI transport, not MLX execution. Other action/fast-path persistence remains outside this regression. No provider cancellation, decode-speed gain or Live-open qualification is claimed.

The [speed shortlist](KENN_SPEED_RESEARCH_2026-10-03.md) still points to decode cost and answer length. Cache correctness cannot establish a faster uncached answer. Previous cap and brief-style diagnostics remain pending Jack's choice; production style, grounding, 384-token ceiling, thinking-off transport and residency stay unchanged. The same-Qwen3-8B MLX comparison is proposed in the earlier runtime receipt, not executed. No dependency or model asset was added. C1, C2 and C3 remain unticked: the 15 s accepted-answer gate is still failed and real Live memory/audio behavior remains unmeasured.
