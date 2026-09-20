# phrase_planner.py
from dataclasses import dataclass
from typing import Dict, List, Optional, Tuple

from data.melody_phrase_profiles import (
    melody_phrase_profile_for_emotion,
    melody_phrase_role_sequence_for_emotion,
)
from composition.intent_context import IntentContext

# ---------------------------------------------------------------------------
# Approach-tone degrees for each cadence target.
# These are the scale degrees one step away from the target that constitute
# a classical "preparation" for the cadence (e.g. IV→V before a half cadence,
# leading-tone before a full cadence).
# ---------------------------------------------------------------------------
_APPROACH_DEGREES: Dict[int, List[int]] = {
    0: [6, 4, 1],   # to tonic:       leading tone (VII), dominant (V), supertonic (II)
    4: [3, 5],      # to dominant:    subdominant (IV), submediant (VI)
    2: [1, 3, 0],   # to mediant:     supertonic, subdominant, tonic
    5: [4, 6],      # to submediant:  dominant, leading tone  (deceptive)
    6: [5, 4],      # to leading tone: submediant, dominant   (unresolved)
}


@dataclass
class PhrasePlan:
    contour: str
    entry_degree: Optional[int] = None
    target_climax: Optional[int] = None
    pre_cadence_degree: Optional[int] = None
    entry_duration_bias: Optional[Dict[float, float]] = None
    motion_duration_bias: Optional[Dict[float, float]] = None
    cadence_duration_bias: Optional[Dict[float, float]] = None
    climax_position: float = 0.67
    tension_peak_position: float = 0.62
    tension_peak_weight: float = 1.0
    cadence_release_strength: float = 1.0
    phrase_type: str = 'normal'

    # ── Cadence model ────────────────────────────────────────────────────
    # cadence_degree: the scale degree to land on at the end of this phrase.
    #
    #   0 = tonic       — full/perfect authentic cadence (I)
    #   4 = dominant    — half cadence (V)
    #   2 = mediant     — imperfect close, bittersweet (III)
    #   5 = submediant  — deceptive cadence (VI)
    #   6 = leading tone — unresolved tension (VII)
    #
    cadence_degree: int = 0

    # Position in the phrase (0–1) where cadence biasing starts ramping up.
    # Default 0.75 means the last 25% of the phrase is the cadence zone.
    cadence_zone_start: float = 0.75

    # Strength multiplier applied at the very end of the zone.
    # Higher = more decisive landing; 5.0 is a very strong pull.
    cadence_weight: float = 3.0

    # True when this is the last phrase of the section — tells the note
    # generator to use maximum cadence strength for the final note.
    is_final_phrase: bool = False

    # Optional arrangement context (plumbed from composition layer).
    section_role: str = ""
    phrase_role: str = ""
    phrase_idx: int = 0
    total_phrases: int = 1
    output_channel: int = 2
    intent: Optional[IntentContext] = None

    # Soft melody intent targets (used as probability multipliers).
    register_center_midi: Optional[int] = None
    register_half_width_midi: Optional[int] = None
    hook_anchor_degree: Optional[int] = None
    chord_tone_push: float = 1.0

    # Phrase arc waypoints as (position 0..1, scale degree 0..6, strength).
    # This gives the note sampler a phrase-level path instead of only local
    # entry/climax/cadence hints.
    arc_waypoints: Optional[List[Tuple[float, int, float]]] = None


