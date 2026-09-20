# KENN backend

The importable Python package lives in `src/kenn`. From `products/kenn`:

```bash
PYTHONPATH=apps/backend/src python3 run_ux_backend.py
```

Run the backend tests from this directory with:

```bash
PYTHONPATH=src:../../tooling .venv/bin/pytest -q src/kenn/tests
```

The SLO adapter is read-only and uses `SLO_CLASSIFICATION_DB` when set. Product-level paths are defined in `src/kenn/paths.py`; extend that module when adding another workspace area.
