"""Live 12 Generative MIDI & Clip Composer Engine.

Generates scale-aware chord progressions, Euclidean rhythms, and Drum Rack patterns
for direct insertion into Ableton Live clips via AbletonOSC.
"""

from __future__ import annotations

import random
from typing import Any, Dict, List, Optional, Tuple

# Note pitch offsets from C (0)
NOTE_OFFSETS = {
    "C": 0, "C#": 1, "Db": 1,
    "D": 2, "D#": 3, "Eb": 3,
    "E": 4,
    "F": 5, "F#": 6, "Gb": 6,
    "G": 7, "G#": 8, "Ab": 8,
    "A": 9, "A#": 10, "Bb": 10,
    "B": 11,
}

# Scale intervals in semitones
SCALE_INTERVALS = {
    "major": [0, 2, 4, 5, 7, 9, 11],
    "minor": [0, 2, 3, 5, 7, 8, 10],
    "dorian": [0, 2, 3, 5, 7, 9, 10],
    "phrygian": [0, 1, 3, 5, 7, 8, 10],
    "lydian": [0, 2, 4, 6, 7, 9, 11],
    "mixolydian": [0, 2, 4, 5, 7, 9, 10],
    "harmonic_minor": [0, 2, 3, 5, 7, 8, 11],
    "pentatonic_minor": [0, 3, 5, 7, 10],
    "pentatonic_major": [0, 2, 4, 7, 9],
}

# Common chord progression roman numeral degree mappings (1-indexed)
PROGRESSIONS = {
    "pop_i_v_vi_iv": [1, 5, 6, 4],
    "ballad_vi_iv_i_v": [6, 4, 1, 5],
    "edm_vi_i_v_iv": [6, 1, 5, 4],
    "jazz_ii_v_i": [2, 5, 1],
    "ambient_i_vi": [1, 6],
}


def get_scale_pitches(root: str = "C", scale_name: str = "minor", octave: int = 3) -> List[int]:
    """Generate all MIDI pitch numbers for the specified scale across octaves."""
    clean_root = root.strip().capitalize()
    offset = NOTE_OFFSETS.get(clean_root, 0)
    intervals = SCALE_INTERVALS.get(scale_name.lower(), SCALE_INTERVALS["minor"])
    base_midi = (octave + 1) * 12 + offset
    pitches = []
    for oct_offset in (-1, 0, 1, 2):
        for interval in intervals:
            p = base_midi + (oct_offset * 12) + interval
            if 0 <= p <= 127:
                pitches.append(p)
    return sorted(set(pitches))


def generate_chord_progression(
    root: str = "C",
    scale_name: str = "minor",
    progression: str | List[int] = "pop_i_v_vi_iv",
    octave: int = 3,
    beats_per_chord: float = 4.0,
    voicing: str = "triad",  # "triad", "seventh", "spread"
    humanize_velocity: bool = True,
    seed: Optional[int] = None,
) -> List[Dict[str, Any]]:
    """Generate a scale-aware chord progression note array formatted for AbletonOSC."""
    if seed is not None:
        random.seed(seed)

    clean_root = root.strip().capitalize()
    offset = NOTE_OFFSETS.get(clean_root, 0)
    intervals = SCALE_INTERVALS.get(scale_name.lower(), SCALE_INTERVALS["minor"])
    base_midi = (octave + 1) * 12 + offset

    degrees = PROGRESSIONS.get(progression) if isinstance(progression, str) else progression
    if not degrees:
        degrees = [1, 5, 6, 4]

    notes: List[Dict[str, Any]] = []
    current_time = 0.0

    for deg in degrees:
        deg_idx = (deg - 1) % len(intervals)
        root_pitch = base_midi + intervals[deg_idx]

        # Diatonic stacking (thirds)
        third_idx = (deg_idx + 2) % len(intervals)
        fifth_idx = (deg_idx + 4) % len(intervals)
        seventh_idx = (deg_idx + 6) % len(intervals)

        third_pitch = base_midi + intervals[third_idx]
        if third_pitch <= root_pitch:
            third_pitch += 12
        fifth_pitch = base_midi + intervals[fifth_idx]
        if fifth_pitch <= third_pitch:
            fifth_pitch += 12
        seventh_pitch = base_midi + intervals[seventh_idx]
        if seventh_pitch <= fifth_pitch:
            seventh_pitch += 12

        if voicing == "triad":
            pitches = [root_pitch, third_pitch, fifth_pitch]
        elif voicing == "seventh":
            pitches = [root_pitch, third_pitch, fifth_pitch, seventh_pitch]
        elif voicing == "spread":
            pitches = [root_pitch - 12, fifth_pitch, third_pitch + 12]
        else:
            pitches = [root_pitch, third_pitch, fifth_pitch]

        base_vel = 88
        for p in pitches:
            vel = base_vel + (random.randint(-6, 6) if humanize_velocity else 0)
            vel = max(1, min(127, vel))
            notes.append({
                "pitch": p,
                "start_time": round(current_time, 3),
                "duration": round(beats_per_chord - 0.05, 3),
                "velocity": vel,
                "mute": False,
                "probability": 1.0,
            })
        current_time += beats_per_chord

    return notes


