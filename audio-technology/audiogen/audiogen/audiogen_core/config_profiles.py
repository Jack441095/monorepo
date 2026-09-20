# core/config_profiles.py
# Project module `config_profiles` (core).

import logging
from copy import deepcopy

from data.conversation_presets import (
    BUILTIN_CONVERSATION_PRESETS,
    load_user_conversation_presets,
    save_user_conversation_presets,
)

logger = logging.getLogger(__name__)

_IGNORED_COMPOSITION_KEYS = frozenset({"add_arpeggio"})


def set_sample_pack(config, pack_name: str):
    if pack_name not in config.sample_packs:
        raise ValueError(f"Unknown sample pack '{pack_name}'")
    config.active_sample_pack = pack_name
    config.samplers = config._initialize_sampler_configurations()
    if config._performance_mode is not None:
        config.set_performance_mode(config._performance_mode)
    logger.info("Sample pack set to %s", pack_name)


def scaffold_sample_pack(config, pack_name: str):
    normalized_name = pack_name.strip().lower()
    if not normalized_name:
        raise ValueError("Sample pack name cannot be empty")
    if normalized_name == "default":
        raise ValueError("Cannot scaffold the reserved 'default' sample pack")
    if normalized_name in config.sample_packs:
        raise ValueError(f"Sample pack '{normalized_name}' already exists")

    scaffold = {
        sampler_name: {
            "root_midi": config.DEFAULT_PACK_ROOTS[sampler_name],
            "file_path": f"samples/{normalized_name}/{sampler_name}.wav",
        }
        for sampler_name in config.SAMPLER_ORDER
    }
    config.sample_packs[normalized_name] = scaffold
    logger.info("Scaffolded sample pack %s", normalized_name)
    return deepcopy(scaffold)


def set_conversation_preset(config, preset_name: str):
    if preset_name not in config.conversation_presets:
        raise ValueError(f"Unknown conversation preset '{preset_name}'")
    config.active_conversation_preset = preset_name
    rebuild_from_active_layers(config)
    logger.info("Conversation preset set to %s", preset_name)


def set_style_profile(config, style_name: str):
    if style_name not in config.style_profiles:
        raise ValueError(f"Unknown style profile '{style_name}'")
    config.active_style_profile = style_name
    rebuild_from_active_layers(config)
    logger.info("Style profile set to %s", style_name)


def apply_layer(config, layer):
    sample_pack = layer.get("sample_pack")
    if sample_pack:
        set_sample_pack(config, sample_pack)

    for attr, value in layer.get("composition", {}).items():
        if attr in _IGNORED_COMPOSITION_KEYS:
            continue
        setattr(config.composition, attr, value)
    for attr, value in layer.get("audio", {}).items():
        setattr(config.audio, attr, value)

    channel_mix = layer.get("channel_mix", {})
    for channel_index, mix_values in channel_mix.items():
        current_mix = dict(config.audio.channel_mix.get(channel_index, {}))
        current_mix.update(mix_values)
        config.audio.channel_mix[channel_index] = current_mix


def rebuild_from_active_layers(config):
    active_fx = config.active_post_process_preset
    config.audio = deepcopy(config._base_audio)
    config.composition = deepcopy(config._base_composition)
    config.ai = deepcopy(config._base_ai)
    config.active_sample_pack = "default"
    config.samplers = config._initialize_sampler_configurations()

    if config._performance_mode is not None:
        config.set_performance_mode(config._performance_mode)

    style = deepcopy(config.style_profiles.get(config.active_style_profile, {}))
    preset = deepcopy(config.conversation_presets.get(config.active_conversation_preset, {}))
    apply_layer(config, style)
    apply_layer(config, preset)
    if config._post_process_override_active:
        config._apply_post_process_preset(active_fx)


def export_conversation_preset(config, preset_name: str):
    if preset_name not in config.conversation_presets:
        raise ValueError(f"Unknown conversation preset '{preset_name}'")
    return deepcopy(config.conversation_presets[preset_name])


def save_conversation_preset(config, new_name: str, source_name=None):
    normalized_name = new_name.strip().lower()
    if not normalized_name:
        raise ValueError("Preset name cannot be empty")
    if normalized_name in BUILTIN_CONVERSATION_PRESETS:
        raise ValueError(f"Cannot overwrite built-in preset '{normalized_name}'")

    source = source_name or config.active_conversation_preset
    preset = export_conversation_preset(config, source)

    user_presets = load_user_conversation_presets()
    user_presets[normalized_name] = preset
    save_user_conversation_presets(user_presets)
    config.conversation_presets[normalized_name] = deepcopy(preset)
    logger.info("Saved conversation preset %s from %s", normalized_name, source)
    return deepcopy(preset)


def update_conversation_preset_field(config, preset_name: str, field_path: str, value):
    normalized_name = preset_name.strip().lower()
    if normalized_name in BUILTIN_CONVERSATION_PRESETS:
        raise ValueError(f"Cannot edit built-in preset '{normalized_name}'. Save it first with 'preset save-as'.")
    if normalized_name not in config.conversation_presets:
        raise ValueError(f"Unknown conversation preset '{normalized_name}'")

    user_presets = load_user_conversation_presets()
    if normalized_name not in user_presets:
        raise ValueError(f"Preset '{normalized_name}' is not user-editable yet. Save it first with 'preset save-as'.")

    preset = deepcopy(user_presets[normalized_name])
    parts = field_path.split(".")

    if field_path == "sample_pack":
        preset["sample_pack"] = str(value)
    elif field_path == "emotion_pool":
        preset["emotion_pool"] = list(value)
    elif field_path == "root_pool":
        preset["root_pool"] = list(value)
    elif len(parts) == 2 and parts[0] in {"composition", "audio"}:
        preset.setdefault(parts[0], {})
        preset[parts[0]][parts[1]] = value
    elif len(parts) == 2 and parts[0] in {"emotion_weights", "root_weights"}:
        preset.setdefault(parts[0], {})
        preset[parts[0]][parts[1]] = value
    else:
        raise ValueError(f"Unsupported preset field '{field_path}'")

    user_presets[normalized_name] = preset
    save_user_conversation_presets(user_presets)
    config.conversation_presets[normalized_name] = deepcopy(preset)
    if config.active_conversation_preset == normalized_name:
        set_conversation_preset(config, normalized_name)
    logger.info("Updated conversation preset %s field %s", normalized_name, field_path)
    return deepcopy(preset)
