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

Live control defaults to the bundled `osc` backend. To select the read-only
Ableton Control Deck MCP adapter, set `KENN_LIVE_BACKEND=control-deck-mcp`,
`KENN_LIVE_MCP_COMMAND` to its built stdio server command, and optionally
`KENN_LIVE_MCP_CWD` and `KENN_LIVE_MCP_TIMEOUT_SECONDS`. The selected MCP
process is persistent, local, shell-free, and restricted to an explicit read
tool allowlist.
