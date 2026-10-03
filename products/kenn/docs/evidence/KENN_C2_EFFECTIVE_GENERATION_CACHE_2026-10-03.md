# Effective generation settings and research follow-through, 3 October 2026

Implementation commit: `a535f9fc`.

The [product research, section 12](../research/KENN_PRODUCT_AND_OPEN_SOURCE_RESEARCH_2026-10-02.md#12-accelerating-the-fixed-qwen-models-follow-up-findings) recommends checking response-cache identity before comparing budgets, thinking or sampling. The [first repair](KENN_C2_RESPONSE_CACHE_IDENTITY_2026-10-03.md) covered task, mode, provider and endpoint. A second regression reproduced stale-answer reuse when the numeric cap changed under the same mode, or when native thinking-off transport changed to the compatible transport.

Both HTTP chat surfaces now include the effective request settings in the cache contract. The settings come from the existing payload builders, including token ceiling, temperature and output format. Stream framing and keep-alive are excluded because they do not change the requested answer. Identical contracts still reuse across surfaces. An explicit `off` and Qwen3's default thinking-off policy share the same effective contract.

## Exact files and behavior

- `apps/backend/src/kenn/llm/llm_rewrite.py`: adds `_http_generation_contract` and supplies it to the payload and stream cache keys. No request settings, output style, grounding rule, residency setting, runtime or model changed. Existing keys naturally miss; no purge, migration or deletion.
- `apps/backend/src/kenn/tests/test_llm_cache_key.py`: synthetic native and compatible provider framing, temporary SQLite cache, changed numeric caps on both transports and surfaces, changed thinking transport, changed effective temperature, unchanged effective thinking policy and keep-alive reuse. Fixtures do not connect to a model or Live.

## Verification

Commands ran sequentially from `products/kenn` with Fake Live and fresh pytest caches.

```sh
KENN_LIVE_BACKEND=fake PYTHONPATH="apps/backend/src:tooling" apps/backend/.venv/bin/python -m pytest -q --tb=short -p no:randomly apps/backend/src/kenn/tests/test_llm_cache_key.py -o cache_dir=/private/tmp/kenn-effective-cache-red-20261003
```

Before implementation: **4 failed, 15 passed**, 0.17 s, exit 1. The four initial regressions reproduced numeric-cap and thinking-transport collisions on both surfaces.

```sh
KENN_LIVE_BACKEND=fake PYTHONPATH="apps/backend/src:tooling" apps/backend/.venv/bin/python -m pytest -q --tb=short -p no:randomly apps/backend/src/kenn/tests/test_llm_cache_key.py apps/backend/src/kenn/tests/test_llm_think_off.py apps/backend/src/kenn/tests/test_llm_usage_telemetry.py apps/backend/src/kenn/tests/test_llm_generation_bounds.py apps/backend/src/kenn/tests/test_llm_plan_schema.py -o cache_dir=/private/tmp/kenn-effective-cache-scoped-final-20261003
```

After implementation and expanded boundaries: **116 passed**, 0.69 s, exit 0.

Mutation check removes only the new contract field in memory:

```sh
KENN_LIVE_BACKEND=fake PYTHONPATH="apps/backend/src:tooling" apps/backend/.venv/bin/python - <<'PYTEST'
import pytest
from kenn.llm import llm_rewrite
original = llm_rewrite._cache_key

def ignore_effective_generation(cfg, messages, output=None):
    if output:
        output = {key: value for key, value in output.items() if key != "generation"}
    return original(cfg, messages, output)

llm_rewrite._cache_key = ignore_effective_generation
raise SystemExit(pytest.main(["-q", "--tb=short", "-p", "no:randomly", "apps/backend/src/kenn/tests/test_llm_cache_key.py", "-o", "cache_dir=/private/tmp/kenn-effective-cache-mutation-20261003"]))
PYTEST
```

**8 failed, 16 passed**, 0.13 s, exit 1, as expected. Numeric-cap, thinking-transport and sampling regressions detect removal of the contract. No checkout mutation.

```sh
KENN_LIVE_BACKEND=fake PYTHONPATH="apps/backend/src:tooling" apps/backend/.venv/bin/python -m pytest -q --tb=short -p no:randomly apps/backend/src/kenn/tests -o cache_dir=/private/tmp/kenn-effective-cache-full-20261003
```

Full backend: **3657 passed, 12 skipped, 1 failed, 6 warnings**, 105.15 s, exit 1. The sole pre-existing failure is `test_personal_path_gate.py::test_the_shipped_tree_has_no_personal_path_or_remote_host`, reporting the unchanged machine-specific path in the handoff note. The log is scratch-only at `/private/tmp/kenn-effective-cache-full-20261003.log`. `git diff --check` passed.

## Research decisions and limits

The [speed shortlist](KENN_SPEED_RESEARCH_2026-10-03.md) is a list of hypotheses from other hardware. The local phase and style receipts remain the basis for decisions:

1. [Measured phases and isolated output cap](KENN_C2_MODEL_PHASES_AND_OUTPUT_CAP_2026-10-03.md): the temporary 128-token cap improved timely acceptance on the five-question stream sample but worsened payload acceptance and truncated accepted answers. Jack's style decision remains open; production stays at the existing ceiling.
2. [Brief-style trial and exact runtime proposal](KENN_C2_BRIEF_STYLE_AND_RUNTIME_PROPOSAL_2026-10-03.md): shorter prose avoided the ceiling but reduced acceptance and useful workflow detail. No production style change. The Qwen3 8B / approximately 1,100-token MLX comparison remains a proposal for this M3 / 16 GB, with prefill and decode separated; no new runtime, dependency, model or draft downloaded.
3. [Latest model diagnostic](KENN_C3_POST_ROUTING_MODEL_DIAGNOSTIC_2026-10-03.md): completed rewrites had median 17.605 tok/s, with uncontrolled Mac and prompt-cache state. One export answer spent 15.234 s decoding despite a 0.061 s prefill. Prefix tuning alone cannot recover that example's deadline. This is not a measured engine improvement over earlier runs.
4. Thinking is already off. Keep-alive remains 30 minutes with a 240-second ping; the observed runtime holds about 5.4 GB and can remain resident throughout a session. Cold-reload, Live-open memory pressure and audio dropout remain unmeasured until Jack schedules a soak. No residency change.
5. A static trace of the existing reverb diagnostic retrieved compression/drum-bus notes without reverb intent evidence for the dense-drums follow-up. No LLM, index rebuild or ranking change in that trace. It identifies a retrieval-quality investigation; weakening grounding would not establish usefulness. No model prose is stored in this receipt.

This is cache correctness work, not decode acceleration. All recorded real-model diagnostics used `KENN_LLM_CACHE=0`, so these collisions do not explain their timing. Replacement weights behind an unchanged alias and actual MLX engine identity remain unqualified; this repair covers effective HTTP request settings only. No new model benchmark, private audio, dependency, permission or CI change. **C1, C2 and C3 remain unticked**: the 15-second eligible-request gate, independent quality comparison, UI and owner-scheduled Live qualification remain open.
