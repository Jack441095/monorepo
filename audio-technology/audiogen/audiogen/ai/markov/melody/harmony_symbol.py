"""Chord-symbol helpers shared across melody modules."""


def simplify_harmony_function(chord_symbol: str) -> str:
    symbol = (chord_symbol or "").strip()
    if not symbol:
        return "maj"
    lowered = symbol.lower()
    if "dim" in lowered or "ø" in symbol or "°" in symbol:
        return "dim"
    if "aug" in lowered or "+" in symbol:
        return "aug"
    if "sus" in lowered:
        return "sus"
    if "min" in lowered or (len(symbol) > 1 and symbol[1] == "m" and symbol[0] != "M"):
        return "min"
    if "maj" in lowered:
        return "maj"
    return "dom"