def bjorklund(steps: int, pulses: int) -> List[int]:
    """Bjorklund Euclidean rhythm algorithm."""
    if pulses <= 0:
        return [0] * steps
    if pulses >= steps:
        return [1] * steps

    pattern: List[List[int]] = []
    counts: List[int] = []
    remainders: List[int] = []

    divisor = steps - pulses
    remainders.append(pulses)
    while True:
        counts.append(divisor // remainders[-1])
        new_remainder = divisor % remainders[-1]
        remainders.append(new_remainder)
        divisor = remainders[-2]
        if remainders[-1] <= 1:
            break
    counts.append(divisor)

    def build(level: int) -> None:
        if level == -1:
            pattern.append([0])
        elif level == -2:
            pattern.append([1])
        else:
            for _ in range(counts[level]):
                build(level - 1)
            if remainders[level] != 0:
                build(level - 2)

    build(len(counts) - 1)
    flat = [item for sublist in pattern for item in sublist]
    idx = flat.index(1)
    return flat[idx:] + flat[:idx]


def generate_euclidean_rhythm(
    hits: int,
    steps: int,
    pitch: int = 36,
    step_duration_beats: float = 0.25,
    base_velocity: int = 100,
    accent_first_hit: bool = True,
) -> List[Dict[str, Any]]:
    """Generate a Euclidean rhythm sequence."""
    pattern = bjorklund(steps, hits)
    notes: List[Dict[str, Any]] = []
    first = True
    for i, active in enumerate(pattern):
        if active:
            vel = base_velocity + (15 if first and accent_first_hit else 0)
            notes.append({
                "pitch": pitch,
                "start_time": round(i * step_duration_beats, 3),
                "duration": round(step_duration_beats * 0.8, 3),
                "velocity": max(1, min(127, vel)),
                "mute": False,
                "probability": 1.0,
            })
            first = False
    return notes


def generate_drum_pattern(
    genre: str = "trap",
    bars: int = 2,
    bpm: float = 140.0,
    accent_velocity: int = 110,
    ghost_velocity: int = 65,
) -> List[Dict[str, Any]]:
    """Generate multi-voice Drum Rack patterns (Kick=36, Snare=38, Clap=39, Hat=42)."""
    notes: List[Dict[str, Any]] = []
    total_beats = bars * 4.0
    clean_genre = genre.lower()

    if clean_genre in {"trap", "hiphop"}:
        # Half-time snare on beat 3 of each bar
        for bar in range(bars):
            bar_start = bar * 4.0
            # Snare/Clap on beat 3
            notes.append({
                "pitch": 39, "start_time": bar_start + 2.0, "duration": 0.2, "velocity": accent_velocity, "mute": False, "probability": 1.0,
            })
            # Kick patterns: beat 1, beat 2.5, beat 3.75
            notes.append({
                "pitch": 36, "start_time": bar_start + 0.0, "duration": 0.4, "velocity": accent_velocity, "mute": False, "probability": 1.0,
            })
            notes.append({
                "pitch": 36, "start_time": bar_start + 1.75, "duration": 0.4, "velocity": accent_velocity - 10, "mute": False, "probability": 1.0,
            })
            notes.append({
                "pitch": 36, "start_time": bar_start + 3.25, "duration": 0.4, "velocity": accent_velocity - 15, "mute": False, "probability": 1.0,
            })
            # 1/8 note Hats with occasional 1/16 roll
            for step in range(16):
                t = bar_start + (step * 0.25)
                vel = accent_velocity - 20 if step % 2 == 0 else ghost_velocity
                notes.append({
                    "pitch": 42, "start_time": round(t, 3), "duration": 0.15, "velocity": vel, "mute": False, "probability": 1.0,
                })

    elif clean_genre in {"house", "techno"}:
        # Four-on-the-floor kick
        for beat in range(int(total_beats)):
            notes.append({
                "pitch": 36, "start_time": float(beat), "duration": 0.3, "velocity": accent_velocity, "mute": False, "probability": 1.0,
            })
            # Claps on 2 and 4
            if beat % 2 == 1:
                notes.append({
                    "pitch": 39, "start_time": float(beat), "duration": 0.2, "velocity": accent_velocity, "mute": False, "probability": 1.0,
                })
            # Offbeat open hi-hat
            notes.append({
                "pitch": 46, "start_time": float(beat) + 0.5, "duration": 0.3, "velocity": accent_velocity - 15, "mute": False, "probability": 1.0,
            })

    else:  # Standard pop/rock
        for bar in range(bars):
            bar_start = bar * 4.0
            # Kick on 1 and 3
            notes.append({"pitch": 36, "start_time": bar_start + 0.0, "duration": 0.3, "velocity": accent_velocity, "mute": False, "probability": 1.0})
            notes.append({"pitch": 36, "start_time": bar_start + 2.0, "duration": 0.3, "velocity": accent_velocity - 5, "mute": False, "probability": 1.0})
            # Snare on 2 and 4
            notes.append({"pitch": 38, "start_time": bar_start + 1.0, "duration": 0.25, "velocity": accent_velocity, "mute": False, "probability": 1.0})
            notes.append({"pitch": 38, "start_time": bar_start + 3.0, "duration": 0.25, "velocity": accent_velocity, "mute": False, "probability": 1.0})
            # 8th note hats
            for step in range(8):
                t = bar_start + (step * 0.5)
                notes.append({"pitch": 42, "start_time": round(t, 3), "duration": 0.2, "velocity": ghost_velocity, "mute": False, "probability": 1.0})

    return sorted(notes, key=lambda n: (n["start_time"], n["pitch"]))


# ---------------------------------------------------------------------------
# Krumhansl-Schmuckler Key & Scale Detection Engine
# ---------------------------------------------------------------------------

# Krumhansl-Kessler key profiles (empirically derived tonal stability weights)
_MAJOR_PROFILE = [6.35, 2.23, 3.48, 2.33, 4.38, 4.09, 2.52, 5.19, 2.39, 3.66, 2.29, 2.88]
_MINOR_PROFILE = [6.33, 2.68, 3.52, 5.38, 2.60, 3.53, 2.54, 4.75, 3.98, 2.69, 3.34, 3.17]
_DORIAN_PROFILE = [6.33, 2.68, 3.52, 5.38, 2.60, 3.53, 2.54, 4.75, 3.34, 3.98, 2.69, 3.17]

_PITCH_NAMES = ["C", "C#", "D", "D#", "E", "F", "F#", "G", "G#", "A", "A#", "B"]


def detect_scale_from_notes(notes: List[Dict[str, Any]] | List[int]) -> Dict[str, Any]:
    """Detect root key and scale mode (major/minor/dorian) using Krumhansl-Schmuckler correlation.

    Args:
        notes: Either list of note dicts with 'pitch' & 'duration', or list of integer MIDI pitches.

    Returns:
        Dict with top detected scale, confidence score (0-1), and candidate rankings.
    """
    import math

    if not notes:
        return {
            "root": "C",
            "scale": "minor",
            "key_display": "C minor",
            "confidence": 0.0,
            "candidates": [],
            "out_of_scale_notes": [],
        }

    # Build pitch class duration-weighted histogram
    histogram = [0.0] * 12
    total_weight = 0.0

    for item in notes:
        if isinstance(item, dict):
            pitch = int(item.get("pitch", 60))
            duration = float(item.get("duration", 1.0))
            velocity = float(item.get("velocity", 100))
            weight = duration * (velocity / 100.0)
        else:
            pitch = int(item)
            weight = 1.0

        pc = pitch % 12
        histogram[pc] += weight
        total_weight += weight

    if total_weight <= 0:
        total_weight = 1.0

    # Normalize histogram to mean 0, std 1
    h_mean = sum(histogram) / 12.0
    h_var = sum((x - h_mean) ** 2 for x in histogram) / 12.0
    h_std = math.sqrt(h_var) if h_var > 1e-9 else 1.0
    h_norm = [(x - h_mean) / h_std for x in histogram]

    def _correlate(profile: List[float], shift: int) -> float:
        # Rotate profile by shift
        rotated = profile[-shift:] + profile[:-shift]
        p_mean = sum(rotated) / 12.0
        p_var = sum((x - p_mean) ** 2 for x in rotated) / 12.0
        p_std = math.sqrt(p_var) if p_var > 1e-9 else 1.0
        p_norm = [(x - p_mean) / p_std for x in rotated]
        # Pearson r
        return sum(h * p for h, p in zip(h_norm, p_norm)) / 12.0

    candidates = []
    for shift in range(12):
        root_name = _PITCH_NAMES[shift]
        r_maj = _correlate(_MAJOR_PROFILE, shift)
        r_min = _correlate(_MINOR_PROFILE, shift)
        r_dor = _correlate(_DORIAN_PROFILE, shift)

        candidates.append({"root": root_name, "scale": "major", "correlation": round(r_maj, 3)})
        candidates.append({"root": root_name, "scale": "minor", "correlation": round(r_min, 3)})
        candidates.append({"root": root_name, "scale": "dorian", "correlation": round(r_dor, 3)})

    candidates.sort(key=lambda c: c["correlation"], reverse=True)
    top = candidates[0]
    best_root = top["root"]
    best_scale = top["scale"]
    best_r = top["correlation"]

    # Transform correlation to normalized confidence (0.0 to 1.0)
    confidence = max(0.0, min(1.0, (best_r + 0.5) / 1.5))

    # Identify notes that are chromatic / out of the best-fit scale
    scale_pitches = get_scale_pitches(root=best_root, scale_name=best_scale, octave=3)
    valid_pitch_classes = {p % 12 for p in scale_pitches}
    out_of_scale = []
    for item in notes:
        p = item.get("pitch") if isinstance(item, dict) else item
        if p is not None and (p % 12) not in valid_pitch_classes:
            out_of_scale.append({
                "pitch": p,
                "pitch_name": _PITCH_NAMES[p % 12],
                "time": item.get("start_time", 0.0) if isinstance(item, dict) else None,
            })

    return {
        "root": best_root,
        "scale": best_scale,
        "key_display": f"{best_root} {best_scale}",
        "confidence": round(confidence, 2),
        "correlation": best_r,
        "candidates": candidates[:5],
        "out_of_scale_notes": out_of_scale,
    }


# ---------------------------------------------------------------------------
# AudioGen Production Groove Humanization Engine
# ---------------------------------------------------------------------------

GROOVE_PROFILES = {
    "lofi_swing": {
        "swing_ratio": 0.60,       # 60% 16th swing
        "laidback_beats": 0.015,   # Laid-back pocket feel (~15ms)
        "velocity_jitter": 8,
    },
    "hiphop_boombap": {
        "swing_ratio": 0.58,
        "laidback_beats": 0.020,   # Snare/beat drag
        "velocity_jitter": 12,
    },
    "edm_shuffle": {
        "swing_ratio": 0.54,
        "laidback_beats": 0.0,
        "velocity_jitter": 5,
    },
    "acoustic_human": {
        "swing_ratio": 0.52,
        "laidback_beats": 0.008,
        "velocity_jitter": 10,
    },
    "straight": {
        "swing_ratio": 0.50,
        "laidback_beats": 0.0,
        "velocity_jitter": 3,
    },
}


def apply_audiogen_groove(
    notes: List[Dict[str, Any]],
    groove_name: str = "lofi_swing",
    seed: Optional[int] = None,
) -> List[Dict[str, Any]]:
    """Apply AudioGen micro-timing swing, laidback offset, and velocity humanization.

    Args:
        notes: List of note dicts with 'pitch', 'start_time', 'duration', 'velocity'.
        groove_name: Profile name ('lofi_swing', 'hiphop_boombap', 'edm_shuffle', 'acoustic_human', 'straight').
    """
    if seed is not None:
        random.seed(seed)

    profile = GROOVE_PROFILES.get(groove_name.lower(), GROOVE_PROFILES["straight"])
    swing = profile["swing_ratio"]
    laidback = profile["laidback_beats"]
    v_jitter = profile["velocity_jitter"]

    humanized: List[Dict[str, Any]] = []
    for n in notes:
        item = dict(n)
        start = float(item.get("start_time", 0.0))
        vel = int(item.get("velocity", 90))

        # Check if note is on an off-beat 16th (e.g. 0.25, 0.75, 1.25...)
        step_16th = round(start / 0.25)
        is_even_16th = (step_16th % 2 == 1)

        offset = laidback
        if is_even_16th and swing != 0.50:
            # Shift the offbeat by the swing amount relative to a 16th grid
            swing_offset = (swing - 0.50) * 0.25
            offset += swing_offset

        # Micro-jitter (+- 2ms)
        timing_jitter = (random.random() - 0.5) * 0.005
        new_start = max(0.0, round(start + offset + timing_jitter, 3))

        # Velocity dynamics jitter
        vel_delta = random.randint(-v_jitter, v_jitter)
        new_vel = max(1, min(127, vel + vel_delta))

        item["start_time"] = new_start
        item["velocity"] = new_vel
        humanized.append(item)

    return sorted(humanized, key=lambda x: (x["start_time"], x["pitch"]))


# ---------------------------------------------------------------------------
# AudioGen Harmonic Bassline Synthesizer
# ---------------------------------------------------------------------------

def generate_audiogen_bassline(
    root: str = "C",
    scale_name: str = "minor",
    style: str = "bouncy",  # "bouncy", "driving", "sustained", "drone"
    bars: int = 4,
    octave: int = 1,  # Sub/bass register (MIDI 24-36)
    groove: str = "straight",
) -> List[Dict[str, Any]]:
    """Synthesize scale-locked basslines using AudioGen register clamping and rhythmic topologies."""
    clean_root = root.strip().capitalize()
    offset = NOTE_OFFSETS.get(clean_root, 0)
    intervals = SCALE_INTERVALS.get(scale_name.lower(), SCALE_INTERVALS["minor"])
    base_pitch = (octave + 1) * 12 + offset  # Octave 1 C = 24

    root_pitch = base_pitch
    fifth_pitch = base_pitch + 7
    octave_pitch = base_pitch + 12

    notes: List[Dict[str, Any]] = []

    for b in range(bars):
        bar_start = b * 4.0

        if style == "drone":
            notes.append({
                "pitch": root_pitch, "start_time": bar_start, "duration": 3.95, "velocity": 95, "mute": False, "probability": 1.0,
            })
        elif style == "sustained":
            # 2 whole notes per bar
            notes.append({"pitch": root_pitch, "start_time": bar_start + 0.0, "duration": 1.95, "velocity": 98, "mute": False, "probability": 1.0})
            notes.append({"pitch": fifth_pitch, "start_time": bar_start + 2.0, "duration": 1.95, "velocity": 92, "mute": False, "probability": 1.0})
        elif style == "driving":
            # 8th-note driving bass
            for step in range(8):
                p = root_pitch if step % 4 != 3 else octave_pitch
                vel = 104 if step % 2 == 0 else 88
                notes.append({
                    "pitch": p,
                    "start_time": round(bar_start + (step * 0.5), 3),
                    "duration": 0.42,
                    "velocity": vel,
                    "mute": False,
                    "probability": 1.0,
                })
        else:  # "bouncy" - Syncopated root/fifth/octave bounce
            notes.append({"pitch": root_pitch, "start_time": bar_start + 0.0, "duration": 0.85, "velocity": 105, "mute": False, "probability": 1.0})
            notes.append({"pitch": root_pitch, "start_time": bar_start + 1.5, "duration": 0.40, "velocity": 92, "mute": False, "probability": 1.0})
            notes.append({"pitch": fifth_pitch, "start_time": bar_start + 2.0, "duration": 0.75, "velocity": 98, "mute": False, "probability": 1.0})
            notes.append({"pitch": octave_pitch, "start_time": bar_start + 3.25, "duration": 0.65, "velocity": 94, "mute": False, "probability": 1.0})

    if groove != "straight":
        notes = apply_audiogen_groove(notes, groove_name=groove)

    return notes

