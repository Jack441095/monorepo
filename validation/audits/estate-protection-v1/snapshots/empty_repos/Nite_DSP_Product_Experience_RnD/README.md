# NITE DSP Product Experience & Workflow R&D

This is an isolated, local-only R&D home. It contains read-only audits, synthetic workflow probes, benchmarks, machine-readable results, and reports. It does not contain production integration.

## Rerun Probes

From this directory:

```bash
python3 benchmarks/search_and_map_benchmark.py
python3 benchmarks/ipc_benchmark.py
python3 experiments/kenn_workflow_probe.py
python3 experiments/cross_product_contract_probe.py
python3 experiments/onboarding_accessibility_localisation_probe.py
python3 user_journeys/synthetic_user_journey_lab.py
```

The scripts use deterministic synthetic fixtures except `ipc_benchmark.py`, which measures the existing AI Platform runtime over a temporary Unix socket and temporary SQLite store.

## Evidence Rules

- OBSERVED: source or existing test behavior.
- MEASURED: a rerun benchmark or executable check.
- INFERRED: conclusion from observed/measured evidence.
- HYPOTHESISED: proposed behavior awaiting validation.
- RECOMMENDED: a decision for a future engineering or research phase.

Synthetic estimates are never human usability research. Candidate capabilities are not live product integrations.

## Primary Outputs

- [Final report](NITE_DSP_PRODUCT_EXPERIENCE_RND_FINAL_REPORT.md)
- [Experiment registry](controller/EXPERIMENT_REGISTRY.json)
- [Worker matrix](controller/WORKER_MATRIX.md)
- [Performance budgets](performance/performance_budget_manifest.json)
