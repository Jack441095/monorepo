# Active source paths and retired comments — 2 October 2026

This bounded cleanup follows `5d0f0f17283e396bc22bb998b763f8ae25ad873f`.
It records source verification, not a completed codebase audit or release qualification.

## Exact changes

| File under `products/kenn/` | Change |
| --- | --- |
| `apps/backend/src/kenn/autonomous_agent.py` | Remove an immediately overwritten legacy mix-output assignment and obsolete path commentary. Remove the mixdown-analysis `try` block after an unconditional return and its unused import; retain the reachable LTAS measurement statements. |
| `packages/chat/requirements.txt` | Resolve the include to the existing `apps/backend/requirements.txt`, shared with the canonical wrapper. |
| `chat/build_runtime_index.py` | Default to `apps/backend/src` under the product root. Preserve explicit engine/index overrides, invalid-directory rejection and configure-before-build order. |
| `chat/tests/test_build_runtime_index.py` | Seven configuration cases execute the real standalone script with fake import/build owners, without creating an index. |
| `apps/backend/src/kenn/core/tool_trigger.py` | Remove a retired roadmap pointer; retain the dated explicit-tool policy. |
| `apps/backend/src/kenn/core/tool_registry.py` | Remove a retired roadmap pointer. |
| `apps/backend/src/kenn/core/tool_registry_defaults.py` | Remove a retired roadmap pointer; name current mix-review/masking owners and accurately describe unavailable AutoMix/separation entries. |
| `apps/backend/src/kenn/core/project_source.py` | Remove retired roadmap references; retain source-file lifetime and single-file constraints. |
| `apps/backend/src/kenn/core/mix_guardrails.py` | Remove a retired roadmap pointer; retain guardrail rationale. |
| `apps/backend/src/kenn/core/track_relevance.py` | Remove a retired roadmap pointer; retain display-scope rationale. |

Both wrapper requirements includes resolve to the same existing manifest. No installation was used to verify this path change. AST comparison establishes that the two output-root assignments were consecutive, with no intervening read, and that the reachable mixdown statements remain identical after removing the unused import. All six header changes leave executable ASTs identical after excluding their module docstrings.

## Verification

From `apps/backend/src`:

```sh
../.venv/bin/python -m pytest -q -p no:randomly kenn/tests/test_orchestrator_autonomous.py kenn/tests/test_autonomous_guardian_integration.py kenn/tests/test_ported_platform_modules.py kenn/tests/test_reference_tool_evidence.py kenn/tests/test_audio_analysis.py
../.venv/bin/python -m pytest -q -p no:randomly kenn/tests/test_stem_masking_chat_tool.py
```

Results: **47 passed in 1.36 s**, then **4 passed in 0.55 s**.

From the monorepo root:

```sh
products/kenn/apps/backend/.venv/bin/python -m pytest -q -p no:randomly products/kenn/chat/tests/test_build_runtime_index.py
products/kenn/apps/backend/.venv/bin/python -m pytest -q -p no:randomly products/kenn/chat/tests
products/kenn/apps/backend/.venv/bin/python -m pytest -q -p no:randomly products/kenn/packages/chat/tests
git diff --check
```

The builder cases first reproduced **2 failures and 5 passes** against the old default, then **7 passed in 0.02 s** after the fix. Six compiled-copy behavioral mutations were caught; the real source was not mutated. The full canonical wrapper suite passed **58 cases in 5.64 s**, including those seven. The package wrapper suite reported **72 passed and 2 failed in 8.58 s**. Both wrapper runs emit the existing Starlette/httpx and anyio deprecation warnings.

The two failures are `test_eval_chat_coverage.py::test_full_chat_coverage_receipt_passes` and `test_eval_runner.py::test_full_evaluation_receipt_passes`. Paired isolated launches using current source and an original-HEAD import hook reproduce identical assertions and byte-equal evaluation receipts. None of the seven touched backend modules is imported by these evaluator paths; neither standalone builder nor requirements file executes there. Source and active-index hashes remain unchanged through the comparison.

The coverage receipt passes **125 of 128** cases. Its failing IDs are `arrangement-energy-transitions`, `wwise-mobile-ambience-memory` and `ambiguity-thin-vocal-eq-vs-recording`. The separate evaluation fails `harsh-after-mastering`, `new-topic-does-not-inherit-old-diagnosis`, `eval-followup-snare-layer-mono`, `upgrade-buffer-recording` and `upgrade-room-null`. These remain open quality findings; expected outputs, grounding guards and index contents were preserved.

An initial attempt to collect both wrappers in one pytest process stops on their existing duplicate `test_app` and `test_eval_runner` module names. The results above use separate processes, matching their collection boundary.

The earlier **3,413-pass** backend run predates this batch. This cleanup did not rerun or certify that full suite, build a container, rebuild an index, run a model or control Live. Legacy container paths, remaining stale document pointers, and the wider Audio_Too inventory remain unqualified audit work in `KENN_PLAN.md`.
