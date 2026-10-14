"""Exact answers to the arithmetic producers ask for, so a figure in an answer is computed rather than recalled.

The grounding gate refuses any figure the evidence does not print, and on the 5 Oct baseline unsupported figures
were the largest single cause of rejected answers. Some of the figures producers ask for have exact answers no note
needs to hold: the delay time of a dotted eighth at 128 BPM, how many milliseconds a 512-sample buffer is at 48 kHz,
which note 220 Hz is, what -6 dB is as a gain factor. Those are computed here from the producer's own words and
handed to the model as tool readings, which the gate already accepts figures from (`additional_evidence_text`).

Only the question typed this turn is read, never the history-expanded search query: a follow-up's search string can
carry an earlier question's tempo, and a calculation from it would answer a question nobody asked.

Every calculation needs the question to ask for that conversion in so many words ("what note is 220 Hz", "-6 dB as a
ratio"), not just to mention a figure near a trigger word: the gate accepts a calculated figure anywhere in the answer,
so an unrequested one ("200 Hz is G3" for a question about cutting 200 Hz) is a licence for an invented sentence. When
the wording is unclear we compute nothing.

Deliberately not here: anything perceptual. "Twice as loud" has no exact dB answer (it depends on level, frequency
and listener), so a question about loudness gets the level and power arithmetic and nothing pretending to be more.
"""

from __future__ import annotations

import math
import re
from decimal import ROUND_HALF_UP, Decimal

# A whole note is four beats, so its length in ms is 4 x 60 000 / BPM.
_MS_PER_WHOLE_NOTE_AT_1_BPM = 240_000.0

_NOTE_WORDS = {
    "whole": 1, "half": 2, "quarter": 4, "crotchet": 4, "eighth": 8, "quaver": 8,
    "sixteenth": 16, "semiquaver": 16, "thirty-second": 32, "32nd": 32, "16th": 16, "8th": 8, "4th": 4,
}
# "half", "whole", "quarter" and "4th" only count with "note" after them: on their own they are "half time", "the whole
# mix", "a quarter of the level", "the 4th bar", and a 1/2-note delay figure for "half time feel" answers nothing asked.
_NOTE_RE = re.compile(
    r"\b(?P<dotted>dotted\s+)?(?P<triplet>triplet\s+)?"
    r"(?:1/(?P<frac>1|2|4|8|16|32)(?P<t>t)?\b|(?P<word>crotchet|eighth|quaver|sixteenth|"
    r"semiquaver|thirty-second|32nd|16th|8th)(?:[\s-]+notes?)?|(?P<noted_word>whole|half|quarter|4th)[\s-]+notes?\b)"
    r"(?P<dotted_after>\s+dotted)?(?P<triplet_after>\s+triplets?)?",
    re.IGNORECASE,
)
_BPM_RE = re.compile(r"\b(\d{2,3}(?:\.\d+)?)\s*bpm\b", re.IGNORECASE)
# No bare "time": "time signature 7/8 at 140 BPM" is about metre, and it drew the full set of delay figures.
_TEMPO_WORDS_RE = re.compile(r"\b(delay|pre-?delay|echo|lfo|sync|ms|milliseconds?|release)\b", re.IGNORECASE)

_SAMPLES_RE = re.compile(r"\b(\d{2,7})\s*samples?\b", re.IGNORECASE)
_RATE_RE = re.compile(r"\b(\d{2,3}(?:\.\d+)?)\s*k\s*hz\b|\b(\d{5,6})\s*hz\b", re.IGNORECASE)

_HZ_RE = re.compile(r"\b(\d{1,5}(?:\.\d+)?)\s*hz\b", re.IGNORECASE)
_NOTE_NAME_RE = re.compile(r"\b([A-G])([#b♯♭]?)(-?\d)\b")
# The conversion has to be asked of the figure itself, so each pattern is anchored to the text right before or right
# after it. "what pitch is the vocal" next to "cut 200 Hz", or "what frequency should I cut" next to a sampler called
# E4, names no conversion and gets none.
_HZ_TO_NOTE_BEFORE_RE = re.compile(
    r"\b(?:which|what)\s+(?:musical\s+)?(?:note|pitch)\s+(?:is|does|would)\s+(?:an?\s+)?\Z", re.IGNORECASE)
_HZ_TO_NOTE_AFTER_RE = re.compile(
    r"\s*(?:is\s+)?(?:which|what)\s+(?:musical\s+)?note\b|\s+(?:as|in|to)\s+(?:an?\s+)?(?:note|pitch|midi)\b",
    re.IGNORECASE)
