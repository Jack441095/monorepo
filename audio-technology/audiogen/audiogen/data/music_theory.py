# music_theory.py
# Core music theory data: scales, chord voicings, and Roman numeral mappings.

from typing import Dict, List

# ---------------------------------------------------------------------------
# SCALES AND MODES
# ---------------------------------------------------------------------------

SCALES_AND_MODES: Dict[str, Dict] = {
    "major": {
        "intervals": [0, 2, 4, 5, 7, 9, 11],
        "alias": "ionian",
        "mood": "bright, happy, resolved, uplifting, optimistic",
    },
    "dorian": {
        "intervals": [0, 2, 3, 5, 7, 9, 10],
        "mood": "minor but hopeful, jazzy, soulful, nostalgic, slightly melancholic",
    },
    "phrygian": {
        "intervals": [0, 1, 3, 5, 7, 8, 10],
        "mood": "dark, exotic, tense, spanish/flamenco, mysterious, anxious",
    },
    "lydian": {
        "intervals": [0, 2, 4, 6, 7, 9, 11],
        "mood": "dreamy, ethereal, floating, wonder, cinematic bright, magical",
    },
    "mixolydian": {
        "intervals": [0, 2, 4, 5, 7, 9, 10],
        "mood": "bluesy major, relaxed, groovy, folk/rock dominant, laid-back",
    },
    "aeolian": {
        "intervals": [0, 2, 3, 5, 7, 8, 10],
        "alias": "natural_minor",
        "mood": "sad, melancholic, introspective, emotional, longing",
    },
    "locrian": {
        "intervals": [0, 1, 3, 5, 6, 8, 10],
        "mood": "unstable, tense, dark, dissonant, uncertain, rare but powerful",
    },
    "harmonic_minor": {
        "intervals": [0, 2, 3, 5, 7, 8, 11],
        "mood": "dramatic minor, exotic, middle-eastern, passionate, tense resolution",
    },
    "melodic_minor_asc": {
        "intervals": [0, 2, 3, 5, 7, 9, 11],
        "mood": "jazzy minor, sophisticated, ascending tension-release, modern",
    },
    "altered": {
        "intervals": [0, 1, 3, 4, 6, 8, 10],
        "mood": "super tense dominant, outside, modern jazz, unstable, searching",
    },
    "whole_tone": {
        "intervals": [0, 2, 4, 6, 8, 10],
        "mood": "dreamy, floating, ambiguous, impressionist, surreal",
    },
    "half_whole_dim": {
        "intervals": [0, 1, 3, 4, 6, 7, 9, 10],
        "mood": "diminished dominant, sinister, suspense, dark jazz",
    },
    "blues": {
        "intervals": [0, 3, 5, 6, 7, 10],
        "mood": "bluesy, soulful, expressive, gritty, emotional bends",
    },
    "major_pentatonic": {
        "intervals": [0, 2, 4, 7, 9],
        "mood": "happy, simple, folk, country, uplifting, innocent",
    },
    "minor_pentatonic": {
        "intervals": [0, 3, 5, 7, 10],
        "mood": "sad/bluesy, rock, expressive, soulful, versatile",
    },
}


