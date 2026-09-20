"""Tokenizer and Dataset Exporter for AudioGen Phase D Neural Generator.

Converts MIDI events and phrase event logs to scale-degree relative tokens:
(pitch_delta, duration_bin, velocity_bin).
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Sequence

# Quantization Constants
PITCH_DELTA_RANGE = (-12, 12)  # 25 pitch delta categories (-12 to +12)
DURATION_BINS = [60, 120, 240, 360, 480, 960]  # 16th-triplet, 16th, 8th, dotted-8th, quarter, half
VELOCITY_BINS = [16, 32, 48, 64, 80, 96, 112, 127]  # 8 velocity levels


def quantize_value(val: float | int, bins: Sequence[int]) -> int:
    """Find closest bin index for a given value."""
    best_idx = 0
    best_diff = abs(val - bins[0])
    for idx, b in enumerate(bins):
        diff = abs(val - b)
        if diff < best_diff:
            best_diff = diff
            best_idx = idx
    return best_idx


def encode_event_to_token(
    pitch: int,
    duration_ticks: int,
    velocity: int,
    root_pitch: int = 60,
) -> tuple[int, int, int]:
    """Encode a single MIDI note event into a (pitch_delta, duration_bin, velocity_bin) token.

    Parameters
    ----------
    pitch : int
        MIDI pitch (21-108).
    duration_ticks : int
        Note duration in ticks.
    velocity : int
        MIDI velocity (1-127).
    root_pitch : int
        Root pitch of the active scale (default 60 = C4).

    Returns
    -------
    tuple[int, int, int]
        Token tuple: (pitch_delta_idx, duration_bin_idx, velocity_bin_idx).
    """
    delta = max(-12, min(12, pitch - root_pitch))
    pitch_idx = delta + 12  # Map -12..12 -> 0..24

    dur_idx = quantize_value(duration_ticks, DURATION_BINS)
    vel_idx = quantize_value(velocity, VELOCITY_BINS)

    return (pitch_idx, dur_idx, vel_idx)


def decode_token_to_event(
    token: tuple[int, int, int],
    start_tick: int = 0,
    root_pitch: int = 60,
) -> dict[str, Any]:
    """Decode a token tuple back into a MIDI note event dict.

    Parameters
    ----------
    token : tuple[int, int, int]
        (pitch_idx, dur_idx, vel_idx).
    start_tick : int
        Start tick for the event.
    root_pitch : int
        Root pitch of the active scale.

    Returns
    -------
    dict
        MIDI event dict with keys 'pitch', 'start_tick', 'duration_ticks', 'velocity'.
    """
    pitch_idx, dur_idx, vel_idx = token

    delta = pitch_idx - 12
    pitch = root_pitch + delta
    dur = DURATION_BINS[min(dur_idx, len(DURATION_BINS) - 1)]
    vel = VELOCITY_BINS[min(vel_idx, len(VELOCITY_BINS) - 1)]

    return {
        "pitch": int(pitch),
        "start_tick": int(start_tick),
        "duration_ticks": int(dur),
        "velocity": int(vel),
    }


def export_events_to_tokens_dataset(
    phrases: list[list[dict[str, Any]]],
    output_jsonl: Path | str,
    root_pitch: int = 60,
) -> Path:
    """Export a list of note event phrases to a JSONL dataset file.

    Parameters
    ----------
    phrases : list[list[dict]]
        List of phrases, where each phrase is a list of note event dicts.
    output_jsonl : Path or str
        Destination JSONL file path.
    root_pitch : int
        Root pitch for scale-degree relative encoding.

    Returns
    -------
    Path
        Path to written JSONL dataset.
    """
    out_path = Path(output_jsonl)
    out_path.parent.mkdir(parents=True, exist_ok=True)

    records = []
    for phrase in phrases:
        tokens = [
            encode_event_to_token(
                pitch=ev.get("pitch", 60),
                duration_ticks=ev.get("duration_ticks", 240),
                velocity=ev.get("velocity", 80),
                root_pitch=root_pitch,
            )
            for ev in phrase
        ]
        if tokens:
            records.append({"tokens": tokens})

    with open(out_path, "w", encoding="utf-8") as f:
        for r in records:
            f.write(json.dumps(r) + "\n")

    return out_path
