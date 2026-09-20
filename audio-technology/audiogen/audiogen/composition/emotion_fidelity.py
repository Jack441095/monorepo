# composition/emotion_fidelity.py
"""Emotion-fidelity check (2026-07-04, docs/AUDIOGEN_COMPOSITION_PLAN.md item 3).

A lightweight, dependency-free scorer that answers: "does this generated song actually
sound like the emotion it was generated for?" It measures a small set of features from a
song's note events and compares them against per-emotion *expected* features derived from
the authoritative generation parameters (`EmotionProfile.tempo_multiplier/density/
scale_intervals` + `EmotionAnchors.brightness`), so it covers all 28 emotions and stays in
sync with the knobs generation actually uses -- no separate hand-tuned table to drift.

Two outputs:
  - `emotion_fidelity_score(events, emotion_name)` -> per-dimension sub-scores + overall
    0..1 fidelity (absolute "how well does it match its own emotion's intent").
  - `discriminate(events, true_emotion_name)` -> where the true emotion ranks when the song
    is scored against every emotion's expected profile (the real "is it recognizable" test:
    a faithful song should rank its own emotion near the top).

Intended uses: a regression guard when changing generation (did we shift an emotion's
character?), and a batch quality signal across emotions/seeds (like this session's ad-hoc
84-song audit, but reusable).
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Dict, List, Optional, Sequence, Tuple

from data.emotion_anchors import anchors_for_emotion
from data.music_data import EMOTION_BY_NAME, EMOTIONS

# Event tuple layout used across the composition engine:
#   (channel, midi, velocity, start_beats, duration_beats, notes)
# Channels: 0=bass, 1=chords, 2=melody, 3=arp, 5=counter_melody.
_CH_BASS = 0
_CH_CHORD = 1
_CH_MELODY = 2

# Feature weights for the overall score. Mode (major/minor) is the single strongest
# emotional signal, so it carries the most weight; energy (density+duration) next.
_WEIGHTS = {
    "mode": 0.34,
    "density": 0.24,
    "note_duration": 0.20,
    "register": 0.14,
    "motion": 0.08,
}


@dataclass
class SongFeatures:
    melody_density: float = 0.0        # melody notes per beat
    mean_register: float = 0.0         # mean melody MIDI pitch
    mean_note_duration: float = 0.0    # mean melody note length (beats)
    mean_abs_interval: float = 0.0     # mean |consecutive melody interval| (semitones)
    minor_third_frac: float = 0.0      # fraction of chord onsets whose quality reads minor
    n_melody: int = 0
    n_chords: int = 0


@dataclass
class FidelityResult:
    emotion: str
    overall: float                              # 0..1
    sub_scores: Dict[str, float] = field(default_factory=dict)
    measured: Optional[SongFeatures] = None
    expected: Optional[Dict[str, float]] = None


def _mean(xs: Sequence[float]) -> float:
    xs = [float(x) for x in xs]
    return sum(xs) / len(xs) if xs else 0.0


def extract_song_features(events: Sequence[tuple], *, total_beats: Optional[float] = None) -> SongFeatures:
    """Measure the feature set from raw song events. `total_beats` defaults to the span of
    the events (max end beat) so density is notes-per-beat over the actual song length."""
    melody = [e for e in events if int(e[0]) == _CH_MELODY and int(e[1]) > 0]
    chords = [e for e in events if int(e[0]) == _CH_CHORD]

    if total_beats is None:
        total_beats = max((float(e[3]) + float(e[4]) for e in events), default=0.0)
    total_beats = max(1e-6, float(total_beats))

    f = SongFeatures(n_melody=len(melody), n_chords=len(chords))
    if melody:
        pitches = [int(e[1]) for e in sorted(melody, key=lambda e: float(e[3]))]
        f.melody_density = len(melody) / total_beats
        f.mean_register = _mean(pitches)
        f.mean_note_duration = _mean([float(e[4]) for e in melody])
        if len(pitches) >= 2:
            f.mean_abs_interval = _mean([abs(pitches[i + 1] - pitches[i]) for i in range(len(pitches) - 1)])

    # Mode signal (major vs minor), measured aggregate and key-relative. Per-chord root
    # detection is unreliable here: bass lines walk/pass, so the bass note nearest a chord
    # onset is often a non-root passing tone, and spread/inverted voicings defeat
    # "lowest note = root". Instead, establish the tonic pitch class as the most common
    # bass pitch class (the bass roots the tonic most often across a song), then measure
    # how much the whole song leans on the minor 3rd (tonic+3) vs the major 3rd (tonic+4)
    # scale degree across all voiced notes. A minor-key song uses tonic+3 and avoids
    # tonic+4; a major-key song does the reverse. Aggregating over the whole song is robust
    # to the per-chord alignment noise that defeats onset-by-onset detection.
    bass_pcs = [int(e[1]) % 12 for e in events if int(e[0]) == _CH_BASS and int(e[1]) > 0]
    if bass_pcs:
        tonic = max(set(bass_pcs), key=bass_pcs.count)
    elif melody:
        mp = [int(e[1]) % 12 for e in melody]
        tonic = max(set(mp), key=mp.count)
    else:
        tonic = 0
    minor3 = (tonic + 3) % 12
    major3 = (tonic + 4) % 12
    n_min = n_maj = 0
    for e in events:
        ch = int(e[0])
        if ch not in (_CH_BASS, _CH_CHORD, _CH_MELODY):
            continue
        note_list = e[5] if (len(e) > 5 and e[5]) else [e[1]]
        for n in note_list:
            if not isinstance(n, int) or n <= 0:
                continue
            pc = int(n) % 12
            if pc == minor3:
                n_min += 1
            elif pc == major3:
                n_maj += 1
    f.minor_third_frac = (n_min / (n_min + n_maj)) if (n_min + n_maj) else 0.5
    return f


def expected_features_for_emotion(emotion_name: str) -> Dict[str, float]:
    """Derive expected feature targets from the authoritative generation parameters.
    Mappings are calibrated against this session's empirical 84-song audit (e.g. grief
    ~0.99 notes/beat & ~0.84 beat durations vs excitement ~1.92 & ~0.36)."""
    emo = EMOTION_BY_NAME.get(emotion_name)
    anc = anchors_for_emotion(emotion_name)
    tempo = float(getattr(emo, "tempo_multiplier", 1.0) or 1.0) if emo else 1.0
    density = float(getattr(emo, "density", 0.5) or 0.5) if emo else 0.5
    brightness = float(getattr(anc, "brightness", 0.0) or 0.0)
    scale = list(getattr(emo, "scale_intervals", []) or []) if emo else []

    # notes/beat: ~0.9 baseline + density lift (empirical slope ~1.05).
    exp_density = 0.9 + 1.05 * density
    # register center: brightness [-0.55..0.8] -> MIDI ~64..78.
    exp_register = 70.0 + brightness * 11.0
    # note duration: higher energy (tempo) -> shorter notes.
    exp_note_dur = max(0.30, 0.92 - 0.30 * tempo)
    # motion: energetic emotions leap more.
    exp_motion = 2.2 + 1.4 * tempo
    # mode: does the emotion's scale contain a minor 3rd (interval 3) but not major (4)?
    # Targets calibrated to the ACTUAL generated minor-3rd-vs-major-3rd usage ratio (this
    # session's added harmonic richness -- borrowed/modal-interchange chords -- means minor
    # emotions realistically read ~0.55-0.70, not a pure ~0.9; major emotions read ~0.05-0.20).
    pcs = {int(x) % 12 for x in scale}
    if 3 in pcs and 4 not in pcs:
        exp_minor_frac = 0.62     # clearly minor scale
    elif 4 in pcs and 3 not in pcs:
        exp_minor_frac = 0.12     # clearly major scale
    else:
        exp_minor_frac = 0.40     # ambiguous (chromatic/whole-tone/both thirds present)
    return {
        "density": exp_density,
        "register": exp_register,
        "note_duration": exp_note_dur,
        "motion": exp_motion,
        "minor_third_frac": exp_minor_frac,
    }


def _kernel(measured: float, expected: float, tolerance: float) -> float:
    """Smooth 0..1 closeness score: 1.0 at exact match, decaying with |diff|/tolerance."""
    if tolerance <= 1e-9:
        return 1.0 if abs(measured - expected) < 1e-9 else 0.0
    d = abs(float(measured) - float(expected)) / float(tolerance)
    return 1.0 / (1.0 + d * d)


def _sub_scores(feat: SongFeatures, exp: Dict[str, float]) -> Dict[str, float]:
    return {
        "mode": _kernel(feat.minor_third_frac, exp["minor_third_frac"], 0.35),
        "density": _kernel(feat.melody_density, exp["density"], 0.45),
        "note_duration": _kernel(feat.mean_note_duration, exp["note_duration"], 0.30),
        "register": _kernel(feat.mean_register, exp["register"], 7.0),
        "motion": _kernel(feat.mean_abs_interval, exp["motion"], 3.0),
    }


def emotion_fidelity_score(events: Sequence[tuple], emotion_name: str) -> FidelityResult:
    """Absolute fidelity: how well the song matches its OWN emotion's expected features."""
    feat = extract_song_features(events)
    exp = expected_features_for_emotion(emotion_name)
    subs = _sub_scores(feat, exp)
    overall = sum(_WEIGHTS[k] * subs[k] for k in _WEIGHTS)
    return FidelityResult(emotion=emotion_name, overall=overall, sub_scores=subs, measured=feat, expected=exp)


def discriminate(
    events: Sequence[tuple],
    true_emotion_name: str,
    *,
    candidates: Optional[Sequence[str]] = None,
) -> Tuple[int, List[Tuple[str, float]]]:
    """Score the song against every emotion's expected profile. Returns
    (rank_of_true_emotion, ranked [(emotion, overall), ...] best-first). A faithful song
    should rank its own emotion near the top. Rank is 1-indexed."""
    feat = extract_song_features(events)
    names = list(candidates) if candidates is not None else [e.name for e in EMOTIONS]
    scored: List[Tuple[str, float]] = []
    for name in names:
        exp = expected_features_for_emotion(name)
        subs = _sub_scores(feat, exp)
        scored.append((name, sum(_WEIGHTS[k] * subs[k] for k in _WEIGHTS)))
    scored.sort(key=lambda kv: -kv[1])
    rank = next((i + 1 for i, (n, _) in enumerate(scored) if n == true_emotion_name), len(scored))
    return rank, scored
