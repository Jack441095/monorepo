# composition/melody_manager.py
# Project module `melody_manager` (composition).

from typing import List, Optional, Tuple

from data.music_data import EmotionProfile

from .harmonic_plan import HarmonicPlan

from .arpeggiator_engine import Arpeggiator
from .melody_planner import MelodyPlanner
from .melody_runtime import MelodyRuntime


class CompositionMelodyManager:
    """Coordinates melody-specific policy glue, runtime, and planning."""

    def __init__(self, owner):
        self.owner = owner
        self.runtime = MelodyRuntime(owner)
        self.arpeggiator = Arpeggiator(owner)
        self.planner = MelodyPlanner(owner)

    def get_melody_emotion(self, emotion: EmotionProfile) -> EmotionProfile:
        owner = self.owner
        if owner.global_scale is None:
            return emotion
        return EmotionProfile(
            name=emotion.name,
            scale_intervals=owner.global_scale,
            tempo_multiplier=emotion.tempo_multiplier,
            velocity_multiplier=emotion.velocity_multiplier,
            density=emotion.density,
            chord_progressions=emotion.chord_progressions,
        )

    def get_melody_params(self, emotion: EmotionProfile) -> Tuple[float, float]:
        return self.runtime.get_melody_params(emotion)

    def prepare_melody_parameters(
        self,
        emotion: EmotionProfile,
        bars: int,
        temperature: float,
        target_notes_per_bar: float = 4.0,
        *,
        melody_total_notes_mult: float = 1.0,
        melody_max_notes_per_phrase: Optional[int] = None,
        counter_line: bool = False,
        register_last_contours: Optional[bool] = None,
    ) -> Tuple[List[str], List[int], float, float]:
        return self.runtime.prepare_melody_parameters(
            emotion,
            bars,
            temperature,
            target_notes_per_bar,
            melody_total_notes_mult=melody_total_notes_mult,
            melody_max_notes_per_phrase=melody_max_notes_per_phrase,
            counter_line=counter_line,
            register_last_contours=register_last_contours,
        )

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
        harmonic: Optional[HarmonicPlan] = None,
    ) -> List[Tuple[int, float]]:
        return self.runtime.generate_markov_melody(
            emotion,
            chords,
            roots,
            bars,
            temperature,
            phrase_contours,
            notes_per_phrase,
            temp_mult,
            bass_notes=bass_notes,
            total_beats=total_beats,
            target_melody_notes=target_melody_notes,
            counter_line=counter_line,
            section_role=section_role,
            harmonic=harmonic,
        )

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
        return self.runtime.convert_melody_tokens_to_events(
            melody_tokens,
            roots,
            bars,
            emotion,
            beats_per_bar,
            channel=channel,
            velocity_scale=velocity_scale,
            octave_shift=octave_shift,
            octave_shift_probability=octave_shift_probability,
        )

    def generate_melody_events_from_harmonic_plan(
        self,
        emotion: EmotionProfile,
        harmonic: HarmonicPlan,
        temperature: float,
        target_notes_per_bar: float,
        melody_style: str,
        melody_styles: Optional[List[Tuple[int, str]]],
        *,
        occupied_intervals: Optional[List[Tuple[float, float]]] = None,
        first_phrase_note_scale: float = 1.0,
        melody_total_notes_mult: float = 1.0,
        melody_max_notes_per_phrase: Optional[int] = None,
        section_role: Optional[str] = None,
        timeline_density_by_bar: Optional[List[float]] = None,
        breath_window_by_bar: Optional[List[float]] = None,
    ) -> List[Tuple]:
        """Melody entry point keyed on a single :class:`HarmonicPlan` snapshot."""
        harmonic.validate()
        return self.generate_melody_events(
            emotion,
            list(harmonic.chords),
            list(harmonic.roots),
            harmonic.bars,
            harmonic.beats_per_bar,
            temperature,
            target_notes_per_bar,
            melody_style,
            melody_styles,
            list(harmonic.chosen_melody),
            list(harmonic.chosen_bass),
            occupied_intervals=occupied_intervals,
            first_phrase_note_scale=first_phrase_note_scale,
            melody_total_notes_mult=melody_total_notes_mult,
            melody_max_notes_per_phrase=melody_max_notes_per_phrase,
            section_role=section_role,
            timeline_density_by_bar=timeline_density_by_bar,
            breath_window_by_bar=breath_window_by_bar,
            harmonic=harmonic,
        )

    def generate_melody_events(
        self,
        emotion: EmotionProfile,
        chords: List[str],
        roots: List[int],
        bars: int,
        beats_per_bar: float,
        temperature: float,
        target_notes_per_bar: float,
        melody_style: str,
        melody_styles: Optional[List[Tuple[int, str]]],
        chosen_bass: List[int],
        chosen_melody: List[int],
        *,
        occupied_intervals: Optional[List[Tuple[float, float]]] = None,
        first_phrase_note_scale: float = 1.0,
        melody_total_notes_mult: float = 1.0,
        melody_max_notes_per_phrase: Optional[int] = None,
        section_role: Optional[str] = None,
        timeline_density_by_bar: Optional[List[float]] = None,
        breath_window_by_bar: Optional[List[float]] = None,
        harmonic: Optional[HarmonicPlan] = None,
    ) -> List[Tuple]:
        return self.planner.generate_melody_events(
            emotion,
            chords,
            roots,
            bars,
            beats_per_bar,
            temperature,
            target_notes_per_bar,
            melody_style,
            melody_styles,
            chosen_melody,
            chosen_bass,
            occupied_intervals=occupied_intervals,
            first_phrase_note_scale=first_phrase_note_scale,
            melody_total_notes_mult=melody_total_notes_mult,
            melody_max_notes_per_phrase=melody_max_notes_per_phrase,
            section_role=section_role,
            timeline_density_by_bar=timeline_density_by_bar,
            breath_window_by_bar=breath_window_by_bar,
            harmonic=harmonic,
        )

    def generate_melody_by_blocks(
        self,
        emotion: EmotionProfile,
        chords: List[str],
        roots: List[int],
        bars: int,
        beats_per_bar: float,
        temperature: float,
        target_notes_per_bar: float,
        melody_styles: List[Tuple[int, str]],
        chosen_melody: List[int],
        bass_notes_per_sixteenth: Optional[List[int]],
        total_quarter_beats: int,
        harmonic: Optional[HarmonicPlan] = None,
    ) -> List[Tuple]:
        return self.planner.generate_melody_by_blocks(
            emotion,
            chords,
            roots,
            bars,
            beats_per_bar,
            temperature,
            target_notes_per_bar,
            melody_styles,
            chosen_melody,
            bass_notes_per_sixteenth,
            total_quarter_beats,
            harmonic=harmonic,
        )

    def resolve_melody_style(self, style: str, emotion: EmotionProfile) -> str:
        return self.owner.arrangement_policy.resolve_melody_style(style, emotion)
