# data/chord_parser.py
# Project module `chord_parser` (data).

# data/chord_parser.py
import re
from typing import List, Optional

from .music_theory import (CHORD_VOICINGS, ROMAN_TO_DEGREE,
                           ROMAN_TO_SCALE_DEGREE)

NOTE_TO_PC = {
    'C': 0, 'C#': 1, 'Db': 1, 'D': 2, 'D#': 3, 'Eb': 3,
    'E': 4, 'F': 5, 'F#': 6, 'Gb': 6, 'G': 7, 'G#': 8,
    'Ab': 8, 'A': 9, 'A#': 10, 'Bb': 10, 'B': 11, 'Cb': 11,
}

PC_TO_NOTE = {
    0: ['C'],  1: ['C#', 'Db'], 2: ['D'],  3: ['D#', 'Eb'],
    4: ['E'],  5: ['F'],        6: ['F#', 'Gb'], 7: ['G'],
    8: ['G#', 'Ab'], 9: ['A'], 10: ['A#', 'Bb'], 11: ['B', 'Cb'],
}

# Longest-match ordering is required.
# added bare '7' so "i7", "IV7" etc. are recognised as dominant-seventh
# rather than falling through to 'maj'.
QUALITIES = [
    'maj7#11', 'maj7#5', 'maj7b5', 'maj7#9', 'maj13#11', 'maj13',
    'min7b5', 'min7#5', 'min7#9', 'min11', 'min13',
    '7#9b13', '7b9#5', '7#9#5', '7b5', '7#5', '7b9', '7#9', '7#11', '7b13',
    'dim7', 'aug7', 'maj7', 'min7', 'dom7', 'maj', 'min', 'aug', 'dim',
    'sus4', 'sus2', '13sus4', '6/9', '69', '6', '9', '11', '13', '7',
    'add9', 'add11',
]

_NOTE_STARTS = set('ABCDEFG')


class ParsedChord:
    def __init__(self, root: str, quality: str, bass_note: Optional[str] = None):
        self.root = root
        self.quality = quality
        self.bass_note = bass_note

    def is_roman(self) -> bool:
        return bool(re.match(r'^[#b]?[IV]+$', self.root))

    def to_absolute(self, key_root_note: str) -> 'ParsedChord':
        if not self.is_roman():
            return self
        degree = ROMAN_TO_SCALE_DEGREE.get(self.root, 0)
        key_pc = NOTE_TO_PC.get(key_root_note, 0)
        major_scale_offsets = [0, 2, 4, 5, 7, 9, 11]
        semitone_offset = major_scale_offsets[degree % 7]
        if self.root.startswith('b'):
            semitone_offset -= 1
        elif self.root.startswith('#'):
            semitone_offset += 1
        pc = (key_pc + semitone_offset) % 12
        candidates = PC_TO_NOTE[pc]
        root_abs = next((n for n in candidates if len(n) == 1), candidates[0])
        return ParsedChord(root_abs, self.quality, self.bass_note)

    def intervals(self) -> List[int]:
        return CHORD_VOICINGS.get(self.quality, CHORD_VOICINGS['maj'])[0]

    def root_pitch_class(self) -> int:
        if self.is_roman():
            raise ValueError("Cannot get pitch class of Roman numeral without key")
        return NOTE_TO_PC.get(self.root, 0)

    def __repr__(self):
        return f"ParsedChord(root={self.root}, quality={self.quality}, bass={self.bass_note})"


def parse_chord_symbol(symbol: str) -> ParsedChord:

    symbol = symbol.strip()

    # FIX 1: split on '/' only when the right-hand token is a note name
    bass = None
    if '/' in symbol:
        main_candidate, bass_candidate = symbol.split('/', 1)
        bass_candidate = bass_candidate.strip()
        if bass_candidate and bass_candidate[0].upper() in _NOTE_STARTS:
            symbol = main_candidate.strip()
            bass = bass_candidate
        # else: '/' is part of the quality (e.g. '6/9'), leave symbol intact

    main = symbol

    # FIX 2: match upper- and lower-case Roman numerals
    roman_match = re.match(r'^([#b]?)([IiVv]+)(.*)$', main)
    if roman_match:
        accidental, numerals, rest = roman_match.groups()
        is_lowercase = numerals[0].islower()
        # Normalize numerals to uppercase while preserving accidental case ('b' / '#').
        # (Uppercasing the full token would incorrectly turn 'b' into 'B'.)
        root = f"{accidental}{numerals.upper()}"
        quality = _extract_quality(rest)
        # Bare lowercase numeral with no explicit quality → minor triad
        if is_lowercase and quality == 'maj' and not rest:
            quality = 'min'
        return ParsedChord(root, quality, bass)

    note_match = re.match(r'^([A-Ga-g][#b]?)(.*)$', main)
    if note_match:
        root, rest = note_match.groups()
        root = root[0].upper() + root[1:].lower()
        quality = _extract_quality(rest)
        return ParsedChord(root, quality, bass)

    return ParsedChord(main, 'maj', bass)


def _extract_quality(rest: str) -> str:
    if not rest:
        return 'maj'
    # Shorthand: bare 'm' (not 'maj', not already 'min…') means minor
    if rest.startswith('m') and not rest.startswith('maj') and not rest.startswith('min'):
        return 'min' + rest[1:]
    for q in QUALITIES:
        if rest.startswith(q):
            return q
    return 'maj'


def chord_symbol_to_intervals(symbol: str) -> List[int]:
    return parse_chord_symbol(symbol).intervals()


def get_root_offset(roman: str) -> int:
    # Legacy helper kept for compatibility; prefer `get_root_pitch_class` which
    # uses the parsed Roman root safely.
    try:
        parsed = parse_chord_symbol(roman)
        if parsed.is_roman():
            return int(ROMAN_TO_DEGREE.get(parsed.root, 0))
    except Exception:
        pass
    return int(ROMAN_TO_DEGREE.get(str(roman), 0))


def get_root_pitch_class(symbol: str, key_root: Optional[str] = None) -> int:
    parsed = parse_chord_symbol(symbol)
    if parsed.is_roman():
        if key_root is None:
            # Map Roman numeral root to semitone offset in the key of C (0=tonic),
            # using the normalized parsed.root (handles lowercase and accidentals).
            return int(ROMAN_TO_DEGREE.get(parsed.root, 0))
        return parsed.to_absolute(key_root).root_pitch_class()
    return parsed.root_pitch_class()


def midi_to_note(midi_note: int) -> str:
    names = ['C', 'C#', 'D', 'D#', 'E', 'F', 'F#', 'G', 'G#', 'A', 'A#', 'B']
    return names[midi_note % 12]