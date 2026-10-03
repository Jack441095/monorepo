# Limiter command routing, 3 October 2026

Implementation commit: `7be9d57e2b1439bb1464b3bc128e7fca45dfe1b8`.

The thirty-turn model diagnostic found that a limiter insertion request reached knowledge generation. Both chat surfaces now send Put, Add and Insert requests to the existing command gateway, which reports that KENN cannot add Limiter yet. This avoids unnecessary answer generation and speculative device advice. Limiter advice questions remain knowledge questions. No device support, permission, grounding policy or model setting changed.

## Files and behavior

- `apps/backend/src/kenn/orchestrator.py`: adds limiter to the existing imperative device and write-intent patterns.
- `apps/backend/src/kenn/tests/test_limiter_command_routing.py`: six public-surface cases require the honest refusal, no retrieval, no answer-model call, no proposal and no Fake Live writes. Three advice-question cases retain knowledge classification.

## Verification

Commands ran sequentially from `products/kenn`, using Fake Live and fresh caches.

```sh
KENN_LIVE_BACKEND=fake PYTHONPATH="apps/backend/src:tooling" apps/backend/.venv/bin/python -m pytest -q --tb=short -p no:randomly apps/backend/src/kenn/tests/test_limiter_command_routing.py -o cache_dir=/private/tmp/kenn-pcache-limiter-routing-red-20261003
```

Before the fix: **6 failed, 3 passed**, 0.98 s, exit 1. All six command cases attempted retrieval instead of stopping at the gateway.

```sh
KENN_LIVE_BACKEND=fake PYTHONPATH="apps/backend/src:tooling" apps/backend/.venv/bin/python -m pytest -q --tb=short -p no:randomly apps/backend/src/kenn/tests/test_limiter_command_routing.py apps/backend/src/kenn/tests/test_mixing_doctor.py apps/backend/src/kenn/tests/test_full_stock_device_control.py -o cache_dir=/private/tmp/kenn-pcache-limiter-routing-green-20261003
```

After the fix: **52 passed**, 0.64 s, exit 0.

Mutation check, loaded in memory without editing the checkout:

```sh
KENN_LIVE_BACKEND=fake PYTHONPATH="apps/backend/src:tooling" apps/backend/.venv/bin/python - <<'PYTEST'
import re
import pytest
import kenn.orchestrator as routing
routing._ABLETON_PATTERNS = [re.compile(p.pattern.replace("|limiter|", "|"), p.flags) for p in routing._ABLETON_PATTERNS]
routing._ABLETON_WRITE_INTENT_RE = re.compile(routing._ABLETON_WRITE_INTENT_RE.pattern.replace("|limiter|", "|"), routing._ABLETON_WRITE_INTENT_RE.flags)
raise SystemExit(pytest.main(["-q", "--tb=short", "-p", "no:randomly", "apps/backend/src/kenn/tests/test_limiter_command_routing.py", "-o", "cache_dir=/private/tmp/kenn-pcache-limiter-routing-mutation-20261003"]))
PYTEST
```

Result: **6 failed, 3 passed**, 1.15 s, exit 1, as expected. The regressions detect removal of the routing fix.

```sh
KENN_LIVE_BACKEND=fake PYTHONPATH="apps/backend/src:tooling" apps/backend/.venv/bin/python -m pytest -q --tb=short -p no:randomly apps/backend/src/kenn/tests -o cache_dir=/private/tmp/kenn-pcache-limiter-routing-full-20261003
```

Full backend: **3635 passed, 12 skipped, 1 failed, 7 warnings**, 91.40 s, exit 1. The sole pre-existing failure is `test_personal_path_gate.py::test_the_shipped_tree_has_no_personal_path_or_remote_host`, detecting a machine-specific path in the unchanged handoff note. No suppression or unrelated edit. `git diff --check` passed. The implementation was committed with explicit staging and pushed only to `fix/review-critical-2026-10-02`.

## Research and limits

The [speed shortlist](KENN_SPEED_RESEARCH_2026-10-03.md) remains external evidence, not an M3 result. The [product research](../research/KENN_PRODUCT_AND_OPEN_SOURCE_RESEARCH_2026-10-02.md) recommends counting stage costs and separating supported, applicable and useful answers. This repair removes a known unnecessary knowledge call; it does not accelerate decoding or prove the 15-second knowledge gate. Advice questions still use normal grounding. No new runtime, asset, dependency, index rebuild or real Live operation.

C1, C2 and C3 remain unticked. The thirty-turn suite still needs a post-fix diagnostic rerun; instruction echoes and evidence applicability remain unresolved. Live-open memory/audio, UI delivery, two-track and project-switch qualification require their own evidence. Private model prose stays outside git.