class PhrasePlanner:
    """Generates phrase plans and applies contour and cadence bias."""

    def __init__(self):
        pass

    @staticmethod
    def _circular_distance(a: int, b: int) -> int:
        return min(abs(a - b), 7 - abs(a - b))

    @staticmethod
    def _nearest_approach_degree(target_degree: int, source_degree: int) -> int:
        options = _APPROACH_DEGREES.get(target_degree, [(target_degree - 1) % 7, (target_degree + 1) % 7])
        return min(options, key=lambda degree: PhrasePlanner._circular_distance(degree, source_degree))

    @staticmethod
    def _step_toward(source_degree: int, target_degree: int, steps: int = 1) -> int:
        src = int(source_degree) % 7
        tgt = int(target_degree) % 7
        up = (tgt - src) % 7
        down = (src - tgt) % 7
        if up == 0 and down == 0:
            return src
        direction = 1 if up <= down else -1
        n = min(abs(int(steps)), up if direction > 0 else down)
        return int((src + direction * n) % 7)

    @staticmethod
    def _arc_waypoints_for_plan(
        *,
        contour: str,
        entry_degree: int,
        target_climax: int,
        pre_cadence_degree: int,
        cadence_degree: int,
        climax_position: float,
        cadence_zone_start: float,
        is_final_phrase: bool,
        emotion_name: str,
    ) -> List[Tuple[float, int, float]]:
        entry = int(entry_degree) % 7
        peak = int(target_climax) % 7
        pre = int(pre_cadence_degree) % 7
        cad = int(cadence_degree) % 7
        contour_s = str(contour or "static").lower()
        if contour_s == "static":
            mid = entry
        elif contour_s == "desc":
            mid = PhrasePlanner._step_toward(entry, peak, 1)
        else:
            mid = PhrasePlanner._step_toward(entry, peak, 1)

        name = str(emotion_name or "").lower()
        body_strength = 1.20
        peak_strength = 1.34
        cadence_strength = 1.50 if is_final_phrase else 1.25
        if name in {"grief", "sadness", "remorse", "disappointment", "relief", "love", "caring"}:
            body_strength *= 1.08
            peak_strength *= 0.92
            cadence_strength *= 1.10
        elif name in {"joy", "excitement", "surprise", "amusement", "optimism", "pride"}:
            body_strength *= 1.02
            peak_strength *= 1.12

        peak_pos = max(0.34, min(0.78, float(climax_position)))
        cad_start = max(0.58, min(0.88, float(cadence_zone_start)))
        pre_pos = max(peak_pos + 0.08, min(0.90, cad_start - 0.06))
        return [
            (0.04, entry, 1.10),
            (0.34, mid, body_strength),
            (peak_pos, peak, peak_strength),
            (pre_pos, pre, 1.26),
            (0.96, cad, cadence_strength),
        ]

    # ------------------------------------------------------------------
    # Plan generation
    # ------------------------------------------------------------------

    def generate_plans(
        self,
        contours: List[str],
        bars: int,
        emotion,
        *,
        section_role: Optional[str] = None,
        output_channel: int = 2,
        handoff_entry_degree: Optional[int] = None,
        joint_hook_degrees: Optional[List[int]] = None,
    ) -> List[PhrasePlan]:
        """
        Build a PhrasePlan per phrase, setting both the climax target and
        the cadence target.

        Cadence strategy:
          • Last phrase  → full cadence (tonic, degree 0) by default.
          • All earlier phrases → half cadence (dominant, degree 4) by default.
          • Emotion overrides modify the final-phrase cadence:
              - grief / remorse / sadness / disappointment  → mediant (2): bittersweet
              - fear / confusion / nervousness / annoyance  → leading tone (6): unresolved
              - surprise / realization                      → submediant (5): deceptive
              - relief / gratitude / love / joy             → tonic (0): full resolution
        """
        plans = []
        num_phrases = len(contours)
        role_sequence = melody_phrase_role_sequence_for_emotion(
            getattr(emotion, "name", "neutral"),
            num_phrases,
        )

        for i, contour in enumerate(contours):
            is_last = (i == num_phrases - 1)
            prev_cadence = plans[-1].cadence_degree if plans else 0
            name = emotion.name.lower() if emotion else "neutral"
            phrase_profile = melody_phrase_profile_for_emotion(name)
            pr = (
                str(role_sequence[i] if i < len(role_sequence) else "")
                or ("opening" if num_phrases <= 1 or i == 0 else ("cadence" if is_last else ("answer" if i % 2 == 1 else "continuation")))
            )

            # ── Climax target ────────────────────────────────────────────
            target = None
            if contour in ('asc', 'arch'):
                base_target = 4 if i < num_phrases // 2 else 6
                if emotion:
                    name = emotion.name.lower()
                    if 'joy' in name or 'excitement' in name:
                        base_target = min(6, base_target + 1)
                    elif 'sad' in name or 'grief' in name:
                        base_target = max(3, base_target - 1)
                target = base_target
            target_shift = int(round(float(phrase_profile.get("target_shift", 0.0))))

            # ── Cadence target ───────────────────────────────────────────
            if is_last:
                section_key = str(section_role or "").strip().lower()
                cadence_degree = int(
                    (phrase_profile.get("final_cadence_by_section") or {}).get(
                        section_key,
                        phrase_profile.get("final_cadence_default", 0),
                    )
                ) % 7
            else:
                cadence_degree = int(
                    (phrase_profile.get("nonfinal_cadence_by_role") or {}).get(pr, 4)
                ) % 7

            entry_degree = prev_cadence
            if contour == 'asc':
                entry_degree = max(0, prev_cadence - 1)
            elif contour == 'desc':
                entry_degree = min(6, prev_cadence + 1)
            elif contour == 'arch':
                entry_degree = max(0, prev_cadence - 1) if target is not None and target >= prev_cadence else prev_cadence
            # Transition handoff: override phrase-0 entry degree when provided so the new
            # section starts near the previous lead pitch (call/response glue).
            if i == 0 and handoff_entry_degree is not None:
                try:
                    entry_degree = int(handoff_entry_degree) % 7
                except Exception:
                    pass

            if target is None:
                if contour == 'desc':
                    target = max(cadence_degree, entry_degree - 1)
                elif contour == 'static':
                    target = entry_degree
                else:
                    target = min(6, max(entry_degree, cadence_degree))
            target = max(0, min(6, int(target + target_shift)))

            pre_cadence_degree = self._nearest_approach_degree(cadence_degree, target)

            entry_duration_bias = {0.25: 0.6, 0.5: 0.95, 1.0: 1.35, 2.0: 1.15, 4.0: 0.55}
            motion_duration_bias = {0.25: 0.9, 0.5: 1.15, 1.0: 1.0, 2.0: 0.8, 4.0: 0.3}
            cadence_duration_bias = {0.25: 0.25, 0.5: 0.6, 1.0: 1.35, 2.0: 1.7, 4.0: 1.2}
            tension_peak_position = 0.62
            tension_peak_weight = 1.0
            cadence_release_strength = 1.0

            if contour == "asc":
                motion_duration_bias[0.5] *= 1.2
                motion_duration_bias[0.25] *= 1.15
                tension_peak_position = 0.72
                tension_peak_weight *= 1.15
            elif contour == "desc":
                cadence_duration_bias[1.0] *= 1.1
                cadence_duration_bias[2.0] *= 1.15
                tension_peak_position = 0.45
                cadence_release_strength *= 1.1
            elif contour == "static":
                entry_duration_bias[1.0] *= 1.1
                motion_duration_bias[0.25] *= 0.75
                motion_duration_bias[2.0] *= 1.2
                tension_peak_position = 0.50
                tension_peak_weight *= 0.8
            elif contour == "arch":
                tension_peak_position = 0.58
                tension_peak_weight *= 1.1

            if name in ("grief", "sadness", "remorse", "disappointment", "relief", "love", "caring"):
                entry_duration_bias[1.0] *= 1.15
                entry_duration_bias[2.0] *= 1.25
                motion_duration_bias[0.25] *= 0.55
                cadence_duration_bias[2.0] *= 1.25
                cadence_duration_bias[4.0] *= 1.35
                tension_peak_weight *= 0.82
                cadence_release_strength *= 1.18
            elif name in ("joy", "excitement", "surprise", "amusement", "optimism", "anger", "curiosity"):
                entry_duration_bias[0.5] *= 1.2
                motion_duration_bias[0.25] *= 1.3
                motion_duration_bias[0.5] *= 1.2
                cadence_duration_bias[2.0] *= 0.85
                cadence_duration_bias[4.0] *= 0.6
                tension_peak_weight *= 1.18
            elif name in ("fear", "nervousness", "confusion", "disgust"):
                motion_duration_bias[0.25] *= 1.25
                motion_duration_bias[0.5] *= 1.15
                cadence_duration_bias[1.0] *= 1.1
                cadence_duration_bias[2.0] *= 0.9
                tension_peak_position = max(tension_peak_position, 0.68)
                tension_peak_weight *= 1.12
                cadence_release_strength *= 0.9

            target_peak_pos = float(phrase_profile.get("peak_pos", tension_peak_position))
            tension_peak_position = float(
                max(0.3, min(0.82, tension_peak_position + (target_peak_pos - tension_peak_position) * 0.6))
            )
            tension_peak_weight *= float(phrase_profile.get("peak_weight", 1.0))
            cadence_release_strength *= float(phrase_profile.get("release_mult", 1.0))

            # Final phrase resolves more forcefully than a mid-phrase half cadence
            cadence_weight = 5.0 if is_last else 2.5

            try:
                rlc = str(section_role or "").strip().lower()
            except Exception:
                rlc = ""
            joint_cell = [int(d) % 7 for d in list(joint_hook_degrees or []) if d is not None]

            phrase_type = "handoff" if (i == 0 and handoff_entry_degree is not None) else "normal"
            arc_waypoints = self._arc_waypoints_for_plan(
                contour=str(contour or "static"),
                entry_degree=int(entry_degree),
                target_climax=int(target),
                pre_cadence_degree=int(pre_cadence_degree),
                cadence_degree=int(cadence_degree),
                climax_position=float(tension_peak_position),
                cadence_zone_start=float(getattr(PhrasePlan, "cadence_zone_start", 0.75)),
                is_final_phrase=bool(is_last),
                emotion_name=str(name),
            )
            if joint_cell and rlc in {"b", "chorus", "hook", "tag"}:
                positions = [0.0, 0.34, 0.67, 1.0]
                arc_waypoints = [
                    (float(pos), int(joint_cell[j % len(joint_cell)]) % 7, 1.0)
                    for j, pos in enumerate(positions)
                ]

            # ── Melody intent targets (register + hook anchor) ─────────────
            # Register targets are expressed in MIDI to match the lane-based scoring
            # and to keep behavior stable across different roots.
            try:
                from audiogen_core.config import CONFIG

                register_center = int(getattr(CONFIG.composition, "melody_lane_center_midi", 72) or 72)
                register_hw = int(getattr(CONFIG.composition, "melody_lane_half_width", 10) or 10)
            except Exception:
                register_center, register_hw = 72, 10

            # Phrase-role arc: opening slightly lower, answer lifts, cadence stabilizes.
            role_shift = int((phrase_profile.get("role_register_shift") or {}).get(pr, 0) or 0)
            # Second half subtle lift.
            try:
                if int(i) >= max(1, int(num_phrases) // 2):
                    role_shift += int(phrase_profile.get("second_half_register_lift", 1) or 0)
            except Exception:
                pass
            register_center = int(register_center) + int(role_shift)

            hook_anchor = None
            if joint_cell and rlc in {"b", "chorus", "hook", "tag"} and pr in {"opening", "answer", "continuation"}:
                hook_anchor = int(joint_cell[int(i) % len(joint_cell)]) % 7
            elif pr in {"opening", "answer"}:
                try:
                    rlc = str(section_role or "").strip().lower()
                except Exception:
                    rlc = ""
                try:
                    base = int(entry_degree if entry_degree is not None else cadence_degree) % 7
                except Exception:
                    base = None
                # Pop hook anchor: chorus openings should land immediately on a stable
                # scale-degree (tonic/mediant/dominant) so the hook reads clearly.
                if base is not None and pr == "opening" and rlc in {"b", "chorus", "hook", "tag"}:
                    stable = list(phrase_profile.get("hook_anchor_pool") or [0, 2, 4])
                    hook_anchor = min(stable, key=lambda d: self._circular_distance(int(d), int(base)))
                else:
                    hook_anchor = int(base) if base is not None else None

            chord_tone_push = float((phrase_profile.get("chord_tone_push_by_role") or {}).get(pr, 1.0) or 1.0)
            plans.append(PhrasePlan(
                contour=contour,
                entry_degree=entry_degree,
                target_climax=target,
                pre_cadence_degree=pre_cadence_degree,
                entry_duration_bias=entry_duration_bias,
                motion_duration_bias=motion_duration_bias,
                cadence_duration_bias=cadence_duration_bias,
                cadence_degree=cadence_degree,
                cadence_weight=cadence_weight,
                tension_peak_position=tension_peak_position,
                tension_peak_weight=tension_peak_weight,
                cadence_release_strength=cadence_release_strength,
                is_final_phrase=is_last,
                phrase_type=str(phrase_type),
                section_role=(section_role or ""),
                phrase_role=pr,
                phrase_idx=int(i),
                total_phrases=int(num_phrases),
                output_channel=int(output_channel),
                register_center_midi=int(register_center),
                register_half_width_midi=int(register_hw),
                hook_anchor_degree=int(hook_anchor) if hook_anchor is not None else None,
                chord_tone_push=float(chord_tone_push),
                arc_waypoints=list(arc_waypoints),
                intent=IntentContext(
                    section_role=str(section_role or ""),
                    phrase_role=str(pr or ""),
                    contour=str(contour or "static"),
                    phrase_idx=int(i),
                    total_phrases=int(num_phrases),
                    output_channel=int(output_channel),
                    cadence_degree=int(cadence_degree),
                    cadence_zone_start=float(getattr(PhrasePlan, "cadence_zone_start", 0.75)),
                    is_final_phrase=bool(is_last),
                    register_center_midi=int(register_center),
                    register_half_width_midi=int(register_hw),
                    hook_anchor_degree=int(hook_anchor) if hook_anchor is not None else None,
                    chord_tone_push=float(chord_tone_push),
                ),
            ))

        return plans

    # ------------------------------------------------------------------
    # Per-note bias (called from NoteGenerator._select_interval)
    # ------------------------------------------------------------------

    def apply_plan_bias(self, interval_probs: Dict[int, float],
                        melody: List, plan: 'PhrasePlan', pos: float):
        current_deg = melody[-1][0]
        targets = []
        try:
            waypoints = list(getattr(plan, "arc_waypoints", None) or [])
        except Exception:
            waypoints = []
        if waypoints:
            try:
                p = max(0.0, min(1.0, float(pos)))
            except Exception:
                p = 0.0
            nearest = min(
                waypoints,
                key=lambda item: abs(float(item[0]) - p),
            )
            try:
                target_degree = int(nearest[1]) % 7
                strength = float(nearest[2])
            except Exception:
                target_degree = int(getattr(plan, "cadence_degree", 0) or 0) % 7
                strength = 1.15
            # Strongest near the waypoint, but still helpful between waypoints.
            dist_pos = min(0.32, abs(float(nearest[0]) - p))
            local_weight = 1.0 - (dist_pos / 0.32) * 0.45
            targets.append((target_degree, max(1.05, float(strength) * float(local_weight))))
        if plan.entry_degree is not None and pos <= 0.28:
            targets.append((plan.entry_degree, 1.25))
        if plan.target_climax is not None:
            if pos < plan.climax_position:
                targets.append((plan.target_climax, 1.55))
            elif pos < plan.cadence_zone_start:
                targets.append((plan.target_climax, 1.15))
        pre_cadence_window_start = max(0.0, plan.cadence_zone_start - 0.18)
        if plan.pre_cadence_degree is not None and pre_cadence_window_start <= pos < plan.cadence_zone_start:
            targets.append((plan.pre_cadence_degree, 1.45))

        # Transition handoff opening: stronger early “pickup” glue and fewer big leaps.
        # This is lightweight and only affects the first ~15% of the phrase.
        try:
            if str(getattr(plan, "phrase_type", "") or "") == "handoff" and pos <= 0.15:
                if plan.entry_degree is not None:
                    targets.append((plan.entry_degree, 1.65))
                for interval in list(interval_probs.keys()):
                    step = abs(int(interval))
                    if step <= 1:
                        interval_probs[interval] *= 1.18
                    elif step >= 4:
                        interval_probs[interval] *= 0.72
        except Exception:
            pass

        for target_degree, boost in targets:
            current_dist = self._circular_distance(current_deg, target_degree)
            for interval in list(interval_probs.keys()):
                new_deg = (current_deg + interval) % 7
                new_dist = self._circular_distance(new_deg, target_degree)
                if new_dist < current_dist:
                    interval_probs[interval] *= boost
                elif new_dist > current_dist:
                    interval_probs[interval] *= max(0.65, 1.0 / boost)