CHORD_VOICINGS: Dict[str, List[List[int]]] = {

    # ── Major family ────────────────────────────────────────────────────────
    "maj":      [[0, 4, 7], [0, 4, 7, 12], [0, 4, 7, 12, 16]],
    "maj6":     [[0, 4, 7, 9], [0, 4, 7, 9, 14]],
    "6":        [[0, 4, 7, 9]],                          # NEW: bare major 6th
    "69":       [[0, 4, 7, 9, 14]],
    "6/9":      [[0, 4, 7, 9, 14], [4, 7, 9, 14, 16]],
    "maj7":     [[0, 4, 7, 11], [4, 7, 11, 14], [7, 11, 14, 17]],
    "maj9":     [[0, 4, 7, 11, 14], [4, 7, 11, 14, 17], [7, 11, 14, 17, 21]],
    "maj13":    [[0, 4, 7, 11, 14, 21], [4, 7, 11, 14, 21, 24]],
    "maj7#11":  [[0, 4, 7, 11, 14, 18], [0, 4, 6, 11, 14]],
    "add9":     [[0, 4, 7, 14]],

    # ── Minor family ────────────────────────────────────────────────────────
    "min":      [[0, 3, 7], [0, 3, 7, 12], [0, 3, 7, 12, 15]],
    "min6":     [[0, 3, 7, 9], [0, 3, 7, 9, 14]],       # NEW
    "min69":    [[0, 3, 7, 9, 14]],                      # NEW
    "min7":     [[0, 3, 7, 10], [3, 7, 10, 14], [7, 10, 14, 17]],
    "min9":     [[0, 3, 7, 10, 14], [3, 7, 10, 14, 17], [7, 10, 14, 17, 21]],
    "min11":    [[0, 3, 7, 10, 14, 17], [3, 7, 10, 14, 17, 21]],
    "min13":    [[0, 3, 7, 10, 14, 17, 21], [3, 7, 10, 14, 17, 21, 24]],
    "min7b5":   [[0, 3, 6, 10], [3, 6, 10, 14]],
    "min(maj7)": [[0, 3, 7, 11]],

    # ── Dominant family ─────────────────────────────────────────────────────
    "7":        [[0, 4, 7, 10], [0, 4, 10, 14]],
    "dom7":     [[0, 4, 7, 10], [4, 7, 10, 14], [7, 10, 14, 17]],
    "9":        [[0, 4, 7, 10, 14], [0, 4, 10, 14, 17]],
    "11":       [[0, 4, 7, 10, 14, 17]],
    "13":       [[0, 4, 7, 10, 14, 21]],
    "7b9":      [[0, 4, 7, 10, 13]],
    "7#9":      [[0, 4, 7, 10, 15]],
    "7b5":      [[0, 4, 6, 10]],
    "7#5":      [[0, 4, 8, 10]],
    "7#11":     [[0, 4, 7, 10, 14, 18]],
    "7b13":     [[0, 4, 7, 10, 20]],
    "9#11":     [[0, 4, 7, 10, 14, 18]],               # NEW (Lydian dominant)
    "9b5":      [[0, 4, 6, 10, 14]],
    "dom7b9":   [[0, 4, 7, 10, 13], [4, 7, 10, 13, 16]],
    "7alt":     [[0, 4, 6, 10, 13], [0, 4, 8, 10, 15]], # NEW (altered dominant)

    # ── Suspended & hybrid ──────────────────────────────────────────────────
    "sus2":     [[0, 2, 7], [0, 2, 7, 12]],
    "sus4":     [[0, 5, 7], [0, 5, 7, 12], [0, 7, 12, 17]],
    "7sus4":    [[0, 5, 7, 10]],
    "9sus4":    [[0, 5, 7, 10, 14]],
    "13sus4":   [[0, 5, 7, 10, 14, 21]],

    # ── Diminished & augmented ───────────────────────────────────────────────
    "dim":      [[0, 3, 6], [0, 3, 6, 9]],
    "dim7":     [[0, 3, 6, 9], [3, 6, 9, 12]],
    "aug":      [[0, 4, 8], [0, 4, 8, 12]],
    "aug7":     [[0, 4, 8, 10]],

    # ── Special / modal / atmospheric ───────────────────────────────────────
    "phryg":    [[0, 1, 3, 7], [0, 3, 7, 10]],
    "lyd":      [[0, 4, 7, 11], [0, 4, 6, 11]],
    "whole-tone": [[0, 2, 4, 6, 8, 10]],
    "tritone":  [[0, 4, 6, 10], [0, 6, 10, 16]],
    "quartal":  [[0, 5, 10, 15, 19], [0, 5, 10, 14, 19]],
}

# ---------------------------------------------------------------------------
# VOICING STYLE FAMILIES
# ---------------------------------------------------------------------------

VOICING_FAMILIES: Dict[str, List[List[int]]] = {
    "shell": [
        [0, 4, 7], [0, 3, 7], [0, 4, 10], [0, 3, 10], [0, 3, 6, 10],
    ],
    "drop2": [
        [0, 4, 7, 10], [0, 4, 7, 11], [0, 3, 7, 10],
        [0, 4, 7, 14], [0, 4, 10, 14], [0, 3, 7, 14],
    ],
    "drop3": [
        [0, 7, 10, 14], [0, 7, 11, 14], [0, 7, 10, 17],
    ],
    "close": [
        [0, 3, 4, 7], [0, 4, 7, 11], [0, 3, 7, 10],
    ],
    "quartal": [
        [0, 5, 10, 15, 19], [0, 5, 10, 14, 19], [0, 5, 10, 15],
    ],
    "open": [
        [0, 12, 16, 19], [0, 12, 15, 19], [0, 10, 14, 19],
    ],
}

