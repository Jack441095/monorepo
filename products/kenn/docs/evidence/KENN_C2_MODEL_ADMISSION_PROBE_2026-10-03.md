# C2 model admission probe, 3 October 2026

Code commit: `5cd3a6495c349ef7dc83f2f23bbcf20c9502b3df`.

The background upgrade lock refuses a second background job, but foreground payload and stream provider wrappers can enter transport while that background request is still active. This is an application admission gap. It does not prove that Ollama executes the requests in parallel, rather than queuing them internally.

Exact files:

- `tooling/scripts/measure_model_admission.py`: a fresh-process diagnostic holds a stubbed background provider request open while advancing each foreground provider wrapper. It reports peak active transport requests and whether foreground entered before release. `--require-single-request` exits 1 for overlap and 2 for fixture errors.
- `apps/backend/src/kenn/tests/test_measure_model_admission.py`: eight cases cover both wrappers, a serialized transport control, restored globals, joined workers, no real provider/cache/log calls, CLI failure and unknown surfaces. The serialized control is not a production fix.

## Verification

Commands ran from `products/kenn` with Fake Live and stubbed transport. No model job, Live operation, index rebuild or other CPU-heavy job ran concurrently.

```sh
KENN_LIVE_BACKEND=fake PYTHONPATH="apps/backend/src:tooling" apps/backend/.venv/bin/python tooling/scripts/measure_model_admission.py --require-single-request
```

Final result: exit 1, expected. Both surfaces reported peak 2, foreground entered before background release, second background refused, no foreground errors. Both native requests carried `think: false`. The background fixture deliberately returns no enhanced answer, so its status is `rejected`; this is not a grounding or quality result.

```sh
KENN_LIVE_BACKEND=fake PYTHONPATH="apps/backend/src:tooling" apps/backend/.venv/bin/python -m pytest -q --tb=short -p no:randomly apps/backend/src/kenn/tests/test_measure_model_admission.py apps/backend/src/kenn/tests/test_answer_upgrades.py apps/backend/src/kenn/tests/test_measure_model_phases.py apps/backend/src/kenn/tests/test_llm_usage_telemetry.py -o cache_dir=/private/tmp/kenn-admission-probe-final-20261003
```

Final restored scoped result: 59 passed in 1.10 s. A mutation recorded peak 1 regardless of actual active requests:

```sh
KENN_LIVE_BACKEND=fake PYTHONPATH="apps/backend/src:tooling" apps/backend/.venv/bin/python -m pytest -q --tb=short -p no:randomly apps/backend/src/kenn/tests/test_measure_model_admission.py -o cache_dir=/private/tmp/kenn-admission-probe-mutation-20261003
```

Mutation result: 3 failed, 5 passed in 0.67 s. Source bytes were restored in a `finally` block before the final probe and scoped run. `git diff --cached --check` passed before the code commit. No production entry point changed, so the full backend suite was not repeated. Its latest preceding receipt has 3837 passes, 12 skips and the pre-existing `test_personal_path_gate.py::test_the_shipped_tree_has_no_personal_path_or_remote_host` failure; its findings are not copied here.

## Research decisions and limits

The [broader research](../research/KENN_PRODUCT_AND_OPEN_SOURCE_RESEARCH_2026-10-02.md#model-execution-and-resource-admission) recommends one expensive workload on this laptop until measurement supports more concurrency, bounded admission, current-turn priority and deterministic commands independent of generation. The probe establishes where the current background-only lock stops protecting admission. It exercises provider wrappers, not public HTTP routing, UI delivery, queued cancellation, fairness or server-side inference. No latency, decode gain, memory release or inference abort was measured. A shared admission change still needs busy/cancellation semantics and isolation checks before landing.

The [speed shortlist](KENN_SPEED_RESEARCH_2026-10-03.md) supplies experiment candidates, not local performance evidence:

- Decode remains the dominant measured stage. Prefix/prefill work alone cannot recover a decode-bound 15 s deadline. Repeated retrieval in the measured HTTP path was milliseconds, so it is not the first speed target.
- The [cap trial](KENN_C2_MODEL_PHASES_AND_OUTPUT_CAP_2026-10-03.md) and [brief-style trial](KENN_C2_BRIEF_STYLE_AND_RUNTIME_PROPOSAL_2026-10-03.md) saved time for some requests but lost acceptance or useful detail. Both stay disabled for Jack's decision; grounding remains unchanged.
- Thinking is already off. Keep-alive avoids cold loading at the cost of roughly 5 GB residency alongside Live; its setting stays unchanged for Jack's decision.
- Same-lineage Qwen3 8B MLX comparison remains the written proposal using this M3 / 16 GB and approximately 1,100-token prompts, with prefill and decode separate. External Qwen3.5/M3 Ultra numbers are not forecasts for this Mac. No runtime, dependency, model file or speculative draft was added.
- Improving answer usefulness still requires scoped conversation evidence, source/version applicability and held-out review. Faster delivery of a rejected or incomplete answer does not qualify the gate. No sealed evaluation set was opened and no model prose or private audio was committed.

C1, C2 and C3 remain unticked. Neither surface has qualified at least 70% accepted model delivery within 15 s with Live open. Memory pressure and audio dropouts remain for Jack's scheduled soak.
