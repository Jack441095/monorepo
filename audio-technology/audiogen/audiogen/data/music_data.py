# music_data.py
# Emotional profiles and chord progression data for the music generation system.

import random
import logging
from typing import List, Optional

from data.chord_parser import get_root_pitch_class
from importlib import util as _importlib_util
from pathlib import Path as _Path
import sys as _sys

# Load EmotionProfile implementation from a filename containing a hyphen.
_here = _Path(__file__).resolve().parent
_src = _here / "emotion_profile_per-emotion_harmony.py"
_spec = _importlib_util.spec_from_file_location("_emotion_profile_impl", str(_src))
if _spec is None or _spec.loader is None:
    raise ImportError("Failed to load emotion profile implementation module spec.")
_emo_mod = _importlib_util.module_from_spec(_spec)
_sys.modules[str(_spec.name)] = _emo_mod
_spec.loader.exec_module(_emo_mod)  # type: ignore[attr-defined]

EmotionProfile = _emo_mod.EmotionProfile
chord_progression_pool_for_section_role = _emo_mod.chord_progression_pool_for_section_role
merged_chord_progression_pool = _emo_mod.merged_chord_progression_pool
from data.music_theory import (CHORD_SUBSTITUTIONS, RELATIVE_SUBSTITUTIONS,
                               TRITONE_SUBSTITUTIONS)

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Helper functions
# ---------------------------------------------------------------------------

def get_root(chord: str, key_root: Optional[str] = None) -> int:
    return get_root_pitch_class(chord, key_root)


def create_passing_chord(chord1: str, chord2: str) -> Optional[str]:
    root1 = get_root(chord1)
    root2 = get_root(chord2)
    interval = (root2 - root1) % 12
    if interval == 5:
        mid_root = (root1 + 2) % 12
        return f"{mid_root}dim7"
    elif interval == 2:
        mid_root = (root1 + 1) % 12
        return f"{mid_root}dim7" if 'min' in chord1 else f"{mid_root}7"
    elif interval == 7:
        return f"V7/{chord2}"
    return None


def substitute_tritone(chord: str) -> str:
    for dom, sub in TRITONE_SUBSTITUTIONS.items():
        if dom in chord:
            return chord.replace(dom, sub)
    return chord


def relative_substitution(chord: str) -> str:
    for rel_from, rel_to in RELATIVE_SUBSTITUTIONS.items():
        if chord.startswith(rel_from):
            return chord.replace(rel_from, rel_to, 1)
    return chord


def apply_substitution(chord: str, substitution_type: str = 'color') -> str:
    if substitution_type == 'tritone' and '7' in chord and 'maj7' not in chord:
        return substitute_tritone(chord)
    elif substitution_type == 'relative':
        return relative_substitution(chord)
    elif substitution_type == 'color':
        for base, subs in CHORD_SUBSTITUTIONS.items():
            if chord.startswith(base):
                root = chord[:len(base)]
                sub = random.choice(subs)
                return root + sub[len(base):]
    return chord


def simplify_chord(chord: str) -> str:
    simplified = ''.join(c for c in chord if not c.isdigit())
    for token in ('#11', 'b9', '#9', 'add', 'sus', '13', '11', '9', '°', 'ø'):
        simplified = simplified.replace(token, '')
    if simplified.endswith('maj7'):
        return simplified[:-4]
    elif simplified.endswith('maj'):
        return simplified
    elif simplified.endswith('min7'):
        return simplified[:-1]
    elif simplified.endswith('min'):
        return simplified
    elif simplified.endswith('7'):
        return simplified[:-1]
    return simplified


def humanize_progression(progression: List[str],
                         humanization_intensity: float = 0.3) -> List[str]:
    if random.random() > humanization_intensity:
        return progression
    variations = []
    for i, chord in enumerate(progression):
        if i < len(progression) - 1 and random.random() < 0.2:
            passing = create_passing_chord(chord, progression[i + 1])
            if passing:
                variations.append(passing)
        if random.random() < 0.15:
            variations.append(apply_substitution(chord, random.choice(['color', 'tritone', 'relative'])))
        else:
            variations.append(chord)
    return variations


def add_passing_chords(progression: List[str], density: float = 0.3) -> List[str]:
    result = []
    for i in range(len(progression) - 1):
        current = progression[i]
        next_chord = progression[i + 1]
        result.append(current)
        interval = abs(get_root(current) - get_root(next_chord)) % 12
        if interval > 4 and random.random() < density:
            passing = create_passing_chord(current, next_chord)
            if passing:
                result.append(passing)
    result.append(progression[-1])
    return result


def humanize_chord_rhythm(progression: List[str],
                          base_duration: float = 4.0) -> List[tuple]:
    result = []
    for i, chord in enumerate(progression):
        if i == 0:
            duration = base_duration * random.uniform(1.0, 1.5)
        elif i == len(progression) - 1:
            duration = base_duration * random.uniform(1.2, 2.0)
        else:
            duration = base_duration * random.uniform(0.5, 1.2)
        if i < len(progression) - 1 and random.random() < 0.3:
            result.append((chord, duration * 0.9))
            result.append((progression[i + 1], duration * 0.1))
        else:
            result.append((chord, duration))
    return [(c, d) for c, d in result if c is not None]


def get_progression_variation(progression: List[str],
                              phrase_position: float) -> List[str]:
    if phrase_position < 0.25:
        return progression[:4]
    elif phrase_position < 0.6:
        return [apply_substitution(c, 'color') if random.random() < 0.3 else c
                for c in progression]
    elif phrase_position < 0.8:
        varied = []
        for chord in progression:
            if 'maj' in chord:
                varied.append(chord.replace('maj', 'maj7#11') if 'maj' in chord else chord)
            elif 'min' in chord:
                varied.append(chord.replace('min', 'min9') if 'min' in chord else chord)
            elif '7' in chord:
                varied.append(chord + '#11' if '#11' not in chord else chord)
            else:
                varied.append(chord + '7' if '7' not in chord else chord)
        return varied
    else:
        return [simplify_chord(c) for c in progression]