# ---------------------------------------------------------------------------
# ROMAN NUMERAL MAPPINGS
# ---------------------------------------------------------------------------

ROMAN_TO_DEGREE = {
    "I": 0,  "i": 0,
    "II": 2, "ii": 2,
    "III": 4, "iii": 4,
    "IV": 5, "iv": 5,
    "V": 7,  "v": 7,
    "VI": 9, "vi": 9,
    "VII": 11, "vii": 11,
    "bII": 1, "bIII": 3, "bV": 6, "bVI": 8, "bVII": 10,
    "#IV": 6, "#V": 8,
    "V/ii": 2, "V/III": 4, "V/iv": 5, "V/V": 7, "V/vi": 9,
}

ROMAN_TO_SCALE_DEGREE = {
    "I": 0,  "i": 0,
    "II": 1, "ii": 1,
    "III": 2, "iii": 2,
    "IV": 3, "iv": 3,
    "V": 4,  "v": 4,
    "VI": 5, "vi": 5,
    "VII": 6, "vii": 6,
    "bII": 1, "bIII": 2, "bV": 3, "bVI": 5, "bVII": 6,
    "#IV": 3, "#V": 4,
    "V/ii": 1, "V/III": 2, "V/iv": 3, "V/V": 4, "V/vi": 5,
}

# ---------------------------------------------------------------------------
# SUBSTITUTION TABLES
# ---------------------------------------------------------------------------

CHORD_SUBSTITUTIONS = {
    'Imaj7':  ['Imaj9', 'Imaj13', 'III7', 'bVII7'],
    'Imaj9':  ['Imaj7', 'Imaj13', 'Imaj7#11', 'III7'],
    'Imaj13': ['Imaj9', 'Imaj7#11', 'bVIImaj7'],
    'ii7':    ['ii9', 'ii11', 'IVmaj7', 'bVII7'],
    'ii9':    ['ii7', 'ii11', 'IVmaj9', 'bVII9'],
    'ii11':   ['ii9', 'IVmaj7', 'bVIImaj7'],
    'V7':     ['V7b9', 'V7#9', 'V13', 'bII7'],
    'V7b9':   ['V7', 'V7#9', 'V13b9', 'bII7b9'],
    'V13':    ['V7', 'V9', 'V7#11', 'bII13'],
    'vi7':    ['vi9', 'vi11', 'Imaj7', 'IVmaj7'],
    'vi9':    ['vi7', 'vi11', 'Imaj9', 'IVmaj9'],
    'IVmaj7': ['IVmaj9', 'IV6', 'ii7', 'bVIImaj7'],
    'IVmaj9': ['IVmaj7', 'IVmaj13', 'ii9', 'bVIImaj9'],
    'maj7':   ['maj9', 'maj13', 'maj7#11'],
    'maj9':   ['maj7', 'maj13', 'maj7#11'],
    'min7':   ['min9', 'min11', 'min(maj7)'],
    'min9':   ['min7', 'min11'],
    'dom7':   ['7b9', '7#9', '7#11', '13'],
    '7b9':    ['7', '7#9', '7alt'],
    '7#9':    ['7', '7b9', '7#11', '7alt'],
    'dim7':   ['dim', 'min7b5'],
    'aug':    ['aug7', '7#5'],
}

TRITONE_SUBSTITUTIONS = {
    'V7':    'bII7',
    'V7b9':  'bII7b9',
    'V7#9':  'bII7#9',
    'V13':   'bII13',
    'V7#11': 'bII7#11',
    'II7':   'bVI7',
    'VI7':   'bIII7',
    'III7':  'bVII7',
}

RELATIVE_SUBSTITUTIONS = {
    'I': 'vi', 'ii': 'IV', 'iii': 'V', 'IV': 'ii',
    'V': 'iii', 'vi': 'I', 'vii°': 'V7',
    'Imaj7': 'vi7', 'ii7': 'IVmaj7', 'iii7': 'V7',
    'IVmaj7': 'ii7', 'V7': 'iii7', 'vi7': 'Imaj7',
}