_NOTE_TO_HZ_BEFORE_RE = re.compile(
    r"(?:\b(?:what|which)\s+(?:frequency|freq|hz|hertz)\s+(?:is|does|would)|\bhow\s+many\s+(?:hz|hertz)\s+is"
    r"|\bfrequency\s+of)\s+(?:an?\s+|the\s+|note\s+)?\Z", re.IGNORECASE)
_NOTE_TO_HZ_AFTER_RE = re.compile(r"\s+(?:in|as|to)\s+(?:hz|hertz|frequency)\b", re.IGNORECASE)
# A reference pitch the producer states: "A=442", "432 tuning", "tuned to 432 Hz". Three digits, because every
# concert pitch in use sits between 415 Hz (baroque) and 466 Hz.
_TUNING_RE = re.compile(
    r"\bA4?\s*=\s*(\d{3}(?:\.\d+)?)|\b(\d{3}(?:\.\d+)?)\s*(?:hz\s*)?tuning\b"
    r"|\btuned\s+(?:to\s+)?(?:A4?\s*=?\s*)?(\d{3}(?:\.\d+)?)|\btuning\s+(?:of\s+|at\s+)?(?:A4?\s*=?\s*)?(\d{3}(?:\.\d+)?)",
    re.IGNORECASE)

_DB_RE = re.compile(r"(?<![\w.])([+\-−]?\d+(?:\.\d+)?)\s*db\b(?!\s*(?:fs|tp|spl|u|v|a)\b)", re.IGNORECASE)
# A conversion phrase, not a bare word: "set ratio 4:1 and threshold -18 dB" mentions a ratio and a dB figure and asks
# for no conversion. "Ratio" only counts after "as"/"in", since "what ratio" is a compressor setting question.
_FACTOR_WORDS_RE = re.compile(
    r"\b(?:as|in|to|into)\s+(?:an?\s+)?(?:linear\s+|amplitude\s+)?"
    r"(?:ratio|multiplier|gain\s+factor|gain|factor|percent(?:age)?|linear|amplitude)\b"
    r"|\b(?:what|which)(?:'s|\s+is)?\s+(?:the\s+|that\s+)?(?:linear\s+)?(?:multiplier|gain\s+factor|factor|percent(?:age)?)\b"
    # "What gain is -6 dB" only with "is": "what gain should I set" is a gain-staging question, not a conversion.
    r"|\bwhat\s+gain\s+is\b|\bdb\s+(?:gain\s+factor|multiplier)\b"
    r"|\bhow\s+many\s+times\b|\b(?:gain\s+factor|multiplier|percentage)\s+(?:of|for)\b",
    re.IGNORECASE)
# Direction words for a dB figure typed without a sign. "Reduce by 6 dB" is -6 dB, and reading it as +6 gave 199.5%.
# A pad is a fixed attenuator, so "a 3 dB pad" is a cut too.
_CUT_WORDS_RE = re.compile(r"\b(cut\w*|reduc\w*|lower\w*|attenuat\w*|drop\w*|down|quieter|pads?)\b", re.IGNORECASE)
_BOOST_WORDS_RE = re.compile(r"\b(boost\w*|rais\w*|increas\w*|up|louder)\b", re.IGNORECASE)
_DOUBLE_RE = re.compile(r"\b(double|doubling|twice|half|halve|halving)\b", re.IGNORECASE)
_LEVEL_WORDS_RE = re.compile(r"\b(level|volume|amplitude|voltage|signal|power|gain|loud\w*)\b", re.IGNORECASE)

NOTE_NAMES = ("C", "C#", "D", "D#", "E", "F", "F#", "G", "G#", "A", "A#", "B")
_FLATS = {"Db": "C#", "Eb": "D#", "Gb": "F#", "Ab": "G#", "Bb": "A#"}


def _fmt(value: float, places: int = 1) -> str:
    """One decimal, with a trailing .0 dropped, so 500.0 ms reads 500 ms and the gate sees the figure as written."""
    # Half-up, as a producer works it on paper: Python's round() and f-strings round a tie to even, which printed
    # 312.5 ms as "about 312" and 156.25 ms as 156.2. repr() first, so 2.675 rounds as typed, not as its binary
    # neighbour 2.67499...
    text = str(Decimal(repr(value)).quantize(Decimal(1).scaleb(-places), rounding=ROUND_HALF_UP))
    return text.rstrip("0").rstrip(".") if "." in text else text


