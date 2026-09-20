# ai/markov/melody/note_generator/_interval.py
"""Interval sampling and cadence helpers for NoteGenerator."""
import logging
from typing import Any, Dict, List, Optional, Tuple

from data.emotion_anchors import anchors_for_emotion
from data.emotion_melody_priors import emotion_melody_prior_for
from data.melody_phrase_profiles import melody_phrase_profile_for_emotion
from midi.midi_range_limiter import RANGE_LIMITER

from ..biasing import EMOTION_INTERVAL_BIAS, get_interval_bias
from ._interval_helpers import canon_chord_symbol_for_interval
from ._interval_role_blend import blend_interval_probs_with_phrase_role

logger = logging.getLogger(__name__)


def _renormalize_probs(probs: Dict[int, float]) -> Dict[int, float]:
    total = sum(float(v) for v in probs.values())
    if total > 0:
        return {k: float(v) / total for k, v in probs.items()}
    return probs


def _apply_emotion_motion_repair(
    probs: Dict[int, float],
    *,
    current_degree: int,
    melody: List[Tuple[int, float]],
    emotion: Any,
    pos: float,
) -> Dict[int, float]:
    """Reduce static repeated notes and reinforce the emotion's contour intent."""

    if not probs or emotion is None:
        return probs
    try:
        emotion_name = str(getattr(emotion, "name", "") or "")
        prior = emotion_melody_prior_for(emotion_name)
    except Exception:
        return probs

    voiced = [int(d) for d, _dur in list(melody or []) if int(d) >= 0]
    recent = voiced[-6:]
    if not recent:
        return probs

    updated = dict(probs)
    repeat_streak = 0
    for degree in reversed(recent):
        if int(degree) == int(current_degree):
            repeat_streak += 1
        else:
            break
    recent_intervals = [recent[i + 1] - recent[i] for i in range(len(recent) - 1)]
    recent_repeat_rate = (
        sum(1 for iv in recent_intervals if int(iv) == 0) / float(len(recent_intervals))
        if recent_intervals
        else 0.0
    )

    # v012_emotion_calibration: some emotions still repeat too much even when
    # static runs are under control. Apply a slightly stronger "get off the note"
    # pressure for those known repeat-prone buckets.
    repeat_prone = {
        "anger",
        "annoyance",
        "confusion",
        "joy",
        "nervousness",
        "fear",
    }
    repeat_prone_boost = 1.0
    try:
        en = str(emotion_name).strip().lower()
        if en in repeat_prone:
            repeat_prone_boost = 1.22
        # v012b: annoyance/confusion are still the worst repeat offenders.
        # Give them extra pressure, but only when the recent line is actually repeating.
        if en in {"annoyance", "confusion"} and (recent_repeat_rate >= 0.25 or repeat_streak >= 2):
            repeat_prone_boost = 1.45
    except Exception:
        repeat_prone_boost = 1.0
    same_note_pressure = 0.0
    if repeat_streak >= 1:
        same_note_pressure += min(0.70, 0.22 * float(repeat_streak))
    if recent_repeat_rate > 0.20:
        same_note_pressure += min(0.45, float(recent_repeat_rate) * 0.55)
    same_note_pressure *= max(0.35, 1.35 - float(prior.repeat_mult))
    same_note_pressure *= float(repeat_prone_boost)
    same_note_pressure = max(0.0, min(0.92, same_note_pressure))
    if 0 in updated and same_note_pressure > 1e-9:
        updated[0] *= max(0.03, 1.0 - same_note_pressure)

    direction_bias = float(prior.ascending_mult) - float(prior.descending_mult)
    direction_strength = min(0.65, abs(direction_bias) * 0.85)

    # v012_emotion_calibration: rising emotions (pride/amusement/optimism) need a
    # clearer upward identity. Add a small extra upward push during the phrase body
    # without overriding cadence behavior.
    rising_identity = {"pride", "amusement", "optimism"}
    try:
        if str(emotion_name).strip().lower() in rising_identity:
            direction_bias = abs(float(direction_bias)) + 0.18
            direction_strength = min(0.78, max(float(direction_strength), 0.22))
    except Exception:
        pass

    if direction_strength > 0.03:
        desired_sign = 1 if direction_bias > 0.0 else -1
        # Strongest in the body of the phrase. Cadence logic can still take over later.
        try:
            mid_weight = 1.0 - min(1.0, max(0.0, abs(float(pos) - 0.55) / 0.55))
        except Exception:
            mid_weight = 0.75
        direction_strength *= 0.45 + 0.55 * float(mid_weight)
        for interval in list(updated.keys()):
            iv = int(interval)
            if iv == 0:
                continue
            if (iv > 0) == (desired_sign > 0):
                updated[interval] *= 1.0 + direction_strength
            else:
                updated[interval] *= max(0.12, 1.0 - direction_strength * 0.72)

    # If the recent line is almost static, make step-outs more likely than big jumps.
    if recent_repeat_rate >= 0.45 or repeat_streak >= 2:
        desired_sign = 0
        if abs(direction_bias) > 0.03:
            desired_sign = 1 if direction_bias > 0.0 else -1
        # v012b: extra "no-repeat" clamp for annoyance/confusion when they're stuck.
        try:
            en = str(emotion_name).strip().lower()
            extra_no_repeat = en in {"annoyance", "confusion"} and (repeat_streak >= 3 or recent_repeat_rate >= 0.55)
        except Exception:
            extra_no_repeat = False
        for interval in list(updated.keys()):
            iv = int(interval)
            a = abs(iv)
            if a == 0:
                base = 0.004 if repeat_streak >= 3 else (0.01 if repeat_streak >= 2 else 0.08)
                updated[interval] *= 0.001 if extra_no_repeat else base
            if a == 1:
                boost = 3.40 if repeat_streak >= 3 else (2.40 if repeat_streak >= 2 else 1.55)
                if desired_sign and (iv > 0) == (desired_sign > 0):
                    boost *= 1.55
                elif desired_sign:
                    boost *= 0.72
                updated[interval] *= boost
            elif a == 2:
                boost = 1.65 if repeat_streak >= 3 else 1.12
                if desired_sign and (iv > 0) == (desired_sign > 0):
                    boost *= 1.22
                updated[interval] *= boost
            elif a >= 4:
                updated[interval] *= 0.62

    return _renormalize_probs(updated)


