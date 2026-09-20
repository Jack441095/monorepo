# ai/markov/melody/motif_manager.py
# Project module `motif_manager` (ai).

# motif_manager.py
import random
from typing import Any, Dict, List, Optional, Tuple

from audiogen_core.composition_runtime_flags import motif_rhythm_only_enabled
from data.melody_motif_profiles import melody_motif_profile_for_emotion, preferred_motif_variations

from ..motif import MotifLibrary
from .harmony_symbol import simplify_harmony_function
from .motif_variations import (
    augment_motif,
    diminish_motif,
    fragment_motif,
    invert_motif,
    retrograde_motif,
    sequence_motif,
)


class MotifManager:
    """Manages motif library and motif application during generation."""

    def __init__(self, motif_length: int = 3, motif_prob: float = 0.7,
                 motif_variation_prob: float = 0.3, rng=random):
        motif_lengths = None
        try:
            from audiogen_core.config import CONFIG

            if bool(getattr(CONFIG.composition, "motif_multi_length_enabled", False)):
                motif_lengths = [3, 4, 5]
        except Exception:
            motif_lengths = None
        self.motif_library = MotifLibrary(motif_length=motif_length, motif_lengths=motif_lengths, filter_repeated=True)
        self.motif_prob = motif_prob
        self.motif_variation_prob = motif_variation_prob
        self.rng = rng

    @staticmethod
    def _preferred_variations_for_contour(contour: str) -> List[str]:
        if contour == "asc":
            return ["transpose", "sequence", "augment"]
        if contour == "desc":
            return ["invert", "retrograde", "transpose"]
        if contour == "arch":
            return ["invert", "retrograde", "fragment"]
        return ["transpose", "fragment", "augment"]

    @staticmethod
    def _simplify_harmony_function(chord_symbol: str) -> str:
        return simplify_harmony_function(chord_symbol)

    @staticmethod
    def _harmonic_family(function: str) -> str:
        if function in {"maj", "min", "sus"}:
            return "stable"
        if function in {"dom", "dim", "aug"}:
            return "tense"
        return "stable"

    @staticmethod
    def _motif_profile_fit(motif, emotion_name: str) -> float:
        profile = melody_motif_profile_for_emotion(emotion_name)
        if not profile:
            return 1.0
        score = 1.0
        preferred_contours = [str(v) for v in profile.get("preferred_contours", [])]
        if preferred_contours:
            if getattr(motif, "contour", "") in preferred_contours:
                score *= 1.32
            else:
                score *= 0.88
        density_target = profile.get("density_target")
        if density_target is not None:
            score *= max(0.76, 1.18 - abs(float(getattr(motif, "rhythmic_density", 0.5)) - float(density_target)))
        avg_interval_target = profile.get("avg_interval_target")
        if avg_interval_target is not None:
            score *= max(0.8, 1.2 - 0.18 * abs(float(getattr(motif, "avg_interval", 1.0)) - float(avg_interval_target)))
        return score

    def _motif_harmony_fit(self, motif, current_chord: str, plan: Any, in_cadence_zone: bool) -> float:
        if not current_chord or not getattr(motif, "chord_progression_context", None):
            return 1.0

        current_function = self._simplify_harmony_function(current_chord)
        motif_functions = [
            self._simplify_harmony_function(chord)
            for chord in motif.chord_progression_context
            if chord
        ]
        if not motif_functions:
            return 1.0

        target_function = motif_functions[-1] if in_cadence_zone else motif_functions[0]
        score = 1.0
        if target_function == current_function:
            score *= 1.35
        elif self._harmonic_family(target_function) == self._harmonic_family(current_function):
            score *= 1.15
        else:
            score *= 0.88

        if getattr(plan, "is_final_phrase", False) and in_cadence_zone:
            if current_function in {"maj", "min"} and target_function in {"maj", "min"}:
                score *= 1.08
            elif current_function in {"dom", "dim", "aug"} and target_function in {"dom", "dim", "aug"}:
                score *= 1.06

        return score

    @staticmethod
    def _weighted_choice(rng, items: List[str], weights: List[float]) -> str:
        if not items:
            return ""
        if not weights or len(weights) != len(items):
            return str(items[0])
        try:
            # Determinism: avoid set/dict order; caller passes stable `items`.
            return str(rng.choices(list(items), weights=list(weights), k=1)[0])
        except Exception:
            try:
                return str(rng.choice(list(items)))
            except Exception:
                return str(items[0])

    def _pick_variation_type(
        self,
        *,
        variation_choices: List[str],
        section_role: str,
        development: float,
        strength: float,
    ) -> str:
        """
        Choose a motif transform type in a role- and development-aware way.

        `strength` (0..1) blends between uniform random (0) and weighted policy (1).
        """
        choices = [str(v) for v in (variation_choices or []) if v]
        if not choices:
            return ""
        # Stable order for deterministic weighting.
        choices = sorted(choices)
        r = (section_role or "").strip().lower()
        dev = max(0.0, min(1.0, float(development)))
        s = max(0.0, min(1.0, float(strength)))

        # Base weights (policy = 1.0 everywhere).
        w: Dict[str, float] = {c: 1.0 for c in choices}

        # Role-weighted policy (very lightweight, but makes hooks read more intentionally):
        # - chorus/tag: prefer stable restatements (transpose/sequence), small rhythmic stretch
        # - a_prime/bridge-like: prefer invert/retrograde/fragment (contrast)
        # - verse/pre: prefer light fragment/transpose
        if r in {"b", "chorus", "hook", "tag"}:
            w["transpose"] = 1.6 + 1.0 * (1.0 - dev)
            w["sequence"] = 1.4 + 1.0 * (1.0 - dev)
            w["augment"] = 1.0 + 0.7 * (1.0 - dev)
            w["diminish"] = 0.95 + 0.35 * (1.0 - dev)
            # As development increases, allow more “deconstruction” even in hooks.
            w["fragment"] = 0.75 + 1.05 * dev
            w["invert"] = 0.70 + 0.95 * dev
            w["retrograde"] = 0.65 + 0.85 * dev
        elif r in {"a_prime"}:
            w["invert"] = 1.25 + 1.05 * dev
            w["retrograde"] = 1.10 + 0.95 * dev
            w["fragment"] = 1.15 + 1.25 * dev
            w["sequence"] = 0.95 + 0.65 * (1.0 - dev)
            w["transpose"] = 0.90 + 0.55 * (1.0 - dev)
            w["augment"] = 0.85 + 0.45 * (1.0 - dev)
            w["diminish"] = 0.90 + 0.35 * (1.0 - dev)
        else:
            # a / pre_chorus / intro/outro: keep it subtle.
            w["transpose"] = 1.25 + 0.65 * (1.0 - dev)
            w["fragment"] = 1.05 + 0.85 * dev
            w["sequence"] = 1.05 + 0.55 * (1.0 - dev)
            w["invert"] = 0.75 + 0.55 * dev
            w["retrograde"] = 0.70 + 0.45 * dev
            w["augment"] = 0.90 + 0.35 * (1.0 - dev)
            w["diminish"] = 0.95 + 0.25 * (1.0 - dev)

        # Blend toward uniform using `strength`.
        weights = []
        for c in choices:
            base = 1.0
            pol = float(w.get(c, 1.0))
            weights.append(float(base + (pol - base) * s))
        return self._weighted_choice(self.rng, choices, weights)

    def extract_from_melody(self, melody: List[Tuple[int, float]],
                            source_emotion: str = 'neutral',
                            chord_sequence: Optional[List[str]] = None):
        """Extract motifs from a melody and add them to the library."""
        self.motif_library.extract_from_melody(melody, source_emotion, chord_sequence)

    def try_apply_motif(self,
                        melody_so_far: List[Tuple[int, float]],
                        num_notes_remaining: int,
                        plan: Any,
                        emotion: Any,
                        chord_weights_per_bar: List[Dict[int, float]],
                        bar: int,
                        current_beat: float,
                        beat_positions_out: Optional[List],
                        current_chord: str = "") -> Tuple[bool, List[Tuple[int, float]], List[int], List[float], float]:

        if not self.motif_library.motifs and not getattr(self.motif_library, "rhythm_motifs", None):
            return False, [], [], [], current_beat

        # Determine candidates based on last interval and rhythm
        if len(melody_so_far) >= 2:
            last_interval = melody_so_far[-1][0] - melody_so_far[-2][0]
            last_rhythm = melody_so_far[-1][1]
            candidates = self.motif_library.motifs_starting_with(last_interval, last_rhythm)
        else:
            candidates = self.motif_library.motifs

        # Rhythm-only motifs (optional): use as rhythmic templates.
        rhythm_only = motif_rhythm_only_enabled()
        if rhythm_only:
            try:
                emo_name = emotion.name.lower() if emotion is not None and getattr(emotion, "name", None) else None
                start_r = last_rhythm if len(melody_so_far) >= 1 else 0.25
                candidates = list(candidates or []) + list(self.motif_library.rhythm_motifs_starting_with(float(start_r), emotion=emo_name) or [])
            except Exception:
                pass

        if not candidates:
            return False, [], [], [], current_beat

        # Score candidates
        scored = []
        in_cadence_zone = (
            hasattr(plan, "cadence_zone_start")
            and current_beat % 4.0 >= plan.cadence_zone_start * 4.0
        )
        for motif in candidates:
            score = 1.0

            # Contour match
            if hasattr(plan, 'contour') and motif.contour == plan.contour:
                score *= 2.0

            # Emotion match
            if emotion and motif.source_emotion == emotion.name.lower():
                score *= 1.5
            if emotion:
                score *= self._motif_profile_fit(motif, emotion.name.lower())

            # Chord tone fit: how many notes of the motif fall on chord tones
            if chord_weights_per_bar and bar < len(chord_weights_per_bar) and chord_weights_per_bar[bar]:
                chord_weights = chord_weights_per_bar[bar]
                chord_tones = set(int(d) for d in chord_weights.keys())
                # Simulate the motif starting from current last note
                current_deg = melody_so_far[-1][0]
                motif_degrees = []
                for interval in motif.intervals:
                    current_deg = (current_deg + interval) % 7
                    motif_degrees.append(current_deg)
                chord_tone_count = sum(1 for d in motif_degrees if d in chord_weights)
                score *= (1.0 + chord_tone_count / len(motif.intervals))

                # If motif extraction provided chord-degree context, use it as a stronger
                # compatibility hint (especially on strong beats / cadences).
                try:
                    m_cd = list(getattr(motif, "chord_degrees", []) or [])
                except Exception:
                    m_cd = []
                if m_cd:
                    try:
                        t = float(current_beat)
                        strong_hits = 0
                        for j, dur in enumerate(list(getattr(motif, "rhythms", []) or [])[: len(m_cd)]):
                            beat_phase = float(t) % 1.0
                            strong = (beat_phase < 1e-6) or abs(beat_phase - 0.5) < 1e-6
                            if strong and (j < len(m_cd)):
                                if set(m_cd[j]) & chord_tones:
                                    strong_hits += 1
                            t += float(dur)
                        if strong_hits > 0:
                            bump = 0.12 * float(strong_hits)
                            if in_cadence_zone:
                                bump *= 1.35
                            score *= (1.0 + bump)
                    except Exception:
                        pass

            # Prefer stepwise first interval
            if abs(motif.intervals[0]) <= 2:
                score *= 1.3

            if len(set(motif.intervals)) > 1:
                score *= 1.15
            if motif.rhythmic_density > 0.45:
                score *= 1.08
            if motif.chord_progression_context:
                score *= 1.05
                score *= self._motif_harmony_fit(
                    motif,
                    current_chord=current_chord,
                    plan=plan,
                    in_cadence_zone=in_cadence_zone,
                )

            scored.append((motif, score))

        # Weighted random selection
        total_score = sum(s for _, s in scored)
        r = self.rng.random() * total_score
        cumulative = 0.0
        chosen_motif = None
        for motif, s in scored:
            cumulative += s
            if r <= cumulative:
                chosen_motif = motif
                break

        if not chosen_motif:
            return False, [], [], [], current_beat

        intervals = list(chosen_motif.intervals)
        rhythms = list(chosen_motif.rhythms)

        # Apply variation
        if self.rng.random() < self.motif_variation_prob:
            emotion_name = emotion.name.lower() if emotion is not None and getattr(emotion, "name", None) else ""
            variation_choices = preferred_motif_variations(
                emotion_name,
                self._preferred_variations_for_contour(getattr(plan, "contour", "static")),
            )
            # Role/development-aware transform choice (realtime-safe).
            try:
                from audiogen_core.config import CONFIG

                strength = float(getattr(CONFIG.composition, "hook_transform_strength", 0.0) or 0.0)
                development = float(getattr(CONFIG.composition, "hook_development", 0.5) or 0.5)
            except Exception:
                strength = 0.0
                development = 0.5
            try:
                section_role = str(getattr(plan, "section_role", "") or "")
            except Exception:
                section_role = ""
            var_type = self._pick_variation_type(
                variation_choices=list(variation_choices or []),
                section_role=str(section_role),
                development=float(development),
                strength=float(strength),
            )
            if not var_type:
                var_type = self.rng.choice(variation_choices)
            if var_type == 'augment' and len(intervals) <= num_notes_remaining:
                intervals, rhythms = augment_motif(intervals, rhythms)
            elif var_type == 'diminish' and len(intervals) <= num_notes_remaining:
                intervals, rhythms = diminish_motif(intervals, rhythms)
            elif var_type == 'invert':
                intervals, _ = invert_motif(intervals, rhythms)
            elif var_type == 'retrograde':
                intervals, rhythms = retrograde_motif(intervals, rhythms)
            elif var_type == 'fragment':
                frag_len = self.rng.randint(1, len(intervals))
                intervals, rhythms = fragment_motif(intervals, rhythms, frag_len)
            elif var_type == 'sequence':
                step = self.rng.choice([-2, -1, 1, 2])
                intervals, rhythms = sequence_motif(intervals, rhythms, step)

        if in_cadence_zone:
            rhythms = [min(dur, 1.0) for dur in rhythms]

        # Build notes — rhythm-only motifs act as a rhythmic template while pitches
        # are chosen from chord weights with a stepwise bias.
        new_notes = []
        added_intervals: List[int] = []
        added_rhythms: List[float] = []
        current_deg = melody_so_far[-1][0]
        if bool(getattr(chosen_motif, "is_rhythm_only", False)) or not intervals:
            # Lightweight degree picker (RT-safe).
            for dur in rhythms:
                pool = None
                weights = None
                if chord_weights_per_bar and bar < len(chord_weights_per_bar) and chord_weights_per_bar[bar]:
                    cw = chord_weights_per_bar[bar]
                    ks = sorted(int(k) for k in cw.keys())
                    if ks:
                        pool = ks
                        weights = [float(cw.get(k, 1.0)) for k in ks]
                if not pool:
                    pool = [0, 2, 4, 5, 6]
                    weights = [1.0 for _ in pool]
                try:
                    adj_w = []
                    for deg, w in zip(pool, weights):
                        dist = min((deg - current_deg) % 7, (current_deg - deg) % 7)
                        adj_w.append(float(w) * (1.35 if dist <= 1 else (1.0 if dist <= 2 else 0.75)))
                    nxt = int(self.rng.choices(list(pool), weights=list(adj_w), k=1)[0])
                except Exception:
                    nxt = int(self.rng.choice(list(pool)))
                step = (int(nxt) - int(current_deg)) % 7
                # Choose signed step in [-3..3] for readability of downstream logic.
                if step > 3:
                    step -= 7
                current_deg = int(nxt)
                new_notes.append((int(current_deg), float(dur)))
                added_intervals.append(int(step))
                added_rhythms.append(float(dur))
                if beat_positions_out is not None:
                    beat_positions_out.append(current_beat)
                current_beat += float(dur)
        else:
            # Standard interval motif.
            for step, dur in zip(intervals, rhythms):
                current_deg = (current_deg + step) % 7
                new_notes.append((current_deg, dur))
                added_intervals.append(step)
                added_rhythms.append(dur)
                if beat_positions_out is not None:
                    beat_positions_out.append(current_beat)
                current_beat += dur

        return True, new_notes, added_intervals, added_rhythms, current_beat
