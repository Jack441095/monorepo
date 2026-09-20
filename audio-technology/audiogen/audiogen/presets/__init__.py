"""Preset + macro plumbing for standalone realtime AudioGen.

This package intentionally contains *no* web/API code; it is safe to use from the
CLI runtime and offline utilities (if any remain).
"""

from .presets import PresetV1, list_presets, load_preset, save_preset  # noqa: F401
from .config_applier import apply_preset_to_config, apply_macros_snapshot, derived_snapshot  # noqa: F401