def note_length_ms(bpm: float, division: int, *, dotted: bool = False, triplet: bool = False) -> float:
    """Length of one 1/division note at bpm, in ms. Dotted adds half; a triplet fits three in the time of two."""
    length = _MS_PER_WHOLE_NOTE_AT_1_BPM / bpm / division
    if dotted:
        length *= 1.5
    if triplet:
        length *= 2.0 / 3.0
    return length


def _note_label(division: int, dotted: bool, triplet: bool) -> str:
    return f"{'dotted ' if dotted else ''}1/{division}{' triplet' if triplet else ''} note"


def tempo_facts(question: str) -> list[str]:
    match = _BPM_RE.search(question)
    if not match:
        return []
    bpm = float(match.group(1))
    if not 20 <= bpm <= 999:
        # Outside any tempo Live accepts (20-999 BPM), so it is more likely a different number than a tempo.
        return []
    notes = []
    for found in _NOTE_RE.finditer(question):
        word = found.group("word") or found.group("noted_word")
        division = int(found.group("frac")) if found.group("frac") else _NOTE_WORDS[word.lower()]
        dotted = bool(found.group("dotted") or found.group("dotted_after"))
        triplet = bool(found.group("triplet") or found.group("triplet_after") or found.group("t"))
        notes.append((division, dotted, triplet))
    if not notes:
        if not _TEMPO_WORDS_RE.search(question):
            # A tempo alone ("my track is 128 BPM, how do I mix the kick?") is not a timing question.
            return []
        # A timing question with no note value: the common delay settings, straight, dotted and triplet.
        notes = [(4, False, False), (8, False, False), (8, True, False), (8, False, True), (16, False, False)]
    facts = []
    for division, dotted, triplet in dict.fromkeys(notes):
        ms = note_length_ms(bpm, division, dotted=dotted, triplet=triplet)
        facts.append(
            f"At {_fmt(bpm, 2)} BPM a {_note_label(division, dotted, triplet)} lasts {_fmt(ms)} ms "
            f"(about {_fmt(ms, 0)} ms), which is {_fmt(1000.0 / ms, 2)} Hz as an LFO rate."
        )
    return facts


def latency_facts(question: str) -> list[str]:
    samples, rate = _SAMPLES_RE.search(question), _RATE_RE.search(question)
    if not samples or not rate:
        return []
    count = int(samples.group(1))
    hz = float(rate.group(1)) * 1000.0 if rate.group(1) else float(rate.group(2))
    if not 8_000 <= hz <= 768_000:
        return []
    ms = count / hz * 1000.0
    rate_text = f"{_fmt(hz / 1000.0, 2)} kHz"
    return [f"{count} samples at {rate_text} is {_fmt(ms, 2)} ms (about {_fmt(ms)} ms); a round trip through a buffer "
            f"that size in and out is twice that, before any converter or plug-in latency."]


def _midi_from_hz(hz: float) -> float:
    # Twelve-tone equal temperament tuned to A4 = 440 Hz (MIDI note 69), the tuning Live's synths default to.
    return 69.0 + 12.0 * math.log2(hz / 440.0)


def _hz_from_midi(note: int) -> float:
    return 440.0 * 2.0 ** ((note - 69) / 12.0)


def _names(note: int) -> str:
    """The note in scientific pitch and in Live's labels, which name each octave one lower (middle C is C3 in Live)."""
    name = NOTE_NAMES[note % 12]
    return (f"{name}{note // 12 - 1} in scientific pitch (MIDI note {note}), which Live's piano roll labels "
            f"{name}{note // 12 - 2}")


