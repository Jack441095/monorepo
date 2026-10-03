# C2 local model admission, 3 October 2026

Code commit: `75b0791ccdefd6308b8591e74d80e39c5851bcff`.

The earlier offline probe admitted foreground generation while a background upgrade held the local provider. KENN now refuses that competing request immediately and retains its grounded fallback. Payload, streaming, routing and keep-alive work share one process-local slot for Ollama and the existing optional MLX path. Cached replies remain available; remote providers retain independent concurrency. Client startup acquires admission before starting the keep-alive thread, so the first answer owns the slot.

Exact files:

- `apps/backend/src/kenn/llm/llm_rewrite.py`: local admission, busy telemetry, release on completion/error/stream close and guarded keep-alive ping. Busy MLX does not load weights or fall through to HTTP.
- `apps/backend/src/kenn/tests/test_llm_model_admission.py`: 17 cases for overlapping work, cached replies, remote isolation, actual grounded fallback, startup ping and release after failure.
- `tooling/scripts/measure_model_admission.py`: reports admission, immediate foreground completion and expected busy errors; `--without-admission` preserves the counterfactual probe.
- `apps/backend/src/kenn/tests/test_measure_model_admission.py`: admission/control matrix and probe isolation.
- `apps/backend/src/kenn/tests/test_llm_usage_telemetry.py` and `test_provider_cache_ownership.py`: use a stubbed remote provider for tests whose contract requires overlapping calls.
- `apps/backend/src/kenn/tests/test_server_smoke.py`: disable canonical and legacy model switches plus background generation within a restored environment. The legacy switch alone allowed an owner-enabled background worker to escape the HTTP fixture and hold admission during later tests. No production configuration was changed by this fixture repair.

## Verification

Commands ran from `products/kenn`, on Fake Live with stubbed providers. One CPU-heavy job ran at a time. No model files, dependencies, index rebuild or real Live operation were needed.

```sh
KENN_LIVE_BACKEND=fake PYTHONPATH="apps/backend/src:tooling" apps/backend/.venv/bin/python tooling/scripts/measure_model_admission.py --require-single-request
```

Exit 0: both surfaces peak at one active provider request. Foreground finishes before background release with `LLMBusyError`; it never enters provider transport. The second background job remains refused. The fixture deliberately rejects its background answer, so that status is not quality evidence.

```sh
KENN_LIVE_BACKEND=fake PYTHONPATH="apps/backend/src:tooling" apps/backend/.venv/bin/python tooling/scripts/measure_model_admission.py --require-single-request --without-admission
```

Expected exit 1: both surfaces peak at two requests and foreground enters before background release. This uses stubbed transport and does not prove simultaneous server-side inference.

```sh
KENN_LLM_ENABLED=1 KENN_LIVE_BACKEND=fake PYTHONPATH="apps/backend/src:tooling" apps/backend/.venv/bin/python -m pytest -q --tb=short -p no:randomly apps/backend/src/kenn/tests/test_server_smoke.py apps/backend/src/kenn/tests/test_stream_cancel_work.py apps/backend/src/kenn/tests/test_provider_cache_ownership.py apps/backend/src/kenn/tests/test_llm_model_admission.py apps/backend/src/kenn/tests/test_measure_model_admission.py apps/backend/src/kenn/tests/test_llm_usage_telemetry.py apps/backend/src/kenn/tests/test_llm_generation_bounds.py apps/backend/src/kenn/tests/test_llm_plan_schema.py apps/backend/src/kenn/tests/test_answer_upgrades.py apps/backend/src/kenn/tests/test_streamed_generation_prefix_guard.py -o cache_dir=/private/tmp/kenn-model-admission-scoped-final-20261003
```

Final scoped result: 224 passed in 5.31 s, including an explicitly enabled owner model environment.

```sh
KENN_LIVE_BACKEND=fake PYTHONPATH="apps/backend/src:tooling" apps/backend/.venv/bin/python -m pytest -q --tb=short -p no:randomly apps/backend/src/kenn/tests -o cache_dir=/private/tmp/kenn-model-admission-full-restored-20261003
```

Final full result: 3867 passed, 12 skipped, 5 warnings and one pre-existing failure in 85.15 s. The failure is `test_personal_path_gate.py::test_the_shipped_tree_has_no_personal_path_or_remote_host`; its historical evidence findings are not copied here. Earlier intermittent stream failures were traced to the smoke fixture's escaped background worker. After fixing environment isolation, those failures do not recur in this run.

Before the guard, the two foreground/background regression cases failed. Disabling local admission temporarily produced 9 failures and 6 passes in the then-current admission module; source was restored before verification. The two client-startup cases also failed before moving startup inside admission. The smoke isolation regression failed with `KENN_LLM_ENABLED=1` before the fixture repair. All pass restored. `git diff --cached --check` passed before the code commit.

## Research decisions and limits

The [broader research](../research/KENN_PRODUCT_AND_OPEN_SOURCE_RESEARCH_2026-10-02.md#model-execution-and-resource-admission) recommends bounded admission on this laptop. This change implements one generation slot with immediate fallback. It provides no foreground priority, preemption, queue, fairness, server abort or cross-process coordination. A background request already holding the slot can cause a foreground fallback. An idle ping can hold it for its existing timeout. Audio analysis and external Ollama clients are outside this guard.

The [speed shortlist](KENN_SPEED_RESEARCH_2026-10-03.md) remains a list of experiments. Admission removes an overlap opportunity; no decode gain, latency gain, memory release or Live-open improvement was measured. Decode remains the dominant measured cost. Prior cap and brief-style trials lost useful detail or acceptance and stay disabled pending Jack's decision. Grounding, thinking, production output ceiling and keep-alive settings remain unchanged.

Keep-alive retains roughly 5 GB alongside Live to avoid cold reloads; memory pressure and audio dropouts remain for Jack's scheduled soak. The Qwen3 8B / approximately 1,100-token MLX comparison remains a written proposal only. No runtime switch, dependency, download or speculative draft was added. Mocked MLX checks do not qualify that runtime. No model prose, private audio or sealed evaluation material was committed.

C1, C2 and C3 stay unticked. Neither surface has qualified at least 70% eligible accepted model answers within 15 s with Live open.
