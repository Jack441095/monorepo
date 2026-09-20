# main.py - J K Gandy
from __future__ import annotations
from runner import main
from runner.session import (
    setup_logging as _setup_logging,
    discover_preset_families as _discover_preset_families,
    apply_drums_enabled as _apply_drums_enabled,
    resolve_drums_from_args as _resolve_drums_from_args,
)
from runner.offline import (
    slice_events_for_bar as _slice_events_for_bar,
)

# Export legacy helper functions for backward compatibility with tests/scripts.
__all__ = [
    "main",
    "_setup_logging",
    "_discover_preset_families",
    "_apply_drums_enabled",
    "_resolve_drums_from_args",
    "_slice_events_for_bar",
]

if __name__ == "__main__":
    raise SystemExit(main())
