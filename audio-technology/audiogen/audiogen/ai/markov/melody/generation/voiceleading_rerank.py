# ai/markov/melody/generation/voiceleading_rerank.py
from typing import Dict, List, Tuple


def voiceleading_local_rerank_delta(
    *,
    phrase: List[Tuple[int, float]],
    start_degree: int,
    start_beat: float,
    beats_per_bar: float,
    chord_weights_per_bar: List[Dict[int, float]],
    strength: float,
) -> float:
    """
    Cheap, deterministic local cost used to rerank phrase candidates.
    Returns a signed delta to add to the phrase score (positive = better).
    """
    s = 0.0
    st = max(0.0, min(1.0, float(strength)))
    if st <= 1e-9 or not phrase:
        return 0.0
    try:
        t = float(start_beat)
        prev_deg = int(start_degree)
        for deg, dur in list(phrase):
            if not isinstance(deg, int) or int(deg) < 0:
                t += float(dur)
                continue
            beat_in_bar = float(t % beats_per_bar) if beats_per_bar > 1e-9 else float(t % 4.0)
            strong = (abs(beat_in_bar - 0.0) < 1e-6) or (abs(beat_in_bar - 2.0) < 1e-6)
            iv = int(deg) - int(prev_deg)
            mag = abs(int(iv))
            if strong and mag >= 3:
                s -= float(st) * 0.08 * float(mag - 2)
            if strong:
                try:
                    bar = int(float(t) // float(beats_per_bar)) if beats_per_bar > 1e-9 else int(float(t) // 4.0)
                    cw = chord_weights_per_bar[bar] if chord_weights_per_bar and 0 <= bar < len(chord_weights_per_bar) else {}
                    chord_tones = set(int(k) % 7 for k in (cw or {}).keys())
                    if chord_tones and (int(deg) % 7) in chord_tones:
                        s += float(st) * 0.03
                    elif chord_tones:
                        s -= float(st) * 0.02
                except Exception:
                    pass
            prev_deg = int(deg)
            t += float(dur)
    except Exception:
        return 0.0
    try:
        return float(max(-2.0, min(2.0, float(s))))
    except Exception:
        return 0.0
