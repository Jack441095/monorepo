# NITE DSP — Intelligent Layer Alignment R&D (Candidate Product #2)

Isolated feasibility programme. Everything in this tree is synthetic-data-only
research. No production repository, owner audio, or customer audio is touched.

## Layout

- `src/nla/` — reference research library (Python / NumPy / SciPy)
  - `corpus.py` deterministic signal generators + ground-truth transforms
  - `methods.py` alignment estimation methods
  - `interaction.py` interaction / improvement metrics
  - `decision.py` relationship classification, abstention, recommendation engine
- `experiments/` — one script per experiment family; JSON results to `results/`
- `cpp_spike/` — isolated C++ proof of core correlators + parity harness
- `results/` — machine-readable experiment outputs
- `reports/` — programme reports
- `datasets/manifests/` — corpus manifests

## Rules honoured

- Production repos READ ONLY.
- No AI attribution in commits; existing human git identity only.
- Deterministic seeds everywhere (`case_seed = hash(case_id) % 2**31`).

Run everything:

```
python3 experiments/run_all.py
```
