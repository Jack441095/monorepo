from __future__ import annotations

import contextlib
from typing import Any, List, Sequence
from midi.midi_range_limiter import RANGE_LIMITER

@contextlib.contextmanager
def feedback_adaptation_context(config: Any, flags: list[str]):
    """
    Context manager that temporarily applies config/limiter adjustments
    based on audio analysis feedback flags, restoring defaults afterward.
    """
    # Save original values
    orig_bass_min = RANGE_LIMITER.configs[0].min_note
    orig_bass_max = RANGE_LIMITER.configs[0].max_note
    
    orig_bass_vel_mult = getattr(config.composition, "bass_velocity_multiplier", 1.0)
    orig_vel_curves_strength = config.composition.velocity_curves_strength
    orig_melody_rest_prob_mult = config.composition.melody_rest_prob_mult
    orig_melody_register_bias = config.composition.emotion_melody_register_bias_semitones
    orig_counter_octave_offset = getattr(config.composition, "counter_melody_octave_offset", 0)

    # 1. "Heavy sub"
    if any(f in flags for f in {"Heavy sub", "Low-end heavy balance", "Side Bass Mud"}):
        config.composition.bass_velocity_multiplier = 0.70
        RANGE_LIMITER.configs[0].min_note = 24
        RANGE_LIMITER.configs[0].max_note = 53
        
    # 2. "Low dynamics"
    if any(f in flags for f in {"Low dynamics", "Uneven loudness"}):
        config.composition.velocity_curves_strength = 0.85
        config.composition.melody_rest_prob_mult = 1.35
        
    # 3. "Low presence"
    if any(f in flags for f in {"Low presence", "Dark tonal balance"}):
        config.composition.emotion_melody_register_bias_semitones = 12
        
    # 4. "Frequency masking" / low correlation
    if any(f in flags for f in {"Frequency masking", "Low-End Phase Cancellation", "Mono risk"}):
        config.composition.counter_melody_octave_offset = -12

    try:
        yield
    finally:
        # Restore original values
        RANGE_LIMITER.configs[0].min_note = orig_bass_min
        RANGE_LIMITER.configs[0].max_note = orig_bass_max
        config.composition.bass_velocity_multiplier = orig_bass_vel_mult
        config.composition.velocity_curves_strength = orig_vel_curves_strength
        config.composition.melody_rest_prob_mult = orig_melody_rest_prob_mult
        config.composition.emotion_melody_register_bias_semitones = orig_melody_register_bias
        config.composition.counter_melody_octave_offset = orig_counter_octave_offset


def adapt_song_sections(sections: Sequence[Any], flags: list[str]) -> List[Any]:
    """Boost melody target notes per bar when presence is low."""
    if any(f in flags for f in {"Low presence", "Dark tonal balance"}):
        from composition.song_generator import SongSectionSpec
        adapted = []
        for spec in sections:
            adapted.append(SongSectionSpec(
                emotion_name=spec.emotion_name,
                bars=spec.bars,
                root_note=spec.root_note,
                temperature=spec.temperature,
                target_notes_per_bar=spec.target_notes_per_bar * 1.3,
                melody_style=spec.melody_style
            ))
        return adapted
    return list(sections)
