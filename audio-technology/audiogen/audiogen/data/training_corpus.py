from __future__ import annotations

from functools import lru_cache
from typing import Iterable, List, Sequence, Tuple

from data.audit import normalize_progression_pool
from data.tokens import ChordToken


def _bucket_from_symbol(symbol: str) -> str:
    """
    Mirror CompositionGenerator._simplify_chord_for_markov() but keep it local to `data/`
    so corpus building does not depend on composition runtime objects.
    """
    s = str(symbol or "")
    if "maj" in s:
        return "maj"
    if "min" in s or (len(s) > 1 and s[1] == "m" and s[0] != "M"):
        return "min"
    if "dim" in s or "ø" in s or "°" in s:
        return "dim"
    if "aug" in s or "+" in s:
        return "aug"
    if "sus" in s:
        return "sus"
    return "dom"


def chord_sequence_for_progression(
    progression: Sequence[str],
    *,
    token_mode: str = "bucket",
) -> List[str]:
    """
    Convert a progression of chord symbols into Markov symbols.

    token_mode:
      - 'bucket': returns simplified buckets only
      - 'degree': returns '<degree>:<bucket>' when roman degree is present, else bucket
    """
    mode = str(token_mode or "bucket").strip().lower()
    use_degree = mode in {"degree", "roman", "degree_bucket"}
    out: List[str] = []
    for ch in list(progression or []):
        s = str(ch or "").strip()
        if not s:
            continue
        bucket = _bucket_from_symbol(s)
        tok = ChordToken.from_symbol(s, bucket=bucket)
        sym = tok.serialize(use_degree=use_degree)
        if sym:
            out.append(sym)
    return out


@lru_cache(maxsize=64)
def get_chord_sequences(
    emotion_names: Tuple[str, ...],
    *,
    token_mode: str = "bucket",
    include_cadences: bool = True,
) -> Tuple[List[List[str]], List[float]]:
    """
    Return (sequences, weights) for chord Markov training using the in-repo emotion pools.

    Cache key is emotion_names + token_mode + include_cadences.
    """
    try:
        from data.music_data import EMOTION_BY_NAME
    except Exception:
        EMOTION_BY_NAME = {}

    seqs: List[List[str]] = []
    weights: List[float] = []
    for name in list(emotion_names or ()):
        emo = EMOTION_BY_NAME.get(str(name or "").strip().lower())
        if emo is None:
            continue
        pools: List[Iterable[str]] = []
        try:
            pools.extend(list(getattr(emo, "chord_progressions", None) or []))
        except Exception:
            pass
        if include_cadences:
            try:
                pools.extend(list(getattr(emo, "cadence_progressions", None) or []))
            except Exception:
                pass
        pools_n = normalize_progression_pool(pools)
        for prog in list(pools_n or []):
            seq = chord_sequence_for_progression(prog, token_mode=str(token_mode))
            if len(seq) >= 2:
                seqs.append(seq)
                weights.append(1.0)
    return seqs, weights

