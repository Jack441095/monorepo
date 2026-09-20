from audiogen_core.config import resolve_config
# composition/harmony_manager.py
# Project module `harmony_manager` (composition).

import hashlib
import os
import random
from typing import List, Optional, Tuple

from audiogen_core.composition_runtime_flags import (
    phrase_length_bars_clamped,
    stable_emotion_velocity_multiplier,
    superphrase_length_bars_clamped,
)
from data.music_data import EmotionProfile
from midi.midi_range_limiter import RANGE_LIMITER

from .intent_context import IntentContext


class CompositionHarmonyManager:
    """Coordinates harmony preparation, voicing, and harmony-side event emission."""

    def __init__(self, owner):
        self.owner = owner

    def prepare_chord_progression(
        self,
        emotion: EmotionProfile,
        root_note: int,
        bars: int,
        key_changes: Optional[List[Tuple[int, int]]],
        temperature: float,
        chord_progression: Optional[List[str]],
        section_role: Optional[str] = None,
        *,
        section_index: int = 0,
        form_section_count: int = 1,
        chord_motion_mult: float = 1.0,
        harmony_temperature_mult: float = 1.0,
        cadence_strength_mult: float = 1.0,
    ) -> Tuple[List[str], List[int]]:
        return self.owner.chord_planner.prepare_chord_progression(
            emotion,
            root_note,
            bars,
            key_changes,
            temperature,
            chord_progression,
            section_role=section_role,
            section_index=section_index,
            form_section_count=form_section_count,
            chord_motion_mult=chord_motion_mult,
            harmony_temperature_mult=harmony_temperature_mult,
            cadence_strength_mult=cadence_strength_mult,
        )

    def generate_chord_progression(
        self,
        emotion: EmotionProfile,
        root_note: int,
        bars: int,
        key_changes: Optional[List[Tuple[int, int]]] = None,
        temperature: float = 0.9,
        section_role: Optional[str] = None,
        **kwargs,
    ) -> Tuple[List[str], List[int]]:
        return self.owner.chord_planner.generate_chord_progression(
            emotion,
            root_note,
            bars,
            key_changes,
            temperature,
            section_role=section_role,
            **kwargs,
        )

    def use_voice_leading(
        self,
        chords: List[str],
        roots: List[int],
        bars: int,
        beats_per_bar: float,
        emotion: Optional[EmotionProfile] = None,
    ) -> Tuple[List[int], List[List[int]], List[int]]:
        owner = self.owner
        use_vl = bool(owner.use_voice_leading)
        # Debug/CI safety: allow disabling voice-leading to avoid rare native segfaults
        # observed in long-running test suites when heavy numeric extensions are loaded.
        # (VoiceLeadingEngine is pure Python, but the crash manifests during full-suite runs.)
        if str(os.environ.get("AUDIOGEN_DISABLE_VOICE_LEADING", "") or "").strip() in {"1", "true", "yes", "on"}:
            use_vl = False
        effort = resolve_config("composition", "realtime_effort", 'full')
        rt_mode = str(getattr(owner, "runtime_generation_mode", "normal") or "normal").strip().lower()
        if use_vl and rt_mode != "normal" and (effort == "minimal" or rt_mode in {"preview", "cold_preview"}):
            use_vl = False
        if use_vl:
            emo_name = (getattr(emotion, "name", "") or "").strip().lower() if emotion is not None else ""
            chosen_bass, chosen_chord, chosen_melody, _ = owner.voice_leading_engine.optimise_global(
                chords, roots, bars, beats_per_bar, emotion_name=emo_name
            )
            return chosen_bass, chosen_chord, chosen_melody

        chosen_bass = [owner._get_bass_chord_tones(ch, rt)[0] for ch, rt in zip(chords, roots)]
        chosen_chord = [owner._chord_voicing(ch, rt, style="closed") for ch, rt in zip(chords, roots)]
        chosen_melody = []
        for ch, rt in zip(chords, roots):
            all_notes = owner._chord_symbol_to_notes(ch, rt)
            chosen_melody.append(all_notes[-1] if all_notes else rt + 12)
        return chosen_bass, chosen_chord, chosen_melody

    def generate_bass_events(
        self,
        chords: List[str],
        roots: List[int],
        bars: int,
        beats_per_bar: float,
        chosen_bass: List[int],
        emotion: EmotionProfile,
        *,
        section_role: Optional[str] = None,
        timeline_targets: Optional[dict] = None,
    ) -> List[Tuple]:
        owner = self.owner
        vel_m = stable_emotion_velocity_multiplier(emotion)
        bass_vel_mult = resolve_config("composition", "bass_velocity_multiplier", 1.0, float)
        base_velocity = int(60 * vel_m * bass_vel_mult)
        events: List[Tuple] = []
        role_lc = str(section_role or "").strip().lower()
        targets = timeline_targets or {}
        bass_motif_enabled = resolve_config("composition", "bass_motif_system_enabled", True, bool)
        bass_motif_strength = resolve_config("composition", "bass_motif_system_strength", 0.72, float)
        emotion_bass_enabled = resolve_config("composition", "emotion_bass_personality_enabled", True, bool)
        emotion_bass_strength = resolve_config("composition", "emotion_bass_personality_strength", 0.65, float)
        bass_motif_strength = max(0.0, min(1.0, float(bass_motif_strength)))
        emotion_bass_strength = max(0.0, min(1.0, float(emotion_bass_strength)))
        try:
            emotion_name = str(getattr(emotion, "name", "") or "").strip().lower()
        except Exception:
            emotion_name = ""

        # Cadence walk: in the last half-bar of phrase-final bars, step into the next bar's root.
        # This is subtle but makes cadences feel "played" instead of held.
        cad = resolve_config("composition", "cadence_strength", 1.0, float)
        enabled = cad >= 1.05
        def _root_and_fifth(note0: int, chord: str, root0: int) -> Tuple[int, int]:
            root_note = RANGE_LIMITER.clamp_note(int(note0), 0)
            tones = owner._get_bass_chord_tones(str(chord), int(root0))
            fifth_candidates = [int(n) for n in tones if (int(n) - int(root_note)) % 12 == 7]
            fifth = int(fifth_candidates[0]) if fifth_candidates else int(root_note)
            return int(root_note), RANGE_LIMITER.clamp_note(int(fifth), 0)

        def _emit(note: int, start: float, dur: float, vel: int) -> None:
            events.append((0, int(note), int(max(1, min(127, vel))), float(start), float(dur), [int(note)]))

        def _family_store() -> dict:
            cur = getattr(owner, "_bass_motif_families", None)
            if isinstance(cur, dict):
                return cur
            cur = {}
            try:
                setattr(owner, "_bass_motif_families", cur)
            except Exception:
                pass
            return cur

        def _base_role_key(role_name: str) -> str:
            rl = str(role_name or "").strip().lower()
            if rl in {"a", "verse", "intro"}:
                return "verse"
            if rl in {"pre_chorus"}:
                return "pre_chorus"
            if rl in {"b", "chorus", "hook", "tag"}:
                return "chorus"
            return "release"

        def _choose_family(role_name: str, chord_name: str) -> str:
            store = _family_store()
            key = _base_role_key(role_name)
            existing = str(store.get(key, "") or "").strip().lower()
            if existing:
                return existing

            verse_family = str(store.get("verse", "") or "").strip().lower()
            chord_lc = str(chord_name or "").strip().lower()
            if key == "verse":
                fam = "pedal_root" if ("m" in chord_lc and "maj" not in chord_lc) else "pedal_fifth"
            elif key == "pre_chorus":
                fam = "climb_root" if verse_family == "pedal_root" else "climb_fifth"
            elif key == "chorus":
                fam = "octave_pulse" if verse_family == "pedal_root" else "octave_fifth"
            else:
                fam = "turnaround_root" if verse_family == "pedal_root" else "turnaround_fifth"
            store[key] = str(fam)
            return str(fam)

        phrase_len = phrase_length_bars_clamped(1, 16)
        superphrase_len = superphrase_length_bars_clamped(1, 32)
        for bar in range(int(bars)):
            bass_note = int(chosen_bass[bar]) if bar < len(chosen_bass) else int(chosen_bass[-1])
            if owner.global_scale is not None:
                bass_note = owner._quantize_to_scale(bass_note, emotion)
            bass_note = RANGE_LIMITER.clamp_note(int(bass_note), 0)

            is_phrase_final = (bar % phrase_len) == (phrase_len - 1)
            is_superphrase_final = (bar % superphrase_len) == (superphrase_len - 1)
            is_last_bar = bar == int(bars) - 1
            cadence_window = 0.0
            breath_window = 0.0
            if isinstance(targets, dict):
                try:
                    cadence_window = float((targets.get("cadence_window", []) or [])[bar])
                except Exception:
                    cadence_window = 0.0
                try:
                    breath_window = float((targets.get("breath_window", []) or [])[bar])
                except Exception:
                    breath_window = 0.0
            root_note, fifth_note = _root_and_fifth(int(bass_note), str(chords[bar]), int(roots[bar]))
            bar_start = float(bar) * float(beats_per_bar)
            quarter = float(beats_per_bar) / 4.0
            half = float(beats_per_bar) / 2.0
            family = _choose_family(role_lc, str(chords[bar])) if bass_motif_enabled and bass_motif_strength > 1e-6 else ""

            if emotion_bass_enabled and emotion_bass_strength > 1e-6 and role_lc in {"a", "verse", "pre_chorus", "b", "chorus", "hook", "tag"}:
                if emotion_name in {"grief", "sadness", "remorse", "melancholy"} and not is_last_bar:
                    # Heavier emotions feel more convincing with slow downward gravity
                    # rather than constant octave pumping.
                    if cadence_window >= 0.55 or role_lc in {"a", "verse"}:
                        step_down = RANGE_LIMITER.clamp_note(int(root_note - 2), 0)
                        if owner.global_scale is not None:
                            step_down = int(owner._quantize_to_scale(int(step_down), emotion))
                        step_down = RANGE_LIMITER.clamp_note(int(step_down), 0)
                        _emit(int(root_note), float(bar_start), float(half), int(base_velocity - 2))
                        _emit(int(step_down), float(bar_start + half), float(half), int(base_velocity - 5))
                        continue
                if emotion_name in {"fear", "anxiety", "nervousness", "dread"} and not is_last_bar:
                    # Pedal pressure keeps fear tense without making the bass too melodic.
                    _emit(int(root_note), float(bar_start), float(half), int(base_velocity + 1))
                    _emit(int(root_note), float(bar_start + half), float(half), int(base_velocity - 1))
                    continue
                if emotion_name in {"relief", "peaceful", "serenity", "calm"} and role_lc in {"a", "verse"}:
                    _emit(int(root_note), float(bar_start), float(beats_per_bar), int(base_velocity - 4))
                    continue

            # Section-role bass grammar:
            # - verse: mostly root/half-notes, leave air
            # - pre-chorus: rising/additional motion into the downbeat
            # - chorus/tag: quarters and octave/fifth energy
            # - outro: simpler holds
            if role_lc in {"b", "chorus", "hook", "tag"} and not is_phrase_final and not is_last_bar:
                octave = RANGE_LIMITER.clamp_note(int(root_note + 12), 0)
                if family == "octave_pulse":
                    pattern = [root_note, octave, root_note, octave]
                else:
                    pattern = [root_note, octave, fifth_note, octave]
                for i, note in enumerate(pattern):
                    accent = 6 if i in {0, 2} else 3
                    _emit(int(note), float(bar_start + (i * quarter)), float(quarter), int(base_velocity + accent))
                continue
            if role_lc == "pre_chorus" and not is_last_bar:
                next_root = int(roots[bar + 1]) if (bar + 1) < len(roots) else int(root_note)
                if owner.global_scale is not None:
                    next_root = int(owner._quantize_to_scale(int(next_root), emotion))
                next_root = RANGE_LIMITER.clamp_note(int(next_root), 0)
                delta = int(next_root) - int(root_note)
                step = 0 if int(delta) == 0 else (2 if int(delta) > 0 else -2)
                walk_1 = int(root_note if step == 0 else RANGE_LIMITER.clamp_note(int(root_note + step), 0))
                walk_2 = int(next_root)
                if abs(int(delta)) > 2 and step != 0:
                    walk_2 = int(RANGE_LIMITER.clamp_note(int(next_root - step), 0))
                if owner.global_scale is not None:
                    walk_1 = int(owner._quantize_to_scale(int(walk_1), emotion))
                    walk_2 = int(owner._quantize_to_scale(int(walk_2), emotion))
                walk_1 = RANGE_LIMITER.clamp_note(int(walk_1), 0)
                walk_2 = RANGE_LIMITER.clamp_note(int(walk_2), 0)
                beat2 = int(root_note) if family == "climb_root" else int(fifth_note)
                pattern = [int(root_note), int(beat2), int(walk_1), int(walk_2)]
                for i, note in enumerate(pattern):
                    accent = 6 if i == 3 else (4 if i == 2 else (2 if i == 1 else 0))
                    _emit(int(note), float(bar_start + (i * quarter)), float(quarter), int(base_velocity + accent))
                continue
            if role_lc in {"a", "verse", "intro"} and cadence_window < 0.95 and breath_window < 0.75:
                _emit(int(root_note), float(bar_start), float(half), int(base_velocity))
                second_note = int(root_note) if family == "pedal_root" else int(fifth_note)
                _emit(int(second_note), float(bar_start + half), float(half), int(base_velocity - 2))
                continue
            if role_lc == "outro" and not is_last_bar:
                _emit(int(root_note), float(bar_start), float(beats_per_bar), int(base_velocity - 4))
                continue

            # Treat superphrase boundaries (e.g. bar 7 in 16-bar sections) as structurally important:
            # small approach tone into the next bar improves A->B handoff without extra layers.
            boundary = bool(is_phrase_final or (int(bars) >= 16 and is_superphrase_final))
            if enabled and boundary and not is_last_bar and (bar + 1) < len(roots):
                # Hold for first half-bar, then approach the next root by nearest diatonic-ish step.
                start = float(bar) * float(beats_per_bar)
                half = float(beats_per_bar) / 2.0
                next_root = int(roots[bar + 1])
                if owner.global_scale is not None:
                    next_root = int(owner._quantize_to_scale(int(next_root), emotion))
                next_root = RANGE_LIMITER.clamp_note(int(next_root), 0)

                # Approach tone: step toward next_root by 1–2 semitones (clamped), but don't jump far.
                approach = bass_note
                delta = int(next_root) - int(bass_note)
                if abs(delta) <= 2:
                    approach = int(next_root)
                else:
                    approach = int(bass_note + (2 if delta > 0 else -2))
                    approach = RANGE_LIMITER.clamp_note(int(approach), 0)
                _emit(int(bass_note), float(start), float(half), int(base_velocity))
                _emit(int(approach), float(start + half), float(half), int(base_velocity + 4))
            else:
                if family == "turnaround_fifth" and not is_last_bar and breath_window < 0.75:
                    _emit(int(root_note), float(bar_start), float(half), int(base_velocity - 1))
                    _emit(int(fifth_note), float(bar_start + half), float(half), int(base_velocity + 2))
                else:
                    _emit(int(bass_note), float(bar_start), float(beats_per_bar), int(base_velocity))

        return events

    @staticmethod
    def _rhythmic_chord_layers_enabled() -> bool:
        return resolve_config("composition", "use_rhythmic_chord_layers", True, bool)
    @staticmethod
    def _anchor_root_octave(root_midi: int, reference_notes: List[int]) -> int:
        if not reference_notes:
            return root_midi
        target = sum(reference_notes) / len(reference_notes)
        r = int(root_midi)
        while r + 12 <= target - 8:
            r += 12
        while r > target + 10:
            r -= 12
        return r

    def _voicing_sus4_shell(self, root_midi: int, reference_notes: List[int]) -> List[int]:
        r = self._anchor_root_octave(root_midi, reference_notes)
        candidates = sorted({r, r + 5, r + 7, r + 12, r + 17})
        out = candidates[-4:] if len(candidates) > 4 else candidates
        return out if len(out) >= 3 else sorted({r, r + 5, r + 7})

    def _voicing_power_shell(self, root_midi: int, reference_notes: List[int]) -> List[int]:
        r = self._anchor_root_octave(root_midi, reference_notes)
        return sorted({r, r + 7, r + 12})

    @staticmethod
    def _sus_resolve_role_mult(section_role: Optional[str]) -> float:
        r = (section_role or "").lower()
        return {
            "pre_chorus": 1.38,
            "b": 1.32,
            "tag": 1.22,
            "a_prime": 1.12,
            "a": 1.02,
            "intro": 0.52,
            "outro": 0.48,
        }.get(r, 0.94)

    @staticmethod
    def _half_bar_role_mult(section_role: Optional[str]) -> float:
        r = (section_role or "").lower()
        return {
            "b": 1.24,
            "pre_chorus": 1.14,
            "intro": 1.16,
            "tag": 1.1,
            "a": 1.06,
            "a_prime": 1.08,
            "outro": 0.78,
        }.get(r, 1.0)

    def _quantize_chord_notes(self, notes: List[int], emotion: EmotionProfile) -> List[int]:
        owner = self.owner
        if owner.global_scale is None:
            return list(notes)
        return owner._quantize_notes(list(notes), emotion)

    def schedule_section_harmonic_rhythm_actions(
        self,
        *,
        chords: List[str],
        roots: List[int],
        bars: int,
        beats_per_bar: float,
        emotion: EmotionProfile,
        section_role: Optional[str] = None,
        chord_rhythm_mult: float = 1.0,
        chord_motion_mult: float = 1.0,
        chord_rhythm_targets: Optional[List[float]] = None,
        motif_strength_targets: Optional[List[float]] = None,
        tension_targets: Optional[List[float]] = None,
        section_index: int = 0,
    ) -> List[Optional[str]]:
        """
        Pre-compute per-bar harmonic-rhythm Markov actions using a deterministic RNG stream
        so the arpeggiator and ``generate_chord_events`` can share the same schedule without
        consuming the section's main ``owner.rng`` (which would desync comping choices).

        Updates ``self._hr_action_hist`` the same way the chord generator would, so
        cross-section Markov continuity stays coherent when this schedule is later applied
        as ``hr_action_override`` in ``generate_chord_events``.
        """
        owner = self.owner
        total_bars = max(0, int(bars))
        if total_bars <= 0 or not chords or not roots:
            return []
        phrase_len = phrase_length_bars_clamped(1, 16)
        phrase_len = max(1, min(16, int(phrase_len)))

        def phrase_role_for_bar(bar_idx: int) -> str:
            try:
                return owner.chord_utils.phrase_role(int(bar_idx), int(total_bars), phrase_length=int(phrase_len))
            except Exception:
                return "continuation"

        cadence_style = "authentic"
        try:
            from data.emotion_anchors import anchors_for_emotion

            cadence_style = str(getattr(anchors_for_emotion(emotion), "cadence", "authentic") or "authentic")
        except Exception:
            cadence_style = "authentic"
        cad_first = resolve_config("composition", "cadence_first_harmony_enabled", True, bool)
        if cad_first:
            try:
                bp_style = str(getattr(owner, "_song_blueprint_cadence_style", "") or "").strip().lower()
            except Exception:
                bp_style = ""
            if bp_style in {"closed"}:
                cadence_style = "authentic"
            elif bp_style in {"open"}:
                cadence_style = "suspended"
            elif bp_style in {"deceptive"}:
                cadence_style = "avoid"

        try:
            cadence_profile = getattr(owner, "_section_cadence_strength_profile", None)
            cadence_profile = list(cadence_profile) if isinstance(cadence_profile, list) else []
        except Exception:
            cadence_profile = []
        try:
            hf_profile = getattr(owner, "_section_harmony_function_target_profile", None)
            hf_profile = list(hf_profile) if isinstance(hf_profile, list) else []
        except Exception:
            hf_profile = []

        crm = max(0.5, min(1.55, float(chord_rhythm_mult)))
        motion = max(0.62, min(1.42, float(chord_motion_mult)))
        parts = [
            str(int(section_index)),
            str(section_role or ""),
            str(int(total_bars)),
            str(int(round(float(beats_per_bar) * 100))),
            f"{float(crm):.4f}:{float(motion):.4f}",
            ",".join(str(int(x)) for x in roots[:total_bars]),
            "|".join(str(c or "") for c in chords[:total_bars]),
        ]
        digest = hashlib.blake2b("|".join(parts).encode("utf-8", errors="replace"), digest_size=8).digest()
        seed = int.from_bytes(digest, "little") & 0xFFFFFFFF
        hr_rng = random.Random(int(seed))

        model = getattr(owner, "harmonic_rhythm_model", None)
        saved_model_rng = getattr(model, "rng", None) if model is not None else None
        if model is not None:
            try:
                model.rng = hr_rng
            except Exception:
                pass

        raw_hist = getattr(self, "_hr_action_hist", [])
        hist: List[str] = list(raw_hist) if isinstance(raw_hist, list) else []
        out: List[Optional[str]] = []
        try:
            hr_enabled = resolve_config("composition", "harmonic_rhythm_markov_enabled", True, bool)
            hr_strength = resolve_config("composition", "harmonic_rhythm_markov_strength", 0.65, float)
            hr_strength = max(0.0, min(1.0, float(hr_strength)))

            for bar in range(total_bars):
                action: Optional[str] = None
                if bar >= len(chords) or bar >= len(roots):
                    out.append(None)
                    continue
                sym = owner._simplify_chord_for_markov(chords[bar])
                is_final_bar = bar == total_bars - 1
                role = phrase_role_for_bar(bar)
                is_phrase_final = (int(bar) % int(phrase_len)) == (int(phrase_len) - 1)
                bar_target = 1.0
                if chord_rhythm_targets and bar < len(chord_rhythm_targets):
                    try:
                        bar_target = max(0.45, min(1.75, float(chord_rhythm_targets[bar])))
                    except Exception:
                        bar_target = 1.0
                motif_strength = 0.0
                if motif_strength_targets and bar < len(motif_strength_targets):
                    try:
                        motif_strength = max(0.0, min(1.0, float(motif_strength_targets[bar])))
                    except Exception:
                        motif_strength = 0.0
                tension = 0.85
                if tension_targets and bar < len(tension_targets):
                    try:
                        tension = float(tension_targets[bar])
                    except Exception:
                        tension = 0.85
                tension = float(max(0.0, min(1.35, float(tension))))
                cadence_strength = 0.0
                if cadence_profile and 0 <= int(bar) < len(cadence_profile):
                    try:
                        cadence_strength = max(0.0, min(1.35, float(cadence_profile[int(bar)])))
                    except Exception:
                        cadence_strength = 0.0
                harmony_function_target = ""
                if hf_profile and 0 <= int(bar) < len(hf_profile):
                    try:
                        harmony_function_target = str(hf_profile[int(bar)] or "").strip().upper()
                    except Exception:
                        harmony_function_target = ""
                if not harmony_function_target:
                    if is_phrase_final or role == "cadence":
                        harmony_function_target = "D"
                    elif bar == 0 or role == "opening":
                        harmony_function_target = "T"
                    else:
                        harmony_function_target = "PD"
                try:
                    prof = getattr(owner, "_section_harmonic_motion_profile", None)
                    if isinstance(prof, list) and 0 <= int(bar) < len(prof):
                        bar_target *= float(prof[int(bar)])
                except Exception:
                    pass

                if hr_enabled and hr_strength > 1e-6 and model is not None:
                    try:
                        total_phrases = max(1, (int(total_bars) + int(phrase_len) - 1) // int(phrase_len))
                        phrase_idx = int(int(bar) // int(phrase_len))
                        is_final_phrase = bool(int(phrase_idx) >= max(0, int(total_phrases) - 1))
                        intent = IntentContext(
                            section_role=str(section_role or ""),
                            phrase_role=str(role or ""),
                            contour="static",
                            phrase_idx=int(phrase_idx),
                            total_phrases=int(total_phrases),
                            output_channel=1,
                            cadence_degree=0,
                            cadence_zone_start=0.75,
                            is_final_phrase=bool(is_final_phrase),
                        )
                    except Exception:
                        intent = None
                    allow_sus = sym == "dom" and "sus" not in chords[bar].lower()
                    a = model.next_action(
                        role=str(getattr(intent, "phrase_role", "") if intent else role),
                        history=list(hist)[-2:],
                        temperature=1.0,
                        bar_target=float(bar_target),
                        motif_strength=float(motif_strength),
                        tension=float(tension),
                        cadence_strength=float(cadence_strength),
                        harmony_function_target=str(harmony_function_target),
                        emotion_name=str(getattr(emotion, "name", "") or ""),
                        section_role=str(section_role or ""),
                        allow_sus=bool(allow_sus),
                        cadence_style=str(cadence_style),
                    )
                    if hr_rng.random() < float(hr_strength):
                        action = str(a)
                    hist = (list(hist) + [str(a)])[-6:]

                if is_phrase_final or role == "cadence" or is_final_bar:
                    if str(action or "").lower() in {"anticipate", "half", "double", "triple"}:
                        action = None

                out.append(action)
        finally:
            if model is not None and saved_model_rng is not None:
                try:
                    model.rng = saved_model_rng
                except Exception:
                    pass

        try:
            setattr(self, "_hr_action_hist", hist)
        except Exception:
            pass
        return out

    def generate_chord_events(
        self,
        chords: List[str],
        roots: List[int],
        bars: int,
        beats_per_bar: float,
        chosen_chord: List[List[int]],
        emotion: EmotionProfile,
        section_role: Optional[str] = None,
        chord_rhythm_mult: float = 1.0,
        chord_motion_mult: float = 1.0,
        chord_rhythm_targets: Optional[List[float]] = None,
        motif_strength_targets: Optional[List[float]] = None,
        tension_targets: Optional[List[float]] = None,
        melody_activity_targets: Optional[List[float]] = None,
        melody_onset_steps_by_bar: Optional[List[List[int]]] = None,
        chord_comping_strength_override: Optional[float] = None,
        hr_action_override: Optional[List[Optional[str]]] = None,
    ) -> List[Tuple]:
        owner = self.owner
        rng = getattr(owner, "rng", random)
        chord_note_vel_jitter = 3
        chord_note_vel_jitter = resolve_config("composition", "chord_note_velocity_jitter", 0, int)
        vel_m = stable_emotion_velocity_multiplier(emotion)
        base_velocity = int(80 * vel_m)
        events: List[Tuple] = []
        bpb = float(beats_per_bar)
        use_rhythm = self._rhythmic_chord_layers_enabled() and bpb >= 2.0
        crm = max(0.5, min(1.55, float(chord_rhythm_mult)))
        motion = max(0.62, min(1.42, float(chord_motion_mult)))
        effective_rhythm = max(0.35, min(2.0, crm * motion))
        hr_ov = hr_action_override
        if hr_ov is not None and len(hr_ov) != int(bars):
            hr_ov = None
        total_bars = max(1, int(bars))
        phrase_len = phrase_length_bars_clamped(1, 16)
        phrase_len = max(1, min(16, int(phrase_len)))
        # Debug trace: harmonic-rhythm action chosen per bar (best-effort).
        # Stored on this manager so SectionPlanner can export a compact per-bar trace.
        try:
            self._debug_hr_action_by_bar = [None for _ in range(int(bars))]
        except Exception:
            self._debug_hr_action_by_bar = []
        try:
            self._debug_tension_used_by_bar = [None for _ in range(int(bars))]
        except Exception:
            self._debug_tension_used_by_bar = []

        # Emotion anchors: cadence archetype (authentic/plagal/suspended/avoid)
        cadence_style = "authentic"
        try:
            from data.emotion_anchors import anchors_for_emotion

            cadence_style = str(getattr(anchors_for_emotion(emotion), "cadence", "authentic") or "authentic")
        except Exception:
            cadence_style = "authentic"
        # Optional song-blueprint cadence override (open/closed/deceptive -> rhythmic style map).
        cad_first = resolve_config("composition", "cadence_first_harmony_enabled", True, bool)
        if cad_first:
            try:
                bp_style = str(getattr(owner, "_song_blueprint_cadence_style", "") or "").strip().lower()
            except Exception:
                bp_style = ""
            if bp_style in {"closed"}:
                cadence_style = "authentic"
            elif bp_style in {"open"}:
                cadence_style = "suspended"
            elif bp_style in {"deceptive"}:
                cadence_style = "avoid"

        def phrase_role_for_bar(bar_idx: int) -> str:
            try:
                return owner.chord_utils.phrase_role(int(bar_idx), int(total_bars), phrase_length=int(phrase_len))
            except Exception:
                return "continuation"

        def role_mult(role: str) -> float:
            # Macro harmonic-rhythm behavior:
            # - opening: fewer changes
            # - continuation: more motion
            # - answer: moderate motion + occasional anticipation
            # - cadence: simplify / fewer splits
            return {
                "opening": 0.75,
                "continuation": 1.15,
                "answer": 1.05,
                "cadence": 0.62,
            }.get(role, 1.0)

        # If enabled, allow chord "hits" to vary even when the harmony is held
        # (i.e., decouple voicing rhythm from chord changes).
        decouple = resolve_config("composition", "chord_hits_decouple_from_changes", True, bool)
        try:
            cadence_profile = getattr(owner, "_section_cadence_strength_profile", None)
            cadence_profile = list(cadence_profile) if isinstance(cadence_profile, list) else []
        except Exception:
            cadence_profile = []
        try:
            hf_profile = getattr(owner, "_section_harmony_function_target_profile", None)
            hf_profile = list(hf_profile) if isinstance(hf_profile, list) else []
        except Exception:
            hf_profile = []

        for bar in range(bars):
            # Use the section RNG for comping/hit choices so repeated emotions
            # don't "lock" into the same exact chord-hit pattern per bar.
            drng = rng
            # Keep emitted chord hits in a smooth register (piano-like comping).
            # This is a last-mile safety net in case a voicing style or rhythmic shell
            # would otherwise jump an octave.
            if bar == 0:
                prev_emit_notes = None

            def _median(ns: List[int]) -> Optional[int]:
                if not ns:
                    return None
                nn = sorted(int(n) for n in ns if isinstance(n, int))
                return int(nn[len(nn) // 2]) if nn else None

            def _shift_close(ns: List[int], ref: Optional[List[int]]) -> List[int]:
                try:
                    if not ns:
                        return ns
                    if not ref:
                        return ns
                    m0 = _median(ns)
                    mr = _median(ref)
                    if m0 is None or mr is None:
                        return ns
                    # Choose octave shift minimizing median distance.
                    best = list(ns)
                    best_d = abs(int(m0) - int(mr))
                    for sh in (-24, -12, 0, 12, 24):
                        cand = [int(RANGE_LIMITER.clamp_note(int(n + sh), 1)) for n in ns]
                        mc = _median(cand)
                        if mc is None:
                            continue
                        d = abs(int(mc) - int(mr))
                        if d < best_d:
                            best_d = d
                            best = cand
                    return best
                except Exception:
                    return ns

            chord_notes = list(chosen_chord[bar]) if chosen_chord and bar < len(chosen_chord) else []
            chord_notes = self._quantize_chord_notes(chord_notes, emotion)
            # Safety net: if voicing collapsed (empty/one-tone), regenerate a usable chord
            # so late-bar hits/anticipations can't degrade into a lone stray note.
            if len(chord_notes) < 2:
                try:
                    chord_notes = list(owner._chord_voicing(str(chords[bar]), int(roots[bar]), style="closed") or [])
                except Exception:
                    chord_notes = []
                if len(chord_notes) < 2:
                    try:
                        chord_notes = list(owner._chord_symbol_to_notes(str(chords[bar]), int(roots[bar])) or [])
                    except Exception:
                        chord_notes = chord_notes or [int(roots[bar])]
                chord_notes = self._quantize_chord_notes(list(chord_notes), emotion)
            sym = owner._simplify_chord_for_markov(chords[bar])
            root_m = int(roots[bar])
            bar_start = bar * bpb
            is_final_bar = bar == bars - 1
            role = phrase_role_for_bar(bar)
            is_phrase_final = (int(bar) % int(phrase_len)) == (int(phrase_len) - 1)
            bar_target = 1.0
            if chord_rhythm_targets and bar < len(chord_rhythm_targets):
                try:
                    bar_target = max(0.45, min(1.75, float(chord_rhythm_targets[bar])))
                except Exception:
                    bar_target = 1.0
            motif_strength = 0.0
            if motif_strength_targets and bar < len(motif_strength_targets):
                try:
                    motif_strength = max(0.0, min(1.0, float(motif_strength_targets[bar])))
                except Exception:
                    motif_strength = 0.0
            tension = 0.85
            if tension_targets and bar < len(tension_targets):
                try:
                    tension = float(tension_targets[bar])
                except Exception:
                    tension = 0.85
            tension = float(max(0.0, min(1.35, float(tension))))
            try:
                if isinstance(getattr(self, "_debug_tension_used_by_bar", None), list) and 0 <= int(bar) < len(self._debug_tension_used_by_bar):
                    self._debug_tension_used_by_bar[int(bar)] = float(tension)
            except Exception:
                pass
            mel_act = 0.0
            if melody_activity_targets and bar < len(melody_activity_targets):
                try:
                    mel_act = max(0.0, min(1.0, float(melody_activity_targets[bar])))
                except Exception:
                    mel_act = 0.0
            cadence_strength = 0.0
            if cadence_profile and 0 <= int(bar) < len(cadence_profile):
                try:
                    cadence_strength = max(0.0, min(1.35, float(cadence_profile[int(bar)])))
                except Exception:
                    cadence_strength = 0.0
            harmony_function_target = ""
            if hf_profile and 0 <= int(bar) < len(hf_profile):
                try:
                    harmony_function_target = str(hf_profile[int(bar)] or "").strip().upper()
                except Exception:
                    harmony_function_target = ""
            if not harmony_function_target:
                if is_phrase_final or role == "cadence":
                    harmony_function_target = "D"
                elif bar == 0 or role == "opening":
                    harmony_function_target = "T"
                else:
                    harmony_function_target = "PD"
            # Optional progression-level motion profile (from ChordPlanner template choice).
            try:
                prof = getattr(owner, "_section_harmonic_motion_profile", None)
                if isinstance(prof, list) and 0 <= int(bar) < len(prof):
                    bar_target *= float(prof[int(bar)])
            except Exception:
                pass
            rm = role_mult(role) * effective_rhythm * bar_target

            # Optional harmonic-rhythm Markov: pick an action and map to chord-hit behavior.
            # When ``hr_ov`` is set (shared schedule from ``schedule_section_harmonic_rhythm_actions``),
            # use the precomputed per-bar action and skip RNG + cadence re-processing here.
            action = None
            if hr_ov is not None and bar < len(hr_ov):
                av = hr_ov[bar]
                action = str(av) if av is not None else None
                try:
                    if isinstance(getattr(self, "_debug_hr_action_by_bar", None), list) and 0 <= int(bar) < len(
                        self._debug_hr_action_by_bar
                    ):
                        self._debug_hr_action_by_bar[int(bar)] = str(action) if action is not None else None
                except Exception:
                    pass
            else:
                hr_enabled = resolve_config("composition", "harmonic_rhythm_markov_enabled", True, bool)
                hr_strength = resolve_config("composition", "harmonic_rhythm_markov_strength", 0.65, float)
                hr_strength = max(0.0, min(1.0, float(hr_strength)))
                if hr_enabled and hr_strength > 1e-6 and hasattr(owner, "harmonic_rhythm_model"):
                    try:
                        total_phrases = max(1, (int(bars) + int(phrase_len) - 1) // int(phrase_len))
                        phrase_idx = int(int(bar) // int(phrase_len))
                        is_final_phrase = bool(int(phrase_idx) >= max(0, int(total_phrases) - 1))
                        intent = IntentContext(
                            section_role=str(section_role or ""),
                            phrase_role=str(role or ""),
                            contour="static",
                            phrase_idx=int(phrase_idx),
                            total_phrases=int(total_phrases),
                            output_channel=1,
                            cadence_degree=0,
                            cadence_zone_start=0.75,
                            is_final_phrase=bool(is_final_phrase),
                        )
                    except Exception:
                        intent = None
                    # Use last few actions as context.
                    try:
                        hist = getattr(self, "_hr_action_hist", [])
                        if not isinstance(hist, list):
                            hist = []
                    except Exception:
                        hist = []
                    allow_sus = sym == "dom" and "sus" not in chords[bar].lower()
                    a = owner.harmonic_rhythm_model.next_action(
                        role=str(getattr(intent, "phrase_role", "") if intent else role),
                        history=list(hist)[-2:],
                        temperature=1.0,
                        bar_target=float(bar_target),
                        motif_strength=float(motif_strength),
                        tension=float(tension),
                        cadence_strength=float(cadence_strength),
                        harmony_function_target=str(harmony_function_target),
                        emotion_name=str(getattr(emotion, "name", "") or ""),
                        section_role=str(section_role or ""),
                        allow_sus=bool(allow_sus),
                        cadence_style=str(cadence_style),
                    )
                    # Blend strength: with probability strength, take Markov action; else keep heuristic.
                    if drng.random() < float(hr_strength):
                        action = str(a)
                    hist = (list(hist) + [str(a)])[-6:]
                    setattr(self, "_hr_action_hist", hist)

                # Record chosen/attempted action (even if heuristic path is taken).
                try:
                    if isinstance(getattr(self, "_debug_hr_action_by_bar", None), list) and 0 <= int(bar) < len(
                        self._debug_hr_action_by_bar
                    ):
                        self._debug_hr_action_by_bar[int(bar)] = str(action) if action is not None else None
                except Exception:
                    pass

                # Cadence articulation: do not allow rhythm actions that disrupt phrase endings.
                if is_phrase_final or role == "cadence" or is_final_bar:
                    if str(action or "").lower() in {"anticipate", "half", "double", "triple"}:
                        action = None
                    # Update debug trace to reflect the override.
                    try:
                        if isinstance(getattr(self, "_debug_hr_action_by_bar", None), list) and 0 <= int(bar) < len(
                            self._debug_hr_action_by_bar
                        ):
                            self._debug_hr_action_by_bar[int(bar)] = str(action) if action is not None else None
                    except Exception:
                        pass

            # Only generate rhythmic splits when enabled (decouple), otherwise
            # keep chord hits aligned to harmonic changes.
            sus_roll = decouple and use_rhythm and sym == "dom" and "sus" not in chords[bar].lower()
            half_roll = (
                decouple
                and use_rhythm
                and sym in {"maj", "min"}
                and len(chord_notes) >= 3
                and not is_final_bar
            )

            # Intra-bar harmonic changes (2–3 chord targets inside a bar).
            # This is distinct from "hits": it can actually pull the next chord(s) earlier.
            intra_enabled = resolve_config("composition", "chord_intra_bar_change_enabled", True, bool)
            intra_strength = resolve_config("composition", "chord_intra_bar_change_strength", 0.35, float)
            intra_max = resolve_config("composition", "chord_intra_bar_change_max_splits", 3, int)
            intra_strength = max(0.0, min(1.0, float(intra_strength)))
            intra_max = max(1, min(3, int(intra_max)))
            intra_roll = (
                intra_enabled
                and decouple
                and use_rhythm
                and intra_max >= 2
                and not is_final_bar
                and (bar + 1) < len(chords)
                and (bar + 1) < len(chosen_chord)
            )

            sus_prob = 0.0
            if sus_roll:
                sus_prob = min(
                    0.62, 0.24 * self._sus_resolve_role_mult(section_role) * rm
                )
            if is_phrase_final or role == "cadence" or is_final_bar:
                sus_prob *= 0.45
            half_prob = 0.0
            if half_roll:
                half_prob = min(
                    0.55, 0.19 * self._half_bar_role_mult(section_role) * rm
                )

            intra_prob = 0.0
            if intra_roll and intra_strength > 1e-6:
                # Scale by rhythmic intensity; keep rare on cadence bars.
                base = 0.06 + 0.10 * max(0.0, float(rm) - 0.9)
                if role == "cadence":
                    base *= 0.45
                intra_prob = max(0.0, min(0.45, float(base * float(intra_strength))))
            # Cadence articulation (cinematic): simplify rhythm on cadence/final bars.
            if is_phrase_final or role == "cadence" or is_final_bar:
                intra_roll = False
                intra_prob = 0.0

            # Anticipation: let the next chord arrive slightly before the barline.
            # Only do this in answer/continuation roles, and never in bar 0.
            anticipate_roll = (
                use_rhythm
                and bar > 0
                and not is_final_bar
                and role in {"answer", "continuation"}
                and (bar + 1) < len(chords)
                and (bar + 1) < len(roots)
            )
            anticipate_prob = 0.0
            if anticipate_roll:
                # Small probability, scaled by rhythmic intensity.
                anticipate_prob = min(0.28, 0.06 * rm)
            # Call/response: if the melody is very active in this bar, reduce chord anticipations.
            if mel_act > 1e-6:
                anticipate_prob *= max(0.15, 1.0 - 0.75 * float(mel_act))
            if is_phrase_final or role == "cadence" or is_final_bar:
                anticipate_roll = False
                anticipate_prob = 0.0
                half_roll = False
                half_prob = 0.0

            # ------------------------------------------------------------------
            # Cinematic comping vocabulary (deterministic patterns).
            # This supersedes ad-hoc splits when enabled, so harmony feels "played".
            # ------------------------------------------------------------------
            comp_enabled = resolve_config("composition", "chord_comping_enabled", True, bool)
            comp_strength = resolve_config("composition", "chord_comping_strength", 0.8, float)
            comp_ant = resolve_config("composition", "chord_comping_anticipation_prob", 0.1, float)
            comp_ant_beats = resolve_config("composition", "chord_comping_anticipation_beats", 0.5, float)
            if chord_comping_strength_override is not None:
                try:
                    comp_strength = float(chord_comping_strength_override)
                except Exception:
                    pass
            comp_strength = max(0.0, min(1.0, float(comp_strength)))
            comp_ant = max(0.0, min(0.5, float(comp_ant)))
            comp_ant_beats = max(0.25, min(1.5, float(comp_ant_beats)))
            # Call/response: when the melody is active, simplify comping (more sustain, fewer patterns).
            # When the melody rests, allow more rhythmic motion.
            comp_strength_eff = float(comp_strength) * float(max(0.25, 1.0 - 0.55 * float(mel_act)))

            def _next_voicing(idx: int) -> List[int]:
                if 0 <= int(idx) < len(chosen_chord):
                    nn = list(chosen_chord[int(idx)]) or []
                else:
                    nn = []
                nn = self._quantize_chord_notes(nn, emotion)
                return [RANGE_LIMITER.clamp_note(int(n), 1) for n in nn]

            def _emit(pattern: str, segments: List[Tuple[float, float, List[int], float]]) -> None:
                # segments: (start_off_beats, dur_beats, notes, vel_mult)
                nonlocal prev_emit_notes
                base_v = int(base_velocity)
                # Optional call/response: if a chord hit would start exactly on a planned
                # melody onset, delay it by one grid step (default 16th) to reduce masking.
                onset_link_on = resolve_config("composition", "chords_avoid_melody_onsets_enabled", True, bool)
                onset_link_strength = resolve_config("composition", "chords_avoid_melody_onsets_strength", 1.0, float)
                onset_link_strength = max(0.0, min(1.0, float(onset_link_strength)))
                grid_beats = resolve_config("composition", "chords_avoid_melody_onsets_grid_beats", 0.25, float)
                grid_beats = max(0.125, min(0.5, float(grid_beats)))
                onset_steps = None
                if onset_link_on and onset_link_strength > 1e-9 and melody_onset_steps_by_bar and 0 <= int(bar) < len(melody_onset_steps_by_bar):
                    try:
                        onset_steps = set(int(s) for s in (melody_onset_steps_by_bar[int(bar)] or []) if s is not None)
                    except Exception:
                        onset_steps = None
                for s_off, dur_b, notes_b, vm in segments:
                    if dur_b <= 1e-6 or not notes_b:
                        continue
                    s_eff = float(s_off)
                    d_eff = float(dur_b)
                    if onset_steps is not None and d_eff > 1e-6:
                        try:
                            step = int(round(float(s_eff) / float(grid_beats)))
                        except Exception:
                            step = None
                        if step is not None and int(step) in onset_steps and float(s_eff) <= 1e-9:
                            # Only shift true bar-onset hits; keep mid-bar hits as-is to
                            # preserve comping vocabulary.
                            if float(grid_beats) < float(d_eff) - 1e-9:
                                s_eff = float(s_eff) + float(grid_beats) * float(onset_link_strength)
                                d_eff = max(0.25, float(d_eff) - float(grid_beats) * float(onset_link_strength))
                    n0 = _shift_close([int(n) for n in notes_b], prev_emit_notes)
                    v0 = int(max(1, min(127, round(base_v * float(vm)))))
                    events.append((1, 0, int(v0), float(bar_start + float(s_eff)), float(d_eff), list(n0)))
                    prev_emit_notes = list(n0)
                try:
                    if isinstance(getattr(self, "_debug_hr_action_by_bar", None), list) and 0 <= int(bar) < len(self._debug_hr_action_by_bar):
                        self._debug_hr_action_by_bar[int(bar)] = str(pattern)
                except Exception:
                    pass

            # Choose a pattern (cinematic: mostly holds/swell, rare anticipations).
            if (
                comp_enabled
                and comp_strength_eff > 1e-6
                and decouple
                and use_rhythm
                and role not in {"cadence"}
                and not is_final_bar
                and drng.random() < comp_strength_eff
            ):
                v0 = [RANGE_LIMITER.clamp_note(int(n), 1) for n in chord_notes]
                v1 = _next_voicing(bar + 1)
                v2 = _next_voicing(bar + 2) if (bar + 2) < bars else []

                # Keep harmony-change patterns only when the next chord is meaningfully different.
                if v1 and v0 and set(v1) == set(v0):
                    v1 = list(v0)
                if v2 and v1 and set(v2) == set(v1):
                    v2 = list(v1)

                # Prefer simpler patterns in opening, slightly more motion in continuation/answer.
                pat = "whole_hold"
                if role == "opening":
                    # Occasionally a gentle swell.
                    pat = "swell_then_settle" if drng.random() < 0.35 else "whole_hold"
                else:
                    # If the harmonic-rhythm model explicitly asked for a timing gesture,
                    # honor it deterministically so we actually get intra-bar chord changes.
                    try:
                        act = str(action or "").strip().lower()
                    except Exception:
                        act = ""
                    if act == "half" and v1 and set(v1) != set(v0) and float(mel_act) < 0.70:
                        pat = "half_change"
                    elif act == "anticipate" and v1 and set(v1) != set(v0) and float(mel_act) < 0.70:
                        pat = "anticipate_3and" if rm >= 1.05 else "anticipate_4and"
                    else:
                        # Continuation/answer: allow half-change when motion is high.
                        # If melody is very active, prefer sustained patterns only.
                        if float(mel_act) >= 0.55:
                            pat = "swell_then_settle" if drng.random() < 0.55 else "whole_hold"
                        elif rm >= 1.00 and v1 and set(v1) != set(v0) and drng.random() < (0.72 + 0.20 * max(0.0, 0.35 - float(mel_act))):
                            pat = "half_change"
                        elif rm >= 1.25 and intra_max >= 3 and v2 and set(v2) != set(v1) and drng.random() < 0.35:
                            pat = "thirds_change"
                        else:
                            pat = "swell_then_settle" if drng.random() < 0.45 else "whole_hold"

                        # Anticipation: pull the next chord earlier (only if we have a next chord).
                        if (
                            v1
                            and set(v1) != set(v0)
                            and role in {"answer", "continuation"}
                            and not is_phrase_final
                            and drng.random() < comp_ant * max(0.35, min(1.35, rm)) * max(0.15, 1.0 - 0.75 * float(mel_act))
                        ):
                            # Higher motion -> earlier anticipation.
                            pat = "anticipate_3and" if rm >= 1.18 and drng.random() < 0.55 else "anticipate_4and"

                if pat == "whole_hold":
                    _emit("comp_whole", [(0.0, float(bpb), v0, 1.0)])
                    continue
                if pat == "swell_then_settle":
                    a = max(1.0, min(float(bpb) * 0.4, float(bpb) - 1.0))
                    _emit("comp_swell", [(0.0, a, v0, 0.92), (a, float(bpb) - a, v0, 1.04)])
                    continue
                if pat == "half_change":
                    h = float(bpb) * 0.5
                    _emit("comp_half_change", [(0.0, h, v0, 0.98), (h, h, (v1 or v0), 1.02)])
                    continue
                if pat == "thirds_change":
                    step = float(bpb) / 3.0
                    _emit(
                        "comp_thirds_change",
                        [
                            (0.0, step, v0, 0.98),
                            (step, step, (v1 or v0), 1.01),
                            (2.0 * step, step, (v2 or v1 or v0), 1.00),
                        ],
                    )
                    continue
                if pat == "anticipate_4and":
                    early = max(0.25, min(float(comp_ant_beats), float(bpb) - 0.75))
                    hold = float(bpb) - float(early)
                    _emit("comp_anticipate4and", [(0.0, hold, v0, 0.98), (hold, early, (v1 or v0), 1.02)])
                    continue
                if pat == "anticipate_3and":
                    # Switch to the next chord on beat 3.5 (in 4/4), i.e. one beat before barline.
                    early = max(0.25, min(float(comp_ant_beats), float(bpb) - 1.25))
                    hold = float(bpb) - float(early)
                    _emit("comp_anticipate3and", [(0.0, hold, v0, 0.98), (hold, early, (v1 or v0), 1.02)])
                    continue

            did_sus = (action == "sus") or (sus_roll and drng.random() < sus_prob)
            if did_sus:
                lead = max(1.0, bpb - 1.0)
                tail = max(0.5, bpb - lead)
                sus_notes = self._voicing_sus4_shell(root_m, chord_notes)
                sus_notes = self._quantize_chord_notes(sus_notes, emotion)
                sus_notes = [RANGE_LIMITER.clamp_note(n, 1) for n in sus_notes]
                full_notes = [RANGE_LIMITER.clamp_note(n, 1) for n in chord_notes]
                sus_notes = _shift_close(sus_notes, prev_emit_notes)
                full_notes = _shift_close(full_notes, sus_notes)
                v0 = int(max(1, min(127, round(base_velocity * 0.9))))
                v1 = int(max(1, min(127, round(base_velocity * 1.06))))
                events.append((1, 0, v0, bar_start, lead, sus_notes))
                events.append((1, 0, v1, bar_start + lead, tail, full_notes))
                prev_emit_notes = list(full_notes)
                continue

            # Two-per-bar or three-per-bar harmonic targets.
            if (action in {"double", "triple"}) or (intra_roll and drng.random() < intra_prob):
                # Decide splits: 2 (half) vs 3 (thirds).
                splits = 2
                if intra_max >= 3:
                    # Prefer 3 when rm is very high (busy sections), otherwise 2.
                    thr_p = max(0.0, min(0.55, float((rm - 1.05) * 0.75)))
                    if action == "triple" or (action is None and drng.random() < thr_p):
                        splits = 3

                step_beats = float(bpb) / float(splits)
                # Gather target voicings: current, next, next-next (if needed).
                v0 = [RANGE_LIMITER.clamp_note(int(n), 1) for n in chord_notes]
                v1 = list(chosen_chord[bar + 1]) if (bar + 1) < len(chosen_chord) else []
                v1 = self._quantize_chord_notes(v1, emotion)
                v1 = [RANGE_LIMITER.clamp_note(int(n), 1) for n in v1]
                v2 = []
                if splits >= 3:
                    if (bar + 2) < len(chosen_chord):
                        v2 = list(chosen_chord[bar + 2])
                    else:
                        v2 = list(v1)
                    v2 = self._quantize_chord_notes(v2, emotion)
                    v2 = [RANGE_LIMITER.clamp_note(int(n), 1) for n in v2]

                # If harmony isn't changing, keep it as rhythmic hits instead of fake changes.
                if v1 and v0 and set(v1) == set(v0):
                    v1 = list(v0)
                if v2 and v1 and set(v2) == set(v1):
                    v2 = list(v1)

                # Smooth register against previous emitted notes.
                v0 = _shift_close(v0, prev_emit_notes)
                v1 = _shift_close(v1, v0) if v1 else v1
                v2 = _shift_close(v2, v1) if v2 else v2

                # Slight velocity contour but keep it subtle.
                base_v = int(base_velocity)
                vv = [int(max(1, min(127, round(base_v * f)))) for f in ([0.96, 1.02, 0.99][:splits])]
                evs = [(v0, vv[0]), (v1 or v0, vv[1])]
                if splits >= 3:
                    evs.append((v2 or (v1 or v0), vv[2]))

                for i, (vx, velx) in enumerate(evs):
                    events.append((1, 0, int(velx), float(bar_start + i * step_beats), float(step_beats), list(vx)))
                    prev_emit_notes = list(vx)
                # Record action for debug trace.
                try:
                    if isinstance(getattr(self, "_debug_hr_action_by_bar", None), list) and 0 <= int(bar) < len(self._debug_hr_action_by_bar):
                        self._debug_hr_action_by_bar[int(bar)] = f"intra{splits}"
                except Exception:
                    pass
                continue

            if (action == "anticipate") or (anticipate_roll and drng.random() < anticipate_prob):
                # Bring the next chord in early by splitting the last 1/2 beat.
                # This improves harmonic rhythm without changing the chord sequence.
                early = max(0.5, min(1.0, bpb * 0.25))
                hold = max(0.5, bpb - early)
                # Current chord holds most of the bar.
                full_notes = [RANGE_LIMITER.clamp_note(n, 1) for n in chord_notes]
                full_notes = _shift_close(full_notes, prev_emit_notes)
                v0 = int(max(1, min(127, round(base_velocity * 0.95))))
                events.append((1, 0, v0, bar_start, hold, full_notes))

                # Next chord enters early near the end of the bar.
                # Use the already voice-led chosen chord for continuity.
                next_notes = list(chosen_chord[bar + 1]) if (bar + 1) < len(chosen_chord) else []
                next_notes = self._quantize_chord_notes(next_notes, emotion)
                next_notes = [RANGE_LIMITER.clamp_note(int(n), 1) for n in next_notes]
                if len(next_notes) < 2:
                    # Fallback to current chord (better than a single-note "blip").
                    next_notes = [RANGE_LIMITER.clamp_note(int(n), 1) for n in chord_notes]
                next_notes = _shift_close(next_notes, full_notes)
                v1 = int(max(1, min(127, round(base_velocity * 1.03))))
                events.append((1, 0, v1, bar_start + hold, early, next_notes))
                prev_emit_notes = list(next_notes)
                continue

            if (action == "half") or (half_roll and drng.random() < half_prob):
                h = bpb * 0.5
                shell = self._voicing_power_shell(root_m, chord_notes)
                shell = self._quantize_chord_notes(shell, emotion)
                shell = [RANGE_LIMITER.clamp_note(n, 1) for n in shell]
                full_notes = [RANGE_LIMITER.clamp_note(n, 1) for n in chord_notes]
                shell = _shift_close(shell, prev_emit_notes)
                full_notes = _shift_close(full_notes, shell)
                v0 = int(max(1, min(127, round(base_velocity * 0.92))))
                v1 = int(max(1, min(127, round(base_velocity * 1.03))))
                events.append((1, 0, v0, bar_start, h, shell))
                events.append((1, 0, v1, bar_start + h, h, full_notes))
                prev_emit_notes = list(full_notes)
                continue

            chord_notes = [RANGE_LIMITER.clamp_note(int(n), 1) for n in chord_notes]
            chord_notes = _shift_close(chord_notes, prev_emit_notes)
            events.append((1, 0, base_velocity, bar_start, bpb, chord_notes))
            prev_emit_notes = list(chord_notes)

        # Optional: make chords feel more "human" by jittering velocity slightly per chord tone.
        # We keep the event schema unchanged by expanding poly chord events into per-note events.
        try:
            j = int(chord_note_vel_jitter)
        except Exception:
            j = 0
        j = max(0, min(20, j))
        if j > 0 and events:
            expanded: List[Tuple] = []
            for ev in events:
                try:
                    if not ev or len(ev) != 6:
                        continue
                    ch, midi, vel, st, dur, notes = ev
                    if int(ch) != 1:
                        expanded.append(ev)
                        continue
                    note_list = notes if isinstance(notes, list) else None
                    if note_list:
                        # Emit a per-note chord event so each tone can get its own jitter,
                        # while keeping the overall chord hit stable by using zero-mean offsets.
                        nn_list: List[int] = []
                        for n in note_list:
                            try:
                                nn_list.append(int(n))
                            except Exception:
                                continue
                        if not nn_list:
                            continue
                        offs = [int(drng.randint(-j, j)) for _ in range(len(nn_list))]
                        # Remove mean so the chord's average velocity stays ~constant.
                        mu = int(round(sum(offs) / float(len(offs)))) if offs else 0
                        offs = [int(o - mu) for o in offs]
                        for nn, o in zip(nn_list, offs):
                            vv = int(vel) + int(o)
                            vv = int(max(1, min(127, vv)))
                            expanded.append((1, int(nn), int(vv), st, dur, []))
                    else:
                        # Single-note chord event (rare): jitter the velocity in place.
                        # (No meaningful "overall chord" to preserve here.)
                        vv = int(vel) + int(drng.randint(-j, j))
                        vv = int(max(1, min(127, vv)))
                        expanded.append((1, int(midi), int(vv), st, dur, []))
                except Exception:
                    expanded.append(ev)
            events = expanded

        return events