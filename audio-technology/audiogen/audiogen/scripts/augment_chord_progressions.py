"""Self-generate additional chord progressions per emotion from that emotion's OWN existing
progressions (docs/AUDIOGEN_COMPOSITION_PLAN.md, variety work 2026-07-04).

Builds a bigram transition model from each emotion's merged_chord_progression_pool (base +
arrangement_chord_sets), then samples NEW progressions of varied length (4-8 chords) that can
only ever use chords/moves already observed in that emotion's own data. Filters out exact
duplicates, non-tonic starts, unfamiliar cadence endings, and low-variety oscillation
(e.g. "I - V - I - V - I - V"). This is what keeps emotional identity intact while adding
harmonic variety -- validated via composition/emotion_fidelity.py (see
tests/audiogen/test_chord_augmentation.py) rather than hand-tuned by ear.

Deterministic: reruns with the same DEFAULT_N_CANDIDATES produce the same output, so this can
be regenerated any time the base hand-written progressions change.

Writes data/chord_progressions_augmented.py (a plain generated data module, kept separate
from the hand-curated data/music_data.py so the two are easy to diff/review independently).
Run from studio/audiogen/audiogen:  python scripts/augment_chord_progressions.py
"""
from __future__ import annotations

import random
from collections import Counter, defaultdict
from pathlib import Path
from typing import Dict, List

import copy

from data.audit import audit_emotion
from data.music_data import EMOTIONS, merged_chord_progression_pool

DEFAULT_N_CANDIDATES = 12
_LENGTHS = [4, 4, 4, 5, 6, 6, 7, 8]  # weighted toward 4-6, some longer arcs
_OUTPUT_PATH = Path(__file__).resolve().parent.parent / "data" / "chord_progressions_augmented.py"


def _is_tonic(sym: str) -> bool:
    s = (sym or "").strip()
    return s.startswith("I") or s.startswith("i")


def _build_model(progressions: List[List[str]]):
    starts: Counter = Counter()
    ends: Counter = Counter()
    transitions: Dict[str, Counter] = defaultdict(Counter)
    for prog in progressions:
        if not prog:
            continue
        starts[prog[0]] += 1
        ends[prog[-1]] += 1
        for a, b in zip(prog, prog[1:]):
            transitions[a][b] += 1
    return starts, ends, transitions


def _sample_progression(starts, transitions, rng, length):
    tonic_starts = [c for c in starts if _is_tonic(c)] or list(starts)
    chord = rng.choices(tonic_starts, weights=[starts[c] for c in tonic_starts], k=1)[0]
    prog = [chord]
    for _ in range(length - 1):
        options = transitions.get(chord)
        if not options:
            chord = rng.choices(list(starts), weights=[starts[c] for c in starts], k=1)[0]
        else:
            symbols = list(options.keys())
            nxt = rng.choices(symbols, weights=[options[s] for s in symbols], k=1)[0]
            if nxt == chord and len(symbols) > 1:
                nxt = rng.choice([s for s in symbols if s != chord])
            chord = nxt
        prog.append(chord)
    return prog


def _clean_emotion(emotion_name: str):
    """A deep copy of the emotion with any PREVIOUSLY augmented progressions stripped back
    out, so every regeneration starts from the true hand-written baseline in music_data.py
    -- not from a prior run's output (data.music_data merges the augmented file back in at
    import time, which would otherwise compound across regenerations)."""
    from data.music_data import EMOTION_BY_NAME

    try:
        from data.chord_progressions_augmented import AUGMENTED_CHORD_PROGRESSIONS as _prev_aug
    except Exception:
        _prev_aug = {}

    emo = copy.deepcopy(EMOTION_BY_NAME[emotion_name.lower()])
    prev = {tuple(p) for p in (_prev_aug.get(emotion_name.lower()) or [])}
    if prev:
        emo.chord_progressions = [p for p in emo.chord_progressions if tuple(p) not in prev]
        sets = getattr(emo, "arrangement_chord_sets", None) or {}
        for role, progs in sets.items():
            sets[role] = [p for p in progs if tuple(p) not in prev]
    return emo


def augment_emotion(emotion_name: str, n_candidates: int = DEFAULT_N_CANDIDATES, seed: int = 0) -> List[List[str]]:
    emo = _clean_emotion(emotion_name)
    pool = merged_chord_progression_pool(emo)
    existing = {tuple(p) for p in pool}
    starts, ends, transitions = _build_model(pool)
    valid_ends = set(ends)

    # Gate every candidate through the harmony audit (data/audit.py) so augmentation can
    # never introduce a tension/cadence/scale-conflict regression that the hand-written
    # data doesn't already have. Checked incrementally (baseline -> baseline+candidate) so
    # a bigram chain that happens to stack too many tension tokens in a row (a real risk:
    # dark emotions' own vocab is tension-heavy, so an unlucky walk can over-concentrate it)
    # gets rejected before it ever reaches data/chord_progressions_augmented.py.
    baseline_issues = len(audit_emotion(emo))

    rng = random.Random(seed)
    seen = set()
    kept: List[List[str]] = []
    working = copy.deepcopy(emo)
    for _ in range(n_candidates * 12):
        if len(kept) >= n_candidates:
            break
        length = rng.choice(_LENGTHS)
        prog = _sample_progression(starts, transitions, rng, length)
        key = tuple(prog)
        if key in existing or key in seen:
            continue
        seen.add(key)
        if not _is_tonic(prog[0]) or prog[-1] not in valid_ends:
            continue
        if any(a == b for a, b in zip(prog, prog[1:])):
            continue
        distinct = len(set(prog))
        if len(prog) >= 5 and distinct < 3:
            continue
        pair_repeats = sum(1 for i in range(len(prog) - 2) if prog[i] == prog[i + 2])
        if pair_repeats > len(prog) // 2:
            continue

        working.chord_progressions = list(emo.chord_progressions) + kept + [prog]
        if len(audit_emotion(working)) > baseline_issues:
            continue  # would introduce a new audit warning -- reject, don't accumulate
        kept.append(prog)
    return kept


def main():
    lines = [
        '"""Auto-generated chord progressions, self-generated per emotion from that emotion\'s',
        "own hand-written chord_progressions in data/music_data.py (bigram transition sampling,",
        "see scripts/augment_chord_progressions.py). Do not hand-edit -- regenerate via:",
        "    python scripts/augment_chord_progressions.py",
        "",
        "Merged into each EmotionProfile.chord_progressions at import time (see the bottom of",
        'data/music_data.py). Validated against emotion_fidelity before being added -- see',
        'tests/audiogen/test_chord_augmentation.py."""',
        "",
        "AUGMENTED_CHORD_PROGRESSIONS = {",
    ]
    for idx, emo in enumerate(EMOTIONS):
        cands = augment_emotion(emo.name, seed=idx)
        lines.append(f'    "{emo.name.lower()}": [')
        for c in cands:
            lines.append(f"        {c!r},")
        lines.append("    ],")
    lines.append("}")
    _OUTPUT_PATH.write_text("\n".join(lines) + "\n")
    total = sum(len(augment_emotion(e.name, seed=i)) for i, e in enumerate(EMOTIONS))
    print(f"Wrote {_OUTPUT_PATH} ({total} new progressions across {len(EMOTIONS)} emotions)")


if __name__ == "__main__":
    main()
