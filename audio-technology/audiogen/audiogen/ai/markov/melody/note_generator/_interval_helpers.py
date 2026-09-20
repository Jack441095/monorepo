# ai/markov/melody/note_generator/_interval_helpers.py
"""Pure helpers for interval / chord-symbol conditioning (unit-testable)."""


def canon_chord_symbol_for_interval(ch: str) -> str:
    """
    Normalize chord symbols so function conditioning is stable across extensions.

    Returns ``root`` + coarse quality suffix (maj/min/dom/dim/aug/sus) or ``""``.
    """
    s = (ch or "").strip()
    if not s:
        return ""
    i = 0
    while i < len(s) and s[i] in {"b", "#"}:
        i += 1
    while i < len(s) and s[i] in {"i", "v", "I", "V"}:
        i += 1
    root = s[:i] if i > 0 else s
    rest = s[i:].lower()
    q = ""
    if "dim" in rest or "°" in s or "ø" in s:
        q = "dim"
    elif "aug" in rest or "+" in s:
        q = "aug"
    elif "sus" in rest:
        q = "sus"
    elif "maj" in rest:
        q = "maj"
    elif "min" in rest or (root and root[0].islower()):
        q = "min"
    elif "7" in rest:
        q = "dom"
    elif root and root[0].isupper():
        q = "maj"
    return f"{root}{q}"
