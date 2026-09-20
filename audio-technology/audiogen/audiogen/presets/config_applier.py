from __future__ import annotations

from typing import Any, Dict, Optional

from audiogen_core.config_guard import allow_config_mutations
from presets.macros import apply_macros_to_config
from presets.presets import PresetV1


def apply_preset_to_config(cfg: Any, preset: PresetV1) -> None:
    with allow_config_mutations("apply_preset_layers"):
        md = dict(getattr(preset, "metadata", {}) or {})
        try:
            cfg.set_sample_pack(str(preset.sample_pack))
        except Exception:
            pass
        try:
            cfg.set_style_profile(str(preset.style_profile))
        except Exception:
            pass
        try:
            cfg.set_conversation_preset(str(preset.conversation_preset))
        except Exception:
            pass
        try:
            setattr(cfg.composition, "arranged_song_mode", str(preset.arrangement_style))
        except Exception:
            pass
        try:
            # FX preset is an audio-layer in core config
            if hasattr(cfg, "set_post_process_preset"):
                cfg.set_post_process_preset(str(preset.fx_preset))
            else:
                setattr(cfg.audio, "active_post_process_preset", str(preset.fx_preset))
        except Exception:
            pass
        try:
            hook_safe = md.get("hook_safe_mode", None)
            if hook_safe is not None and hasattr(cfg, "set_composition_hook_safe_mode"):
                cfg.set_composition_hook_safe_mode(bool(hook_safe))
        except Exception:
            pass
        try:
            overrides = dict(md.get("composition_overrides", {}) or {})
        except Exception:
            overrides = {}
        for k, v in overrides.items():
            try:
                setattr(cfg.composition, str(k), v)
            except Exception:
                continue
        # Ensure sampler configs reflect audio knobs (e.g. drone volume -> amplitude_db).
        try:
            if hasattr(cfg, "rebuild_samplers"):
                cfg.rebuild_samplers()
        except Exception:
            pass


def apply_macros_snapshot(cfg: Any, macros: Dict[str, float]) -> None:
    with allow_config_mutations("apply_macros"):
        apply_macros_to_config(cfg, dict(macros or {}))
        try:
            if hasattr(cfg, "rebuild_samplers"):
                cfg.rebuild_samplers()
        except Exception:
            pass


def derived_snapshot(
    cfg: Any,
    *,
    active_preset: Optional[PresetV1] = None,
    macros: Optional[Dict[str, float]] = None,
) -> Dict[str, Any]:
    return {
        "layers": {
            "sample_pack": str(getattr(cfg, "active_sample_pack", "default") or "default"),
            "style_profile": str(getattr(cfg, "active_style_profile", "default") or "default"),
            "conversation_preset": str(getattr(cfg, "active_conversation_preset", "default_ambient_01") or "default_ambient_01"),
            "arrangement_style": str(
                getattr(getattr(cfg, "composition", None), "arranged_song_mode", "default") or "default"
            ),
            "fx_preset": str(getattr(cfg, "active_post_process_preset", "default") or "default"),
        },
        "preset": None if active_preset is None else active_preset.to_dict(),
        "macros": dict(macros or {}),
    }
