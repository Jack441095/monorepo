# ai/markov/melody/training/train.py
import logging
from typing import Dict, List, Optional, Tuple

from ai.markov.melody.contour import (
    get_phrase_intervals_by_contour,
    infer_contour_sequence,
)
from ai.markov.melody.training import features as feat

logger = logging.getLogger(__name__)

def train_from_melodies(gen,
                        melodies: List[List[Tuple[int, float]]],
                        phrase_contours: Optional[List[List[str]]] = None,
                        phrase_roles: Optional[List[List[str]]] = None,
                        emotion_name: str = 'neutral',
                        emotion_names: Optional[List[str]] = None,
                        chord_sequences: Optional[List[List[str]]] = None,
                        root_notes: Optional[List[Optional[int]]] = None,
                        scale_intervals_by_melody: Optional[List[Optional[List[int]]]] = None,
                        beats_per_bar_by_melody: Optional[List[Optional[float]]] = None,
                        bpm_by_melody: Optional[List[Optional[float]]] = None):
    """Train Markov models and motif library from melodies."""
    try:
        from audiogen_core.config import CONFIG

        rest_safe_iv = bool(getattr(CONFIG.composition, "melody_train_rest_safe_intervals_enabled", True))
        signed_rr = bool(getattr(CONFIG.composition, "melody_rest_rhythm_tokens_train_enabled", False))
    except Exception:
        rest_safe_iv = True
        signed_rr = False

    interval_sequences = []
    rhythm_sequences = []
    usable_weights: List[float] = []
    melody_weights = feat.build_recency_weights(len(melodies))
    for i, mel in enumerate(melodies):
        if len(mel) < 2:
            continue
        intervals = feat.melody_interval_steps(mel, rest_safe_iv)
        if not intervals:
            continue
        interval_sequences.append(intervals)
        rhythms = [
            feat.rhythm_token_for_event(int(d), float(dur), signed_rr)
            for d, dur in mel
        ]
        rhythm_sequences.append(rhythms)
        usable_weights.append(melody_weights[i])
        source_emotion = emotion_name
        if emotion_names and i < len(emotion_names):
            source_emotion = str(emotion_names[i] or emotion_name).strip().lower() or emotion_name
        gen.motif.extract_from_melody(
            mel, source_emotion=source_emotion,
            chord_sequence=chord_sequences[i] if chord_sequences else None
        )

    gen.markov.train_intervals_and_rhythms(
        interval_sequences,
        rhythm_sequences,
        sequence_weights=usable_weights
    )

    def _beats_per_bar_for(i: int) -> float:
        try:
            if beats_per_bar_by_melody and 0 <= int(i) < len(beats_per_bar_by_melody):
                v = beats_per_bar_by_melody[int(i)]
                if v is not None:
                    return max(0.25, float(v))
        except Exception:
            pass
        return 4.0

    def _tempo_bucket_for(i: int) -> str:
        # Coarse tempo buckets: stable and backoff-friendly.
        try:
            if bpm_by_melody and 0 <= int(i) < len(bpm_by_melody):
                v = bpm_by_melody[int(i)]
                if v is not None:
                    bpm = float(v)
                else:
                    bpm = None
            else:
                bpm = None
        except Exception:
            bpm = None
        if bpm is None:
            return "unk"
        bpm = max(20.0, min(260.0, float(bpm)))
        if bpm < 78.0:
            return "slow"
        if bpm < 118.0:
            return "mid"
        return "fast"

    def _keypc_for(i: int) -> str:
        try:
            if root_notes and 0 <= int(i) < len(root_notes):
                r = root_notes[int(i)]
                if r is not None:
                    return str(int(r) % 12)
        except Exception:
            pass
        return "unk"

    def _mode_for(i: int) -> str:
        # Coarse mode tags based on scale intervals (relative to tonic).
        # Keep buckets broad so they generalize and avoid sparsity.
        try:
            if scale_intervals_by_melody and 0 <= int(i) < len(scale_intervals_by_melody):
                iv = scale_intervals_by_melody[int(i)]
                if isinstance(iv, list) and iv:
                    pcs = [int(x) % 12 for x in iv]
                else:
                    pcs = None
            else:
                pcs = None
        except Exception:
            pcs = None
        if not pcs:
            return "unk"
        major = [0, 2, 4, 5, 7, 9, 11]
        minor = [0, 2, 3, 5, 7, 8, 10]
        try:
            s = sorted(set(int(x) % 12 for x in pcs))
            if s == major:
                return "maj"
            if s == minor:
                return "min"
        except Exception:
            pass
        return "other"

    # Phase 2g: register-band conditioned models (low/mid/high) when root+scale are provided.
    # This trains separate Markovs for interval/rhythm behavior in different pitch ranges.
    def _degree_to_midi(degree: int, root: int, scale_intervals: List[int]) -> int:
        tonic = int(root) - int(scale_intervals[0] if scale_intervals else 0)
        while tonic < 48:
            tonic += 12
        while tonic > 72:
            tonic -= 12
        if not scale_intervals:
            return int(tonic)
        return int(tonic) + int(scale_intervals[int(degree) % len(scale_intervals)])

    def _register_bin(midi: int) -> str:
        try:
            from audiogen_core.config import CONFIG

            low_max = int(getattr(CONFIG.composition, "melody_register_band_low_max_midi", 59) or 59)
            high_min = int(getattr(CONFIG.composition, "melody_register_band_high_min_midi", 73) or 73)
        except Exception:
            low_max = 59
            high_min = 73
        m = int(midi)
        if m <= int(low_max):
            return "low"
        if m >= int(high_min):
            return "high"
        return "mid"

    reg_iv: Dict[str, List[List[int]]] = {"low": [], "mid": [], "high": []}
    reg_iv_w: Dict[str, List[float]] = {"low": [], "mid": [], "high": []}
    reg_rhy: Dict[str, List[List[float]]] = {"low": [], "mid": [], "high": []}
    reg_rhy_w: Dict[str, List[float]] = {"low": [], "mid": [], "high": []}
    if root_notes and scale_intervals_by_melody and len(root_notes) == len(melodies) and len(scale_intervals_by_melody) == len(melodies):
        for i, mel in enumerate(melodies):
            if len(mel) < 2:
                continue
            root = root_notes[i]
            scale_iv = scale_intervals_by_melody[i]
            if root is None or not scale_iv:
                continue
            w = float(melody_weights[i])
            # Rhythm tokens bucketed by last voiced midi (or current voiced if none yet).
            last_voiced_midi: Optional[int] = None
            for (deg, dur) in mel:
                try:
                    dg = int(deg)
                except Exception:
                    dg = -1
                if dg >= 0:
                    try:
                        last_voiced_midi = _degree_to_midi(int(dg) % 7, int(root), list(scale_iv))
                    except Exception:
                        last_voiced_midi = last_voiced_midi
                bb = _register_bin(int(last_voiced_midi)) if last_voiced_midi is not None else "mid"
                try:
                    rtok = feat.rhythm_token_for_event(int(dg), float(dur), signed_rr)
                except Exception:
                    rtok = float(dur)
                reg_rhy[bb].append([float(rtok)])
                reg_rhy_w[bb].append(float(w))

            # Interval tokens bucketed by source voiced note midi.
            voiced = [(int(d), float(dur)) for d, dur in mel if isinstance(d, int) and int(d) >= 0]
            if len(voiced) >= 2:
                for j in range(len(voiced) - 1):
                    d0 = int(voiced[j][0]) % 7
                    d1 = int(voiced[j + 1][0]) % 7
                    try:
                        m0 = _degree_to_midi(d0, int(root), list(scale_iv))
                    except Exception:
                        continue
                    bb = _register_bin(int(m0))
                    reg_iv[bb].append([int(d1) - int(d0)])
                    reg_iv_w[bb].append(float(w))
        try:
            gen.markov.train_register_conditioned_intervals(reg_iv, register_sequence_weights=reg_iv_w)
            gen.markov.train_register_conditioned_rhythms(reg_rhy, register_sequence_weights=reg_rhy_w)
        except Exception:
            logger.debug("Register-conditioned Markov training skipped", exc_info=True)

    # Phase 2a: P(next_interval | preceding note duration bucket), separate Markov per bucket.
    try:
        from ai.markov.melody.ensemble.bucketing import NUM_PREV_DURATION_BUCKETS

        bucket_to_seqs: Dict[int, List[List[int]]] = {i: [] for i in range(NUM_PREV_DURATION_BUCKETS)}
        bucket_weights: Dict[int, List[float]] = {i: [] for i in range(NUM_PREV_DURATION_BUCKETS)}
        for i, mel in enumerate(melodies):
            if len(mel) < 2:
                continue
            per = feat.interval_sequences_by_prev_duration_bucket(mel, rest_safe_iv)
            w = melody_weights[i]
            for b in range(NUM_PREV_DURATION_BUCKETS):
                seq = per[b]
                if len(seq) >= 1:
                    bucket_to_seqs[b].append(seq)
                    bucket_weights[b].append(w)
        gen.markov.train_intervals_by_prev_duration_bucket(bucket_to_seqs, bucket_weights)
    except Exception:
        logger.debug("Prev-duration bucket interval training skipped", exc_info=True)

    # Phase 2c: phrase-gesture interval models (opening / middle / cadence).
    try:
        train_gesture = bool(getattr(CONFIG.composition, "melody_train_gesture_interval_models", False))
    except Exception:
        train_gesture = False
    if train_gesture:
        try:
            from ai.markov.melody.ensemble.bucketing import GESTURE_KEYS

            gesture_to_seqs: Dict[str, List[List[int]]] = {g: [] for g in GESTURE_KEYS}
            gesture_weights: Dict[str, List[float]] = {g: [] for g in GESTURE_KEYS}
            for i, mel in enumerate(melodies):
                if len(mel) < 2:
                    continue
                per = feat.interval_sequences_by_phrase_gesture(mel, rest_safe_iv)
                w = melody_weights[i]
                for g in GESTURE_KEYS:
                    seq = per[g]
                    if len(seq) >= 1:
                        gesture_to_seqs[g].append(seq)
                        gesture_weights[g].append(w)
            gen.markov.train_gesture_intervals(gesture_to_seqs, gesture_weights)
        except Exception:
            logger.debug("Gesture interval training skipped", exc_info=True)

    if phrase_contours:
        gen.markov.train_phrase_contours(phrase_contours, sequence_weights=melody_weights)
    else:
        inferred = [infer_contour_sequence(mel) for mel in melodies]
        gen.markov.train_phrase_contours(inferred, sequence_weights=melody_weights)

    # Train per-contour interval models (previously extracted but never
    # trained — the models always fell back to the global interval model).
    combined_buckets: Dict[str, List[List[int]]] = {c: [] for c in ('asc', 'desc', 'arch', 'static')}
    contour_weights: Dict[str, List[float]] = {c: [] for c in ('asc', 'desc', 'arch', 'static')}
    for mel_idx, mel in enumerate(melodies):
        weight = melody_weights[mel_idx]
        for contour, seqs in get_phrase_intervals_by_contour(
            mel, rest_safe_intervals=rest_safe_iv
        ).items():
            combined_buckets[contour].extend(seqs)
            contour_weights[contour].extend([weight] * len(seqs))
    gen.markov.train_contour_intervals(combined_buckets, contour_sequence_weights=contour_weights)

    # Phase 2f: beat-strength conditioned models (downbeat vs offbeat).
    # This helps hooks feel grounded on beat 1 without over-constraining passing motion.
    beat_iv_buckets: Dict[str, List[List[int]]] = {"downbeat": [], "offbeat": []}
    beat_iv_weights: Dict[str, List[float]] = {"downbeat": [], "offbeat": []}
    beat_rhy_buckets: Dict[str, List[List[float]]] = {"downbeat": [], "offbeat": []}
    beat_rhy_weights: Dict[str, List[float]] = {"downbeat": [], "offbeat": []}
    for mel_idx, mel in enumerate(melodies):
        if len(mel) < 3:
            continue
        w = float(melody_weights[mel_idx])
        beat = 0.0
        bpb0 = _beats_per_bar_for(int(mel_idx))
        # Intervals: bucket by the onset of the source voiced note.
        last_voiced_degree = None
        last_voiced_beat = None
        # Rhythms: bucket by onset beat of each event.
        for i, (deg, dur) in enumerate(mel):
            try:
                beat_in_bar = float(beat) % float(bpb0)
            except Exception:
                beat_in_bar = 0.0
            bb = "downbeat" if abs(float(beat_in_bar) - 0.0) < 1e-6 else "offbeat"
            try:
                dg = int(deg) if isinstance(deg, int) else -1
            except Exception:
                dg = -1
            rtok = feat.rhythm_token_for_event(dg, float(dur), signed_rr)
            beat_rhy_buckets[bb].append([float(rtok)])
            beat_rhy_weights[bb].append(float(w))

            # Interval token when we have two voiced notes.
            try:
                di = int(deg) if isinstance(deg, int) else -1
            except Exception:
                di = -1
            if isinstance(di, int) and int(di) >= 0:
                if last_voiced_degree is not None and last_voiced_beat is not None:
                    # Bucket by onset of previous voiced note (musically: the interval begins there).
                    try:
                        prev_bin = "downbeat" if abs(float(last_voiced_beat) % float(bpb0)) < 1e-6 else "offbeat"
                    except Exception:
                        prev_bin = "offbeat"
                    beat_iv_buckets[prev_bin].append([int(di) - int(last_voiced_degree)])
                    beat_iv_weights[prev_bin].append(float(w))
                last_voiced_degree = int(di)
                last_voiced_beat = float(beat)

            try:
                beat += abs(float(dur))
            except Exception:
                beat += 0.5

    try:
        gen.markov.train_beat_conditioned_intervals(beat_iv_buckets, beat_sequence_weights=beat_iv_weights)
        gen.markov.train_beat_conditioned_rhythms(beat_rhy_buckets, beat_sequence_weights=beat_rhy_weights)
    except Exception:
        logger.debug("Beat-conditioned Markov training skipped", exc_info=True)

    # Optional: train phrase-role interval models (opening/continuation/answer/cadence).
    # This improves alignment between phrase planning and the interval Markov statistics.
    try:
        from audiogen_core.config import CONFIG

        enable_role = bool(getattr(CONFIG.composition, "melody_train_phrase_role_models", False))
    except Exception:
        enable_role = False

    if enable_role:
        role_buckets: Dict[str, List[List[int]]] = {r: [] for r in ("opening", "continuation", "answer", "cadence")}
        role_weights: Dict[str, List[float]] = {r: [] for r in ("opening", "continuation", "answer", "cadence")}
        role_rhythm_buckets: Dict[str, List[List[float]]] = {r: [] for r in ("opening", "continuation", "answer", "cadence")}
        role_rhythm_weights: Dict[str, List[float]] = {r: [] for r in ("opening", "continuation", "answer", "cadence")}

        def role_for_phrase(i: int, total: int) -> str:
            if total <= 1 or i == 0:
                return "opening"
            if i == total - 1:
                return "cadence"
            return "answer" if (i % 2 == 1) else "continuation"

        # Prefer "true" phrase segmentation when roles are provided: we split into
        # fixed-bar phrases (same helper as training export) and map intervals to
        # the supplied phrase_roles. This keeps role models aligned with the
        # composition planner's phrase structure.
        try:
            from utils.phrase_extractor import split_into_phrases
        except Exception:
            split_into_phrases = None

        for mel_idx, mel in enumerate(melodies):
            if len(mel) < 3:
                continue
            weight = melody_weights[mel_idx]

            # True-segmentation path.
            roles_seq = None
            if phrase_roles and mel_idx < len(phrase_roles):
                try:
                    roles_seq = list(phrase_roles[mel_idx] or [])
                except Exception:
                    roles_seq = None
            if roles_seq and split_into_phrases is not None:
                try:
                    phrases, _ = split_into_phrases(mel, phrase_bars=4, beats_per_bar=4.0)
                except Exception:
                    phrases = []
                if phrases and len(phrases) == len(roles_seq):
                    for r, phrase in zip(roles_seq, phrases):
                        if len(phrase) < 2:
                            continue
                        role = str(r or "").strip().lower() or "continuation"
                        if role not in role_buckets:
                            role = "continuation"
                        intervals = feat.melody_interval_steps(phrase, rest_safe_iv)
                        if not intervals:
                            continue
                        role_buckets[role].append(intervals)
                        role_weights[role].append(weight)
                        role_rhythm_buckets[role].append([float(d) for _, d in phrase])
                        role_rhythm_weights[role].append(float(weight))
                    continue

            # Fallback: approximate segmentation by note count (legacy behavior).
            contours = None
            if phrase_contours and mel_idx < len(phrase_contours):
                contours = list(phrase_contours[mel_idx])
            if not contours:
                contours = infer_contour_sequence(mel)
            n_ph = max(1, len(contours))
            n_notes = len(mel)
            cuts = [int(round(i * n_notes / n_ph)) for i in range(n_ph + 1)]
            cuts[0] = 0
            cuts[-1] = n_notes
            for p_idx in range(n_ph):
                s = cuts[p_idx]
                e = cuts[p_idx + 1]
                phrase = mel[s:e]
                if len(phrase) < 2:
                    continue
                intervals = feat.melody_interval_steps(phrase, rest_safe_iv)
                if not intervals:
                    continue
                r = role_for_phrase(p_idx, n_ph)
                role_buckets[r].append(intervals)
                role_weights[r].append(weight)
                role_rhythm_buckets[r].append([float(d) for _, d in phrase])
                role_rhythm_weights[r].append(float(weight))

        gen.markov.train_role_intervals(role_buckets, role_sequence_weights=role_weights)
        try:
            gen.markov.train_role_rhythms(role_rhythm_buckets, role_sequence_weights=role_rhythm_weights)
        except Exception:
            pass

    if gen.markov.use_chord_conditioned and chord_sequences:
        chord_intervals: Dict[str, List[List[int]]] = {}
        chord_interval_weights: Dict[str, List[float]] = {}
        for mel_idx, (mel, chords_seq) in enumerate(zip(melodies, chord_sequences)):
            if len(mel) < 2 or len(chords_seq) != len(mel):
                continue
            seq_weight = melody_weights[mel_idx]
            if rest_safe_iv:
                vidx = [
                    i
                    for i, (d, _) in enumerate(mel)
                    if isinstance(d, int) and int(d) >= 0
                ]
                for j in range(len(vidx) - 1):
                    i0, i1 = vidx[j], vidx[j + 1]
                    interval = int(mel[i1][0]) - int(mel[i0][0])
                    chord = chords_seq[i0]
                    quality = gen.markov.extract_chord_quality(chord)
                    if quality not in chord_intervals:
                        chord_intervals[quality] = []
                        chord_interval_weights[quality] = []
                    chord_intervals[quality].append([interval])
                    chord_interval_weights[quality].append(seq_weight)
            else:
                intervals = feat.melody_interval_steps(mel, False)
                for i, interval in enumerate(intervals):
                    chord = chords_seq[i]
                    quality = gen.markov.extract_chord_quality(chord)
                    if quality not in chord_intervals:
                        chord_intervals[quality] = []
                        chord_interval_weights[quality] = []
                    chord_intervals[quality].append([interval])
                    chord_interval_weights[quality].append(seq_weight)
        for quality, intervals in chord_intervals.items():
            gen.markov.train_chord_conditioned_from_sequences(
                quality,
                intervals,
                sequence_weights=chord_interval_weights.get(quality)
            )

    # NEW: function + position conditioning (function × phrase_role × bar_in_phrase)
    try:
        from audiogen_core.config import CONFIG

        enabled = float(getattr(CONFIG.composition, "melody_function_condition_blend", 0.0)) > 1e-6
    except Exception:
        enabled = False

    if enabled and chord_sequences:
        try:
            from utils.phrase_extractor import split_into_phrases
        except Exception:
            split_into_phrases = None

        func_buckets: Dict[Tuple[str, str, int], List[List[int]]] = {}
        func_weights: Dict[Tuple[str, str, int], List[float]] = {}

        for mel_idx, mel in enumerate(melodies):
            if len(mel) < 3 or mel_idx >= len(chord_sequences):
                continue
            chords_seq = chord_sequences[mel_idx] or []
            if len(chords_seq) != len(mel):
                continue
            w = melody_weights[mel_idx]
            bpb0 = _beats_per_bar_for(int(mel_idx))
            tempo_bucket = _tempo_bucket_for(int(mel_idx))
            keypc = _keypc_for(int(mel_idx))
            mode = _mode_for(int(mel_idx))

            # Phrase roles: prefer provided, else derive from contour count.
            roles_seq = None
            if phrase_roles and mel_idx < len(phrase_roles):
                try:
                    roles_seq = list(phrase_roles[mel_idx] or [])
                except Exception:
                    roles_seq = None
            if not roles_seq:
                contours = None
                if phrase_contours and mel_idx < len(phrase_contours):
                    contours = list(phrase_contours[mel_idx] or [])
                n_ph = max(1, len(contours) if contours else 1)
                def role_for_phrase(i: int, total: int) -> str:
                    if total <= 1 or i == 0:
                        return "opening"
                    if i == total - 1:
                        return "cadence"
                    return "answer" if (i % 2 == 1) else "continuation"
                roles_seq = [role_for_phrase(i, n_ph) for i in range(n_ph)]

            # Compute per-note bar index from durations (4/4 fixed).
            beat = 0.0
            for i in range(len(mel) - 1):
                deg0, dur0 = mel[i]
                deg1, _ = mel[i + 1]
                chord = chords_seq[i]
                try:
                    bar = int(float(beat) // float(bpb0)) if float(bpb0) > 1e-9 else int(float(beat) // 4.0)
                except Exception:
                    bar = 0
                phrase_idx = max(0, int(bar // 4))
                bar_in_phrase = int(bar % 4)
                role = roles_seq[min(phrase_idx, len(roles_seq) - 1)] if roles_seq else "continuation"
                func = gen.markov.extract_harmonic_function(chord)
                feat_key = gen.markov.extract_harmonic_feature_key(chord)
                # Embed meter + tempo bucket into the feature key string so the tuple key
                # shape stays stable and hierarchical backoff still works.
                feat_key_m = f"{feat_key}|m:{float(bpb0):g}|tb:{tempo_bucket}|keypc:{keypc}|mode:{mode}"
                key = (str(feat_key_m), str(role), int(bar_in_phrase))
                if rest_safe_iv:
                    try:
                        d0i = int(deg0)
                        d1i = int(deg1)
                    except Exception:
                        d0i, d1i = -1, -1
                    if d0i < 0 or d1i < 0:
                        beat += float(dur0)
                        continue
                    interval = d1i - d0i
                else:
                    interval = int(deg1) - int(deg0)
                func_buckets.setdefault(key, []).append([interval])
                func_weights.setdefault(key, []).append(float(w))
                # Also train a coarse fallback bucket so sampling can back off.
                key2 = (f"{str(func)}|m:{float(bpb0):g}|tb:{tempo_bucket}|keypc:{keypc}|mode:{mode}", str(role), int(bar_in_phrase))
                func_buckets.setdefault(key2, []).append([interval])
                func_weights.setdefault(key2, []).append(float(w))
                beat += float(dur0)

        for key, seqs in func_buckets.items():
            gen.markov.train_function_conditioned_from_sequences(
                key,
                seqs,
                sequence_weights=func_weights.get(key),
            )

        # Rhythm conditioning: train per-key RhythmMarkov on contiguous segments where
        # the key is stable, so it learns local rhythmic tendencies per function/role/position.
        rh_buckets: Dict[Tuple[str, str, int], List[List[float]]] = {}
        rh_weights: Dict[Tuple[str, str, int], List[float]] = {}
        for mel_idx, mel in enumerate(melodies):
            if len(mel) < 3 or mel_idx >= len(chord_sequences):
                continue
            chords_seq = chord_sequences[mel_idx] or []
            if len(chords_seq) != len(mel):
                continue
            w = float(melody_weights[mel_idx])
            bpb0 = _beats_per_bar_for(int(mel_idx))
            tempo_bucket = _tempo_bucket_for(int(mel_idx))
            keypc = _keypc_for(int(mel_idx))
            mode = _mode_for(int(mel_idx))
            roles_seq = None
            if phrase_roles and mel_idx < len(phrase_roles):
                try:
                    roles_seq = list(phrase_roles[mel_idx] or [])
                except Exception:
                    roles_seq = None
            if not roles_seq:
                contours = None
                if phrase_contours and mel_idx < len(phrase_contours):
                    contours = list(phrase_contours[mel_idx] or [])
                n_ph = max(1, len(contours) if contours else 1)
                def role_for_phrase(i: int, total: int) -> str:
                    if total <= 1 or i == 0:
                        return "opening"
                    if i == total - 1:
                        return "cadence"
                    return "answer" if (i % 2 == 1) else "continuation"
                roles_seq = [role_for_phrase(i, n_ph) for i in range(n_ph)]

            beat = 0.0
            current_key = None
            seg: List[float] = []
            for i in range(len(mel)):
                deg, dur = mel[i]
                chord = chords_seq[i]
                try:
                    bar = int(float(beat) // float(bpb0)) if float(bpb0) > 1e-9 else int(float(beat) // 4.0)
                except Exception:
                    bar = 0
                phrase_idx = max(0, int(bar // 4))
                bar_in_phrase = int(bar % 4)
                role = roles_seq[min(phrase_idx, len(roles_seq) - 1)] if roles_seq else "continuation"
                func = gen.markov.extract_harmonic_function(chord)
                feat_key = gen.markov.extract_harmonic_feature_key(chord)
                feat_key_m = f"{feat_key}|m:{float(bpb0):g}|tb:{tempo_bucket}|keypc:{keypc}|mode:{mode}"
                key = (str(feat_key_m), str(role), int(bar_in_phrase))
                if current_key is None:
                    current_key = key
                if key != current_key:
                    if len(seg) >= 2:
                        rh_buckets.setdefault(current_key, []).append(list(seg))
                        rh_weights.setdefault(current_key, []).append(w)
                    seg = []
                    current_key = key
                try:
                    dg = int(deg) if isinstance(deg, int) else -1
                except Exception:
                    dg = -1
                rtok = feat.rhythm_token_for_event(dg, float(dur), signed_rr)
                seg.append(rtok)
                beat += abs(float(dur))
                # Coarse fallback: segment by function bucket too.
                try:
                    key2 = (f"{str(func)}|m:{float(bpb0):g}|tb:{tempo_bucket}|keypc:{keypc}|mode:{mode}", str(role), int(bar_in_phrase))
                    if key2 != key:
                        # Just add single-duration samples to the coarse model; it will still learn
                        # general tendencies per role/position without over-fragmenting segments.
                        rh_buckets.setdefault(key2, []).append([float(rtok)])
                        rh_weights.setdefault(key2, []).append(float(w))
                except Exception:
                    pass
            if current_key is not None and len(seg) >= 2:
                rh_buckets.setdefault(current_key, []).append(list(seg))
                rh_weights.setdefault(current_key, []).append(w)

        for key, seqs in rh_buckets.items():
            gen.markov.train_function_conditioned_rhythm_from_sequences(
                key, seqs, sequence_weights=rh_weights.get(key)
            )