class NoteGeneratorIntervalMixin:
    def _select_interval(self,
                         interval_context: List[int],
                         current_degree: int,
                         melody: List[Tuple[int, float]],
                         current_beat: float,
                         plan,
                         emotion,
                         bar: int,
                         pos: float,
                         chords: Optional[List[str]],
                         roots: Optional[List[int]],
                         chord_weights_per_bar: Optional[List[Dict[int, float]]],
                         bass_notes: Optional[List[int]],
                         beats_per_bar: float,
                         total_beats: int,
                         target_melody_notes: Optional[List[int]],
                         temperature: float,
                         rep_tracker: Optional[Any] = None,
                         *,
                         planned_duration_beats: Optional[float] = None,
                         occupied_step_weights: Optional[Dict[int, float]] = None,
                         occupied_step_pcs: Optional[Dict[int, set[int]]] = None,
                         mask_strength: float = 0.0,
                         grid: float = 0.25,
                         phrase_total_notes: Optional[int] = None,
                         bar_intent: Optional[Dict[str, Any]] = None,
                         voiced_chords_per_bar: Optional[List[List[int]]] = None,
                         return_probs: bool = False):
        # ── Base probabilities ─────────────────────────────────────────────
        chord_conditioned_active = getattr(self.markov, 'use_chord_conditioned', False)
        intent = getattr(plan, "intent", None) if plan is not None else None
        contour = None
        try:
            contour = str(getattr(intent, "contour", "") or "") if intent is not None else ""
        except Exception:
            contour = ""
        if chord_conditioned_active and chords and bar < len(chords):
            chord_quality = self.markov.extract_chord_quality(chords[bar])
            interval_probs = self.markov.get_chord_conditioned_interval_probs(
                chord_quality, interval_context, temperature)
        elif hasattr(self.markov, 'get_interval_probs_for_contour') and (contour or (plan and getattr(plan, "contour", None))):
            c = contour or str(getattr(plan, "contour", "") or "")
            interval_probs = self.markov.get_interval_probs_for_contour(
                c, interval_context, temperature)
        else:
            interval_probs = self.markov.get_interval_probs(interval_context, temperature)

        # Optional: blend in phrase-role interval model (trained on segmented data).
        try:
            from audiogen_core.config import CONFIG

            blend = float(getattr(CONFIG.composition, "melody_phrase_role_model_blend", 0.35))
            role_enabled = bool(getattr(CONFIG.composition, "melody_role_conditioning_enabled", True))
        except Exception:
            blend = 0.35
            role_enabled = True
        interval_probs = blend_interval_probs_with_phrase_role(
            self.markov,
            plan,
            intent,
            interval_probs,
            interval_context,
            temperature,
            blend=float(blend),
            role_enabled=bool(role_enabled),
        )

        # Register-band conditioned blend (low/mid/high).
        try:
            from audiogen_core.config import CONFIG
            from composition.scoring_utils import blend_probs as _blend_rb

            rb_on = bool(getattr(CONFIG.composition, "melody_register_band_conditioning_enabled", True))
            rb_blend = float(getattr(CONFIG.composition, "melody_register_band_condition_blend", 0.22) or 0.22)
            low_max = int(getattr(CONFIG.composition, "melody_register_band_low_max_midi", 59) or 59)
            high_min = int(getattr(CONFIG.composition, "melody_register_band_high_min_midi", 73) or 73)
        except Exception:
            rb_on = True
            rb_blend = 0.22
            low_max = 59
            high_min = 73
            _blend_rb = None
        if (
            rb_on
            and rb_blend > 1e-6
            and _blend_rb is not None
            and hasattr(self.markov, "get_interval_probs_for_register_bin")
            and emotion is not None
            and getattr(emotion, "scale_intervals", None)
        ):
            try:
                # Prefer bar root if provided, else fallback to first root.
                root0 = None
                if roots and 0 <= int(bar) < len(roots):
                    root0 = int(roots[int(bar)])
                elif roots:
                    root0 = int(roots[0])
                if root0 is not None:
                    scale_iv = list(getattr(emotion, "scale_intervals", []) or [])
                    tonic = int(root0) - int(scale_iv[0] if scale_iv else 0)
                    while tonic < 48:
                        tonic += 12
                    while tonic > 72:
                        tonic -= 12
                    midi = int(tonic) + int(scale_iv[int(current_degree) % len(scale_iv)])
                    rbin = "low" if midi <= int(low_max) else ("high" if midi >= int(high_min) else "mid")
                else:
                    rbin = "mid"
            except Exception:
                rbin = "mid"
            try:
                rp = self.markov.get_interval_probs_for_register_bin(str(rbin), interval_context, temperature)
            except Exception:
                rp = {}
            if rp:
                interval_probs = _blend_rb(interval_probs, rp, float(rb_blend))

        # Beat-strength conditioned blend (downbeat vs offbeat).
        try:
            from audiogen_core.config import CONFIG
            from composition.scoring_utils import blend_probs as _blend_bb

            bb_on = bool(getattr(CONFIG.composition, "melody_beat_strength_conditioning_enabled", True))
            bb_blend = float(getattr(CONFIG.composition, "melody_beat_strength_condition_blend", 0.22) or 0.22)
        except Exception:
            bb_on = True
            bb_blend = 0.22
            _blend_bb = None
        if bb_on and bb_blend > 1e-6 and _blend_bb is not None and hasattr(self.markov, "get_interval_probs_for_beat_bin"):
            try:
                beat_in_bar = float(current_beat) % float(beats_per_bar)
            except Exception:
                beat_in_bar = 0.0
            beat_bin = "downbeat" if abs(float(beat_in_bar) - 0.0) < 1e-6 else "offbeat"
            try:
                bp = self.markov.get_interval_probs_for_beat_bin(beat_bin, interval_context, temperature)
            except Exception:
                bp = {}
            if bp:
                interval_probs = _blend_bb(interval_probs, bp, float(bb_blend))

        # Optional global Markov blend (emotion ↔ global), applied to the base distribution
        # before musical-intent multipliers.
        try:
            from audiogen_core.config import CONFIG
            from composition.scoring_utils import blend_probs

            g_alpha = float(getattr(CONFIG.composition, "melody_global_markov_blend", 0.0))
        except Exception:
            g_alpha = 0.0
            blend_probs = None
        if g_alpha > 1e-6 and blend_probs is not None:
            gp = {}
            try:
                gp = self.markov.get_global_interval_probs(interval_context, temperature)
            except Exception:
                gp = {}
            if gp:
                interval_probs = blend_probs(interval_probs, gp, float(g_alpha))

        # Optional: function + position chord-conditioning blend.
        try:
            from audiogen_core.config import CONFIG
            from composition.scoring_utils import blend_probs

            f_alpha = float(getattr(CONFIG.composition, "melody_function_condition_blend", 0.0))
            h_on = bool(getattr(CONFIG.composition, "melody_function_context_hierarchy_enabled", True))
            h_alpha = float(getattr(CONFIG.composition, "melody_function_context_hierarchy_strength", 0.45) or 0.45)
        except Exception:
            f_alpha = 0.0
            h_on = True
            h_alpha = 0.45
            blend_probs = None
        if f_alpha > 1e-6 and blend_probs is not None and chords and bar < len(chords):
            try:
                ch0 = canon_chord_symbol_for_interval(chords[bar])
                func = self.markov.extract_harmonic_function(ch0)
                feat = self.markov.extract_harmonic_feature_key(ch0)
            except Exception:
                func = "other"
                feat = "other"
            try:
                role = str(getattr(intent, "phrase_role", "") or "") if intent is not None else str(getattr(plan, "phrase_role", "") or "")
            except Exception:
                role = ""
            bar_in_phrase = int(bar % 4)
            key = (str(feat), str(role or "continuation"), int(bar_in_phrase))
            key_h = key
            if h_on and plan is not None:
                try:
                    sec_role = str(getattr(plan, "section_role", "") or "").strip().lower() or "none"
                except Exception:
                    sec_role = "none"
                try:
                    cad_deg = int(getattr(plan, "cadence_degree", 0) or 0)
                except Exception:
                    cad_deg = 0
                try:
                    pos = float(getattr(plan, "position", 0.0) or 0.0)
                except Exception:
                    pos = 0.0
                cad_band = "cad_hi" if pos >= float(getattr(plan, "cadence_zone_start", 0.75) or 0.75) else "cad_lo"
                # Extend hierarchy key with meter + tempo bucket when available.
                try:
                    bpb0 = max(0.25, float(beats_per_bar))
                except Exception:
                    bpb0 = 4.0
                try:
                    from audiogen_core.config import CONFIG

                    bpm0 = float(getattr(getattr(CONFIG, "audio", None), "global_tempo", 0.0) or 0.0)
                except Exception:
                    bpm0 = 0.0
                if bpm0 > 1e-9:
                    if bpm0 < 78.0:
                        tb = "slow"
                    elif bpm0 < 118.0:
                        tb = "mid"
                    else:
                        tb = "fast"
                else:
                    tb = "unk"
                # Key/mode tags (coarse):
                # - keypc: tonic pitch class from current bar root (if available)
                # - mode: maj/min/other/unk from emotion.scale_intervals
                try:
                    keypc = "unk"
                    if roots and 0 <= int(bar) < len(roots):
                        keypc = str(int(roots[int(bar)]) % 12)
                    elif roots:
                        keypc = str(int(roots[0]) % 12)
                except Exception:
                    keypc = "unk"
                try:
                    mode = "unk"
                    if emotion is not None and getattr(emotion, "scale_intervals", None):
                        pcs = sorted(set(int(x) % 12 for x in list(getattr(emotion, "scale_intervals", []) or [])))
                        if pcs == [0, 2, 4, 5, 7, 9, 11]:
                            mode = "maj"
                        elif pcs == [0, 2, 3, 5, 7, 8, 10]:
                            mode = "min"
                        else:
                            mode = "other"
                except Exception:
                    mode = "unk"
                feat_h = f"{feat}|sec_role:{sec_role}|cad:{int(cad_deg)%7}|{cad_band}|m:{float(bpb0):g}|tb:{tb}|keypc:{keypc}|mode:{mode}"
                key_h = (str(feat_h), str(role or "continuation"), int(bar_in_phrase))
            try:
                fp = self.markov.get_interval_probs_for_function_key(key_h, interval_context, temperature)
            except Exception:
                fp = {}
            if fp and h_on and key_h != key:
                try:
                    f_base = self.markov.get_interval_probs_for_function_key(key, interval_context, temperature)
                except Exception:
                    f_base = {}
                if f_base:
                    try:
                        fp = blend_probs(f_base, fp, float(max(0.0, min(1.0, h_alpha))))
                    except Exception:
                        pass
            if not fp:
                # Backoff to coarse function bucket if detailed feature key is sparse.
                try:
                    fp = self.markov.get_interval_probs_for_function_key(
                        (str(func), str(role or "continuation"), int(bar_in_phrase)),
                        interval_context,
                        temperature,
                    )
                except Exception:
                    fp = {}
            if fp:
                interval_probs = blend_probs(interval_probs, fp, float(f_alpha))

        # Phase 2c: phrase-gesture interval blend (opening / middle / cadence).
        try:
            from audiogen_core.config import CONFIG
            from composition.scoring_utils import blend_probs as _blend_g

            g_on = bool(getattr(CONFIG.composition, "melody_gesture_interval_markov_enabled", False))
            g_blend = float(getattr(CONFIG.composition, "melody_gesture_interval_markov_blend", 0.28) or 0.28)
        except Exception:
            g_on = False
            g_blend = 0.28
        if g_on and g_blend > 1e-6 and interval_probs and hasattr(self.markov, "get_interval_probs_for_gesture"):
            gpos = float(pos)
            try:
                ptn = phrase_total_notes
                if ptn is not None and int(ptn) >= 2:
                    vcnt = sum(1 for d, _ in melody if isinstance(d, int) and int(d) >= 0)
                    gpos = float(max(0, int(vcnt) - 1)) / float(max(1, int(ptn) - 1))
                    gpos = max(0.0, min(1.0, gpos))
            except Exception:
                gpos = float(pos)
            try:
                gp = self.markov.get_interval_probs_for_gesture(gpos, interval_context, temperature)
            except Exception:
                gp = {}
            if gp:
                try:
                    interval_probs = _blend_g(interval_probs, gp, float(g_blend))
                except Exception:
                    pass

        # Phase 2a: blend trained P(next_interval | preceding note duration bucket).
        try:
            from audiogen_core.config import CONFIG
            from composition.scoring_utils import blend_probs as _blend_pd

            pd_on = bool(getattr(CONFIG.composition, "melody_interval_prev_duration_markov_enabled", False))
            pd_blend = float(getattr(CONFIG.composition, "melody_interval_prev_duration_markov_blend", 0.35) or 0.35)
        except Exception:
            pd_on = False
            pd_blend = 0.35
        if pd_on and pd_blend > 1e-6 and melody and interval_probs:
            pd = self._last_voiced_note_duration(melody)
            if pd is not None and float(pd) > 1e-12:
                try:
                    bp = self.markov.get_interval_probs_for_prev_duration_bucket(
                        float(pd), interval_context, temperature)
                except Exception:
                    bp = {}
                if bp:
                    interval_probs = _blend_pd(interval_probs, bp, float(pd_blend))

        # Phase 2d: optional linear logit residual (trained weights; numpy).
        try:
            from audiogen_core.config import CONFIG

            nr_on = bool(getattr(CONFIG.composition, "melody_neural_logit_residual_enabled", False))
            nr_st = float(getattr(CONFIG.composition, "melody_neural_logit_residual_strength", 0.35) or 0.35)
            nr_path = str(getattr(CONFIG.composition, "melody_neural_logit_residual_path", "") or "")
            nr_order = int(getattr(CONFIG.composition, "melody_neural_logit_residual_order", 6) or 6)
        except Exception:
            nr_on = False
            nr_st = 0.35
            nr_path = ""
            nr_order = 6
        if nr_on and nr_st > 1e-9 and nr_path.strip() and interval_probs:
            try:
                from ai.markov.melody.logit_residual import apply_interval_logit_residual

                gpos_nr = float(pos)
                try:
                    ptn = phrase_total_notes
                    if ptn is not None and int(ptn) >= 2:
                        vcnt = sum(1 for d, _ in melody if isinstance(d, int) and int(d) >= 0)
                        gpos_nr = float(max(0, int(vcnt) - 1)) / float(max(1, int(ptn) - 1))
                        gpos_nr = max(0.0, min(1.0, gpos_nr))
                except Exception:
                    gpos_nr = float(pos)
                tail = list(interval_context or [])
                while len(tail) < int(nr_order):
                    tail.insert(0, 0)
                tail = tail[-int(nr_order) :]
                ename = ""
                try:
                    ename = str(getattr(emotion, "name", "") or "") if emotion is not None else ""
                except Exception:
                    ename = ""
                try:
                    nr_section_role = str(getattr(plan, "section_role", "") or "") if plan is not None else ""
                except Exception:
                    nr_section_role = ""
                try:
                    nr_phrase_role = str(getattr(intent, "phrase_role", "") or "") if intent is not None else str(getattr(plan, "phrase_role", "") or "")
                except Exception:
                    nr_phrase_role = ""
                try:
                    nr_contour = str(getattr(intent, "contour", "") or "") if intent is not None else str(getattr(plan, "contour", "") or "")
                except Exception:
                    nr_contour = ""
                try:
                    nr_chord = str(chords[bar] or "") if chords and 0 <= int(bar) < len(chords) else ""
                except Exception:
                    nr_chord = ""
                try:
                    nr_prev_dur = self._last_voiced_note_duration(melody)
                except Exception:
                    nr_prev_dur = None
                interval_probs = apply_interval_logit_residual(
                    interval_probs,
                    interval_context_tail=tail,
                    phrase_pos=float(gpos_nr),
                    emotion_name=ename,
                    strength=float(nr_st),
                    weight_path=nr_path.strip(),
                    order=int(nr_order),
                    section_role=nr_section_role,
                    phrase_role=nr_phrase_role,
                    contour=nr_contour,
                    chord_symbol=nr_chord,
                    prev_duration=nr_prev_dur,
                )
            except Exception:
                pass

        if not interval_probs:
            return 0

        mults: Dict[int, float] = {k: 1.0 for k in interval_probs}

        # Repetition penalty
        last_degrees = [d for d, _ in melody[-self.max_repetitions:]]
        if (len(last_degrees) >= self.max_repetitions
                and all(d == last_degrees[0] for d in last_degrees)
                and 0 in mults):
            mults[0] *= self.repeat_penalty

        # --------------------------------------------------------------
        # Markov upgrade: duration → interval coupling (flagged)
        # Short last note → stepwise; long held note → slightly wider motion.
        # --------------------------------------------------------------
        try:
            from audiogen_core.config import CONFIG

            idc_on = bool(getattr(CONFIG.composition, "melody_interval_duration_coupling_enabled", False))
            idc_strength = float(getattr(CONFIG.composition, "melody_interval_duration_coupling_strength", 0.65) or 0.65)
        except Exception:
            idc_on = False
            idc_strength = 0.65
        idc_strength = max(0.0, min(1.0, float(idc_strength)))
        if idc_on and idc_strength > 1e-9 and melody:
            try:
                last_dur = float(melody[-1][1])
            except Exception:
                last_dur = -1.0
            if last_dur > 1e-12:
                s = idc_strength
                if last_dur <= 0.5 + 1e-9:
                    for interval in mults:
                        a = abs(int(interval))
                        if a <= 1:
                            mults[interval] *= 1.0 + 0.55 * s
                        elif a >= 4:
                            mults[interval] *= max(0.05, 1.0 - 0.40 * s)
                elif last_dur >= 2.0 - 1e-9:
                    for interval in mults:
                        a = abs(int(interval))
                        if a >= 2:
                            mults[interval] *= 1.0 + 0.50 * s
                        elif a == 0:
                            mults[interval] *= max(0.05, 1.0 - 0.20 * s)

        # Tension: blend section-scale and phrase-scale motion.
        global_tension = self._compute_tension(current_beat, total_beats, emotion)
        local_tension = self._compute_phrase_tension(pos, plan, emotion)
        current_chord = chords[bar] if chords and bar < len(chords) else ""
        harmonic_tension = self._compute_harmonic_tension(current_chord, pos, plan=plan)
        tension = float(min(1.0, (global_tension * 0.35 + local_tension * 0.65) * harmonic_tension))
        for interval in mults:
            if abs(interval) <= 1:
                mults[interval] *= (1.0 - tension * 0.5)
            else:
                mults[interval] *= (1.0 + tension * 0.5)

        # Emotion stepwise bias
        emotion_prior = None
        if emotion is not None:
            name = str(getattr(emotion, "name", "") or "").lower()
            emotion_prior = emotion_melody_prior_for(name)
            if 'sad' in name or 'grief' in name:
                stepwise_boost = self.stepwise_boost_base * 1.5
                leap_penalty = 0.2 / self.emotion_intensity
            elif 'joy' in name or 'excitement' in name:
                stepwise_boost = self.stepwise_boost_base * 0.8
                leap_penalty = 0.5 / self.emotion_intensity
            else:
                stepwise_boost = self.stepwise_boost_base
                leap_penalty = 0.3
        else:
            stepwise_boost = self.stepwise_boost_base
            leap_penalty = 0.3

        # Style profile bias (deterministic, config-gated). This is applied as a soft
        # reweighting on top of existing emotion/tension logic.
        from audiogen_core.composition_runtime_flags import markov_style_strength

        s = markov_style_strength()
        if s > 1e-6 and emotion is not None:
            try:
                from composition.markov_style_profiles import style_profile_for_emotion_and_role

                sec_role = ""
                try:
                    sec_role = str(getattr(getattr(plan, "intent", None), "section_role", "") or "") if plan is not None else ""
                except Exception:
                    sec_role = ""
                prof = style_profile_for_emotion_and_role(str(getattr(emotion, "name", "") or ""), sec_role)
                allow = float(getattr(prof, "leap_allowance", 0.5) or 0.5)
                allow = max(0.0, min(1.0, float(allow)))
                # Lower allowance => more stepwise emphasis and stronger leap penalty.
                step_target = 0.85 + 1.10 * (1.0 - float(allow))  # 0.85..1.95
                leap_target = 0.85 + 0.90 * float(allow)          # 0.85..1.75
                stepwise_boost *= (1.0 + (float(step_target) - 1.0) * float(s))
                leap_penalty *= (1.0 + (float(leap_target) - 1.0) * float(s))
                # Export for downstream debug trace (best-effort).
                try:
                    setattr(self, "_debug_style_profile_id", str(getattr(prof, "profile_id", "")))
                    setattr(self, "_debug_style_leap_allowance", float(allow))
                except Exception:
                    pass
            except Exception:
                pass
        stepwise_boost *= (1.0 - tension * 0.5)
        for interval in mults:
            mults[interval] *= stepwise_boost if abs(interval) <= 1 else leap_penalty
        if emotion_prior is not None:
            for interval in mults:
                try:
                    iv = int(interval)
                except Exception:
                    iv = 0
                a = abs(iv)
                if iv == 0:
                    mults[interval] *= emotion_prior.repeat_mult
                elif a <= 1:
                    mults[interval] *= emotion_prior.interval_step_mult
                elif a <= 3:
                    mults[interval] *= emotion_prior.interval_small_leap_mult
                else:
                    mults[interval] *= emotion_prior.interval_large_leap_mult
                if iv > 0:
                    mults[interval] *= emotion_prior.ascending_mult
                elif iv < 0:
                    mults[interval] *= emotion_prior.descending_mult

        # Emotion interval bias
        if emotion is not None:
            name = str(getattr(emotion, "name", "") or "").lower()
            if name in EMOTION_INTERVAL_BIAS:
                bias = EMOTION_INTERVAL_BIAS[name]
                for interval in mults:
                    mults[interval] *= bias.get(interval, 1.0) ** (3 * self.emotion_intensity)
            leap_bias = float(melody_phrase_profile_for_emotion(name).get("leap_bias", 1.0))
            if abs(leap_bias - 1.0) > 1e-6:
                for interval in mults:
                    if abs(interval) >= 2:
                        mults[interval] *= leap_bias
                    elif abs(interval) <= 1:
                        mults[interval] *= max(0.75, 2.0 - leap_bias)

        # Leap recovery active bias (2026-07-02, docs/AUDIOGEN_COMPOSITION_PLAN.md item 14).
        # ai/markov/melody/beauty.py's score_lyrical_melody() already measures whether a
        # leap (wrapped scale-degree distance >= 3) is followed by a step (<= 1) and uses
        # that to rerank whole finished candidate phrases — a post-hoc, whole-phrase nudge.
        # This applies the same preference live, at the note that immediately follows a
        # leap, using the identical wrapped-distance definition beauty.py uses, so the
        # classic "leap then step back" shape is more consistent rather than only emergent
        # from reranking.
        try:
            from audiogen_core.config import CONFIG

            recovery_strength = float(getattr(CONFIG.composition, "melody_leap_recovery_bias_strength", 0.0) or 0.0)
        except Exception:
            recovery_strength = 0.0
        if recovery_strength > 1e-6:
            voiced_recent = []
            for d, _ in reversed(melody):
                try:
                    di = int(d)
                except Exception:
                    continue
                if di >= 0:
                    voiced_recent.append(di % 7)
                    if len(voiced_recent) >= 2:
                        break
            if len(voiced_recent) >= 2:
                wrapped = abs(voiced_recent[0] - voiced_recent[1]) % 7
                wrapped = min(wrapped, 7 - wrapped)
                if wrapped >= 3:
                    strength = max(0.0, min(1.0, recovery_strength))
                    for interval in mults:
                        if abs(interval) <= 1:
                            mults[interval] *= (1.0 + 0.6 * strength)
                        elif abs(interval) >= 3:
                            mults[interval] *= max(0.3, 1.0 - 0.5 * strength)

        # Dynamic n-gram repetition penalty (RT-cheap).
        if rep_tracker is not None:
            try:
                for interval in list(mults.keys()):
                    mults[interval] *= float(
                        rep_tracker.penalty_for_next_interval(
                            current_degree=int(current_degree),
                            candidate_interval=int(interval),
                        )
                    )
            except Exception:
                pass

        # Chord tone bias
        safe_bar = bar < len(chord_weights_per_bar) if chord_weights_per_bar else False
        if chords and roots and bar < len(chords) and safe_bar and chord_weights_per_bar[bar]:
            chord_weights = chord_weights_per_bar[bar]
            beat_in_bar = float(current_beat % beats_per_bar)

            # Strong-beat anchoring:
            # - beat 1 (0.0): strongest chord-tone pull
            # - beat 3 (2.0): strong pull
            # - beats 2/4 (1.0, 3.0): medium pull
            # - offbeats: weak pull (allow passing/color tones)
            def _beat_strength(b: float) -> float:
                if abs(b - 0.0) < 1e-6:
                    return 1.0
                if abs(b - 2.0) < 1e-6:
                    return 0.85
                if abs(b - 1.0) < 1e-6 or abs(b - 3.0) < 1e-6:
                    return 0.55
                return 0.22

            strength = _beat_strength(beat_in_bar)
            # Use the dedicated "downbeat" multiplier only on the bar downbeat.
            if abs(beat_in_bar - 0.0) < 1e-6:
                mult_base = float(self.downbeat_chord_multiplier)
            else:
                mult_base = float(self.chord_tone_multiplier)
            # Scale by beat strength (offbeats stay permissive).
            mult_base *= (0.55 + 0.85 * strength)

            chord_tones = set(int(d) for d in chord_weights.keys())
            curr_is_chord_tone = int(current_degree % 7) in chord_tones if chord_tones else False
            is_offbeat = abs(beat_in_bar - round(beat_in_bar)) > 1e-6

            # On offbeats, reduce absolute chord-tone pull so stepwise passing tones can win.
            if is_offbeat and curr_is_chord_tone:
                mult_base *= 0.35

            for interval in mults:
                next_deg = (current_degree + interval) % 7
                if next_deg in chord_weights:
                    mults[interval] *= mult_base * chord_weights[next_deg]
                else:
                    # On strong beats, discourage landing on non-chord degrees.
                    if strength >= 0.8:
                        mults[interval] *= 0.28

                # Strong-beat chord-tone contract for longer notes:
                # If this onset is on a strong beat and the *planned duration* is long-ish,
                # strongly prefer chord tones (avoid "hanging" non-chord tones on long values).
                try:
                    from audiogen_core.config import CONFIG

                    ct_on = bool(getattr(CONFIG.composition, "melody_strongbeat_chordtone_contract_enabled", True))
                    ct_min_d = float(
                        getattr(CONFIG.composition, "melody_strongbeat_chordtone_contract_min_duration_beats", 0.75) or 0.75
                    )
                    ct_non_mult = float(
                        getattr(CONFIG.composition, "melody_strongbeat_chordtone_contract_nonchord_mult", 0.06) or 0.06
                    )
                except Exception:
                    ct_on = True
                    ct_min_d = 0.75
                    ct_non_mult = 0.06
                ct_non_mult = max(0.0, min(1.0, float(ct_non_mult)))
                if (
                    ct_on
                    and planned_duration_beats is not None
                    and strength >= 0.8
                    and float(planned_duration_beats) >= float(ct_min_d)
                    and chord_tones
                ):
                    if int(next_deg) not in chord_tones:
                        mults[interval] *= max(0.0, float(ct_non_mult))

                # Offbeat passing/neighbor tones:
                # If we're *on an offbeat* and currently on a chord tone, gently encourage
                # stepwise motion to a non-chord tone (passing/neighbor) *only if* it can
                # resolve by step to a chord tone on the next beat.
                if is_offbeat and curr_is_chord_tone:
                    if abs(int(interval)) <= 1:
                        if next_deg not in chord_tones and chord_tones:
                            # Can resolve if a chord tone is one step away from next_deg.
                            resolves = ((next_deg + 1) % 7 in chord_tones) or ((next_deg - 1) % 7 in chord_tones)
                            if resolves:
                                mults[interval] *= 2.4
                        else:
                            # Don't over-pin every offbeat to chord tones (avoids "blocky" feel).
                            if next_deg in chord_tones:
                                # Especially avoid repeating the same chord tone on subdivisions.
                                mults[interval] *= 0.08 if int(interval) == 0 else 0.45
                            else:
                                mults[interval] *= 0.35
                    else:
                        # Offbeat leaps to non-chord tones tend to sound random.
                        if next_deg not in chord_tones:
                            mults[interval] *= 0.72

        # Soft register preference: penalize leaving the channel's preferred register band.
        try:
            from audiogen_core.config import CONFIG

            reg_pref_on = bool(getattr(CONFIG.composition, "melody_register_preference_enabled", True))
            reg_pref_st = float(getattr(CONFIG.composition, "melody_register_preference_strength", 0.35) or 0.35)
        except Exception:
            reg_pref_on = True
            reg_pref_st = 0.35
        reg_pref_st = max(0.0, min(1.0, float(reg_pref_st)))
        if reg_pref_on and reg_pref_st > 1e-9 and emotion and roots and bar < len(roots) and getattr(plan, "output_channel", None) is not None:
            try:
                ch_out = int(getattr(plan, "output_channel", 2))
                root_m = int(roots[bar])
                scale = list(getattr(emotion, "scale_intervals", []) or [])
                if scale:
                    cfg = getattr(RANGE_LIMITER, "configs", {}).get(int(ch_out))
                else:
                    cfg = None
            except Exception:
                cfg = None
                scale = []
                ch_out = 2
                root_m = 60

            if cfg is not None and scale:
                pref_min = int(getattr(cfg, "preferred_min", getattr(cfg, "min_note", 0)))
                pref_max = int(getattr(cfg, "preferred_max", getattr(cfg, "max_note", 127)))
                hard_min = int(getattr(cfg, "min_note", pref_min))
                hard_max = int(getattr(cfg, "max_note", pref_max))
                pref_min, pref_max = min(pref_min, pref_max), max(pref_min, pref_max)
                hard_min, hard_max = min(hard_min, hard_max), max(hard_min, hard_max)

                def _range_mult(midi: int) -> float:
                    # 1.0 inside preferred band; fall off smoothly outside, harder near absolute extremes.
                    if pref_min <= int(midi) <= pref_max:
                        # mild penalty near absolute extremes even if in preferred
                        edge = min(int(midi) - hard_min, hard_max - int(midi))
                        if edge <= 2:
                            return float(max(0.55, 1.0 - 0.10 * float(3 - edge)))
                        return 1.0
                    # distance outside preferred band (in semitones)
                    if int(midi) < pref_min:
                        d = float(pref_min - int(midi))
                    else:
                        d = float(int(midi) - pref_max)
                    # Map: 1 semitone outside -> small penalty, 12 outside -> strong penalty.
                    x = min(1.0, d / 12.0)
                    return float(max(0.15, 1.0 - float(reg_pref_st) * (0.25 + 0.75 * x)))

                try:
                    updated = dict(mults)
                    for interval in list(updated.keys()):
                        nxt = (int(current_degree) + int(interval)) % 7
                        midi = int(self._degree_to_midi(int(nxt), int(root_m), list(scale)))
                        updated[interval] *= float(_range_mult(midi))
                    mults = updated
                except Exception:
                    pass

        # Composition per-bar intent shaping: use planned harmonic function target and cadence strength
        # to adjust motion in a "composed" way, even if the literal chord function differs.
        if bar_intent and mults:
            try:
                fn = str(bar_intent.get("harmony_function_target") or bar_intent.get("function") or "").strip().upper()
            except Exception:
                fn = ""
            try:
                cad = float(bar_intent.get("cadence_strength") or bar_intent.get("cadence_window") or 0.0)
            except Exception:
                cad = 0.0
            cad = max(0.0, min(1.35, float(cad)))
            if fn or cad > 1e-9:
                try:
                    from audiogen_core.config import CONFIG
                    st = float(getattr(CONFIG.composition, "melody_intent_interval_strength", 0.22) or 0.22)
                except Exception:
                    st = 0.22
                st = max(0.0, min(1.0, float(st)))
                if st > 1e-9:
                    # D bars: steer toward cadence target earlier + avoid big leaps late.
                    if fn == "D" or cad >= 0.75:
                        s = float(st) * (0.55 + 0.45 * min(1.0, float(cad)))
                        try:
                            cad_deg = int(getattr(plan, "cadence_degree", 0) or 0) % 7
                        except Exception:
                            cad_deg = 0
                        for interval in list(mults.keys()):
                            nxt = (int(current_degree) + int(interval)) % 7
                            d = abs(int(nxt) - int(cad_deg))
                            d = min(d, 7 - d)
                            if d == 0:
                                mults[interval] *= 1.0 + 0.55 * s
                            elif d == 1:
                                mults[interval] *= 1.0 + 0.22 * s
                            elif d >= 3:
                                mults[interval] *= max(0.12, 1.0 - 0.28 * s)
                            # Also slightly discourage large leaps on cadence-function bars.
                            if abs(int(interval)) >= 4:
                                mults[interval] *= max(0.15, 1.0 - 0.18 * s)
                    # PD bars: allow more motion (pre-dominant movement).
                    elif fn == "PD":
                        s = float(st) * 0.70
                        for interval in list(mults.keys()):
                            a = abs(int(interval))
                            if a == 0:
                                mults[interval] *= max(0.12, 1.0 - 0.22 * s)
                            elif a in {1, 2}:
                                mults[interval] *= 1.0 + 0.18 * s
                            elif a >= 4:
                                mults[interval] *= 1.0 + 0.08 * s
                    # T bars: prefer stability (stepwise / repeated) slightly.
                    elif fn == "T":
                        s = float(st) * 0.55
                        for interval in list(mults.keys()):
                            a = abs(int(interval))
                            if a == 0:
                                mults[interval] *= 1.0 + 0.28 * s
                            elif a == 1:
                                mults[interval] *= 1.0 + 0.10 * s
                            elif a >= 4:
                                mults[interval] *= max(0.18, 1.0 - 0.14 * s)

        # Voiced-chord pitch-class affinity (soft): prefer landing on PCs currently voiced in harmony.
        # This tightens audible glue when the arrangement is dense, without hard constraints.
        if voiced_chords_per_bar and emotion is not None and roots and 0 <= int(bar) < len(roots) and 0 <= int(bar) < len(voiced_chords_per_bar):
            try:
                pcs = {int(n) % 12 for n in (voiced_chords_per_bar[int(bar)] or []) if isinstance(n, int)}
            except Exception:
                pcs = set()
            if pcs:
                try:
                    from audiogen_core.config import CONFIG
                    pc_on = bool(getattr(CONFIG.composition, "melody_voiced_chord_pc_affinity_enabled", True))
                    pc_st = float(getattr(CONFIG.composition, "melody_voiced_chord_pc_affinity_strength", 0.18) or 0.18)
                except Exception:
                    pc_on = True
                    pc_st = 0.18
                pc_st = max(0.0, min(1.0, float(pc_st)))
                if pc_on and pc_st > 1e-9:
                    try:
                        root_m = int(roots[int(bar)])
                        scale = list(getattr(emotion, "scale_intervals", []) or [])
                    except Exception:
                        root_m = int(roots[int(bar)])
                        scale = []
                    if scale:
                        for interval in list(mults.keys()):
                            nxt = (int(current_degree) + int(interval)) % 7
                            midi = int(self._degree_to_midi(int(nxt), int(root_m), scale))
                            if (int(midi) % 12) in pcs:
                                mults[interval] *= 1.0 + 0.55 * float(pc_st)
                            else:
                                # Very mild penalty only on strong beats, to avoid over-pinning.
                                try:
                                    beat_in_bar = float(current_beat) % float(beats_per_bar)
                                except Exception:
                                    beat_in_bar = 0.0
                                strong = (abs(beat_in_bar - 0.0) < 1e-6) or (abs(beat_in_bar - 2.0) < 1e-6)
                                if strong:
                                    mults[interval] *= max(0.35, 1.0 - 0.18 * float(pc_st))

        # Pitch proximity bias
        if emotion and roots and bar < len(roots) and safe_bar and chord_weights_per_bar[bar]:
            current_root = roots[bar]
            scale = emotion.scale_intervals
            current_pitch = self._degree_to_midi(current_degree, current_root, scale)
            for interval in mults:
                next_deg = (current_degree + interval) % 7
                next_pitch = self._degree_to_midi(next_deg, current_root, scale)
                norm_dist = min(abs(next_pitch - current_pitch) / 24.0, 1.0)
                mults[interval] *= 1.0 + (1.0 - norm_dist) * 2.0

            # Runtime masking (pitch-aware): if another layer is active at this onset step,
            # discourage choosing a degree that lands on the same pitch class.
            if occupied_step_pcs and mask_strength > 1e-6:
                try:
                    step_i = int(round(float(current_beat) / float(grid)))
                    pcs = occupied_step_pcs.get(int(step_i))
                except Exception:
                    pcs = None
                    step_i = None
                if pcs:
                    try:
                        from audiogen_core.config import CONFIG

                        pc_avoid = float(getattr(CONFIG.composition, "masking_pc_avoid_strength", 0.55) or 0.55)
                    except Exception:
                        pc_avoid = 0.55
                    pc_avoid = max(0.0, min(1.0, float(pc_avoid)))
                    w = 1.0
                    if occupied_step_weights and step_i is not None and int(step_i) in occupied_step_weights:
                        try:
                            w = float(occupied_step_weights.get(int(step_i), 1.0) or 1.0)
                        except Exception:
                            w = 1.0
                    w = max(0.0, min(1.0, float(w)))
                    amt = float(mask_strength) * float(pc_avoid) * (0.55 + 0.45 * float(w))
                    amt = max(0.0, min(0.95, float(amt)))
                    pcs_set = {int(x) % 12 for x in set(pcs or set())}
                    if pcs_set and amt > 1e-9:
                        for interval in mults:
                            next_deg = (current_degree + interval) % 7
                            next_pitch = self._degree_to_midi(next_deg, current_root, scale)
                            if (int(next_pitch) % 12) in pcs_set:
                                mults[interval] *= max(0.08, 1.0 - float(amt))
                    # No renormalisation needed; final_probs below normalises.

            # ── Melody intent: register + hook anchor (soft, phrase-aware) ──
            try:
                from audiogen_core.config import CONFIG

                intent_on = bool(getattr(CONFIG.composition, "melody_intent_enabled", True))
                reg_strength = float(getattr(CONFIG.composition, "melody_intent_register_strength", 0.35))
                hook_strength = float(getattr(CONFIG.composition, "melody_hook_anchor_strength", 0.25))
            except Exception:
                intent_on, reg_strength, hook_strength = True, 0.35, 0.25

            if intent_on and intent is not None:
                # Register pull: prefer pitches nearer the intent lane center for this phrase.
                try:
                    center = getattr(intent, "register_center_midi", None)
                    hw = getattr(intent, "register_half_width_midi", None)
                    if center is not None and hw is not None and reg_strength > 1e-6:
                        center_i = int(center)
                        hw_i = max(4, min(24, int(hw)))
                        # Use a smooth penalty outside the lane; mild boost inside.
                        for interval in mults:
                            next_deg = (current_degree + interval) % 7
                            next_pitch = self._degree_to_midi(next_deg, current_root, scale)
                            d = abs(int(next_pitch) - int(center_i))
                            if d <= hw_i:
                                # inside lane: up to +reg_strength
                                mults[interval] *= 1.0 + float(reg_strength) * (1.0 - float(d) / float(hw_i))
                            else:
                                # outside lane: downweight gradually (never hard-zero)
                                over = float(d - hw_i) / float(max(1, hw_i))
                                mults[interval] *= max(0.15, 1.0 - float(reg_strength) * 0.75 * float(over))
                except Exception:
                    pass

                # Hook anchor pull: on strong beats early in the phrase, prefer returning to anchor.
                try:
                    anchor = getattr(intent, "hook_anchor_degree", None)
                    cz = float(getattr(intent, "cadence_zone_start", getattr(plan, "cadence_zone_start", 0.75)) or 0.75)
                    beat_in_bar = float(current_beat % beats_per_bar)
                    is_strong = (abs(beat_in_bar - 0.0) < 1e-6) or (abs(beat_in_bar - 2.0) < 1e-6)
                    if (
                        anchor is not None
                        and hook_strength > 1e-6
                        and float(pos) < float(cz) - 1e-6
                        and is_strong
                    ):
                        a = int(anchor) % 7
                        cur_d = min(abs(int(current_degree) - a), 7 - abs(int(current_degree) - a))
                        for interval in mults:
                            nxt = (int(current_degree) + int(interval)) % 7
                            nxt_d = min(abs(int(nxt) - a), 7 - abs(int(nxt) - a))
                            if nxt_d == 0:
                                mults[interval] *= 1.0 + float(hook_strength) * 2.0
                            elif nxt_d < cur_d:
                                mults[interval] *= 1.0 + float(hook_strength) * 0.65
                            elif nxt_d > cur_d and cur_d <= 2:
                                mults[interval] *= max(0.2, 1.0 - float(hook_strength) * 0.55)
                except Exception:
                    pass

        # Contour bias
        for interval, bias in get_interval_bias(plan.contour, pos).items():
            if interval in mults:
                mults[interval] *= bias

        # Plan bias (climax) — apply_plan_bias takes and mutates a probs-like
        # dict, so pass mults directly (it only multiplies values).
        self.planner.apply_plan_bias(mults, melody, plan, pos)

        # Voice leading penalty
        if bass_notes and melody:
            beat_idx = int(current_beat // 0.25)
            if beat_idx < len(bass_notes):
                for interval in mults:
                    if current_degree <= 1 and interval < 0:
                        mults[interval] *= 0.5
                    if current_degree >= 5 and interval > 0:
                        mults[interval] *= 0.7
                    if abs(interval) > 2:
                        mults[interval] *= 0.8

        # Target melody note bias
        if target_melody_notes is not None:
            bar_idx = int(current_beat // beats_per_bar)
            if bar_idx < len(target_melody_notes) and emotion and roots and bar < len(roots):
                target_midi = target_melody_notes[bar_idx]
                target_pc = target_midi % 12
                target_degree = None
                current_root = roots[bar]
                for d, ivl in enumerate(emotion.scale_intervals):
                    if (current_root + ivl) % 12 == target_pc:
                        target_degree = d
                        break
                if target_degree is not None:
                    for interval in mults:
                        next_deg = (current_degree + interval) % 7
                        cur_dist = min(abs(current_degree - target_degree),
                                       7 - abs(current_degree - target_degree))
                        nxt_dist = min(abs(next_deg - target_degree),
                                       7 - abs(next_deg - target_degree))
                        if nxt_dist < cur_dist:
                            mults[interval] *= 2.0
                        elif nxt_dist > cur_dist:
                            mults[interval] *= 0.5

        # ── Cadence zone bias ────────────────────────────────────────────────
        # In the final portion of the phrase, progressively steer the melody
        # toward the cadence target degree.  The bias ramps up quadratically so
        # it is gentle at the zone entry and decisive near the last note.
        # (The very last note is handled separately in generate_phrase via
        # _select_cadence_final_interval, which applies a near-forced override.)
        cadence_zone = getattr(plan, 'cadence_zone_start', 1.0)
        if pos >= cadence_zone:
            cadence_target = getattr(plan, 'cadence_degree', 0)
            cadence_weight = float(getattr(plan, 'cadence_weight', 3.0))
            # Macro cadence knobs: global (composition) + melody-specific multiplier.
            try:
                from audiogen_core.config import CONFIG

                cad = float(getattr(CONFIG.composition, "cadence_strength", 1.0))
                m_cad = float(getattr(CONFIG.composition, "melody_cadence_strength", 1.0))
                cad = max(0.0, min(2.0, cad))
                m_cad = max(0.0, min(2.0, m_cad))
                cadence_weight *= (cad * m_cad)
            except Exception:
                pass
            zone_width = max(1e-6, 1.0 - cadence_zone)
            # Quadratic ramp: slow at zone entry, accelerates toward phrase end
            cadence_ramp = ((pos - cadence_zone) / zone_width) ** 2

            # Emotion anchors: cadence archetype can change what we steer *toward*
            # inside the cadence zone (not just on the final note).
            try:
                cadence_style = str(getattr(anchors_for_emotion(emotion), "cadence", "authentic") or "authentic").lower()
            except Exception:
                cadence_style = "authentic"
            cadence_style = cadence_style if cadence_style in {"authentic", "plagal", "suspended", "avoid"} else "authentic"

            # Authentic cadence broadening (tonic triad):
            # When a phrase is resolving to tonic (degree 0), allow stable landings on
            # 1/3/5 (degrees 0/2/4) as secondary targets. This makes endings feel more
            # "composed" (tonic triad vocabulary) while still preferring true tonic.
            #
            # This applies only in the cadence zone and ramps with cadence_ramp, so
            # it won't flatten the phrase body into arpeggios.
            tonic_triad_targets: Optional[List[int]] = None
            try:
                is_final_phrase = bool(getattr(plan, "is_final_phrase", False))
            except Exception:
                is_final_phrase = False
            try:
                ct = int(cadence_target) % 7
            except Exception:
                ct = 0
            if cadence_style in {"authentic", "plagal"} and ct == 0:
                tonic_triad_targets = [0, 2, 4]
                # Slightly stronger in the final phrase so the close reads clearly.
                if is_final_phrase:
                    cadence_weight *= 1.10

            # Prefer a "hanging" target for suspended/avoid styles (when possible).
            if cadence_style in {"suspended", "avoid"}:
                chord_tones = set()
                try:
                    if chord_weights_per_bar and 0 <= int(bar) < len(chord_weights_per_bar):
                        chord_tones = set(int(d) % 7 for d in (chord_weights_per_bar[int(bar)] or {}).keys())
                except Exception:
                    chord_tones = set()

                # Anticipation: near the end of the bar, prefer suspending *into* the next chord.
                ref_bar = int(bar)
                try:
                    in_last_quarter = (float(current_beat) % float(beats_per_bar)) >= (float(beats_per_bar) * 0.75)
                except Exception:
                    in_last_quarter = False
                try:
                    if in_last_quarter and chords and (int(bar) + 1) < len(chords):
                        ref_bar = int(bar) + 1
                        if chord_weights_per_bar and ref_bar < len(chord_weights_per_bar):
                            chord_tones = set(int(d) % 7 for d in (chord_weights_per_bar[ref_bar] or {}).keys())
                except Exception:
                    ref_bar = int(bar)

                # Make the hanging target chord-aware (dominant bars suspend differently).
                try:
                    func = self.markov.extract_harmonic_function(
                        canon_chord_symbol_for_interval(chords[ref_bar] if chords and ref_bar < len(chords) else "")
                    )
                except Exception:
                    func = "other"
                is_dom = str(func or "").lower() == "dom"
                if cadence_style == "suspended":
                    # Dominant: prefer 4 (sus4-ish), else prefer 2.
                    prefs = ([3, 1] if is_dom else [1, 3])
                else:  # avoid
                    # Dominant: prefer 7 (leading tension), else prefer 2.
                    prefs = ([6, 1] if is_dom else [1, 6])
                alt = next((d for d in prefs if d not in chord_tones), None)
                if alt is None:
                    alt = prefs[0]
                cadence_target = int(alt) % 7
                # Reduce "hard landing" pressure; keep it directional, not forced.
                cadence_weight *= 0.75
            elif cadence_style == "plagal":
                # Softer cadence steering; still aims for cadence_degree but less aggressively.
                cadence_weight *= 0.92

            # Probe: record which cadence target we ended up steering toward.
            pass

            for interval in mults:
                next_deg = (current_degree + interval) % 7
                # Distance to primary cadence target.
                dist = min(abs(next_deg - cadence_target), 7 - abs(next_deg - cadence_target))
                # Distance to best tonic-triad target (if enabled).
                dist_triad = None
                if tonic_triad_targets:
                    try:
                        dists = [
                            min(abs(int(next_deg) - int(t)), 7 - abs(int(next_deg) - int(t)))
                            for t in list(tonic_triad_targets)
                        ]
                        dist_triad = min(int(d) for d in dists) if dists else None
                    except Exception:
                        dist_triad = None

                if dist == 0:
                    # Landing on primary target: progressive strong boost
                    mults[interval] *= 1.0 + cadence_ramp * cadence_weight
                elif dist_triad == 0:
                    # Landing on tonic triad tone: strong but secondary boost (keeps "1" preferred).
                    mults[interval] *= 1.0 + cadence_ramp * cadence_weight * 0.55
                elif dist == 1 or dist_triad == 1:
                    # One step away — classic approach tone: mild boost
                    mults[interval] *= 1.0 + cadence_ramp * cadence_weight * 0.3
                elif dist == 2 or dist_triad == 2:
                    # Neutral — no change
                    pass
                else:
                    # Moving further from cadence vocabulary: increasing penalty
                    mults[interval] *= max(0.05, 1.0 - cadence_ramp * 0.7)

        # ── Single normalisation ───────────────────────────────────────────
        final_probs = {k: v * mults.get(k, 1.0) for k, v in interval_probs.items()}
        total = sum(final_probs.values())
        if total > 0:
            final_probs = {k: v / total for k, v in final_probs.items()}
        else:
            final_probs = interval_probs

        # Anti-stuck: detect small melodic loops and penalize repeating them.
        try:
            from audiogen_core.config import CONFIG

            antistuck = bool(getattr(CONFIG.composition, "melody_antistuck_enabled", True))
            loop_mult = float(getattr(CONFIG.composition, "melody_loop_penalty_mult", 0.6))
        except Exception:
            antistuck = True
            loop_mult = 0.6
        if antistuck and melody and len(melody) >= 5 and loop_mult < 0.999:
            try:
                # Degree history for last 5 notes.
                degs = [int(d) for d, _ in melody[-5:] if isinstance(d, int)]
                if len(degs) == 5:
                    # Patterns:
                    # - ABAB? (two-note oscillation)
                    # - ABCAB? (three-note loop)
                    two_loop = (degs[0] == degs[2] == degs[4]) and (degs[1] == degs[3]) and (degs[0] != degs[1])
                    three_loop = (degs[0] == degs[3]) and (degs[1] == degs[4]) and (degs[0] != degs[1] != degs[2])
                    if two_loop or three_loop:
                        # Penalize intervals that keep the loop going (repeat or immediate backstep).
                        updated = dict(final_probs)
                        for interval in list(updated.keys()):
                            nxt = (int(current_degree) + int(interval)) % 7
                            if nxt in {degs[-1], degs[-2]}:
                                updated[interval] *= max(0.0, min(1.0, loop_mult))
                        tot = sum(updated.values())
                        if tot > 0:
                            final_probs = {k: v / tot for k, v in updated.items()}
            except Exception:
                pass

        # Emotion motion repair: the Markov model can still prefer repeated
        # degrees too strongly, especially with small datasets. This pass keeps
        # that learned distribution, but reduces another static note when the
        # recent phrase is already stuck and nudges direction toward the emotion
        # prior's contour intent.
        final_probs = _apply_emotion_motion_repair(
            final_probs,
            current_degree=int(current_degree),
            melody=melody,
            emotion=emotion,
            pos=float(pos),
        )

        # ── Hard register filter (avoid out-of-range notes before clamping) ──
        try:
            from audiogen_core.config import CONFIG

            reg_filter = bool(getattr(CONFIG.composition, "melody_register_filter_enabled", True))
        except Exception:
            reg_filter = True
        if reg_filter and emotion and roots and bar < len(roots) and getattr(plan, "output_channel", None) is not None:
            try:
                ch = int(getattr(plan, "output_channel", 2))
                root_m = int(roots[bar])
                scale = list(getattr(emotion, "scale_intervals", []) or [])
                if scale:
                    updated = dict(final_probs)
                    deg_mod = max(1, int(len(scale) or 0)) if scale else 7
                    for interval in list(updated.keys()):
                        nxt = (int(current_degree) + int(interval)) % int(deg_mod)
                        midi = int(self._degree_to_midi(int(nxt), root_m, scale))
                        clamped = int(RANGE_LIMITER.clamp_note(midi, ch))
                        if clamped != midi:
                            updated[interval] *= 0.0
                    tot = sum(updated.values())
                    if tot > 0:
                        final_probs = {k: v / tot for k, v in updated.items()}
            except Exception:
                pass

        # ── Bass motion coupling (context feature) ──────────────────────────
        # If we know the bass line at this beat, prefer contrary motion and
        # discourage large parallel motion on strong beats.
        try:
            from audiogen_core.config import CONFIG

            contrary_mult = float(getattr(CONFIG.composition, "melody_bass_contrary_bonus_mult", 1.0))
            parallel_mult = float(getattr(CONFIG.composition, "melody_bass_parallel_penalty_mult", 1.0))
        except Exception:
            contrary_mult = parallel_mult = 1.0
        if (
            bass_notes
            and abs(float(contrary_mult) - 1.0) > 1e-9 or abs(float(parallel_mult) - 1.0) > 1e-9
        ):
            try:
                beat_idx = int(float(current_beat) // 0.25)
                if 0 <= beat_idx < len(bass_notes):
                    b0 = int(bass_notes[max(0, beat_idx - 1)])
                    b1 = int(bass_notes[beat_idx])
                    d_b = b1 - b0
                    # Only act when bass is actually moving.
                    if d_b != 0:
                        strong = abs(float(current_beat) % float(beats_per_bar)) < 1e-6
                        updated = dict(final_probs)
                        for interval in list(updated.keys()):
                            d_m = int(interval)
                            if d_m == 0:
                                continue
                            same_dir = (d_m > 0) == (d_b > 0)
                            if strong and same_dir and abs(d_m) >= 2 and parallel_mult != 1.0:
                                updated[interval] *= max(0.0, float(parallel_mult))
                            elif (not same_dir) and abs(d_m) >= 1 and contrary_mult != 1.0:
                                updated[interval] *= max(0.0, float(contrary_mult))
                        tot = sum(updated.values())
                        if tot > 0:
                            final_probs = {k: v / tot for k, v in updated.items()}
            except Exception:
                pass

        # ── Arrangement-aware biases (section role + phrase role) ───────────
        # This is a light-touch layer on top of the learned distribution.
        # Defaults are neutral (multipliers = 1.0) unless configured.
        try:
            from audiogen_core.config import CONFIG

            chorus_step_mult = float(getattr(CONFIG.composition, "melody_role_chorus_stepwise_mult", 1.0))
            chorus_ct_mult = float(getattr(CONFIG.composition, "melody_role_chorus_chord_tone_mult", 1.0))
            verse_leap_mult = float(getattr(CONFIG.composition, "melody_role_verse_leap_mult", 1.0))
            outro_step_mult = float(getattr(CONFIG.composition, "melody_role_outro_stepwise_mult", 1.0))
        except Exception:
            chorus_step_mult = chorus_ct_mult = verse_leap_mult = outro_step_mult = 1.0

        sec_role = (getattr(plan, "section_role", "") or "").lower()
        phr_role = (getattr(plan, "phrase_role", "") or "").lower()
        if sec_role or phr_role:
            updated = dict(final_probs)
            chord_tones = set()
            safe_bar = bar < len(chord_weights_per_bar) if chord_weights_per_bar else False
            if safe_bar and chord_weights_per_bar and chord_weights_per_bar[bar]:
                chord_tones = set(int(d) for d in chord_weights_per_bar[bar].keys())

            is_chorusish = sec_role in {
                "b",
                "chorus",
                "hook",
                "pre_chorus",
                "tag",
                "a_prime",
            }
            is_verseish = sec_role in {"a", "intro"}
            is_outro = sec_role == "outro"

            # Joint-fit knob: on strong beats, prefer chord tones slightly.
            # Default is neutral (mult=1.0) unless enabled in config.
            try:
                from audiogen_core.config import CONFIG

                strong_ct_mult = float(getattr(CONFIG.composition, "melody_strongbeat_chord_tone_mult", 1.0) or 1.0)
            except Exception:
                strong_ct_mult = 1.0
            try:
                beat_in_bar = float(current_beat) % float(beats_per_bar)
            except Exception:
                beat_in_bar = 0.0
            strong_beat = (abs(float(beat_in_bar) - 0.0) < 1e-6) or (abs(float(beat_in_bar) - 2.0) < 1e-6)
            try:
                deg_mod = max(1, int(len(list(getattr(emotion, "scale_intervals", []) or [])) or 0)) if emotion else 7
            except Exception:
                deg_mod = 7

            for interval in list(updated.keys()):
                nxt = (int(current_degree) + int(interval)) % int(deg_mod)
                if is_chorusish and abs(int(interval)) <= 1:
                    updated[interval] *= chorus_step_mult
                if is_chorusish and chord_tones and nxt in chord_tones:
                    updated[interval] *= chorus_ct_mult
                if is_verseish and abs(int(interval)) >= 3:
                    updated[interval] *= verse_leap_mult
                if is_outro and abs(int(interval)) <= 1:
                    updated[interval] *= outro_step_mult
                if strong_beat and chord_tones and nxt in chord_tones and strong_ct_mult != 1.0:
                    updated[interval] *= max(0.0, float(strong_ct_mult))

            tot2 = sum(updated.values())
            if tot2 > 0:
                final_probs = {k: v / tot2 for k, v in updated.items()}
        
        # Emotion‑based interval boost: larger intervals for energetic emotions
        if emotion:
            name = emotion.name.lower()
            if name in ('joy', 'excitement', 'anger', 'surprise', 'pride', 'optimism', 'amusement'):
                # Keep the emotional "energy" (more leaps) but avoid harming joint harmony fit:
                # on strong beats, prefer leap choices that land on chord tones.
                for interval in list(final_probs.keys()):
                    if abs(interval) < 2:
                        continue
                    mult = 1.8
                    try:
                        nxt = (int(current_degree) + int(interval)) % int(deg_mod)
                        if strong_beat and chord_tones:
                            # If we're on a strong beat, only strongly boost leaps that land on chord tones.
                            # Non-chord-tone landings still get a small boost (keeps emotion), but less so.
                            mult = 2.2 if int(nxt) in chord_tones else 1.15
                    except Exception:
                        pass
                    final_probs[interval] *= float(mult)
                total = sum(final_probs.values())
                if total > 0:
                    final_probs = {k: v / total for k, v in final_probs.items()}

        # Allow callers (joint duration×interval rerank) to retrieve the final distribution
        # without running any additional sampling/rerank logic.
        if return_probs:
            return dict(final_probs)

        # Optional K-sample rerank at phrase openings/cadences to make hooks clearer
        # and phrase endings resolve more decisively, without changing the base
        # Markov distribution itself.
        try:
            from audiogen_core.config import CONFIG

            k_samples = int(CONFIG.composition.melody_phrase_planning.melody_k_samples)
            open_step_bonus = float(getattr(CONFIG.composition, "melody_rerank_opening_stepwise_bonus", 0.06))
            open_ct_bonus = float(getattr(CONFIG.composition, "melody_rerank_opening_chord_tone_bonus", 0.05))
            cad_t_bonus = float(getattr(CONFIG.composition, "melody_rerank_cadence_target_bonus", 0.10))
            cad_a_bonus = float(getattr(CONFIG.composition, "melody_rerank_cadence_approach_bonus", 0.04))
            mid_contour_bonus = float(getattr(CONFIG.composition, "melody_rerank_mid_contour_bonus", 0.0))
            motif_continue_bonus = float(getattr(CONFIG.composition, "melody_rerank_motif_continue_bonus", 0.0))
            look_w = float(getattr(CONFIG.composition, "melody_rerank_lookahead_weight", 0.22))
            look_m = int(getattr(CONFIG.composition, "melody_rerank_lookahead_top_m", 7))
        except Exception:
            k_samples = 1
            open_step_bonus = 0.06
            open_ct_bonus = 0.05
            cad_t_bonus = 0.10
            cad_a_bonus = 0.04
            mid_contour_bonus = 0.0
            motif_continue_bonus = 0.0
            look_w = 0.22
            look_m = 7

        keys = sorted(final_probs.keys(), key=repr)
        weights = [final_probs[k] for k in keys]
        k = max(1, int(k_samples))

        entry_zone = getattr(plan, "entry_zone_end", 0.22)
        cadence_zone = getattr(plan, "cadence_zone_start", 1.0)
        in_opening = bool(pos <= float(entry_zone))
        in_cadence = bool(pos >= float(cadence_zone))
        in_mid = not in_opening and not in_cadence

        # Only rerank in zones where it matters musically (and is enabled).
        mid_enabled = (abs(float(mid_contour_bonus)) > 1e-9) or (abs(float(motif_continue_bonus)) > 1e-9)
        if k == 1 or not (in_opening or in_cadence or (in_mid and mid_enabled)):
            if return_probs:
                return dict(final_probs)
            return self.rng.choices(keys, weights=weights)[0]

        chord_tones = set()
        safe_bar = bar < len(chord_weights_per_bar) if chord_weights_per_bar else False
        if safe_bar and chord_weights_per_bar and chord_weights_per_bar[bar]:
            chord_tones = set(int(d) for d in chord_weights_per_bar[bar].keys())

        cadence_target = getattr(plan, "cadence_degree", 0)
        contour_bias = {}
        try:
            contour_bias = get_interval_bias(getattr(plan, "contour", "static"), float(pos)) or {}
        except Exception:
            contour_bias = {}

        motif_next_intervals = set()
        if motif_continue_bonus > 1e-9 and melody and len(melody) >= 2:
            try:
                last_interval = int(melody[-1][0] - melody[-2][0])
                last_rhythm = float(melody[-1][1])
                candidates = self.motif.motif_library.motifs_starting_with(last_interval, last_rhythm)
                for m in candidates:
                    if getattr(m, "intervals", None) and len(m.intervals) >= 2:
                        motif_next_intervals.add(int(m.intervals[1]))
            except Exception:
                motif_next_intervals = set()

        def _dist(a: int, b: int) -> int:
            d = abs(int(a) - int(b))
            return min(d, 7 - d)

        def score(interval: int) -> float:
            p = float(final_probs.get(interval, 0.0))
            s = p
            nxt = (int(current_degree) + int(interval)) % 7
            abs_iv = abs(int(interval))
            # Cinematic constraints: keep motion controlled except near climaxes/cadences.
            try:
                t_arc = str(getattr(plan, "tension_arc", "") or "").lower()
            except Exception:
                t_arc = ""
            try:
                cont = str(getattr(plan, "contour", "static") or "static").lower()
            except Exception:
                cont = "static"
            allow_leaps = cont in {"rise", "climax", "peak", "arch_up"} or (t_arc in {"spike", "rise"} and pos >= 0.55)
            if in_opening:
                if abs(int(interval)) <= 1:
                    s += open_step_bonus
                if chord_tones and nxt in chord_tones:
                    s += open_ct_bonus
                # If we’re inside a motif continuation context, reward staying on motif.
                if motif_next_intervals and int(interval) in motif_next_intervals:
                    s += float(motif_continue_bonus) * 0.55
                # Openings: strongly prefer stepwise motion.
                if abs_iv >= 3:
                    s -= 0.06 * float(abs_iv)
            if in_mid:
                if contour_bias and float(contour_bias.get(int(interval), 1.0)) > 1.0:
                    s += float(mid_contour_bonus)
                if motif_next_intervals and int(interval) in motif_next_intervals:
                    s += float(motif_continue_bonus)
                # Flat arcs: avoid big jumps (more "composed" and less random).
                if t_arc in {"flat"} and abs_iv >= 3:
                    s -= 0.05 * float(abs_iv)
                # Outside climax contours, gently discourage big leaps.
                if (not allow_leaps) and abs_iv >= 4:
                    s -= 0.04 * float(abs_iv)
            if in_cadence:
                d = _dist(nxt, cadence_target)
                if d == 0:
                    s += cad_t_bonus
                elif d == 1:
                    s += cad_a_bonus
                # Cadence: motif continuation can be very effective (hooky landing).
                if motif_next_intervals and int(interval) in motif_next_intervals:
                    s += float(motif_continue_bonus) * 0.45
                # Cadence: prefer stepwise approach, avoid big jumps.
                if abs_iv >= 3:
                    s -= 0.07 * float(abs_iv)

            # Short-horizon lookahead: score the best plausible *next* interval under the
            # base Markov (keeps phrasing more intentional without a full beam search).
            if (in_opening or in_cadence) and float(look_w) > 1e-9:
                try:
                    o = int(getattr(self.markov.interval, "order", 2) or 2)
                    ctx2 = (list(interval_context or []) + [int(interval)])[-max(1, int(o)) :]
                    next_probs = self.markov.get_interval_probs(ctx2, temperature)
                    if next_probs:
                        # Only consider the top-M candidates to keep this cheap.
                        items = sorted(next_probs.items(), key=lambda kv: float(kv[1]), reverse=True)[: max(2, int(look_m))]
                        best2 = None
                        best2s = -1e9
                        for iv2, pr2 in items:
                            try:
                                nd2 = (int(nxt) + int(iv2)) % 7
                                s2 = float(pr2)
                                if in_cadence:
                                    d2 = _dist(int(nd2), int(cadence_target))
                                    if d2 == 0:
                                        s2 += float(cad_t_bonus) * 0.55
                                    elif d2 == 1:
                                        s2 += float(cad_a_bonus) * 0.35
                                if in_opening and abs(int(iv2)) <= 1:
                                    s2 += float(open_step_bonus) * 0.35
                                if s2 > best2s:
                                    best2s = float(s2)
                                    best2 = int(iv2)
                            except Exception:
                                continue
                        if best2 is not None:
                            s += float(look_w) * float(best2s)
                except Exception:
                    pass
            return s

        candidates = self.rng.choices(keys, weights=weights, k=k)
        return max(candidates, key=score)


    def _select_cadence_final_interval(self,
                                        current_degree: int,
                                        target_degree: int,
                                        interval_context: List[int],
                                        temperature: float) -> int:
        """
        Choose the interval for the final note of a phrase so it lands on
        (or very close to) target_degree.

        Uses Markov base probabilities but overrides them with a large
        multiplicative bias (20×) toward intervals that hit the target,
        so the landing is decisive while still being shaped by learned
        transition statistics.  Intervals that miss by more than one
        step receive a strong penalty (0.05×).
        """
        probs = self.markov.get_interval_probs(interval_context, temperature)

        if not probs:
            # No Markov context — take the shortest path to the target
            up   = (target_degree - current_degree) % 7
            down = (current_degree - target_degree) % 7
            return up if up <= down else -down

        # Macro cadence knobs: scale landing strength without changing the base model.
        try:
            from audiogen_core.config import CONFIG

            cad = float(getattr(CONFIG.composition, "cadence_strength", 1.0))
            m_cad = float(getattr(CONFIG.composition, "melody_cadence_strength", 1.0))
            cad = max(0.0, min(2.0, cad))
            m_cad = max(0.0, min(2.0, m_cad))
            strength = cad * m_cad
        except Exception:
            strength = 1.0

        land_mult = 20.0 * strength
        approach_mult = 2.0 * max(0.25, strength ** 0.5)
        miss_mult = 0.05 * (1.0 / max(0.25, strength))

        weighted: Dict[int, float] = {}
        for interval, base_prob in probs.items():
            next_deg = (current_degree + interval) % 7
            dist = min(abs(next_deg - target_degree),
                       7 - abs(next_deg - target_degree))
            if dist == 0:
                weighted[interval] = base_prob * land_mult   # land on target
            elif dist == 1:
                weighted[interval] = base_prob * approach_mult    # approach tone
            else:
                weighted[interval] = base_prob * miss_mult   # miss penalty

        total = sum(weighted.values())
        if total > 0:
            weighted = {k: v / total for k, v in weighted.items()}
        else:
            weighted = probs

        ks = sorted(weighted.keys(), key=repr)
        return self.rng.choices(ks, weights=[weighted[k] for k in ks])[0]
