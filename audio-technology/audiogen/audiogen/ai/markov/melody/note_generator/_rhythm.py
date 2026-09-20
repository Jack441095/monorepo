# ai/markov/melody/note_generator/_rhythm.py
"""Rhythm sampling and phrase-level rhythm biasing for NoteGenerator."""
import logging
from typing import Any, Dict, List, Optional

from audiogen_core.constants import DURATIONS

from ..biasing import EMOTION_RHYTHM_BIAS

logger = logging.getLogger(__name__)


# 2026-07-04: `_abs_dur(dur)` is called at ~15 bias stages here (57.5M calls / ~10.5s on
# the retrained path). An earlier `@lru_cache` on this was found to be *net-negative* --
# microbenchmarked at 5.00s cached vs 3.93s as a plain function, because hashing a float
# arg + a cache-dict lookup costs more than the trivial `abs(float(x))` it guards. Kept as
# a plain single-definition helper (no cache) so every call site stays a one-liner while
# paying only the real computation, not memoization overhead.
def _abs_dur(x: float) -> float:
    return abs(float(x))


class NoteGeneratorRhythmMixin:
    def _rhythm_distribution(
        self,
        rhythm_context: List[float],
        temperature: float,
        current_beat: float,
        beats_per_bar: float,
        emotion,
        *,
        plan=None,
        phrase_pos: float = 0.0,
        current_chord: Optional[str] = None,
        phrase_end_beat: Optional[float] = None,
        last_interval: Optional[int] = None,
        occupied_steps: Optional[set[int]] = None,
        occupied_step_weights: Optional[Dict[int, float]] = None,
        mask_strength: float = 0.0,
        grid: float = 0.25,
        rep_tracker: Optional[Any] = None,
        breath_window_by_bar: Optional[List[float]] = None,
        interval_context_for_joint: Optional[List[int]] = None,
        bar_intent: Optional[Dict[str, Any]] = None,
        roots: Optional[List[int]] = None,
    ) -> Dict[float, float]:
        """
        Return the rhythm distribution after all conditioning/bias layers.
        This is used for both sampling and joint (duration×interval) reranking.
        """
        rhythm_probs = self.markov.get_rhythm_probs(rhythm_context, temperature)

        # Optional: phrase-role rhythm-conditioning (opening/continuation/answer/cadence).
        try:
            from audiogen_core.config import CONFIG
            from composition.scoring_utils import blend_probs

            r_blend = float(getattr(CONFIG.composition, "melody_phrase_role_rhythm_model_blend", 0.25))
            role_enabled = bool(getattr(CONFIG.composition, "melody_role_conditioning_enabled", True))
        except Exception:
            r_blend = 0.25
            role_enabled = True
            blend_probs = None
        if role_enabled and r_blend > 1e-6 and blend_probs is not None and hasattr(self.markov, "get_rhythm_probs_for_role") and plan is not None:
            intent = getattr(plan, "intent", None) if plan is not None else None
            try:
                role = str(getattr(intent, "phrase_role", "") or "") if intent is not None else str(getattr(plan, "phrase_role", "") or "")
                role = role.strip().lower() or "continuation"
            except Exception:
                role = "continuation"
            try:
                rp = self.markov.get_rhythm_probs_for_role(role, rhythm_context, temperature)
            except Exception:
                rp = {}
            if rp:
                rhythm_probs = blend_probs(rhythm_probs, rp, float(r_blend))

        # Beat-strength conditioned rhythm blend (downbeat vs offbeat).
        try:
            from audiogen_core.config import CONFIG
            from composition.scoring_utils import blend_probs as _blend_bb

            bb_on = bool(getattr(CONFIG.composition, "melody_beat_strength_conditioning_enabled", True))
            bb_blend = float(getattr(CONFIG.composition, "melody_beat_strength_condition_blend", 0.22) or 0.22)
        except Exception:
            bb_on = True
            bb_blend = 0.22
            _blend_bb = None
        if bb_on and bb_blend > 1e-6 and _blend_bb is not None and hasattr(self.markov, "get_rhythm_probs_for_beat_bin"):
            try:
                beat_in_bar = float(current_beat) % float(beats_per_bar)
            except Exception:
                beat_in_bar = 0.0
            beat_bin = "downbeat" if abs(float(beat_in_bar) - 0.0) < 1e-6 else "offbeat"
            try:
                bp = self.markov.get_rhythm_probs_for_beat_bin(beat_bin, rhythm_context, temperature)
            except Exception:
                bp = {}
            if bp:
                rhythm_probs = _blend_bb(rhythm_probs, bp, float(bb_blend))

        # Optional global Markov blend (emotion ↔ global).
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
                gp = self.markov.get_global_rhythm_probs(rhythm_context, temperature)
            except Exception:
                gp = {}
            if gp:
                rhythm_probs = blend_probs(rhythm_probs, gp, float(g_alpha))

        # Optional: function + position rhythm-conditioning blend.
        try:
            from audiogen_core.config import CONFIG
            from composition.scoring_utils import blend_probs

            f_alpha = float(getattr(CONFIG.composition, "melody_function_rhythm_condition_blend", 0.0))
            h_on = bool(getattr(CONFIG.composition, "melody_function_context_hierarchy_enabled", True))
            h_alpha = float(getattr(CONFIG.composition, "melody_function_context_hierarchy_strength", 0.45) or 0.45)
        except Exception:
            f_alpha = 0.0
            h_on = True
            h_alpha = 0.45
            blend_probs = None
        if f_alpha > 1e-6 and blend_probs is not None and current_chord:
            intent = getattr(plan, "intent", None) if plan is not None else None
            try:
                func = self.markov.extract_harmonic_function(current_chord)
                feat = self.markov.extract_harmonic_feature_key(current_chord)
            except Exception:
                func = "other"
                feat = "other"
            try:
                role = str(getattr(intent, "phrase_role", "") or "") if intent is not None else str(getattr(plan, "phrase_role", "") or "")
            except Exception:
                role = ""
            try:
                bar_in_phrase = int((float(current_beat) // float(beats_per_bar)) % 4)
            except Exception:
                bar_in_phrase = 0
            key = (str(feat), str((role or "continuation").strip().lower() or "continuation"), int(bar_in_phrase))
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
                    pos0 = float(getattr(plan, "position", 0.0) or 0.0)
                except Exception:
                    pos0 = 0.0
                cad_band = "cad_hi" if pos0 >= float(getattr(plan, "cadence_zone_start", 0.75) or 0.75) else "cad_lo"
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
                try:
                    keypc = "unk"
                    bar_i = int(float(current_beat) // float(beats_per_bar)) if float(beats_per_bar) > 1e-9 else 0
                    if roots and 0 <= int(bar_i) < len(roots):
                        keypc = str(int(roots[int(bar_i)]) % 12)
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
                key_h = (str(feat_h), str((role or "continuation").strip().lower() or "continuation"), int(bar_in_phrase))
            try:
                fp = self.markov.get_rhythm_probs_for_function_key(key_h, rhythm_context, temperature)
            except Exception:
                fp = {}
            if fp and h_on and key_h != key:
                try:
                    f_base = self.markov.get_rhythm_probs_for_function_key(key, rhythm_context, temperature)
                except Exception:
                    f_base = {}
                if f_base:
                    try:
                        fp = blend_probs(f_base, fp, float(max(0.0, min(1.0, h_alpha))))
                    except Exception:
                        pass
            if not fp:
                try:
                    fp = self.markov.get_rhythm_probs_for_function_key(
                        (str(func), str((role or "continuation").strip().lower() or "continuation"), int(bar_in_phrase)),
                        rhythm_context,
                        temperature,
                    )
                except Exception:
                    fp = {}
            if fp:
                rhythm_probs = blend_probs(rhythm_probs, fp, float(f_alpha))

        # Emotion rhythm bias
        if emotion is not None:
            try:
                name = str(getattr(emotion, "name", "") or "").lower()
            except Exception:
                name = ""
            if name in EMOTION_RHYTHM_BIAS:
                try:
                    bias = EMOTION_RHYTHM_BIAS[name]
                    upd = dict(rhythm_probs)
                    for dur in list(upd.keys()):
                        upd[dur] *= float(bias.get(_abs_dur(dur), 1.0))
                    tot = float(sum(float(v) for v in upd.values()))
                    if tot > 1e-12:
                        rhythm_probs = {k: float(v) / tot for k, v in upd.items()}
                except Exception:
                    pass

        # Phrase-level rhythm bias (entry/motion/cadence duration templates)
        try:
            rhythm_probs = self._apply_phrase_rhythm_bias(
                rhythm_probs,
                plan,
                float(phrase_pos),
                float(current_beat),
                float(beats_per_bar),
            )
        except Exception:
            pass

        # Local tension rhythm bias
        try:
            local_tension = float(getattr(getattr(plan, "intent", None), "local_tension", 0.0) or 0.0) if plan is not None else 0.0
        except Exception:
            local_tension = 0.0
        if local_tension > 1e-9:
            try:
                rhythm_probs = self._apply_local_tension_rhythm_bias(rhythm_probs, float(local_tension))
            except Exception:
                pass

        # Rhythm–pitch coupling (interval → duration)
        try:
            from audiogen_core.config import CONFIG

            coupling_on = bool(getattr(CONFIG.composition, "melody_rhythm_pitch_coupling_enabled", False))
            coupling_strength = float(getattr(CONFIG.composition, "melody_rhythm_pitch_coupling_strength", 0.65))
        except Exception:
            coupling_on = False
            coupling_strength = 0.65
        coupling_strength = max(0.0, min(1.0, float(coupling_strength)))
        if coupling_on and coupling_strength > 1e-9 and last_interval is not None:
            try:
                rhythm_probs = self._apply_pitch_rhythm_coupling(rhythm_probs, int(last_interval), float(coupling_strength))
            except Exception:
                pass

        # Masking constraints (avoid occupied onset steps)
        if mask_strength > 1e-9 and occupied_steps:
            try:
                rhythm_probs = self._apply_masking_rhythm_bias(
                    rhythm_probs,
                    current_beat=float(current_beat),
                    beats_per_bar=float(beats_per_bar),
                    occupied_steps=set(occupied_steps),
                    occupied_step_weights=dict(occupied_step_weights or {}),
                    mask_strength=float(mask_strength),
                    grid=float(grid),
                )
            except Exception:
                pass

        # Anti-stuck (repeat same duration many times)
        try:
            from audiogen_core.config import CONFIG

            antistuck = bool(getattr(CONFIG.composition, "melody_rhythm_antistuck_enabled", True))
            rep_mult = float(getattr(CONFIG.composition, "melody_rhythm_repeat_penalty_mult", 0.7))
        except Exception:
            antistuck = True
            rep_mult = 0.7
        if antistuck and rhythm_context:
            try:
                last = float(rhythm_context[-1])
                streak = 1
                for d in reversed(rhythm_context[:-1]):
                    if abs(float(d) - last) < 1e-9:
                        streak += 1
                    else:
                        break
                if streak >= 3 and last in rhythm_probs:
                    rhythm_probs[last] *= max(0.0, min(1.0, rep_mult))
                    total = sum(rhythm_probs.values())
                    if total > 0:
                        rhythm_probs = {k: v / total for k, v in rhythm_probs.items()}
            except Exception:
                pass

        # Dynamic n-gram repetition penalty (RT-cheap).
        if rep_tracker is not None:
            try:
                penalized = dict(rhythm_probs)
                for dur in list(penalized.keys()):
                    penalized[dur] *= float(rep_tracker.penalty_for_next_rhythm(candidate_dur=float(dur)))
                total = sum(penalized.values())
                if total > 0:
                    rhythm_probs = {k: v / total for k, v in penalized.items()}
            except Exception:
                pass

        # Breath-window rhythm sparsity (high breath → longer IOIs).
        try:
            from audiogen_core.config import CONFIG

            br_r_on = bool(getattr(CONFIG.composition, "melody_breath_rhythm_bias_enabled", False))
            br_r_st = float(getattr(CONFIG.composition, "melody_breath_rhythm_bias_strength", 0.65) or 0.65)
        except Exception:
            br_r_on = False
            br_r_st = 0.65
        br_r_st = max(0.0, min(1.0, float(br_r_st)))
        if br_r_on and br_r_st > 1e-9 and breath_window_by_bar:
            try:
                bar_i = int(float(current_beat) // float(beats_per_bar))
            except Exception:
                bar_i = 0
            if 0 <= bar_i < len(breath_window_by_bar):
                bw = max(0.0, min(1.0, float(breath_window_by_bar[bar_i] or 0.0)))
                if bw > 1e-9:
                    s = br_r_st * bw
                    upd = dict(rhythm_probs)
                    for dur in list(upd.keys()):
                        d0 = _abs_dur(dur)
                        mult = 1.0
                        if d0 >= 1.0:
                            mult *= 1.0 + 0.45 * s
                        if d0 <= 0.25:
                            mult *= max(0.08, 1.0 - 0.40 * s)
                        upd[dur] = float(upd.get(dur, 0.0)) * mult
                    tot = float(sum(float(v) for v in upd.values()))
                    if tot > 1e-12:
                        rhythm_probs = {k: float(v) / tot for k, v in upd.items()}

        # Composition per-bar intent shaping (function/cadence strength).
        if bar_intent and rhythm_probs:
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
                    st = float(getattr(CONFIG.composition, "melody_intent_rhythm_strength", 0.18) or 0.18)
                except Exception:
                    st = 0.18
                st = max(0.0, min(1.0, float(st)))
                if st > 1e-9:
                    upd = dict(rhythm_probs)
                    if fn == "D" or cad >= 0.75:
                        s = float(st) * min(1.0, float(cad) / 0.95 if cad > 0 else 0.85)
                        for dur in list(upd.keys()):
                            d0 = _abs_dur(dur)
                            if d0 >= 1.0:
                                upd[dur] *= 1.0 + 0.45 * s
                            if d0 <= 0.25:
                                upd[dur] *= max(0.08, 1.0 - 0.35 * s)
                    elif fn == "PD":
                        s = float(st) * 0.65
                        for dur in list(upd.keys()):
                            d0 = _abs_dur(dur)
                            if d0 <= 0.5:
                                upd[dur] *= 1.0 + 0.22 * s
                            if d0 >= 2.0:
                                upd[dur] *= max(0.08, 1.0 - 0.20 * s)
                    elif fn == "T":
                        s = float(st) * 0.55
                        for dur in list(upd.keys()):
                            d0 = _abs_dur(dur)
                            if d0 >= 1.0:
                                upd[dur] *= 1.0 + 0.20 * s
                    tot = float(sum(float(v) for v in upd.values()))
                    if tot > 1e-12:
                        rhythm_probs = {k: float(v) / tot for k, v in upd.items()}

        # Joint rhythm–pitch rerank: reweight durations using interval Markov marginal.
        try:
            from audiogen_core.config import CONFIG

            jr_on = bool(getattr(CONFIG.composition, "melody_joint_rhythm_pitch_rerank_enabled", False))
            jr_st = float(getattr(CONFIG.composition, "melody_joint_rhythm_pitch_rerank_strength", 0.55) or 0.55)
            jr_k = int(getattr(CONFIG.composition, "melody_joint_rhythm_pitch_rerank_k", 0) or 0)
        except Exception:
            jr_on = False
            jr_st = 0.55
            jr_k = 0
        jr_st = max(0.0, min(1.0, float(jr_st)))
        if jr_on and jr_st > 1e-9 and interval_context_for_joint is not None and rhythm_probs:
            try:
                ip = self.markov.get_interval_probs(list(interval_context_for_joint), float(temperature))
            except Exception:
                ip = {}
            if ip:
                probs0 = dict(rhythm_probs)
                if jr_k > 0:
                    items = sorted(probs0.items(), key=lambda kv: -float(kv[1]))[: int(jr_k)]
                    probs0 = {k: v for k, v in items}
                    tot0 = float(sum(float(v) for v in probs0.values()))
                    if tot0 > 1e-12:
                        probs0 = {k: float(v) / tot0 for k, v in probs0.items()}
                upd = dict(probs0)
                for dur in list(upd.keys()):
                    comp = self._duration_interval_compat(ip, _abs_dur(dur))
                    upd[dur] = float(upd[dur]) * (1.0 + jr_st * (float(comp) - 0.5) * 2.0)
                tot = float(sum(float(v) for v in upd.values()))
                if tot > 1e-12:
                    rhythm_probs = {k: float(v) / tot for k, v in upd.items()}

        return dict(rhythm_probs)

    def _select_rhythm(self, rhythm_context: List[float], temperature: float,
                       current_beat: float, beats_per_bar: float, emotion, plan=None,
                       phrase_pos: float = 0.0, current_chord: Optional[str] = None,
                       phrase_end_beat: Optional[float] = None,
                       last_interval: Optional[int] = None,
                       occupied_steps: Optional[set[int]] = None,
                       occupied_step_weights: Optional[Dict[int, float]] = None,
                       mask_strength: float = 0.0,
                       grid: float = 0.25,
                       rep_tracker: Optional[Any] = None,
                       breath_window_by_bar: Optional[List[float]] = None,
                       interval_context_for_joint: Optional[List[int]] = None,
                       bar_intent: Optional[Dict[str, Any]] = None,
                       roots: Optional[List[int]] = None) -> float:
        rhythm_probs = self._rhythm_distribution(
            rhythm_context,
            temperature,
            current_beat,
            beats_per_bar,
            emotion,
            plan=plan,
            phrase_pos=float(phrase_pos),
            current_chord=current_chord,
            phrase_end_beat=phrase_end_beat,
            last_interval=last_interval,
            occupied_steps=occupied_steps,
            occupied_step_weights=occupied_step_weights,
            mask_strength=float(mask_strength),
            grid=float(grid),
            rep_tracker=rep_tracker,
            breath_window_by_bar=breath_window_by_bar,
            interval_context_for_joint=interval_context_for_joint,
            bar_intent=bar_intent,
            roots=roots,
        )
        try:
            from audiogen_core.config import CONFIG

            single_pass = bool(
                getattr(CONFIG.composition, "melody_rhythm_single_pass_enabled", False)
            )
        except Exception:
            single_pass = False

        if single_pass:
            # Preserve `_rhythm_distribution` early-exit sentinel semantics.
            if isinstance(rhythm_probs, (int, float)):
                return float(rhythm_probs)
            if not isinstance(rhythm_probs, dict) or not rhythm_probs:
                return DURATIONS[0]
            ks = sorted(rhythm_probs.keys(), key=repr)
            return self.rng.choices(ks, weights=[rhythm_probs[k] for k in ks])[0]

        # NOTE (2026-07-03, docs/AUDIOGEN_COMPOSITION_PLAN.md item 18): the role/beat/
        # global/function-conditioned blends, phrase rhythm bias, local-tension-from-plan
        # bias, rhythm-pitch coupling, masking, anti-stuck, rep_tracker penalty,
        # breath-window bias, bar-intent shaping, and joint rhythm-pitch rerank were all
        # previously computed a SECOND time here, byte-for-byte identical to what
        # `_rhythm_distribution` above it already does, doubling the cost of every
        # Markov query and blend on every note (this is what `melody_rhythm_single_pass_
        # enabled` used to bypass wholesale, at the cost of also skipping the logic below
        # that is genuinely unique to this function). Removed; only the unique logic below
        # remains.
        if not rhythm_probs:
            return DURATIONS[0]

        # --------------------------------------------------------------
        # Markov upgrade A: bar/phrase-position conditioning (flagged)
        # --------------------------------------------------------------
        from audiogen_core.composition_runtime_flags import melody_position_conditioning

        pos_on, pos_strength = melody_position_conditioning()
        if pos_on and pos_strength > 1e-6:
            try:
                beat_in_bar = float(current_beat) % float(beats_per_bar)
                to_bar_end = float(beats_per_bar) - float(beat_in_bar)
            except Exception:
                to_bar_end = float(beats_per_bar)

            to_phrase_end = None
            if phrase_end_beat is not None:
                try:
                    to_phrase_end = float(phrase_end_beat) - float(current_beat)
                except Exception:
                    to_phrase_end = None
            near_phrase_end = (to_phrase_end is not None) and (float(to_phrase_end) <= 2.0)

            updated = dict(rhythm_probs)
            for dur in list(updated.keys()):
                d0 = _abs_dur(dur)
                mult = 1.0
                # Close to bar end: reward landing exactly on the boundary.
                if float(to_bar_end) <= 1.0 + 1e-6:
                    if abs(float(d0) - float(to_bar_end)) <= 1e-6:
                        mult *= 1.0 + 1.25 * pos_strength
                    elif float(d0) > float(to_bar_end) + 1e-6:
                        mult *= 0.40 + 0.45 * (1.0 - pos_strength)
                # Cadence closure: near phrase end, slightly prefer longer holds.
                if near_phrase_end:
                    if d0 >= 1.0:
                        mult *= 1.0 + 0.55 * pos_strength
                    if d0 <= 0.25:
                        mult *= 0.80 - 0.35 * pos_strength
                # Pickup glue: just before a downbeat, allow short anticipations.
                if float(to_bar_end) <= 0.50 + 1e-6 and abs(float(d0) - 0.25) <= 1e-9:
                    mult *= 1.0 + 0.45 * pos_strength
                updated[dur] = float(updated.get(dur, 0.0)) * float(mult)
            total = float(sum(float(v) for v in updated.values()))
            if total > 1e-12:
                rhythm_probs = {k: float(v) / total for k, v in updated.items()}

        # --------------------------------------------------------------
        # Markov upgrade B: rhythm–pitch coupling (flagged)
        # Condition duration on last interval bucket + beat phase.
        # --------------------------------------------------------------
        try:
            from audiogen_core.config import CONFIG

            rpc_on = bool(getattr(CONFIG.composition, "melody_rhythm_pitch_coupling_enabled", False))
            rpc_strength = float(getattr(CONFIG.composition, "melody_rhythm_pitch_coupling_strength", 0.65) or 0.65)
        except Exception:
            rpc_on = False
            rpc_strength = 0.65
        rpc_strength = max(0.0, min(1.0, float(rpc_strength)))
        if rpc_on and rpc_strength > 1e-6 and last_interval is not None:
            try:
                iv = abs(int(last_interval))
            except Exception:
                iv = 0
            if iv <= 1:
                bucket = "small"
            elif iv <= 3:
                bucket = "med"
            else:
                bucket = "large"
            try:
                beat_phase = float(current_beat) % 1.0
            except Exception:
                beat_phase = 0.0
            strongish = (beat_phase < 1e-6) or abs(beat_phase - 0.5) < 1e-6

            updated = dict(rhythm_probs)
            for dur in list(updated.keys()):
                d0 = _abs_dur(dur)
                mult = 1.0
                if bucket == "large":
                    if d0 >= 1.0:
                        mult *= 1.0 + (0.55 if strongish else 0.35) * rpc_strength
                    if d0 <= 0.25:
                        mult *= 0.85 - 0.35 * rpc_strength
                elif bucket == "small":
                    if d0 <= 0.5:
                        mult *= 1.0 + 0.30 * rpc_strength
                updated[dur] = float(updated.get(dur, 0.0)) * float(mult)
            total = float(sum(float(v) for v in updated.values()))
            if total > 1e-12:
                rhythm_probs = {k: float(v) / total for k, v in updated.items()}

        # Style profile rhythm activity bias (deterministic, config-gated).
        # Lower activity => penalize short durations; higher activity => slightly favor them.
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
                act = float(getattr(prof, "melody_rhythm_activity", 0.5) or 0.5)
                act = max(0.0, min(1.0, float(act)))
                # Map to a factor for short durs: 0 => 0.75, 1 => 1.15 (then blend by s).
                short = 0.75 + 0.40 * float(act)
                short = 1.0 + (float(short) - 1.0) * float(s)
                long = 1.25 - 0.30 * float(act)
                long = 1.0 + (float(long) - 1.0) * float(s)
                updated = dict(rhythm_probs)
                for dur in list(updated.keys()):
                    d = _abs_dur(dur)
                    if d <= 0.5:
                        updated[dur] *= max(0.05, float(short))
                    elif d >= 2.0:
                        updated[dur] *= max(0.05, float(long))
                total = sum(updated.values())
                if total > 0:
                    rhythm_probs = {k: v / total for k, v in updated.items()}
                try:
                    setattr(self, "_debug_style_rhythm_activity", float(act))
                except Exception:
                    pass
            except Exception:
                pass

        # Runtime masking (call/response): avoid placing lead onsets where other layers
        # are already active (e.g. arp). We apply a soft penalty to candidate durations
        # based on the *current onset step*.
        if (occupied_steps or occupied_step_weights) and mask_strength > 1e-6:
            try:
                step = int(round(float(current_beat) / float(grid)))
                w = None
                if occupied_step_weights and step in occupied_step_weights:
                    w = float(occupied_step_weights.get(step, 0.0) or 0.0)
                elif occupied_steps and step in occupied_steps:
                    w = 1.0
                if w is not None and w > 1e-9:
                    w = max(0.0, min(1.0, float(w)))
                    amt = float(mask_strength) * (0.55 + 0.45 * float(w))
                    for dur in list(rhythm_probs.keys()):
                        rhythm_probs[dur] *= max(0.05, 1.0 - float(amt))
                    total = sum(rhythm_probs.values())
                    if total > 0:
                        rhythm_probs = {k: v / total for k, v in rhythm_probs.items()}
            except Exception:
                pass

        # Optional grid-based masking: penalize durations that would *span* highly occupied steps,
        # not only onsets. This helps dense arp beds read as a partner rather than a collision.
        try:
            from audiogen_core.config import CONFIG

            grid_mask_on = bool(getattr(CONFIG.composition, "masking_grid_enabled", False))
            grid_mask_strength = float(getattr(CONFIG.composition, "masking_grid_strength", 0.7) or 0.7)
        except Exception:
            grid_mask_on = False
            grid_mask_strength = 0.7
        grid_mask_strength = max(0.0, min(1.0, float(grid_mask_strength)))
        if (
            grid_mask_on
            and occupied_step_weights
            and mask_strength > 1e-6
            and grid_mask_strength > 1e-6
            and rhythm_probs
        ):
            try:
                step0 = int(round(float(current_beat) / float(grid)))
                updated = dict(rhythm_probs)
                for dur in list(updated.keys()):
                    try:
                        n_steps = int(max(1, round(_abs_dur(dur) / float(grid))))
                    except Exception:
                        n_steps = 1
                    # Mean occupancy over the span [step0, step0+n_steps).
                    s = 0.0
                    c = 0
                    for i in range(int(step0), int(step0) + int(n_steps)):
                        if int(i) in occupied_step_weights:
                            s += float(occupied_step_weights.get(int(i), 0.0) or 0.0)
                        c += 1
                    occ = float(s) / float(max(1, c))
                    occ = max(0.0, min(1.0, float(occ)))
                    amt = float(mask_strength) * float(grid_mask_strength) * (0.40 + 0.60 * float(occ))
                    updated[dur] *= max(0.05, 1.0 - float(amt))
                total = sum(updated.values())
                if total > 0:
                    rhythm_probs = {k: v / total for k, v in updated.items()}
            except Exception:
                pass

        # If a phrase boundary is known, avoid durations that would spill past it.
        # This makes phrase endings and cadences feel intentional rather than
        # landing mid-bar or mid-thought.
        if phrase_end_beat is not None:
            remaining = float(phrase_end_beat - current_beat)
            if remaining <= 1e-6:
                return 0.0
            rhythm_probs = {
                dur: prob for dur, prob in rhythm_probs.items()
                if _abs_dur(dur) <= remaining + 1e-6
            } or rhythm_probs

        on_downbeat = abs(current_beat % beats_per_bar) < 1e-6
        rhythm_probs = self._bias_rhythm(rhythm_probs, emotion, on_downbeat=on_downbeat)

        if emotion is not None:
            name = emotion.name.lower()
            if name in EMOTION_RHYTHM_BIAS:
                bias = EMOTION_RHYTHM_BIAS[name]
                for dur in list(rhythm_probs.keys()):
                    factor = bias.get(dur, None)
                    if factor is None:
                        factor = bias.get(_abs_dur(dur), 1.0)
                    rhythm_probs[dur] *= factor ** (3 * self.emotion_intensity)
                total = sum(rhythm_probs.values())
                if total > 0:
                    rhythm_probs = {k: v / total for k, v in rhythm_probs.items()}

        if not on_downbeat and abs((current_beat % beats_per_bar) - 2.0) < 1e-6:
            for k in (DURATIONS[2], -DURATIONS[2]):
                if k in rhythm_probs:
                    rhythm_probs[k] *= 1.5
            total = sum(rhythm_probs.values())
            if total > 0:
                rhythm_probs = {k: v / total for k, v in rhythm_probs.items()}
        # NOTE (2026-07-03, item 18): this function's own tension figure (blending
        # phrase-position tension with harmonic tension) is intentionally distinct
        # from `_rhythm_distribution`'s simpler plan.intent.local_tension bias above
        # it, so both are kept. The phrase-rhythm-bias call, anti-stuck penalty,
        # rep_tracker penalty, breath-window bias, bar-intent shaping, and joint
        # rhythm-pitch rerank that used to follow here were exact duplicates of what
        # `_rhythm_distribution` already applied earlier in this same call and have
        # been removed.
        local_tension = self._compute_phrase_tension(phrase_pos, plan, emotion)
        harmonic_tension = self._compute_harmonic_tension(current_chord or "", phrase_pos, plan=plan)
        local_tension = float(min(1.0, local_tension * harmonic_tension))
        rhythm_probs = self._apply_local_tension_rhythm_bias(rhythm_probs, local_tension)

        ks = sorted(rhythm_probs.keys(), key=repr)
        return self.rng.choices(ks, weights=[rhythm_probs[k] for k in ks])[0]

    @staticmethod
    def _apply_local_tension_rhythm_bias(
        rhythm_probs: Dict[float, float],
        local_tension: float,
    ) -> Dict[float, float]:
        if not rhythm_probs:
            return rhythm_probs

        updated = dict(rhythm_probs)
        for dur in list(updated.keys()):
            ad = _abs_dur(dur)
            if local_tension >= 0.7:
                if ad <= 0.5:
                    updated[dur] *= 1.25
                elif ad >= 2.0:
                    updated[dur] *= 0.7
            elif local_tension <= 0.35:
                if ad <= 0.5:
                    updated[dur] *= 0.78
                elif ad >= 2.0:
                    updated[dur] *= 1.25

        total = sum(updated.values())
        if total > 0:
            return {k: v / total for k, v in updated.items()}
        return rhythm_probs

    def _apply_phrase_rhythm_bias(
        self,
        rhythm_probs: Dict[float, float],
        plan,
        phrase_pos: float,
        current_beat: float,
        beats_per_bar: float,
    ) -> Dict[float, float]:
        if not plan or not rhythm_probs:
            return rhythm_probs

        if phrase_pos <= 0.22:
            duration_bias = getattr(plan, "entry_duration_bias", None)
        elif phrase_pos >= getattr(plan, "cadence_zone_start", 1.0):
            duration_bias = getattr(plan, "cadence_duration_bias", None)
        else:
            duration_bias = getattr(plan, "motion_duration_bias", None)

        if not duration_bias:
            return rhythm_probs

        updated = dict(rhythm_probs)
        for dur in list(updated.keys()):
            m = duration_bias.get(dur, None)
            if m is None:
                m = duration_bias.get(_abs_dur(dur), 1.0)
            updated[dur] *= m

        beat_in_bar = current_beat % beats_per_bar
        if phrase_pos >= getattr(plan, "cadence_zone_start", 1.0):
            remaining_in_bar = beats_per_bar - beat_in_bar if beat_in_bar > 1e-6 else beats_per_bar
            for dur in list(updated.keys()):
                if _abs_dur(dur) > remaining_in_bar + 1e-6:
                    updated[dur] *= 0.45

        total = sum(updated.values())
        if total > 0:
            return {k: v / total for k, v in updated.items()}
        return rhythm_probs
