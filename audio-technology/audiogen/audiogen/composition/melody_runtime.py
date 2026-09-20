# composition/melody_runtime.py
"""MelodyRuntime: runtime melody parameter prep, generation, and event conversion.

Split 2026-07-14 from a single 1,789-line flat module
(docs/codebase_scan_12_07.md, "large un-decomposed files") into this file
plus three sibling mixin files, layered by dependency (mirrors the
ChordPlanner split done earlier this session and the existing
composition/mixins/ pattern used for CompositionGenerator's
CachingMixin/PerformanceMixin, since MelodyRuntime -- like ChordPlanner -- is
a single class spanning nearly the entire original file, not a set of
independent module-level functions):

  melody_runtime_phrase_plan.py -- leaf layer: phrase-state sequencing,
                                    contour diversification/anti-repeat,
                                    phrase-length alignment, chorus-hook
                                    phrase stabilization/composition, the
                                    transition-pickup writer, and the
                                    counter-line Markov context manager
  melody_runtime_prepare.py     -- prepare_melody_parameters, which only
                                    calls into the leaf layer (via self.)
                                    plus self.owner state
  melody_runtime_rhythm.py      -- bar-intent bridging, phrase rhythm
                                    template selection/application, onset
                                    planning, phrase target/cadence
                                    enforcement, boundary fills -- parallel
                                    to melody_runtime_prepare.py (also only
                                    depends on the leaf layer)
  this file                     -- generate_markov_melody and
                                    convert_melody_tokens_to_events, the top
                                    of the call graph: generate_markov_melody
                                    calls into both the leaf layer and the
                                    rhythm layer (via self.)

Every name the flat module exposed (the `MelodyRuntime` class and its public
methods) is unchanged here, so `from .melody_runtime import MelodyRuntime` /
`from composition.melody_runtime import MelodyRuntime` and
`<owner>.melody_runtime.<method>(...)` call sites (the only import styles
used anywhere in this codebase for this module -- verified via a repo-wide
grep) keep working with zero changes. Because Python resolves `self.<method>`
via MRO at call time, cross-layer calls between the mixins need no imports
between the mixin files themselves; only this file needs to know about all
three and combine them via multiple inheritance.
"""

from __future__ import annotations

import contextlib
import random
from typing import List, Optional, Tuple

from audiogen_core.config import resolve_config
from audiogen_core.composition_runtime_flags import (
    stable_emotion_dynamics_enabled,
    stable_emotion_velocity_multiplier,
)
from data.melody_articulation_profiles import melody_articulation_profile_for_emotion
from data.melody_emotion_profiles import melody_emotion_profile_for_emotion
from data.music_data import EmotionProfile
from midi.midi_range_limiter import RANGE_LIMITER

from .harmonic_plan import HarmonicPlan
from .melody_runtime_phrase_plan import _MelodyPhrasePlanMixin
from .melody_runtime_prepare import _MelodyPrepareMixin
from .melody_runtime_rhythm import _MelodyRhythmMixin


