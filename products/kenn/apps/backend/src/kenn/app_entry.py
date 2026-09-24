"""Entry point for the packaged KENN app: settings file -> environment -> server.

A signed app bundle is read-only, and testers have no shell to export
variables. This entry point, run before any other KENN module is imported:

1. puts everything KENN writes (receipts, chats, caches, logs) under one
   user-writable data folder, by default ``~/Library/Application Support/KENN``;
2. reads ``settings.json`` from that folder (created with defaults on first
   run) and turns each setting into the environment variable KENN already
   understands.

Variables already set in the environment always win, so a developer's shell
setup keeps working unchanged.
"""

from __future__ import annotations

import json
import os
import sys
from pathlib import Path
from typing import Any, MutableMapping

DEFAULT_DATA_ROOT = Path.home() / "Library" / "Application Support" / "KENN"

# Every file or folder KENN writes, relative to the data folder.
DATA_LOCATIONS = {
    "KENN_RUNTIME_ROOT": "runtime",
    "KENN_CHATS_DIR": "chats",
    "KENN_DB_PATH": "chats/kenn.db",
    "KENN_SESSION_FILE": "chats/session.json",
    "KENN_LIVE_RECEIPT_JOURNAL": "live/ableton_receipts.jsonl",
    "KENN_LIVE_LLM_SHADOW_LOG": "live/live_llm_shadow.jsonl",
    "KENN_LIVE_LLM_PROMOTION_STATE": "live/live_llm_promotion.json",
    "KENN_ANALYSIS_CACHE_DIR": "analysis_cache",
    "KENN_MIX_OUTPUT_ROOT": "mix_outputs",
}

# settings.json key -> (environment variable, default for a beta tester build).
SETTINGS = {
    # Live control still needs Apply on every proposal; this only lets KENN propose writes at all.
    "allow_daw_control": ("KENN_ALLOW_DAW_CONTROL", True),
    "port": ("KENN_PORT", 8090),
    # The AI planner stays out of tester builds until it passes its promotion gate.
    "live_llm_enabled": ("KENN_LIVE_LLM_ENABLED", False),
    "llm_enabled": ("KENN_LLM_ENABLED", False),
    "llm_provider": ("KENN_LLM_PROVIDER", ""),
    "llm_model": ("KENN_LLM_MODEL", ""),
    "llm_base_url": ("KENN_LLM_BASE_URL", ""),
    "telemetry_opt_out": ("KENN_TELEMETRY_OPT_OUT", True),
}


def _as_env(value: Any) -> str:
    if isinstance(value, bool):
        return "1" if value else "0"
    return str(value)


def load_settings(data_root: Path) -> dict[str, Any]:
    """settings.json merged over the defaults; written with defaults if missing."""
    defaults = {key: default for key, (_env, default) in SETTINGS.items()}
    path = data_root / "settings.json"
    try:
        stored = json.loads(path.read_text(encoding="utf-8"))
    except FileNotFoundError:
        stored = None
    except (OSError, ValueError):
        stored = {}  # unreadable: run on defaults, leave the file for the user to fix
    if stored is None:
        try:
            data_root.mkdir(parents=True, exist_ok=True)
            path.write_text(json.dumps(defaults, indent=2) + "\n", encoding="utf-8")
        except OSError:
            pass
        stored = {}
    return {**defaults, **{key: value for key, value in stored.items() if key in SETTINGS}}


def prepare_environment(environ: MutableMapping[str, str] | None = None, data_root: Path | None = None) -> Path:
    """Fill the environment from the data folder and settings; return the data folder."""
    environ = os.environ if environ is None else environ
    root = Path(environ.get("KENN_DATA_ROOT") or data_root or DEFAULT_DATA_ROOT).expanduser()
    environ.setdefault("KENN_DATA_ROOT", str(root))
    for variable, relative in DATA_LOCATIONS.items():
        environ.setdefault(variable, str(root / relative))
    for folder in ("runtime", "chats", "live", "analysis_cache", "mix_outputs"):
        (root / folder).mkdir(parents=True, exist_ok=True)
    settings = load_settings(root)
    for key, (variable, _default) in SETTINGS.items():
        value = settings.get(key)
        if value not in (None, ""):
            environ.setdefault(variable, _as_env(value))
    return root


def main() -> int:
    prepare_environment()
    source_root = Path(__file__).resolve().parents[1]
    if str(source_root) not in sys.path:
        sys.path.insert(0, str(source_root))
    from kenn.server import main as server_main  # imported only after the environment is ready

    return server_main()


if __name__ == "__main__":
    raise SystemExit(main())