def pitch_facts(question: str) -> list[str]:
    for tuning in _TUNING_RE.finditer(question):
        stated = next(group for group in tuning.groups() if group)
        if float(stated) != 440.0:
            # Every figure below assumes A4 = 440 Hz, so under a stated 432 or 442 each one would be a wrong pitch
            # the gate then accepts. Saying nothing is safe: the model answers in words, as it did before this file.
            return []
    facts = []
    for found in _HZ_RE.finditer(question):
        if not (_HZ_TO_NOTE_BEFORE_RE.search(question[:found.start()])
                or _HZ_TO_NOTE_AFTER_RE.match(question, found.end())):
            continue
        hz = float(found.group(1))
        if not 8.0 <= hz <= 20_000.0:
            continue
        exact = _midi_from_hz(hz)
        # Half-up for the same reason as _fmt; a tie here is a frequency exactly 50 cents between two notes.
        nearest = math.floor(exact + 0.5)
        if not 0 <= nearest <= 127:
            # Above 12.54 kHz (MIDI 127) or below 8.18 Hz (MIDI 0) there is no MIDI note to name, and "MIDI note 135"
            # would be a number no clip in Live can hold.
            continue
        cents = (exact - nearest) * 100.0
        offset = "exactly" if abs(cents) < 0.5 else f"{_fmt(abs(cents), 0)} cents {'sharp' if cents > 0 else 'flat'} of"
        facts.append(f"{_fmt(hz, 2)} Hz is {offset} {_names(nearest)}, at A4 = 440 Hz.")
    for found in _NOTE_NAME_RE.finditer(question):
        if not (_NOTE_TO_HZ_BEFORE_RE.search(question[:found.start()])
                or _NOTE_TO_HZ_AFTER_RE.match(question, found.end())):
            continue
        letter, accidental, octave = found.group(1), found.group(2), int(found.group(3))
        name = letter + {"♯": "#", "♭": "b"}.get(accidental, accidental)
        name = _FLATS.get(name, name)
        if name not in NOTE_NAMES:
            continue
        # The octave as typed is read as scientific pitch, the common convention; the answer names Live's label
        # too, so a producer reading Live's piano roll can tell which one they meant.
        note = (octave + 1) * 12 + NOTE_NAMES.index(name)
        if 0 <= note <= 127:
            facts.append(f"{name}{octave} is {_fmt(_hz_from_midi(note), 2)} Hz: {_names(note)}, at A4 = 440 Hz.")
    return facts


def _direction_window(question: str, found: re.Match) -> str:
    """The words that can say which way an unsigned dB figure goes: its own clause up to 30 characters before it, and
    the word right after "dB" ("6 dB down", "a 3 dB pad")."""
    before = re.split(r"[,.;?!]", question[max(0, found.start() - 30):found.start()])[-1]
    after = re.match(r"\s*\w*", question[found.end():]).group(0)
    return before + after


def level_facts(question: str) -> list[str]:
    facts = []
    conversion = _FACTOR_WORDS_RE.search(question)
    figures = [found for found in _DB_RE.finditer(question) if abs(float(found.group(1).replace("−", "-"))) <= 120]
    if conversion and figures:
        # Only the figure closest to the conversion phrase. Converting every dB in the question gave an unasked
        # factor for "my threshold is at -18 dB", and printed "6 dB per octave ... what is 6 dB" twice (14 Oct 2026).
        found = min(figures, key=lambda f: min(abs(f.start() - conversion.end()), abs(conversion.start() - f.end())))
        typed = found.group(1).replace("−", "-")
        db = float(typed)
        signed = typed[0] in "+-"
        # Direction words count only next to the figure. Scanning the whole question read "a pad plugin", "the
        # lower band" and "the track volume up" as the figure's direction and printed a confident wrong factor.
        window = _direction_window(question, found)
        cut, boost = bool(_CUT_WORDS_RE.search(window)), bool(_BOOST_WORDS_RE.search(window))
        # Neither direction named ("the 3 dB point of the filter", "what percent is 3 dB"), or both ("cut the lows
        # and boost the highs by 3 dB"): which way the figure goes would be a guess, and a factor for the wrong
        # direction (141.3% for a 3 dB pad) is worse than none, so we print nothing. 0 dB is unity either way.
        guessing = not signed and db != 0 and cut == boost
        if not guessing:
            if not signed and cut:
                db = -db
            # "+" for a boost the producer typed or named, so "+3 dB" is not read back as a level of 3 dB.
            plus = "+" if db > 0 else ""
            amplitude, power = 10.0 ** (db / 20.0), 10.0 ** (db / 10.0)
            facts.append(f"{plus}{_fmt(db)} dB is a gain factor of {_fmt(amplitude, 3)} on amplitude "
                         f"({_fmt(amplitude * 100.0)}%) and {_fmt(power, 3)} on power.")
    if _DOUBLE_RE.search(question) and _LEVEL_WORDS_RE.search(question):
        facts.append("Doubling amplitude (voltage, sample values) is +6.02 dB and halving it is -6.02 dB; doubling power "
                     "is +3.01 dB and halving it is -3.01 dB. How much louder something sounds is a perception, not this "
                     "arithmetic.")
    return facts


def calculated_facts(question: str) -> str:
    """Every calculation the typed question asks for, as tool-reading sentences; "" when it asks for none."""
    if not question:
        return ""
    facts = tempo_facts(question) + latency_facts(question) + pitch_facts(question) + level_facts(question)
    return " ".join(f"KENN calculation: {fact}" for fact in facts)
