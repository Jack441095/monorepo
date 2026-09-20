# composition/melody_planner.py
# ---------------------------------------------------------------------------
# Melody event orchestration (Markov lead; block styles resolve via policies).
#
# When ``SectionPlan.harmonic_plan`` is set, pass it as ``harmonic`` so Markov
# phrase weights use the same voiced snapshot as arp/counter. Do not mix ad-hoc
# ``plan.chords`` slices with a stale ``harmonic_plan``; refresh the plan after
# mutating harmony fields (see ``SectionPlan.refresh_harmonic_plan``).
# ---------------------------------------------------------------------------
from typing import List, Optional, Tuple

from data.arp_curve_defaults import ALLOWED_ARP_MODES
from data.music_data import EmotionProfile

from .harmonic_plan import HarmonicPlan


class MelodyPlanner:
    """Owns melody planning/orchestration decisions for a section."""

    def __init__(self, owner):
        self.owner = owner

    @staticmethod
    def expand_bass_notes_per_sixteenth(
        chosen_bass: List[int],
        beats_per_bar: float = 4.0,
        grid: float = 0.25,
    ) -> List[int]:
        steps_per_bar = max(1, int(round(beats_per_bar / grid)))
        expanded: List[int] = []
        for bass_note in chosen_bass:
            expanded.extend([bass_note] * steps_per_bar)
        return expanded

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
        chosen_melody: List[int],
        chosen_bass: Optional[List[int]] = None,
        occupied_intervals: Optional[List[Tuple[float, float]]] = None,
        first_phrase_note_scale: float = 1.0,
        melody_total_notes_mult: float = 1.0,
        melody_max_notes_per_phrase: Optional[int] = None,
        section_role: Optional[str] = None,
        timeline_density_by_bar: Optional[List[float]] = None,
        breath_window_by_bar: Optional[List[float]] = None,
        harmonic: Optional[HarmonicPlan] = None,
    ) -> List[Tuple]:
        if harmonic is not None:
            harmonic.validate()
            chords = list(harmonic.chords)
            roots = list(harmonic.roots)
            bars = int(harmonic.bars)
            beats_per_bar = float(harmonic.beats_per_bar)
            chosen_melody = list(harmonic.chosen_melody)
            chosen_bass = list(harmonic.chosen_bass)
        melody_emotion = self.owner.melody_manager.get_melody_emotion(emotion)
        total_quarter_beats = bars * 4
        bass_notes_per_sixteenth = self.expand_bass_notes_per_sixteenth(
            chosen_bass or [],
            beats_per_bar=beats_per_bar,
        )

        if melody_styles is not None:
            return self.generate_melody_by_blocks(
                melody_emotion,
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
                first_phrase_note_scale=first_phrase_note_scale,
                melody_total_notes_mult=melody_total_notes_mult,
                melody_max_notes_per_phrase=melody_max_notes_per_phrase,
                harmonic=harmonic,
            )

        style = (melody_style or "markov").lower()
        phrase_contours, notes_per_phrase, temp_mult, _ = self.owner.melody_runtime.prepare_melody_parameters(
            melody_emotion,
            bars,
            temperature,
            target_notes_per_bar,
            first_phrase_note_scale=first_phrase_note_scale,
            melody_total_notes_mult=melody_total_notes_mult,
            melody_max_notes_per_phrase=melody_max_notes_per_phrase,
            section_role=section_role,
            timeline_density_by_bar=timeline_density_by_bar,
        )

        if style in {"arp", "arpeggio", "arpeggiated", "chord_arp"}:
            if harmonic is not None:
                harmonic.validate()
                return self.owner.melody_manager.arpeggiator.generate_from_harmonic_plan(
                    melody_emotion,
                    harmonic,
                    target_notes_per_bar,
                    phrase_contours,
                    channel=2,
                    velocity_scale=1.0,
                    chosen_lane=chosen_melody,
                    arp_mode=style if style in ALLOWED_ARP_MODES else None,
                    section_role=section_role,
                )
            return self.owner.melody_manager.arpeggiator.generate_from_chords(
                melody_emotion,
                chords,
                roots,
                bars,
                beats_per_bar,
                target_notes_per_bar,
                phrase_contours=phrase_contours,
                channel=2,
                velocity_scale=1.0,
                chosen_lane=chosen_melody,
                arp_mode=style if style in ALLOWED_ARP_MODES else None,
                section_role=section_role,
            )

        melody_tokens = self.owner.melody_runtime.generate_markov_melody(
            melody_emotion,
            chords,
            roots,
            bars,
            temperature,
            phrase_contours,
            notes_per_phrase,
            temp_mult,
            bass_notes=bass_notes_per_sixteenth,
            total_beats=total_quarter_beats,
            target_melody_notes=chosen_melody,
            section_role=section_role,
            occupied_intervals=occupied_intervals,
            breath_window_by_bar=breath_window_by_bar,
            harmonic=harmonic,
        )
        return self.owner.melody_runtime.convert_melody_tokens_to_events(
            melody_tokens, roots, bars, melody_emotion, beats_per_bar
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
        first_phrase_note_scale: float = 1.0,
        melody_total_notes_mult: float = 1.0,
        melody_max_notes_per_phrase: Optional[int] = None,
        harmonic: Optional[HarmonicPlan] = None,
    ) -> List[Tuple]:
        events = []
        current_bar = 0
        for block_bars, style in melody_styles:
            if current_bar + block_bars > bars:
                block_bars = bars - current_bar
            if block_bars <= 0:
                break

            if harmonic is not None:
                block_harmonic = harmonic.slice_for_bar_range(current_bar, block_bars)
                block_chords = list(block_harmonic.chords)
                block_roots = list(block_harmonic.roots)
                block_melody_notes = list(block_harmonic.chosen_melody)
            else:
                block_chords = chords[current_bar:current_bar + block_bars]
                block_roots = roots[current_bar:current_bar + block_bars]
                block_melody_notes = chosen_melody[current_bar:current_bar + block_bars]

            start_beat = current_bar * beats_per_bar
            fp_scale = first_phrase_note_scale if current_bar == 0 else 1.0
            block_mult = float(melody_total_notes_mult)
            if current_bar > 0:
                block_mult *= 0.98
            phrase_contours, notes_per_phrase, temp_mult, _ = self.owner.melody_runtime.prepare_melody_parameters(
                emotion,
                block_bars,
                temperature,
                target_notes_per_bar,
                first_phrase_note_scale=fp_scale,
                melody_total_notes_mult=block_mult,
                melody_max_notes_per_phrase=melody_max_notes_per_phrase,
                timeline_density_by_bar=None,
            )
            block_hp = harmonic.slice_for_bar_range(current_bar, block_bars) if harmonic is not None else None
            melody_tokens = self.owner.melody_runtime.generate_markov_melody(
                emotion,
                block_chords,
                block_roots,
                block_bars,
                temperature,
                phrase_contours,
                notes_per_phrase,
                temp_mult,
                bass_notes=bass_notes_per_sixteenth,
                total_beats=total_quarter_beats,
                target_melody_notes=block_melody_notes,
                harmonic=block_hp,
            )
            block_events = self.owner.melody_runtime.convert_melody_tokens_to_events(
                melody_tokens, block_roots, block_bars, emotion, beats_per_bar
            )

            for ev in block_events:
                channel, midi, vel, start, dur, notes = ev
                events.append((channel, midi, vel, start + start_beat, dur, notes))

            current_bar += block_bars
        return events