EMOTIONS = [
    EmotionProfile("admiration",
        scale_intervals=[0, 2, 4, 5, 7, 9, 11],   # major
        tempo_multiplier=0.72, velocity_multiplier=0.88, density=0.42,
        chord_progressions=[
            # Specialised — lush, open, appreciative
            ["Imaj9", "iii7", "vi11", "Imaj13"],
            ["Imaj7", "V13sus4", "Imaj9", "Imaj13"],
            ["Imaj9", "ii9", "iii9", "Imaj13"],
            ["Imaj13", "vi13", "IVmaj9", "Imaj9"],
            ["Imaj9", "IVmaj13", "ii11", "V13"],
            # Emotion-specific replacements (were generic I-V-vi-IV etc.)
            ["Imaj9", "V13sus4", "iii9", "IVmaj13"],       # smooth descending thirds
            ["Imaj13", "vi7", "IVmaj9", "Imaj13"],         # warmer pop back-cycle
            ["I", "iii", "IV", "V"],                        # ascending bass line
            ["Imaj7", "IV6", "iii7", "vi7"],                # circle of thirds
            ["Imaj9", "ii9", "IVmaj7", "Imaj9"],            # plagal resolution
            # Cinematic / score-like — long breath, minimal harmonic rhythm
            ["Imaj9", "vi7", "IVmaj9", "Imaj9"],
            ["Imaj7", "Imaj7", "IVmaj7", "vi7"],
            ["I", "Imaj7", "IV", "I"],
        ],
        cadence_progressions=[["V13", "Imaj9"], ["ii11", "Imaj13"], ["IVmaj7", "Imaj7"], ["Vsus4", "I"]],
        arrangement_chord_sets={
            "intro": [
                ["Imaj9", "Imaj7", "IVmaj9", "Imaj9"],
                ["Imaj9", "iii7", "IVmaj7", "Imaj9"],
            ],
            "a": [
                ["Imaj9", "iii7", "vi11", "IVmaj9"],
                ["Imaj9", "ii9", "IVmaj7", "vi7"],
                ["I", "iii", "IV", "vi"],
            ],
            "pre_chorus": [
                ["vi11", "ii9", "IVmaj9", "V13sus4"],
                ["iii7", "vi11", "ii9", "V13"],
                ["Imaj9", "ii9", "IVmaj9", "V13sus4"],
            ],
            "b": [
                ["Imaj9", "V13", "vi11", "Imaj9"],
                ["Imaj9", "ii9", "V13", "Imaj9"],
                ["I", "V", "IV", "I"],
            ],
            "a_prime": [
                ["Imaj9", "iii7", "vi11", "Imaj13"],
                ["Imaj13", "vi13", "IVmaj9", "Imaj9"],
            ],
            "outro": [
                ["Imaj9", "IVmaj7", "Imaj9", "Imaj9"],
                ["Imaj7", "ii7", "Imaj9", "Imaj9"],
            ],
        }),

    EmotionProfile("amusement",
        scale_intervals=[0, 2, 4, 5, 7, 9, 11],   # major
        tempo_multiplier=1.65, velocity_multiplier=0.95, density=0.88,
        chord_progressions=[
            # Specialised — bright, bouncy, slightly quirky
            ["I69", "bVIImaj9", "IVmaj7", "I69"],
            ["I7", "IV7", "bVII7", "I7"],
            ["Iadd9", "Vsus4", "V7", "I69"],
            ["I", "bVII", "IV", "I"],
            ["I69", "bVImaj7", "bVII9", "IVadd9"],
            # Emotion-specific
            ["I7", "IV7", "I7", "V7"],                      # blues-flavoured
            ["I", "IV", "bVII", "IV"],                      # back-cycling
            ["I7", "bVII7", "IV7", "I7"],                   # bluesy major
            ["I", "ii", "IV", "I"],                         # simple & happy
            ["I", "bIII", "IV", "I"],                       # borrowed bIII colour
        ],
        cadence_progressions=[["IV", "I"], ["bVII", "I"]],
        arrangement_chord_sets={
            "intro": [
                ["I69", "bVIImaj9", "IVmaj7", "I69"],
                ["I7", "IV7", "bVII7", "I7"],
            ],
            "a": [
                ["I7", "IV7", "bVII7", "I7"],
                ["Iadd9", "Vsus4", "V7", "I69"],
                ["I", "bVII", "IV", "I"],
            ],
            "b": [
                ["Iadd9", "Vsus4", "V7", "I69"],
                ["I", "bVII", "IV", "I"],
                ["I69", "bVImaj7", "bVII9", "IVadd9"],
            ],
            "a_prime": [
                ["I", "bVII", "IV", "I"],
                ["I69", "bVImaj7", "bVII9", "IVadd9"],
            ],
            "outro": [
                ["I69", "bVImaj7", "bVII9", "IVadd9"],
                ["I", "IV", "bVII", "IV"],
            ],
        }),

    EmotionProfile("anger",
        scale_intervals=[0, 1, 4, 5, 7, 8, 10],   # Phrygian dominant
        tempo_multiplier=1.90, velocity_multiplier=1.20, density=0.99,
        chord_progressions=[
            # Specialised — half-step clashes, Phrygian tension
            # FIX: removed i(phryg), i5, VII7alt — replaced with valid equivalents
            ["i", "bII7b9", "v", "i"],
            ["i", "bIIaug", "VII7b9", "i"],
            ["i", "bII", "bVI", "i"],
            ["i", "VII7b9", "bII7b9", "i"],
            ["i", "bII", "i", "bII"],
            # Emotion-specific — Andalusian and Phrygian cadences
            ["i", "VII", "bVI", "bVII"],                    # Andalusian descending
            ["i", "bVI", "bVII", "bII"],                    # chromatic rise to bII
            ["i", "bII", "VII", "i"],                       # Phrygian cadence
            ["i", "III", "VII", "bVI"],                     # modal minor sequence
            ["i", "bVI", "III", "bII"],                     # tritone motion
        ],
        cadence_progressions=[["bII", "i"], ["VII7b9", "i"]],
        arrangement_chord_sets={
            # Anger should feel like forward pressure + bite.
            # Intro/A: keep it driving but not too "resolved" yet.
            "intro": [
                ["i", "bII", "i", "bII"],
                ["i", "VII7b9", "bII", "i"],
                ["i", "bVI", "bVII", "bII"],
            ],
            "a": [
                ["i", "bII7b9", "v", "i"],
                ["i", "bII", "bVI", "i"],
                ["i", "VII", "bVI", "bVII"],
            ],
            "pre_chorus": [
                ["i", "bVI", "bVII", "bII"],
                ["i", "III", "VII", "bVI"],
                ["i", "bVI", "III", "bII"],
            ],
            # Chorus/B: allow stronger closure to underline intensity.
            "b": [
                ["i", "bII", "VII", "i"],
                ["i", "VII7b9", "bII7b9", "i"],
                ["i", "bIIaug", "VII7b9", "i"],
            ],
            "a_prime": [
                ["i", "bII7b9", "v", "i"],
                ["i", "bVI", "bVII", "bII"],
            ],
            "tag": [
                ["i", "bII", "i", "bII"],
                ["i", "bII", "VII", "i"],
            ],
            "outro": [
                ["i", "bII", "bVI", "i"],
                ["i", "VII", "bVI", "bVII"],
            ],
        }),

    EmotionProfile("annoyance",
        scale_intervals=[0, 1, 3, 5, 7, 8, 10],   # Phrygian
        # Less "bouncy": slightly slower + less dense so the irritation reads as tense/stuck.
        tempo_multiplier=1.35, velocity_multiplier=0.98, density=0.78,
        chord_progressions=[
            # Specialised — repetitive, unresolved, clashing
            ["imin7", "bII", "imin7", "bII"],
            ["i", "bII", "i", "bII"],
            ["i", "VII7", "i", "VII7"],
            ["i", "bVI", "VII7", "i"],
            ["i", "bVI", "VII", "i"],
            # Emotion-specific — short, stabbing, stuck
            ["i", "bII", "VII7", "bII"],                    # unresolved loop (less altered)
            ["i", "v", "bII", "i"],                         # tense modal pull
            ["i", "bVI", "bII", "bII"],                     # dark color → bII (avoid tonic end)
        ],
        cadence_progressions=[["bII", "i"], ["VII7", "i"]],
        arrangement_chord_sets={
            "intro": [
                ["imin7", "bII", "imin7", "bII"],
                ["i", "bII", "i", "bII"],
            ],
            "a": [
                ["i", "bII", "i", "bII"],
                ["i", "VII7", "i", "VII7"],
                ["i", "bII", "VII7", "bII"],
            ],
            "b": [
                ["i", "VII7", "i", "VII7"],
                ["i", "bII", "VII7", "bII"],
                ["i", "bVI", "bII", "bII"],
            ],
            "a_prime": [
                ["i", "bII", "VII7", "bII"],
                ["i", "bVI", "bII", "bII"],
            ],
            "outro": [
                ["i", "bVI", "bII", "bII"],
                ["i", "bVI", "VII7", "i"],
            ],
        }),

    EmotionProfile("approval",
        scale_intervals=[0, 2, 4, 5, 7, 9, 11],   # major
        tempo_multiplier=1.12, velocity_multiplier=0.96, density=0.68,
        chord_progressions=[
            # Specialised — affirmative, clear cadences
            ["Imaj9", "vi9", "ii11", "V13"],
            ["I6", "IVmaj9", "ii9", "V9"],
            ["Imaj7", "vi7", "ii7", "V7"],
            ["I", "V", "vi", "IV"],
            ["Imaj9", "iii7", "vi11", "IVmaj9"],
            # Emotion-specific — decisive, forward-moving
            ["I", "IV", "ii", "V"],                         # classic approach chord
            ["I", "V", "I", "IV"],                          # bouncy affirmation
            ["I6", "ii7", "V7", "I"],                       # jazz cadence
            ["Imaj7", "ii9", "V9", "Imaj7"],                # smooth resolution
            ["I", "iii", "IV", "V"],                        # ascending step cadence
        ],
        cadence_progressions=[["V7", "I"], ["ii9", "Imaj9"]],
        arrangement_chord_sets={
            "intro": [
                ["Imaj9", "vi9", "ii11", "V13"],
                ["I6", "IVmaj9", "ii9", "V9"],
            ],
            "a": [
                ["I6", "IVmaj9", "ii9", "V9"],
                ["Imaj7", "vi7", "ii7", "V7"],
                ["I", "V", "vi", "IV"],
            ],
            "b": [
                ["I", "V", "I", "IV"],
                ["I6", "ii7", "V7", "I"],
                ["Imaj7", "ii9", "V9", "Imaj7"],
            ],
            "a_prime": [
                ["I6", "ii7", "V7", "I"],
                ["Imaj7", "ii9", "V9", "Imaj7"],
            ],
            "outro": [
                ["Imaj7", "ii9", "V9", "Imaj7"],
                ["Imaj9", "vi9", "ii11", "V13"],
            ],
        }),

    EmotionProfile("caring",
        scale_intervals=[0, 2, 4, 7, 9],           # major pentatonic
        tempo_multiplier=0.55, velocity_multiplier=0.72, density=0.30,
        chord_progressions=[
            # Specialised — simple, pure, warm
            ["I", "IV", "I", "V"],
            ["I", "vi", "IV", "I"],
            ["Imaj9", "Imaj13", "IVmaj9", "Imaj9"],
            ["Imaj7", "ii11", "Imaj13", "IVmaj9"],
            ["I", "V/vi", "vi", "IV"],
            # Emotion-specific — gentle, stepwise
            ["Imaj7", "IV", "I", "V"],                      # warm approach
            ["I", "IV", "Vsus4", "I"],                      # suspended resolution
            ["I", "iii", "IV", "I"],                        # inner-voice thirds
            ["Imaj9", "IVmaj9", "I", "V"],                  # lush pentatonic
            ["I", "vi", "I", "IV"],                         # circular warmth
            # Cinematic / score-like — stasis, falling thirds
            ["Imaj7", "Imaj7", "IV", "Imaj7"],
            ["I6", "IV6", "I6", "Imaj7"],
        ],
        cadence_progressions=[["IV", "I"], ["Vsus4", "I"], ["IVmaj7", "Imaj7"]],
        arrangement_chord_sets={
            "intro": [
                ["I", "IV", "I", "V"],
                ["I", "vi", "IV", "I"],
            ],
            "a": [
                ["I", "vi", "IV", "I"],
                ["Imaj9", "Imaj13", "IVmaj9", "Imaj9"],
                ["Imaj7", "ii11", "Imaj13", "IVmaj9"],
            ],
            "b": [
                ["Imaj9", "Imaj13", "IVmaj9", "Imaj9"],
                ["Imaj7", "ii11", "Imaj13", "IVmaj9"],
                ["I", "V/vi", "vi", "IV"],
            ],
            "a_prime": [
                ["Imaj7", "ii11", "Imaj13", "IVmaj9"],
                ["I", "V/vi", "vi", "IV"],
            ],
            "outro": [
                ["I", "V/vi", "vi", "IV"],
                ["Imaj7", "IV", "I", "V"],
            ],
        }),

    EmotionProfile("confusion",
        # Pop/EDM: keep harmony ambiguous, but avoid scale-quantization "correcting"
        # the intended chromatic/augmented colors. Use chromatic so chord symbols
        # remain as-authored.
        scale_intervals=[0, 1, 2, 3, 4, 5, 6, 7, 8, 9, 10, 11],  # chromatic
        tempo_multiplier=0.92, velocity_multiplier=0.82, density=0.52,
        chord_progressions=[
            # Pop/EDM ambiguity: keep it "questioning" with borrowed bII/bVI colors,
            # but reduce constant augmented-chord cycles.
            ["I", "bII", "bVI", "bII"],
            ["I", "bVI", "bIII", "bVII"],
            ["I", "bVII", "bVI", "IV"],
            ["I", "II", "bVI", "IV"],
            ["I", "bII", "IV", "bVI"],
            # A little "surreal" spice (rare aug usage)
            ["Iaug", "bVI", "Vaug", "bII"],
            # Added 2026-07-02 (AUDIOGEN_COMPOSITION_PLAN item 8) — more ways to stay
            # "unanswered": chromatic-mediant drift, deceptive dominants, and one more
            # rare augmented moment (kept to 2/12 total, matching the original ratio).
            ["I", "bIII", "bVI", "IV"],                      # chromatic mediant shift
            ["I", "V", "bVI", "bII"],                        # normal open, rug-pulled
            ["I", "IV", "bII", "V"],                          # circles the dominant, never lands
            ["I", "bVII", "bII", "IV"],                       # borrowed color, avoids T/D clarity
            ["Iaug", "IV", "bVI", "bIII"],                    # second rare aug moment
            ["I", "bVI", "V", "bII"],                         # dominant appears, immediately undercut
        ],
        # Confusion reads best with suspended/avoidant cadences (no clean tonic landing).
        cadence_progressions=[["bII", "V"], ["V", "bII"]],
        # Added 2026-07-02: confusion had no per-role arc before, so every section drew
        # from the same flat pool regardless of position in the song. Arc intent: intro/a
        # wander without commitment, pre_chorus/b lean into the most unresolved material
        # (peak "questioning"), outro/tag never resolve — confusion doesn't get an answer.
        arrangement_chord_sets={
            "intro": [
                ["I", "bII", "bVI", "bII"],
                ["I", "bVI", "bVII", "V"],
                ["I", "bIII", "IV", "bVI"],
            ],
            "a": [
                ["I", "bVI", "bIII", "bVII"],
                ["I", "II", "bVI", "IV"],
                ["I", "IV", "bII", "V"],
            ],
            "pre_chorus": [
                ["I", "V", "bVI", "bII"],
                ["I", "bVII", "bII", "IV"],
                ["I", "bII", "IV", "bVI"],
            ],
            "b": [
                ["I", "bVI", "V", "bII"],
                ["Iaug", "bVI", "Vaug", "bII"],
                ["Iaug", "IV", "bVI", "bIII"],
            ],
            "a_prime": [
                ["I", "bVI", "bIII", "bVII"],
                ["I", "V", "bVI", "bII"],
            ],
            "tag": [
                ["I", "bII", "bVI", "bII"],
                ["I", "IV", "bII", "V"],
            ],
            "outro": [
                ["I", "bVI", "bVII", "bII"],
                ["I", "IV", "bVI", "bIII"],
            ],
        }),

    EmotionProfile("curiosity",
        scale_intervals=[0, 2, 4, 6, 7, 9, 11],   # Lydian
        tempo_multiplier=1.18, velocity_multiplier=0.92, density=0.72,
        chord_progressions=[
            # Specialised — Lydian #11 colour, exploratory
            ["Imaj7#11", "ii9", "V13sus4", "Imaj9"],
            ["Iadd9", "IVmaj7#11", "vi7", "V9sus4"],
            ["Imaj7#11", "iii7", "vi7", "ii7"],
            ["Imaj9", "V13sus4", "Imaj13", "Imaj9"],
            ["Imaj7#11", "bVIImaj9", "iii7", "vi11"],
            # Emotion-specific — Lydian II chord, questioning
            ["Imaj7#11", "bVIImaj7", "IVmaj7", "V13sus4"],  # back-cycling with #11
            ["Imaj9", "II9", "V13sus4", "Imaj9"],            # Lydian II approach
            ["I", "bVII", "IV", "V"],                        # modal adventure
            ["Imaj7#11", "IVmaj7#11", "V13sus4", "Imaj9"],  # double Lydian
            ["I", "II", "vi", "V"],                          # unexpected II chord
            # Cinematic / score-like — same scale, less jumping (still Lydian-leaning)
            ["Imaj9", "vi7", "ii7", "Imaj9"],
            ["Imaj7#11", "Imaj7#11", "IVmaj7#11", "Imaj7#11"],
        ],
        cadence_progressions=[["V13sus4", "Imaj9"], ["II9", "Imaj7#11"]],
        arrangement_chord_sets={
            "intro": [
                ["Imaj7#11", "ii9", "V13sus4", "Imaj9"],
                ["Iadd9", "IVmaj7#11", "vi7", "V9sus4"],
            ],
            "a": [
                ["Iadd9", "IVmaj7#11", "vi7", "V9sus4"],
                ["Imaj7#11", "iii7", "vi7", "ii7"],
                ["Imaj9", "V13sus4", "Imaj13", "Imaj9"],
            ],
            "b": [
                ["Imaj7#11", "iii7", "vi7", "ii7"],
                ["Imaj9", "V13sus4", "Imaj13", "Imaj9"],
                ["Imaj7#11", "bVIImaj9", "iii7", "vi11"],
            ],
            "a_prime": [
                ["Imaj9", "V13sus4", "Imaj13", "Imaj9"],
                ["Imaj7#11", "bVIImaj9", "iii7", "vi11"],
            ],
            "outro": [
                ["Imaj7#11", "bVIImaj9", "iii7", "vi11"],
                ["Imaj7#11", "bVIImaj7", "IVmaj7", "V13sus4"],
            ],
        }),

    EmotionProfile("desire",
        # True Dorian (minor with natural 6): pop-friendly "yearning" without
        # melodic-minor leading tone.
        scale_intervals=[0, 2, 3, 5, 7, 9, 10],   # Dorian
        tempo_multiplier=0.75, velocity_multiplier=0.94, density=0.58,
        chord_progressions=[
            # Specialised — longing, unresolved
            ["i9", "iv11", "bVII13", "V9sus4"],
            ["i13", "bVImaj9", "iv9", "V13"],
            ["i9", "bVII9", "iv9", "V7b9"],
            ["i11", "bVII13", "iv13", "i9"],
            ["i9", "VI9", "imin7b5", "V7"],
            # Emotion-specific — Dorian colour, yearning
            ["i9", "VII9", "IV9", "V9"],                    # Dorian IV major lift
            ["i", "bVII", "IV", "i"],                       # classic Dorian loop
            ["i7", "VII7", "iv7", "i7"],                    # iv minor drag
            ["i9", "VI9", "bVII9", "i9"],                   # chromatic upper neighbour
            ["i", "IV", "bVII", "i"],                       # Dorian characteristic
        ],
        cadence_progressions=[["IV", "i"], ["V9sus4", "i9"]],
        arrangement_chord_sets={
            "intro": [
                ["i9", "iv11", "bVII13", "V9sus4"],
                ["i13", "bVImaj9", "iv9", "V13"],
            ],
            "a": [
                ["i13", "bVImaj9", "iv9", "V13"],
                ["i9", "bVII9", "iv9", "V7b9"],
                ["i11", "bVII13", "iv13", "i9"],
            ],
            "b": [
                ["i9", "bVII9", "iv9", "V7b9"],
                ["i11", "bVII13", "iv13", "i9"],
                ["i9", "VI9", "imin7b5", "V7"],
            ],
            "a_prime": [
                ["i11", "bVII13", "iv13", "i9"],
                ["i9", "VI9", "imin7b5", "V7"],
            ],
            "outro": [
                ["i9", "VI9", "imin7b5", "V7"],
                ["i9", "VII9", "IV9", "V9"],
            ],
        }),

    EmotionProfile("disappointment",
        scale_intervals=[0, 2, 3, 5, 7, 8, 10],   # natural minor / Aeolian
        tempo_multiplier=0.55, velocity_multiplier=0.72, density=0.38,
        chord_progressions=[
            # Specialised — deflated, descending
            ["i", "iv", "VI", "VII"],
            ["iadd9", "iv9", "bVI", "VII"],
            ["i", "bVI", "iv", "bVII"],
            ["i", "VII", "bVI", "VII"],
            ["i", "VI", "III", "VII"],
            # Emotion-specific — sinking, no resolution upward
            ["i", "VI", "iv", "bVII"],                      # minor plagal drift (avoid tonic landing)
            ["i", "bVII", "bVI", "v"],                      # descending bass
            ["i", "iv", "bVI", "bVII"],                     # modal drift out
            ["i9", "VII9", "bVI9", "v9"],                   # descending 9th chain
            ["i", "III", "VII", "bVII"],                    # passive minor loop (avoid tonic landing)
        ],
        cadence_progressions=[["iv", "i"], ["bVII", "i"]],
        arrangement_chord_sets={
            "intro": [
                ["i", "iv", "VI", "VII"],
                ["iadd9", "iv9", "bVI", "VII"],
            ],
            "a": [
                ["iadd9", "iv9", "bVI", "VII"],
                ["i", "bVI", "iv", "bVII"],
                ["i", "VII", "bVI", "VII"],
            ],
            "b": [
                ["i", "iv", "VI", "VII"],
                ["iadd9", "iv9", "bVI", "VII"],
                ["i", "bVI", "iv", "bVII"],
            ],
            "a_prime": [
                ["i", "VII", "bVI", "VII"],
                ["i", "VI", "III", "VII"],
            ],
            "outro": [
                ["i", "VI", "III", "VII"],
                ["i", "VI", "iv", "bVII"],
            ],
        }),

    EmotionProfile("disapproval",
        scale_intervals=[0, 1, 3, 5, 7, 8, 10],   # Phrygian
        tempo_multiplier=1.35, velocity_multiplier=0.96, density=0.55,
        chord_progressions=[
            # Specialised — Phrygian tension, no resolution
            # FIX: removed i min(maj7), bIIaug
            ["i", "bII", "VII7b9", "i"],
            ["imin7", "bIImaj7", "VII7b9", "i"],
            ["i", "bII", "i", "bII"],
            ["i", "bIImaj7", "i", "bIImaj7"],
            ["i", "bII", "VII", "i"],
            # Emotion-specific — forceful refusal
            ["i", "VII", "bVI", "bVII"],                    # Andalusian colour
            ["i", "bVI", "VII", "bII"],                     # chromatic slide
            ["i", "bII", "VII7", "i"],                      # double Phrygian tension (less altered)
            ["i", "bIII", "bVI", "bVII"],                   # borrowed minor pool
            ["i", "VII", "i", "bII"],                       # oscillation + lurch
        ],
        cadence_progressions=[["bII", "i"], ["VII7b9", "i"]],
        arrangement_chord_sets={
            "intro": [
                ["i", "bII", "i", "bII"],
                ["i", "bIImaj7", "i", "bIImaj7"],
            ],
            "a": [
                ["i", "bIImaj7", "i", "bIImaj7"],
                ["i", "VII", "bVI", "bVII"],
                ["i", "bVI", "VII", "bII"],
            ],
            "b": [
                ["i", "bII", "i", "bII"],
                ["i", "bIImaj7", "i", "bIImaj7"],
                ["i", "VII", "bVI", "bVII"],
            ],
            "a_prime": [
                ["i", "bVI", "VII", "bII"],
                ["i", "bIII", "bVI", "bVII"],
            ],
            "outro": [
                ["i", "bIII", "bVI", "bVII"],
                ["i", "VII", "i", "bII"],
            ],
        }),

    EmotionProfile("disgust",
        # Disgust needs chromatic "sour" tones; when runtime scale-quantization is enabled,
        # a narrow octatonic scale can unintentionally neutralize intended altered chords.
        # Use full chromatic scale so chord symbols remain as-authored.
        scale_intervals=[0, 1, 2, 3, 4, 5, 6, 7, 8, 9, 10, 11],  # chromatic
        # Slightly slower/heavier than pure "agitation" so the affect reads as repulsion
        # (and avoids RT underruns from very short bar windows).
        tempo_multiplier=1.20, velocity_multiplier=1.02, density=0.62,
        chord_progressions=[
            # Specialised — octatonic, chromatic, harsh
            # FIX: removed i oct, bII oct, tritone, i7b9#9, bIImaj7#5
            ["i7", "bII7", "VIIdim7", "i"],
            ["imin7b5", "bIImaj7", "imin7b5", "bIImaj7"],
            ["i7", "bIIdim7", "i7", "bIIdim7"],
            # Emotion-specific — octatonic symmetry, no tonal gravity
            ["i", "bIII", "bV", "VI"],                      # symmetric dim cycle
            ["i", "bIII", "bV", "i"],                       # smear without constant dim7 oscillation
            ["i", "VII", "bVI", "bV"],                      # semitone descent
            ["i", "bII", "III", "bV"],                      # tritone tension
            # More "sour" turns: keep it biting, but reduce constant altered-9 dominance for pop/EDM.
            ["i", "bII7", "idim7", "bII7"],                 # neighbor stab + dim smear (less altered)
            ["i7", "VIIdim7", "bII7", "VIIdim7"],           # alternating collapse (less altered)
            ["bII7", "III7", "bV", "i"],                    # repulsive lift then drop (less altered)
        ],
        cadence_progressions=[["bII7", "i"], ["VIIdim7", "i"]],
        arrangement_chord_sets={
            "intro": [
                ["imin7b5", "bIImaj7", "imin7b5", "bIImaj7"],
                ["i7", "bIIdim7", "i7", "bIIdim7"],
            ],
            "a": [
                ["i7", "bIIdim7", "i7", "bIIdim7"],
                ["i", "bIII", "bV", "VI"],
                ["i", "VII", "bVI", "bV"],
            ],
            "b": [
                ["i", "bIII", "bV", "VI"],
                ["i", "VII", "bVI", "bV"],
                ["i", "bII", "III", "bV"],
            ],
            "a_prime": [
                ["i", "VII", "bVI", "bV"],
                ["i", "bII", "III", "bV"],
            ],
            "outro": [
                ["i", "bII", "III", "bV"],
                ["i", "bII7", "idim7", "bII7"],
            ],
        }),

    EmotionProfile("embarrassment",
        # Pop/EDM: harmonic minor leading tone can sound "theatrical"; use Aeolian
        # and keep embarrassment via hesitant cadences + chromatic neighbor colors.
        scale_intervals=[0, 2, 3, 5, 7, 8, 10],   # natural minor / Aeolian
        tempo_multiplier=0.95, velocity_multiplier=0.78, density=0.32,
        chord_progressions=[
            # Specialised — hesitant, chromatic, harmonic minor colour
            # FIX: removed i add b9, i7b9#9
            ["i7", "IVmaj7", "i7", "VII7"],
            ["i", "bII", "i7", "VII7"],
            ["i", "bVI", "VII7", "bII"],
            ["i9", "V7", "i9", "V7"],
            ["i", "III", "iv", "VII7"],
            # Emotion-specific — stuttering, unresolved
            ["i", "bVI", "iv", "bII"],                      # minor plagal with bVI (avoid tonic landing)
            ["i7", "VI7", "iv7", "VII7"],                   # chromatic neighbours (avoid tonic landing)
            ["i", "bVII", "VI", "VII7"],                    # subtonic descent (avoid tonic landing)
            ["i9", "V7", "iv9", "V7"],                      # hesitant dominant (no landing)
            ["i", "iv", "VI", "VII7"],                      # minor subdominant loop (avoid tonic landing)
        ],
        cadence_progressions=[["VII7", "i"], ["V7", "i"]],
        arrangement_chord_sets={
            "intro": [
                ["i7", "IVmaj7", "i7", "VII7"],
                ["i", "bII", "i7", "VII7"],
            ],
            "a": [
                ["i", "bII", "i7", "VII7"],
                ["i", "bVI", "VII7", "bII"],
                ["i9", "V7", "i9", "V7"],
            ],
            "b": [
                ["i7", "IVmaj7", "i7", "VII7"],
                ["i", "bII", "i7", "VII7"],
                ["i", "bVI", "VII7", "bII"],
            ],
            "a_prime": [
                ["i9", "V7", "i9", "V7"],
                ["i", "III", "iv", "VII7"],
            ],
            "outro": [
                ["i", "III", "iv", "VII7"],
                ["i", "bVI", "iv", "bII"],
            ],
        }),

    EmotionProfile("excitement",
        # Pop/EDM excitement: Mixolydian supports dominant-7 "anthem" energy
        # without constant #11 color.
        scale_intervals=[0, 2, 4, 5, 7, 9, 10],   # Mixolydian
        tempo_multiplier=1.82, velocity_multiplier=1.10, density=0.98,
        chord_progressions=[
            # Specialised — fast, energetic, hooky
            ["I", "V", "vi", "IV"],
            ["Iadd9", "V13sus4", "Iadd9", "V13"],
            ["I69", "IVmaj13", "V9sus4", "Iadd9"],
            ["Iadd9", "V13", "vi11", "IVadd9"],
            ["I7", "IV7", "V7", "I7"],
            # Emotion-specific — driving, Lydian energy
            ["I", "bVII", "IV", "V"],                       # modal rock energy
            ["Iadd9", "V9sus4", "vi11", "IVadd9"],          # pop extension (variation)
            ["I", "II", "IV", "V"],                         # Lydian II push
            ["I", "V", "bVII", "IV"],                       # rock turnaround
            ["Iadd9", "bVII", "IVadd9", "V7"],              # back-cycle drive (clearer pop cadence)
        ],
        cadence_progressions=[["V13", "I"], ["IV", "V"]],
        arrangement_chord_sets={
            "intro": [
                ["I", "V", "vi", "IV"],
                ["Iadd9", "V13sus4", "Iadd9", "V13"],
            ],
            "a": [
                ["Iadd9", "V13sus4", "Iadd9", "V13"],
                ["I69", "IVmaj13", "V9sus4", "Iadd9"],
                ["Iadd9", "V13", "vi11", "IVadd9"],
            ],
            "b": [
                ["Iadd9", "V13", "vi11", "IVadd9"],
                ["I7", "IV7", "V7", "I7"],
                ["Iadd9", "V9sus4", "vi11", "IVadd9"],
            ],
            "a_prime": [
                ["I7", "IV7", "V7", "I7"],
                ["Iadd9", "V9sus4", "vi11", "IVadd9"],
            ],
            "outro": [
                ["Iadd9", "V9sus4", "vi11", "IVadd9"],
                ["I", "V", "bVII", "IV"],
            ],
        }),

    EmotionProfile("fear",
        # Pop/EDM fear: octatonic (half-whole diminished) supports dim7 + b9 color
        # without forcing Locrian's b5 as a constant center.
        scale_intervals=[0, 1, 3, 4, 6, 7, 9, 10],   # half_whole_dim
        tempo_multiplier=1.80, velocity_multiplier=0.95, density=0.65,
        chord_progressions=[
            # Specialised — diminished, tritone, unresolved
            # FIX: removed i°7, vii°7 (degree symbols)
            ["i", "bVI", "bII", "bVI"],
            ["imin7b5", "iv", "bII", "iv"],
            ["i", "bII", "bVI", "bII"],
            ["i", "bII", "i", "bII"],
            ["i", "bII", "i", "VIIdim7"],
            # Emotion-specific — Locrian instability, avoid clean tonic closure
            ["idim7", "VIIdim7", "bII", "VIIdim7"],         # dim discharge
            ["i", "bVI", "bII", "VIIdim7"],                 # bVI surprise → dim
            ["idim7", "VII7", "bII", "VIIdim7"],            # dominant discharge → dim
            ["imin7b5", "bII7", "imin7b5", "bII7"],         # half-dim tremor (no dim7 tag)
            ["i", "bVI", "bVII", "bII"],                    # dark pop loop (no dim)
        ],
        # Fear cadence should generally avoid authentic resolution.
        cadence_progressions=[["bII7", "VIIdim7"], ["VIIdim7", "bII"]],
        arrangement_chord_sets={
            # Fear wants instability: avoid ending sections on tonic-like symbols where possible.
            "intro": [
                ["idim7", "VIIdim7", "idim7", "VIIdim7"],
                ["imin7b5", "iv", "VIIdim7", "bII"],
            ],
            "a": [
                ["i", "bII", "i", "VIIdim7"],
                ["i", "VIIdim7", "bII", "VIIdim7"],
                ["i", "bII", "bVI", "bII"],
            ],
            "pre_chorus": [
                ["idim7", "VII7", "bII", "VIIdim7"],
                ["i", "VII7", "bII", "bIIdim7"],
                ["i", "bVI", "bII", "VIIdim7"],
            ],
            # Chorus/B can be more active, but still avoid clean closure.
            "b": [
                ["imin7b5", "bII7", "imin7b5", "VIIdim7"],
                ["idim7", "VIIdim7", "idim7", "VIIdim7"],
                ["i", "bII", "bVI", "bII"],
            ],
            "a_prime": [
                ["i", "VIIdim7", "bII", "VIIdim7"],
                ["idim7", "VII7", "bII", "VIIdim7"],
            ],
            "tag": [
                ["idim7", "VIIdim7", "idim7", "VIIdim7"],
                ["i", "bII", "i", "VIIdim7"],
            ],
            "outro": [
                ["imin7b5", "iv", "VIIdim7", "bII"],
                ["i", "bII", "bVI", "bII"],
            ],
        }),

    EmotionProfile("gratitude",
        scale_intervals=[0, 2, 4, 5, 7, 9, 11],   # major
        tempo_multiplier=0.78, velocity_multiplier=0.86, density=0.45,
        chord_progressions=[
            # Specialised — warm, gracefully resolved
            ["Imaj9", "IVmaj13", "ii11", "V13"],
            ["Imaj13", "vi13", "IVmaj9", "Imaj9"],
            ["Imaj9", "ii9", "V13", "Imaj9"],
            ["Imaj13", "iii7", "vi11", "Imaj9"],
            ["Imaj9", "IV69", "I", "V/vi"],
            # Emotion-specific — heartfelt, flowing
            ["Imaj9", "iii7", "IVmaj9", "V13"],             # inner-voice thirds
            ["I", "vi", "IVmaj7", "I"],                     # safer pop warmth
            ["Imaj7", "IV", "ii7", "V7"],                   # jazz gratitude
            ["I", "vi", "IVmaj7", "V7"],                    # classic resolution
            ["Imaj9", "V7sus4", "V7", "Imaj9"],             # suspended arrival
            # Cinematic / score-like — long pedals, open voicing
            ["Imaj7", "IVmaj7", "Imaj7", "vi7"],
            ["I", "Imaj7", "IV", "I"],
        ],
        cadence_progressions=[["V13", "Imaj9"], ["IVmaj7", "Imaj9"], ["IV", "Imaj7"], ["Vsus4", "I"]],
        arrangement_chord_sets={
            "intro": [
                ["Imaj9", "IVmaj7", "Imaj9", "Imaj9"],
                ["Imaj9", "vi7", "IVmaj7", "Imaj9"],
            ],
            "a": [
                ["Imaj9", "iii7", "IVmaj9", "vi7"],
                ["I", "vi", "IVmaj7", "ii7"],
                ["Imaj7", "IV", "ii7", "vi7"],
            ],
            "pre_chorus": [
                ["vi7", "ii11", "IVmaj9", "V13"],
                ["iii7", "vi11", "ii7", "V7sus4"],
                ["Imaj9", "ii9", "IVmaj7", "V13"],
            ],
            "b": [
                ["Imaj9", "IVmaj9", "V13", "Imaj9"],
                ["I", "vi", "IVmaj7", "I"],
                ["Imaj9", "V7sus4", "V7", "Imaj9"],
            ],
            "a_prime": [
                ["Imaj13", "iii7", "vi11", "Imaj9"],
                ["Imaj9", "IV69", "ii11", "Imaj9"],
            ],
            "outro": [
                ["Imaj9", "IVmaj7", "Imaj9", "Imaj9"],
                ["Imaj7", "ii7", "Imaj9", "Imaj9"],
            ],
        }),

    EmotionProfile("grief",
        scale_intervals=[0, 2, 3, 5, 7, 8, 10],   # natural minor / Aeolian
        tempo_multiplier=0.35, velocity_multiplier=0.70, density=0.22,
        chord_progressions=[
            # Specialised — very slow harmonic rhythm, minimal movement
            ["i", "iv", "i", "iv"],
            ["i9", "iv9", "bVI", "VII"],
            ["i", "VI", "iv", "iv"],
            ["i", "iv", "bVI", "bVI"],
            ["i", "VI", "III", "VII"],
            # Emotion-specific — barely moving, no energy to resolve
            ["i", "bVI", "i", "bVI"],                       # tonic–bVI rocking
            ["i", "III", "i", "III"],                       # minor–relative major
            ["i9", "VII9", "i9", "VII9"],                   # subtonic oscillation
            ["i", "v", "i", "v"],                           # minor dominant rocking
            ["i", "iv", "v", "v"],                          # slow minor cadence (avoid tonic landing)
            # Cinematic / score-like — minimal motion, avoid tonic-heavy bar endings (grief: cadence=avoid in anchors)
            ["i", "iv", "bVI", "bVII"],
            ["i9", "iv9", "VII9", "bVI9"],
            ["i", "bVII", "iv", "bVI"],
        ],
        cadence_progressions=[["iv", "i"], ["bVI", "i"], ["bVII", "i"]],
        arrangement_chord_sets={
            "intro": [
                ["i9", "iv9", "bVI", "VII"],
                ["i", "iv", "bVI", "bVI"],
            ],
            "a": [
                ["i", "iv", "bVI", "bVI"],
                ["i", "VI", "III", "VII"],
                ["i", "bVI", "i", "bVI"],
            ],
            "b": [
                ["i9", "iv9", "bVI", "VII"],
                ["i", "iv", "bVI", "bVI"],
                ["i", "VI", "III", "VII"],
            ],
            "a_prime": [
                ["i", "bVI", "i", "bVI"],
                ["i9", "VII9", "i9", "VII9"],
            ],
            "outro": [
                ["i9", "VII9", "i9", "VII9"],
                ["i", "v", "i", "v"],
            ],
        }),

    EmotionProfile("joy",
        scale_intervals=[0, 2, 4, 6, 7, 9, 11],   # Lydian (bright, floating)
        tempo_multiplier=1.62, velocity_multiplier=1.05, density=0.95,
        chord_progressions=[
            # Specialised — Lydian brightness, celebratory
            ["I", "V", "vi", "IV"],
            ["Imaj7", "ii9", "V13sus4", "Imaj9"],
            ["Imaj13", "IVmaj9", "ii13", "V13"],
            ["I69", "V13", "vi11", "IVmaj13"],
            ["Imaj9", "V13sus4", "Imaj13", "Imaj9"],
            # Emotion-specific — joyful Lydian moves
            ["Imaj7", "IV", "V", "I"],                      # bright but simpler landing
            ["I", "V", "IV", "I"],                          # triumphant close
            ["Imaj9", "II9", "V", "I"],                     # Lydian II lift
            ["I", "vi", "IV", "I"],                         # pop-safe lift
            ["Imaj9", "ii9", "IV", "V"],                    # ascending joy
        ],
        cadence_progressions=[["V13", "I"], ["IV", "Imaj9"]],
        arrangement_chord_sets={
            "intro": [
                ["Imaj9", "Imaj13", "IVmaj9", "Imaj9"],
                ["Imaj7", "Imaj9", "IVmaj7", "Imaj9"],
            ],
            "a": [
                ["Imaj7", "ii9", "V13sus4", "Imaj9"],
                ["Imaj13", "IVmaj9", "ii13", "V13"],
                ["I", "V", "vi", "IV"],
            ],
            "b": [
                ["Imaj9", "II9", "V13sus4", "Imaj9"],
                ["Imaj9", "IVmaj9", "V13", "Imaj9"],
                ["Imaj9", "II9", "V", "I"],
            ],
            "a_prime": [
                ["Imaj9", "V13sus4", "Imaj13", "Imaj9"],
                ["Imaj13", "IVmaj9", "V13", "Imaj9"],
            ],
            "outro": [
                ["Imaj9", "IVmaj7", "Imaj9", "Imaj9"],
                ["Imaj7", "IV", "Imaj9", "Imaj9"],
            ],
        },
    ),

    EmotionProfile("love",
        scale_intervals=[0, 2, 4, 5, 7, 9, 11],   # major
        tempo_multiplier=0.82, velocity_multiplier=0.90, density=0.58,
        chord_progressions=[
            # Specialised — lush, flowing, 9ths and 13ths
            ["Imaj9", "vi11", "ii13", "V13"],
            ["Imaj13", "vi9", "IVmaj13", "Imaj9"],
            ["Imaj9", "iii7", "vi7", "ii7"],
            ["Imaj9", "vi11", "IVmaj9", "Imaj13"],
            ["Imaj7", "iii7", "vi11", "Imaj9"],
            # Emotion-specific — romantic, voice-leading sensitive
            ["Imaj9", "iii7", "vi11", "V13"],               # thirds & ninths
            ["Imaj13", "IVmaj9", "ii11", "V13sus4"],        # suspended longing
            ["Imaj7", "vi9", "IVmaj9", "V13"],              # cleaner pop pull
            ["I", "iii", "vi", "IV"],                       # circle of thirds
            ["Imaj9", "vi9", "IVmaj9", "V13"],              # classic love sequence
            # Cinematic / score-like
            ["Imaj7", "Imaj7", "vi7", "Imaj7"],
            ["Imaj9", "IVmaj7", "Imaj9", "Imaj9"],
        ],
        cadence_progressions=[["V13sus4", "Imaj9"], ["IVmaj9", "Imaj13"], ["IVmaj7", "Imaj7"]],
        arrangement_chord_sets={
            "intro": [
                ["Imaj9", "vi9", "IVmaj9", "Imaj9"],
                ["Imaj9", "iii7", "vi7", "Imaj9"],
            ],
            "a": [
                ["Imaj9", "iii7", "vi7", "IVmaj9"],
                ["Imaj9", "vi9", "IVmaj9", "ii7"],
                ["I", "iii", "vi", "IV"],
            ],
            "pre_chorus": [
                ["vi11", "ii11", "IVmaj9", "V13sus4"],
                ["iii7", "vi11", "ii7", "V13"],
                ["Imaj9", "vi9", "ii11", "V13sus4"],
            ],
            "b": [
                ["Imaj9", "V13sus4", "vi9", "Imaj9"],
                ["Imaj9", "vi9", "IVmaj9", "Imaj9"],
                ["I", "V", "vi", "I"],
            ],
            "a_prime": [
                ["Imaj13", "vi9", "IVmaj9", "Imaj9"],
                ["Imaj9", "iii7", "vi11", "Imaj13"],
            ],
            "outro": [
                ["Imaj9", "IVmaj9", "Imaj9", "Imaj9"],
                ["Imaj7", "vi7", "Imaj9", "Imaj9"],
            ],
        }),

    EmotionProfile("nervousness",
        # Pop/EDM nervousness: octatonic supports half-diminished tremor colors
        # while keeping quantization compatible with authored chords.
        scale_intervals=[0, 1, 3, 4, 6, 7, 9, 10],   # half_whole_dim
        tempo_multiplier=1.75, velocity_multiplier=0.96, density=0.82,
        chord_progressions=[
            # Specialised — Locrian instability, oscillating
            # FIX: removed "i min7b5" (space) → "imin7b5"; "vii°7" → "VIIdim7"
            ["imin7b5", "VIIdim7", "imin7b5", "VIIdim7"],
            ["i", "bII", "VIIdim7", "i"],
            ["i", "VII7", "i", "VII7"],
            ["i7", "V7", "i7", "V7"],
            ["i", "bII", "i", "bII"],
            # Emotion-specific — erratic, no safe landing
            ["imin7b5", "bII7", "imin7b5", "bII7"],         # half-dim tremor (less altered)
            ["i", "bVI", "bVII", "bII"],                    # lurching forward
            ["i", "VIIdim7", "i", "bII"],                   # dim7 insertion
            ["i", "bII", "v", "i"],                         # furtive motion
            ["i7", "bII7", "i7", "VII7"],                   # Phrygian shudder (less altered)
        ],
        cadence_progressions=[["bII7", "i"], ["VIIdim7", "imin7b5"]],
        arrangement_chord_sets={
            "intro": [
                ["imin7b5", "VIIdim7", "imin7b5", "VIIdim7"],
                ["i", "VII7", "i", "VII7"],
            ],
            "a": [
                ["i", "VII7", "i", "VII7"],
                ["i7", "V7", "i7", "V7"],
                ["i", "bII", "i", "bII"],
            ],
            "b": [
                ["i7", "V7", "i7", "V7"],
                ["i", "bII", "i", "bII"],
                ["imin7b5", "bII7", "imin7b5", "bII7"],
            ],
            "a_prime": [
                ["i", "bII", "i", "bII"],
                ["imin7b5", "bII7", "imin7b5", "bII7"],
            ],
            "outro": [
                ["imin7b5", "bII7", "imin7b5", "bII7"],
                ["i", "bVI", "bVII", "bII"],
            ],
        }),

    EmotionProfile("optimism",
        scale_intervals=[0, 2, 4, 6, 7, 9, 11],   # Lydian
        tempo_multiplier=1.28, velocity_multiplier=0.98, density=0.75,
        chord_progressions=[
            # Specialised — Lydian #11, forward-moving
            ["I", "V", "vi", "IV"],
            ["Imaj7", "IVmaj9", "ii9", "V13sus4"],
            ["Imaj9", "ii13", "V9sus4", "Imaj13"],
            ["Imaj9", "IVmaj9", "V13", "I"],
            ["I6", "IV6", "V7", "I"],
            # Emotion-specific — steady forward momentum
            ["Imaj9", "ii9", "IVmaj9", "V13"],              # cleaner drive
            ["I", "II", "IV", "I"],                         # Lydian II assertion
            ["I", "vi", "IVmaj7", "V"],                     # safer forward motion
            ["Imaj7", "ii9", "V9sus4", "Imaj9"],            # simpler resolution
            ["I", "V", "IV", "I"],                          # mainstream close
        ],
        cadence_progressions=[["V13", "I"], ["V9sus4", "Imaj9"]],
        arrangement_chord_sets={
            "intro": [
                ["Imaj9", "I6", "IVmaj9", "Imaj9"],
                ["Imaj7", "IVmaj9", "Imaj9", "Imaj9"],
            ],
            "a": [
                ["I", "V", "vi", "IV"],
                ["Imaj9", "IVmaj9", "ii9", "vi"],
                ["I", "II", "IV", "vi"],
            ],
            "pre_chorus": [
                ["vi", "IVmaj9", "ii9", "V13sus4"],
                ["Imaj9", "ii13", "IVmaj9", "V9sus4"],
                ["II", "IV", "ii9", "V13"],
            ],
            "b": [
                ["Imaj9", "V13", "vi", "I"],
                ["I", "II", "V", "I"],
                ["Imaj9", "IVmaj9", "V13", "I"],
            ],
            "a_prime": [
                ["Imaj9", "vi7", "IVmaj9", "I"],
                ["Imaj7", "ii9", "V9sus4", "Imaj9"],
            ],
            "outro": [
                ["Imaj9", "IVmaj9", "I", "I"],
                ["I6", "V7", "I", "I"],
            ],
        }),

    EmotionProfile("pride",
        scale_intervals=[0, 2, 4, 5, 7, 9, 11],   # major
        tempo_multiplier=1.15, velocity_multiplier=1.02, density=0.72,
        chord_progressions=[
            # Specialised — strong, assertive, marchlike
            ["Imaj9", "IVmaj9", "Imaj13", "V13"],
            ["Imaj7", "vi9", "ii11", "V13"],
            ["Imaj9", "V13", "Imaj13", "Imaj9"],
            ["Imaj7", "bVIImaj7", "IVmaj7", "Imaj7"],
            ["I", "IV", "I", "V"],
            # Emotion-specific — strong cadences, assertive
            ["Imaj9", "IVmaj9", "V13", "Imaj9"],            # full cycle assertion
            ["I", "bVII", "IV", "I"],                       # modal confidence
            ["Imaj7", "V7", "IVmaj7", "I"],                 # double subdominant
            ["I", "IV", "bVII", "I"],                       # triumphant bVII
            ["Imaj13", "ii11", "V13", "Imaj13"],            # lush affirmation
        ],
        cadence_progressions=[["V13", "Imaj9"], ["IV", "I"]],
        arrangement_chord_sets={
            "intro": [
                ["Imaj9", "IVmaj9", "Imaj13", "V13"],
                ["Imaj7", "vi9", "ii11", "V13"],
            ],
            "a": [
                ["Imaj7", "vi9", "ii11", "V13"],
                ["Imaj9", "V13", "Imaj13", "Imaj9"],
                ["Imaj7", "bVIImaj7", "IVmaj7", "Imaj7"],
            ],
            "b": [
                ["Imaj9", "IVmaj9", "V13", "Imaj9"],
                ["I", "bVII", "IV", "I"],
                ["Imaj7", "V7", "IVmaj7", "I"],
            ],
            "a_prime": [
                ["I", "bVII", "IV", "I"],
                ["Imaj7", "V7", "IVmaj7", "I"],
            ],
            "outro": [
                ["Imaj7", "V7", "IVmaj7", "I"],
                ["I", "IV", "bVII", "I"],
            ],
        }),

    EmotionProfile("realization",
        # FIX: was [0,1,4,5,7,8,10] (Phrygian dominant) — same as anger.
        # Changed to Dorian [0,2,3,5,7,9,10]: modal, contemplative,
        # characteristic raised 6th gives a sense of unexpected clarity.
        scale_intervals=[0, 2, 3, 5, 7, 9, 10],   # Dorian
        tempo_multiplier=0.82, velocity_multiplier=0.86, density=0.42,
        chord_progressions=[
            # Specialised — Dorian modal colour, gradual shift
            ["i7b9", "bII", "V7", "Imaj9"],
            ["imin7b5", "VIIdim7", "V13", "Imaj13"],
            ["iv", "bVI", "V7", "Imaj9"],
            ["i", "bII", "V", "Imaj7"],
            ["i", "VI", "II7", "V7"],
            # Emotion-specific — Dorian characteristic moves
            ["i", "IV", "VII", "i"],                        # Dorian IV major lift
            ["i9", "IVmaj7", "VII9", "i9"],                 # Dorian 9th clarity
            ["i", "II", "v", "i"],                          # Dorian major II
            ["i7", "IVmaj7", "bVII9", "i7"],                # modal dawn
            ["i", "bVII", "IV", "i"],                       # Dorian loop
            # Cinematic / score-like — unhurried, clear modal home
            ["i9", "bVII9", "iv9", "i9"],
            ["i7", "i7", "bVIImaj7", "i7"],
        ],
        cadence_progressions=[["IV", "i"], ["V7", "Imaj9"], ["bVII", "i"]],
        arrangement_chord_sets={
            "intro": [
                ["i7b9", "bII", "V7", "Imaj9"],
                ["imin7b5", "VIIdim7", "V13", "Imaj13"],
            ],
            "a": [
                ["imin7b5", "VIIdim7", "V13", "Imaj13"],
                ["iv", "bVI", "V7", "Imaj9"],
                ["i", "bII", "V", "Imaj7"],
            ],
            "b": [
                ["iv", "bVI", "V7", "Imaj9"],
                ["i", "bII", "V", "Imaj7"],
                ["i", "IV", "VII", "i"],
            ],
            "a_prime": [
                ["i", "bII", "V", "Imaj7"],
                ["i", "IV", "VII", "i"],
            ],
            "outro": [
                ["i", "IV", "VII", "i"],
                ["i9", "IVmaj7", "VII9", "i9"],
            ],
        }),

    EmotionProfile("relief",
        scale_intervals=[0, 2, 4, 5, 7, 9, 11],   # major
        tempo_multiplier=0.52, velocity_multiplier=0.73, density=0.32,
        chord_progressions=[
            # Specialised — minor to major resolution, falling tension
            ["i", "VII7b9", "Imaj9", "IVmaj13"],
            ["imin7b5", "VIIdim7", "Imaj13", "ii11"],
            ["iv", "VII7", "Imaj9", "Imaj7"],
            ["i", "VII7", "Imaj9", "IVmaj9"],
            ["i", "VI", "II7", "V7", "I"],
            # Emotion-specific — exhale, tension dropping to major
            ["i", "bVII", "Imaj7", "IVmaj7"],               # modal pivot
            ["iv", "V7", "Imaj9", "Imaj13"],                # iv → I resolution
            ["i", "V7", "Imaj9", "ii7"],                    # clear major arrival
            ["bVI", "V7", "Imaj7", "Imaj9"],                # bVI surprise resolve
            ["i", "III", "Imaj7", "IVmaj9"],                # parallel major shift
            # Cinematic / score-like
            ["Imaj7", "Imaj7", "IVmaj7", "Imaj7"],
            ["Imaj9", "vi7", "Imaj9", "IVmaj9"],
        ],
        cadence_progressions=[["V7", "Imaj9"], ["IVmaj7", "Imaj13"], ["IV", "Imaj7"], ["Vsus4", "I"]],
        arrangement_chord_sets={
            "intro": [
                ["i", "VII7b9", "Imaj9", "IVmaj13"],
                ["imin7b5", "VIIdim7", "Imaj13", "ii11"],
            ],
            "a": [
                ["imin7b5", "VIIdim7", "Imaj13", "ii11"],
                ["iv", "VII7", "Imaj9", "Imaj7"],
                ["i", "VII7", "Imaj9", "IVmaj9"],
            ],
            "b": [
                ["iv", "VII7", "Imaj9", "Imaj7"],
                ["i", "VII7", "Imaj9", "IVmaj9"],
                ["i", "VI", "II7", "V7", "I"],
            ],
            "a_prime": [
                ["i", "VII7", "Imaj9", "IVmaj9"],
                ["i", "VI", "II7", "V7", "I"],
            ],
            "outro": [
                ["i", "VI", "II7", "V7", "I"],
                ["i", "bVII", "Imaj7", "IVmaj7"],
            ],
        }),

    EmotionProfile("remorse",
        scale_intervals=[0, 2, 3, 5, 7, 8, 10],   # natural minor / Aeolian
        tempo_multiplier=0.45, velocity_multiplier=0.73, density=0.24,
        chord_progressions=[
            # Specialised — slow, descending, no uplift
            ["i9", "iv11", "VII9", "i11"],
            ["i13", "VI9", "iv9", "VII9"],
            ["iadd9", "iv9", "bVImaj7", "bVImaj7"],
            ["i9", "iv11", "bVI", "bVII"],
            ["i", "iv", "VII7", "VII7"],
            # Emotion-specific — penitent, descending lines
            ["i", "bVI", "bVII", "bVII"],                   # minor descent (avoid tonic landing)
            ["i", "iv", "bVI", "v"],                        # minor leading tone avoidance
            ["i", "III", "bVI", "iv"],                      # sad arch
            ["i9", "vi9", "iv9", "VII9"],                   # minor diatonic descent (avoid tonic landing)
            ["i", "VI", "iv", "iv"],                        # iv → (no tonic landing)
        ],
        # Remorse cadence should avoid clean resolution.
        cadence_progressions=[["iv", "bVI"], ["bVI", "v"]],
        arrangement_chord_sets={
            "intro": [
                ["i13", "VI9", "iv9", "VII9"],
                ["iadd9", "iv9", "bVImaj7", "bVImaj7"],
            ],
            "a": [
                ["iadd9", "iv9", "bVImaj7", "bVImaj7"],
                ["i9", "iv11", "bVI", "bVII"],
                ["i", "iv", "VII7", "VII7"],
            ],
            "b": [
                ["i13", "VI9", "iv9", "VII9"],
                ["iadd9", "iv9", "bVImaj7", "bVImaj7"],
                ["i9", "iv11", "bVI", "bVII"],
            ],
            "a_prime": [
                ["i", "iv", "VII7", "VII7"],
                ["i", "bVI", "bVII", "bVII"],
            ],
            "outro": [
                ["i", "bVI", "bVII", "bVII"],
                ["i", "iv", "bVI", "v"],
            ],
        }),

    EmotionProfile("sadness",
        scale_intervals=[0, 2, 3, 5, 7, 8, 10],   # natural minor / Aeolian
        tempo_multiplier=0.52, velocity_multiplier=0.75, density=0.38,
        chord_progressions=[
            # Specialised — descending Aeolian, melancholic
            ["i", "VI", "iv", "VII"],
            ["i9", "iv9", "VII9", "iadd9"],
            ["i", "bVI", "iv", "i"],
            ["i", "VI", "bVI", "i"],
            ["i", "III", "iv", "i"],
            # Emotion-specific — stepwise descent, emotional weight
            ["i", "bVI", "bVII", "i"],                      # classic Aeolian
            ["i", "VI", "III", "VII"],                      # cycle of relative
            ["i", "iv", "bVI", "v"],                        # v without resolution
            ["i9", "VII9", "bVI9", "v9"],                   # descending 9ths
            ["i", "iv", "i", "iv"],                         # tonic–subdominant pull
            # Cinematic / score-like — small harmonic rhythm, no rush to cadence
            ["i9", "i9", "iv9", "bVI9"],
            ["i", "bVII", "bVI", "i"],
        ],
        cadence_progressions=[["iv", "i"], ["bVI", "i"], ["bVII", "i"]],
        arrangement_chord_sets={
            "intro": [
                ["i", "i", "iv", "i"],
                ["i9", "i9", "iv9", "i9"],
            ],
            "a": [
                ["i", "VI", "iv", "VII"],
                ["i9", "iv9", "VII9", "iadd9"],
                ["i", "VI", "bVI", "i"],
            ],
            "b": [
                ["i", "bVI", "bVII", "i"],
                ["i9", "iv11", "bVImaj7", "i"],
                ["i", "III", "bVI", "iv"],
            ],
            "a_prime": [
                ["i", "iv", "bVI", "i"],
                ["i", "VI", "iv", "i"],
            ],
            "outro": [
                ["i", "iv", "i", "i"],
                ["i9", "iv9", "i9", "i9"],
            ],
        },
    ),

    EmotionProfile("surprise",
        scale_intervals=[0, 2, 4, 6, 8, 10],      # whole-tone
        tempo_multiplier=1.72, velocity_multiplier=1.08, density=0.82,
        chord_progressions=[
            # Specialised — augmented, whole-tone, unexpected
            # FIX: removed IIIwt, Vwt, bIIIwt, "I whole", b13
            ["Iaug", "bVI", "Vaug", "I"],
            ["I", "bII", "V", "I"],
            ["I", "bVI", "I", "bII"],
            ["I", "bII", "bVI", "Iaug"],
            ["I", "bVImaj7", "I", "bVImaj7"],
            # Emotion-specific — sudden swerves, tritone motion
            ["I", "bVImaj7", "bII", "I"],                   # unexpected slide
            ["I", "bVI", "III", "bII"],                     # chromatic surprise
            ["I", "bII", "Vsus4", "I"],                     # surprise-sus snap
            ["I", "bV", "bII", "I"],                        # double tritone
            ["Iaug", "bII", "Vaug", "I"],                   # bII landing
        ],
        cadence_progressions=[["bII", "I"], ["Vaug", "I"]],
        arrangement_chord_sets={
            "intro": [
                ["Iaug", "bVI", "Vaug", "I"],
                ["I", "bII", "V", "I"],
            ],
            "a": [
                ["I", "bII", "V", "I"],
                ["I", "bVI", "I", "bII"],
                ["I", "bII", "bVI", "Iaug"],
            ],
            "b": [
                ["I", "bVI", "I", "bII"],
                ["I", "bII", "bVI", "Iaug"],
                ["I", "bVImaj7", "I", "bVImaj7"],
            ],
            "a_prime": [
                ["I", "bII", "bVI", "Iaug"],
                ["I", "bVImaj7", "I", "bVImaj7"],
            ],
            "outro": [
                ["I", "bVImaj7", "I", "bVImaj7"],
                ["I", "bVImaj7", "bII", "I"],
            ],
        }),

    EmotionProfile("neutral",
        scale_intervals=[0, 2, 4, 5, 7, 9, 11],   # major
        tempo_multiplier=1.00, velocity_multiplier=0.85, density=0.45,
        chord_progressions=[
            # Balanced — neither dark nor bright
            ["I", "V", "vi", "IV"],
            ["Imaj7", "vi", "ii", "V"],
            ["Imaj7", "vi7", "ii7", "V7"],
            ["I", "iii", "IV", "I"],
            # Emotion-specific — balanced, centred
            ["I", "vi", "IV", "V"],                         # classic loop
            ["Imaj7", "ii7", "V7", "Imaj7"],                # jazz neutral
            ["I", "IV", "ii", "V"],                         # approach chord
            ["vi", "IV", "I", "V"],                         # darker tint but still diatonic-major
            ["I", "IV", "V", "I"],                          # simple neutral cadence
            # Cinematic / score-like — static tonic, very slow change
            ["Imaj7", "Imaj7", "IVmaj7", "Imaj7"],
            ["I", "vi", "I", "IV"],
            ["Imaj9", "IVmaj9", "Imaj9", "vi7"],
        ],
        cadence_progressions=[["V7", "I"], ["ii7", "Imaj7"], ["IV", "Imaj7"], ["Vsus4", "I"], ["IVmaj7", "Imaj7"]],
        arrangement_chord_sets={
            "intro": [
                ["I", "I", "IV", "I"],
                ["Imaj7", "vi", "IV", "Imaj7"],
            ],
            "a": [
                ["I", "V", "vi", "IV"],
                ["I", "vi", "IV", "ii"],
                ["vi", "IV", "I", "ii"],
            ],
            "pre_chorus": [
                ["vi", "IV", "ii", "V"],
                ["I", "ii7", "IV", "V7"],
                ["iii", "vi", "ii", "V"],
            ],
            "b": [
                ["I", "V", "IV", "I"],
                ["Imaj7", "vi", "ii7", "I"],
                ["I", "IV", "V", "I"],
            ],
            "a_prime": [
                ["I", "vi", "IV", "I"],
                ["Imaj7", "ii7", "V7", "Imaj7"],
            ],
            "outro": [
                ["I", "IV", "I", "I"],
                ["Imaj7", "ii7", "Imaj7", "Imaj7"],
            ],
        }),
]

# Convenience lookup
EMOTION_BY_NAME = {e.name.lower(): e for e in EMOTIONS}

try:
    for _e in EMOTIONS:
        try:
            _e.velocity_multiplier = 1.0
        except Exception:
            pass
except Exception:
    pass

# Merge in self-generated chord-progression variety (see
# scripts/augment_chord_progressions.py + docs/AUDIOGEN_COMPOSITION_PLAN.md). Each
# emotion's extras are sampled ONLY from that emotion's own hand-written progressions
# above (bigram transitions), then fidelity-validated, so this adds harmonic variety
# without diluting the emotion's identity. Kept in a separate generated file so the
# hand-curated data above stays easy to read/diff on its own.
try:
    from data.chord_progressions_augmented import AUGMENTED_CHORD_PROGRESSIONS as _AUG_CHORDS
except Exception:
    _AUG_CHORDS = {}
for _e in EMOTIONS:
    try:
        _extra = _AUG_CHORDS.get(_e.name.lower()) or []
        if _extra:
            _e.chord_progressions = list(_e.chord_progressions) + [list(_p) for _p in _extra]
    except Exception:
        pass
