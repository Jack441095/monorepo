# Response cache identity and research priorities, 3 October 2026

Implementation commit: `7ada01202d12909646888c7ae837f674aa10ae60`.

The product research identified cache-contract drift as a correctness risk when comparing output budgets or runtimes. Plain prose calls discarded answer mode, so a cached general answer could satisfy a quick-fix request with a smaller token budget. Task, provider and endpoint also failed to separate responses. These collisions are now covered by offline regressions; this is not a measured decode-speed improvement.

## Files and behavior

- `apps/backend/src/kenn/llm/llm_rewrite.py`: cache keys include provider and endpoint; both chat surfaces supply task and answer mode alongside their output format. Identical contracts still share responses across surfaces. SQLite storage, TTL and eviction are unchanged. Existing keys naturally miss; no cache purge or migration.
- `apps/backend/src/kenn/tests/test_llm_cache_key.py`: actual temporary SQLite storage and synthetic provider replies cover different modes, tasks, providers and endpoints, valid reuse across surfaces, and cache-disabled requests. No real model, HTTP connection or Live operation.

No output budget, answer style, sampling, thinking, residency, grounding policy, runtime, dependency, permission or CI setting changed.

## Verification

Commands ran sequentially from `products/kenn`, with Fake Live and fresh pytest caches.

```sh
KENN_LIVE_BACKEND=fake PYTHONPATH="apps/backend/src:tooling" apps/backend/.venv/bin/python -m pytest -q --tb=short -p no:randomly apps/backend/src/kenn/tests/test_llm_cache_key.py -o cache_dir=/private/tmp/kenn-pcache-contract-red-confirmed-20261003
```

Before the fix: **8 failed, 5 passed**, 0.29 s, exit 1. All eight failures reproduced inappropriate reuse.

```sh
KENN_LIVE_BACKEND=fake PYTHONPATH="apps/backend/src:tooling" apps/backend/.venv/bin/python -m pytest -q --tb=short -p no:randomly apps/backend/src/kenn/tests/test_llm_cache_key.py apps/backend/src/kenn/tests/test_llm_think_off.py apps/backend/src/kenn/tests/test_llm_usage_telemetry.py apps/backend/src/kenn/tests/test_llm_generation_bounds.py apps/backend/src/kenn/tests/test_llm_plan_schema.py -o cache_dir=/private/tmp/kenn-pcache-contract-scoped-20261003
```

After the fix: **105 passed**, 0.71 s, exit 0.

Mutation check, loaded in memory without changing the checkout:

```sh
KENN_LIVE_BACKEND=fake PYTHONPATH="apps/backend/src:tooling" apps/backend/.venv/bin/python - <<'PYTEST'
import pytest
from kenn.llm import llm_rewrite
original = llm_rewrite._cache_key
def ignore_request_identity(cfg, messages, output=None):
    cfg = {key: value for key, value in cfg.items() if key not in {"provider", "base_url"}}
    if output:
        output = {key: value for key, value in output.items() if key not in {"task", "answer_mode"}}
    return original(cfg, messages, output)
llm_rewrite._cache_key = ignore_request_identity
raise SystemExit(pytest.main(["-q", "--tb=short", "-p", "no:randomly", "apps/backend/src/kenn/tests/test_llm_cache_key.py", "-o", "cache_dir=/private/tmp/kenn-pcache-contract-mutation-20261003"]))
PYTEST
```

Executed as the equivalent scratch script `/private/tmp/kenn-cache-contract-mutation-20261003.py`: **8 failed, 5 passed**, 0.07 s, exit 1, as expected. The regressions detect removal of the new identity fields.

```sh
KENN_LIVE_BACKEND=fake PYTHONPATH="apps/backend/src:tooling" apps/backend/.venv/bin/python -m pytest -q --tb=short -p no:randomly apps/backend/src/kenn/tests -o cache_dir=/private/tmp/kenn-pcache-contract-full-20261003
```

Full backend: **3646 passed, 12 skipped, 1 failed, 6 warnings**, 104.45 s, exit 1. The sole pre-existing failure is `test_personal_path_gate.py::test_the_shipped_tree_has_no_personal_path_or_remote_host`, detecting a machine-specific path in the unchanged handoff note. No suppression or unrelated edit. `git diff --check` passed.

## Research decisions and limits

The [speed shortlist](KENN_SPEED_RESEARCH_2026-10-03.md) supplies hypotheses from other hardware. The [product research, section 12](../research/KENN_PRODUCT_AND_OPEN_SOURCE_RESEARCH_2026-10-02.md#12-accelerating-the-fixed-qwen-models-follow-up-findings) supplies phase measurement, cache-contract and answer-quality checks. Neither is a local speed result.

1. Decode and answer length remain the priorities. The latest diagnostic had an almost fully cached export prefill of 0.061 s but 15.234 s decoding. Prefix tuning cannot recover that example's deadline by itself. Recent completed rewrites reached a median 17.605 tok/s, but Mac state and prompt cache were uncontrolled: no causal engine speed gain.
2. The isolated 128-token cap improved timely acceptance only on the small stream sample and truncated accepted answers; brief style with the existing ceiling weakened acceptance and workflow quality. Production style stays unchanged for Jack's decision. These are five-question diagnostics, not the eligible-request gate or a held-out quality qualification.
3. Thinking is already off. Keep-alive holds about 5.4 GB in the observed native runtime; the 30-minute setting plus 240-second ping can retain it throughout a session. Cold reload cost and Live-open memory/audio remain unmeasured. No residency change without Jack.
4. The exact Qwen3 8B / approximately 1,100-token [MLX comparison proposal](KENN_C2_BRIEF_STYLE_AND_RUNTIME_PROPOSAL_2026-10-03.md) remains unexecuted. Other-hardware MLX or speculative-decoding numbers do not predict this M3 / 16 GB. New runtime, dependency, draft or model files require Jack's approval. KV compression and the already bounded 4096 context offer no demonstrated decode gain here.
5. Improving supported, applicable and useful answers remains separate from speeding generation. The [latest answer review](KENN_C3_POST_ROUTING_MODEL_DIAGNOSTIC_2026-10-03.md) still finds accepted answers that miss intent, unsupported-number rejections and weak follow-up fallbacks. Do not weaken grounding to improve acceptance counts.

At this receipt's implementation commit, thinking/sampling overrides, changed numeric budgets under the same mode/task, replaced weights behind the same alias, and MLX engine identity remained separate audit work. The [later effective-generation receipt](KENN_C2_EFFECTIVE_GENERATION_CACHE_2026-10-03.md) covers HTTP numeric budgets, thinking transport and sampling. Replacement weights and actual MLX identity remain open. All prior real-model timings used `KENN_LLM_CACHE=0`; these collisions cannot explain their latency. No new model benchmark, index rebuild, private model prose or audio in this commit. C1, C2 and C3 remain unticked; UI, payload conversation and owner-scheduled Live qualification remain open.