class MelodyRuntime(
    _MelodyPrepareMixin,
    _MelodyRhythmMixin,
    _MelodyPhrasePlanMixin,
):
    """Owns runtime melody parameter prep, generation, and event conversion."""

    def __init__(self, owner):
        self.owner = owner

    def generate_markov_melody(
        self,
        emotion: EmotionProfile,
        chords: List[str],
        roots: List[int],
        bars: int,
        temperature: float,
        phrase_contours: List[str],
        notes_per_phrase: List[int],
        temp_mult: float,
        bass_notes: Optional[List[int]] = None,
        total_beats: Optional[int] = None,
        target_melody_notes: Optional[List[int]] = None,
        counter_line: bool = False,
        section_role: Optional[str] = None,
        occupied_intervals: Optional[List[Tuple[float, float]]] = None,
        breath_window_by_bar: Optional[List[float]] = None,
        harmonic: Optional[HarmonicPlan] = None,
    ) -> List[Tuple[int, float]]:
        del bars
        try:
            if hasattr(self.owner, "_apply_retrained_melody_markov_for_emotion"):
                self.owner._apply_retrained_melody_markov_for_emotion(emotion)
        except Exception:
            pass
        voiced_chords_per_bar: Optional[List[List[int]]] = None
        if harmonic is not None:
            harmonic.validate()
            chords = list(harmonic.chords)
            roots = list(harmonic.roots)
            target_melody_notes = list(harmonic.chosen_melody)
            voiced_chords_per_bar = harmonic.voiced_chords_as_lists()
        ctx = self._counter_line_markov_context() if counter_line else contextlib.nullcontext()
        out_ch = 5 if counter_line else 2

        def _opening_signature(tokens: List[Tuple[int, float]]) -> Optional[Tuple[int, ...]]:
            if not tokens or not roots:
                return None
            scale = list(getattr(emotion, "scale_intervals", []) or [])
            if not scale:
                return None
            # Degree -> midi using the same mapping as the Markov generator.
            def _deg_to_midi(deg: int, root: int) -> int:
                tonic = int(root) - int(scale[0])
                while tonic < 48:
                    tonic += 12
                while tonic > 72:
                    tonic -= 12
                return tonic + int(scale[int(deg) % len(scale)])

            sig = []
            beat = 0.0
            for deg, dur in tokens:
                if not isinstance(deg, int) or deg < 0:
                    beat += float(dur)
                    continue
                bar = int(beat // 4.0)
                root = roots[min(max(0, bar), len(roots) - 1)]
                sig.append(int(_deg_to_midi(int(deg), int(root))))
                beat += float(dur)
                if len(sig) >= 3:
                    break
            return tuple(sig) if sig else None

        max_attempts = 1
        bump = 0.08
        if resolve_config("composition", "melody_avoid_recent_openings", True, bool):
            max_attempts = max(1, int(resolve_config("composition", "melody_opening_max_attempts", 2, int)))
            bump = float(resolve_config("composition", "melody_opening_temp_bump", 0.08, float))
        melody_tokens: List[Tuple[int, float]] = []
        with ctx:
            for attempt in range(max_attempts):
                temp_eff = float(temperature) * float(temp_mult) * (1.0 + bump * float(attempt))
                # Transition handoff: if we know the previous section's lead pitch class,
                # start this section on the closest scale degree. This creates a natural
                # "answer" feeling across section boundaries.
                start_degree = 0
                hctx = {}
                try:
                    hctx = getattr(self.owner, "_emotion_transition_handoff_ctx", None) or {}
                    pc = hctx.get("previous_lead_pc")
                    if pc is not None and roots and emotion and getattr(emotion, "scale_intervals", None):
                        root0 = int(roots[0])
                        scale = list(emotion.scale_intervals)
                        scale_pcs = [int(iv) % 12 for iv in scale]
                        rel = (int(pc) - (root0 % 12)) % 12
                        if scale_pcs:
                            # If rel is not exactly in-scale, choose the nearest scale degree
                            # (circular semitone distance) so chromatic handoffs still connect.
                            def _cdist(a: int, b: int) -> int:
                                d = abs(int(a) - int(b)) % 12
                                return min(d, 12 - d)
                            start_degree = int(min(range(len(scale_pcs)), key=lambda i: _cdist(rel, scale_pcs[i])))
                except Exception:
                    start_degree = 0
                # Plumb handoff context into the Markov melody generator so phrase planning
                # can shape the opening phrase around the previous lead/chord tones.
                prev_ctx = getattr(self.owner.melody_gen, "_transition_handoff_context", None)
                try:
                    setattr(self.owner.melody_gen, "_transition_handoff_context", dict(hctx or {}))
                except Exception:
                    pass
                runtime_mode_value = str(getattr(self.owner, "runtime_generation_mode", "normal") or "normal")
                oq_on = resolve_config("composition", "offline_quality_render_enabled", False, bool)
                if oq_on and runtime_mode_value.strip().lower() not in {"safe", "balanced", "emergency", "preview", "cold_preview"}:
                    runtime_mode_value = "offline_quality"
                hook_ctx = getattr(self.owner, "_joint_hook_degrees", None)
                if not resolve_config("composition", "joint_plan_markov_conditioning_enabled", False, bool):
                    hook_ctx = None
                try:
                    setattr(
                        self.owner.melody_gen,
                        "_joint_hook_degrees",
                        list(hook_ctx) if hook_ctx else None,
                    )
                    tokens = self.owner.melody_gen.generate_with_phrases(
                        phrase_contours=phrase_contours,
                        start_degree=int(start_degree),
                        notes_per_phrase=notes_per_phrase,
                        temperature=temp_eff,
                        emotion=emotion,
                        chords=chords,
                        roots=roots,
                        bass_notes=bass_notes,
                        total_beats=total_beats,
                        target_melody_notes=target_melody_notes,
                        section_role=section_role,
                        output_channel=int(out_ch),
                        occupied_intervals=occupied_intervals,
                        runtime_mode=str(runtime_mode_value),
                        breath_window_by_bar=breath_window_by_bar,
                        voiced_chords_per_bar=voiced_chords_per_bar,
                        bar_intent_by_bar=self._bar_intent_rows_for_current_section(chords=chords),
                    )
                finally:
                    try:
                        setattr(self.owner.melody_gen, "_joint_hook_degrees", None)
                    except Exception:
                        pass
                    try:
                        setattr(self.owner.melody_gen, "_transition_handoff_context", prev_ctx)
                    except Exception:
                        pass
                sig = _opening_signature(tokens)
                recent = set(getattr(self.owner, "recent_melody_openings", ()))
                if sig and sig in recent and attempt + 1 < max_attempts:
                    continue
                melody_tokens = tokens
                break
        # Phrase-level structure passes (audible improvement):
        # - rhythm templates: consistent phrase groove
        # - mid-phrase target: "goal note" before the cadence
        melody_tokens = self._apply_phrase_rhythm_templates(
            melody_tokens,
            emotion=emotion,
            phrase_contours=phrase_contours,
            notes_per_phrase=notes_per_phrase,
            total_beats=total_beats,
            rng=getattr(self.owner, "rng", random),
        )
        melody_tokens = self._enforce_phrase_mid_targets(
            melody_tokens,
            emotion=emotion,
            phrase_contours=phrase_contours,
            notes_per_phrase=notes_per_phrase,
        )
        melody_tokens = self._enforce_phrase_targets(
            melody_tokens,
            emotion=emotion,
            phrase_contours=phrase_contours,
            notes_per_phrase=notes_per_phrase,
        )
        melody_tokens = self._apply_phrase_boundary_fills(
            melody_tokens,
            emotion=emotion,
            phrase_contours=phrase_contours,
            notes_per_phrase=notes_per_phrase,
        )
        hook_on = resolve_config("composition", "chorus_hook_composer_enabled", True, bool)
        hook_strength = resolve_config("composition", "chorus_hook_composer_strength", 0.72, float)
        if hook_on:
            melody_tokens = self._apply_chorus_hook_composer(
                melody_tokens,
                notes_per_phrase=list(notes_per_phrase),
                section_role=section_role,
                strength=float(hook_strength),
            )
        pickup_on = resolve_config("composition", "transition_pickup_writer_enabled", True, bool)
        pickup_strength = resolve_config("composition", "transition_pickup_writer_strength", 0.72, float)
        if pickup_on:
            try:
                next_role = str(getattr(self.owner, "_next_section_role_hint", "") or "")
            except Exception:
                next_role = ""
            melody_tokens = self._apply_transition_pickup_writer(
                melody_tokens,
                notes_per_phrase=list(notes_per_phrase),
                section_role=section_role,
                next_role=next_role,
                hook_anchor_degree=getattr(self.owner, "hook_anchor_degree", None),
                strength=float(pickup_strength),
            )
        contracts_on = resolve_config("composition", "cadence_contracts_enabled", True, bool)
        contracts_strength = resolve_config("composition", "cadence_contracts_strength", 0.76, float)
        if contracts_on:
            melody_tokens = self._enforce_cadence_contracts(
                melody_tokens,
                emotion=emotion,
                phrase_contours=phrase_contours,
                notes_per_phrase=notes_per_phrase,
                section_role=section_role,
                strength=float(contracts_strength),
            )
        return melody_tokens

    def convert_melody_tokens_to_events(
        self,
        melody_tokens: List[Tuple[int, float]],
        roots: List[int],
        bars: int,
        emotion: EmotionProfile,
        beats_per_bar: float = 4.0,
        channel: int = 2,
        velocity_scale: float = 1.0,
        octave_shift: int = 0,
        octave_shift_probability: float = 0.0,
    ) -> List[Tuple]:
        events = []
        scale = emotion.scale_intervals
        # Base velocities: keep lead melody forward in the mix.
        # The sampler's velocity→amplitude mapping is intentionally non-linear, so
        # modest changes here can make a large perceived loudness difference.
        base_v = 60
        if int(channel) == 2:
            base_v = 82
        elif int(channel) == 5:
            # Counter melody should read as a second voice, not disappear.
            # Keep it under the lead (channel 2) but clearly above pads/drone.
            base_v = 72
        vel_m = stable_emotion_velocity_multiplier(emotion)
        current_beat = 0.0
        name = emotion.name.lower()
        articulation = melody_articulation_profile_for_emotion(name)
        gate_mult = max(0.7, min(1.2, float(articulation.get("gate_mult", 1.0))))
        vel_mult = max(0.85, min(1.2, float(articulation.get("velocity_mult", 1.0))))

        emo_profile = melody_emotion_profile_for_emotion(name)

        strict = resolve_config("composition", "emotion_melody_strictness", 0.7, float)
        global_reg_bias = resolve_config("composition", "emotion_melody_register_bias_semitones", 0, int)
        strict = max(0.0, min(1.0, strict))
        base_shift = int(emo_profile.register_shift_semitones)
        blended_shift = int(round(base_shift * strict))
        stable_dyn = stable_emotion_dynamics_enabled()

        for note_index, (degree, duration) in enumerate(melody_tokens):
            if current_beat >= bars * beats_per_bar:
                break
            bar = int(current_beat // beats_per_bar)
            if bar >= bars:
                break

            midi_note = roots[bar] + scale[degree % len(scale)]

            # Emotion-driven register shaping.
            midi_note += blended_shift
            midi_note += int(global_reg_bias)

            if self.owner.global_scale is not None:
                midi_note = self.owner._quantize_to_scale(midi_note, emotion)

            rng = getattr(self.owner, "rng", random)
            # Emotion-specific octave jump for more dramatic registers.
            if emo_profile.octave_jump_chance > 0.0 and rng.random() < float(emo_profile.octave_jump_chance):
                midi_note += 12 if blended_shift >= 0 else -12
            if octave_shift and rng.random() < octave_shift_probability:
                midi_note += octave_shift

            midi_note = RANGE_LIMITER.clamp_note(midi_note, channel)
            density_vel = 1.0
            if not stable_dyn:
                try:
                    density_vel = (1.0 + float(getattr(emotion, "density", 0.0) or 0.0) * 0.3)
                except Exception:
                    density_vel = 1.0
            from composition.velocity_context import VelocityContext

            ctx = VelocityContext(
                channel=channel,
                bar=bar,
                note_index=note_index,
                base_velocity=base_v,
                emotion_vel_mult=vel_m,
                density_vel=density_vel,
                velocity_scale=velocity_scale,
                articulation_vel_mult=vel_mult,
                section_dynamic=1.0,
            )
            velocity = ctx.compute()
            ctx.log_chain()
            event_duration = max(0.1, float(duration) * gate_mult)
            events.append((channel, midi_note, velocity, current_beat, event_duration, [midi_note]))
            current_beat += duration

        return events
