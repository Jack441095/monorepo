# ai/markov/melody/generator.py
# Project module `generator` (ai).

from typing import Dict, List, Optional, Tuple

from audiogen_core.constants import DURATIONS
from ai.markov.melody.contour import recompute_beat_positions
from .ensemble import MarkovModelSet
from .generation.phrase_generation import generate_with_phrases as _generate_with_phrases
from .generation.voiceleading_rerank import voiceleading_local_rerank_delta
from .motif_manager import MotifManager
from .note_generator import NoteGenerator
from .phrase_planner import PhrasePlanner
from .phrase_repetition import PhraseRepetitionMixin
from .post_processor import PostProcessor
from .tension_model import TensionModelMixin
from .training import features as _training_features
from .training.train import train_from_melodies as _train_from_melodies
from .voice_leading import VoiceLeadingMixin

_voiceleading_local_rerank_delta = voiceleading_local_rerank_delta


class MelodyGenerator(
    PhraseRepetitionMixin,
    TensionModelMixin,
    VoiceLeadingMixin,
):
    """Main melody generator – facade composing specialized modules."""

    @staticmethod
    def _build_recency_weights(count: int, start: float = 0.7, end: float = 1.3) -> List[float]:
        return _training_features.build_recency_weights(count, start, end)

    @staticmethod
    def _melody_interval_steps(melody: List[Tuple[int, float]], rest_safe: bool) -> List[int]:
        return _training_features.melody_interval_steps(melody, rest_safe)

    @staticmethod
    def _rhythm_token_for_event(degree: int, dur: float, signed_rest: bool) -> float:
        return _training_features.rhythm_token_for_event(degree, dur, signed_rest)

    @staticmethod
    def _interval_sequences_by_prev_duration_bucket(
        melody: List[Tuple[int, float]],
        rest_safe: bool,
    ) -> Dict[int, List[int]]:
        return _training_features.interval_sequences_by_prev_duration_bucket(melody, rest_safe)

    @staticmethod
    def _interval_sequences_by_phrase_gesture(
        melody: List[Tuple[int, float]],
        rest_safe: bool,
    ) -> Dict[str, List[int]]:
        return _training_features.interval_sequences_by_phrase_gesture(melody, rest_safe)

    def __init__(
        self,
        interval_order: int = 3,
        rhythm_order: int = 4,
        phrase_order: int = 2,
        smoothing: float = 0.01,
        motif_length: int = 3,
        motif_prob: float = 0.45,
        max_repetitions: int = 2,
        repeat_penalty: float = 0.1,
        embellishment_prob: float = 0.2,
        motif_variation_prob: float = 0.65,
        enforce_climax: bool = False,
        emotion_intensity: float = 1.0,
        stepwise_boost_base: float = 5.0,
        chord_tone_multiplier: float = 15.0,
        downbeat_chord_multiplier: float = 20.0,
        enforce_chord_tones_prob: float = 0.9,
        enforce_phrase_structure_prob: float = 0.9,
        rest_prob: float = 0.15,
        rest_durations: Optional[List[float]] = None,
        phrase_repetition_prob: float = 0.3,
        max_phrase_memory: int = 100,
        use_chord_conditioned_markov: bool = False,
        use_rejection_sampling: bool = False,
        rejection_max_attempts: int = 3,
        rejection_threshold: float = 10.0,
        phrase_gap_prob: float = 0.0,
        phrase_gap_duration: float = 1.0,
        rng=None,
    ):
        if rng is None:
            import random as _random

            rng = _random
        PhraseRepetitionMixin.__init__(self, phrase_repetition_prob, max_phrase_memory, rng=rng)
        TensionModelMixin.__init__(self)
        VoiceLeadingMixin.__init__(self)

        backoff_decay = 0.7
        try:
            from audiogen_core.config import CONFIG

            backoff_decay = float(getattr(CONFIG.composition, "markov_backoff_decay", 0.7) or 0.7)
        except Exception:
            backoff_decay = 0.7
        self.markov = MarkovModelSet(
            interval_order=interval_order,
            rhythm_order=rhythm_order,
            phrase_order=phrase_order,
            smoothing=smoothing,
            backoff_decay=float(backoff_decay),
            use_chord_conditioned=use_chord_conditioned_markov,
            rng=rng,
        )
        self.rng = rng
        self.motif = MotifManager(
            motif_length=motif_length,
            motif_prob=motif_prob,
            motif_variation_prob=motif_variation_prob,
            rng=self.rng,
        )
        self.planner = PhrasePlanner()
        self.note_gen = NoteGenerator(
            markov_models=self.markov,
            motif_manager=self.motif,
            phrase_planner=self.planner,
            rng=self.rng,
            stepwise_boost_base=stepwise_boost_base,
            chord_tone_multiplier=chord_tone_multiplier,
            downbeat_chord_multiplier=downbeat_chord_multiplier,
            max_repetitions=max_repetitions,
            repeat_penalty=repeat_penalty,
            emotion_intensity=emotion_intensity,
        )
        self.post = PostProcessor(grid=0.25, rng=self.rng)

        self.embellishment_prob = embellishment_prob
        self.enforce_climax = enforce_climax
        self.enforce_chord_tones_prob = enforce_chord_tones_prob
        self.enforce_phrase_structure_prob = enforce_phrase_structure_prob
        self.rest_prob = rest_prob
        self.rest_durations = rest_durations if rest_durations is not None else DURATIONS
        self.use_rejection_sampling = use_rejection_sampling
        self.rejection_max_attempts = rejection_max_attempts
        self.rejection_threshold = rejection_threshold

        self.phrase_gap_prob = phrase_gap_prob
        self.phrase_gap_duration = phrase_gap_duration

        self.interval_markov = self.markov.interval
        self.rhythm_markov = self.markov.rhythm
        self.phrase_markov = self.markov.phrase
        self.motif_library = self.motif.motif_library
        self.motif_prob = motif_prob
        self.motif_variation_prob = motif_variation_prob
        self.max_repetitions = max_repetitions
        self.repeat_penalty = repeat_penalty
        self.stepwise_boost_base = stepwise_boost_base
        self.chord_tone_multiplier = chord_tone_multiplier
        self.downbeat_chord_multiplier = downbeat_chord_multiplier
        self.emotion_intensity = emotion_intensity

    def apply_emotion_params(self, params: dict):
        """Update parameters from an emotion configuration."""
        if "stepwise_boost_base" in params:
            self.stepwise_boost_base = params["stepwise_boost_base"]
            self.note_gen.stepwise_boost_base = params["stepwise_boost_base"]
        if "chord_tone_multiplier" in params:
            self.chord_tone_multiplier = params["chord_tone_multiplier"]
            self.note_gen.chord_tone_multiplier = params["chord_tone_multiplier"]
        if "downbeat_chord_multiplier" in params:
            self.downbeat_chord_multiplier = params["downbeat_chord_multiplier"]
            self.note_gen.downbeat_chord_multiplier = params["downbeat_chord_multiplier"]
        if "emotion_intensity" in params:
            self.emotion_intensity = self.note_gen._sanitize_emotion_intensity(
                params["emotion_intensity"]
            )
            self.note_gen.emotion_intensity = self.emotion_intensity
        if "motif_prob" in params:
            self.motif_prob = params["motif_prob"]
            self.motif.motif_prob = params["motif_prob"]
        if "rest_prob" in params:
            self.rest_prob = params["rest_prob"]
        if "enforce_phrase_structure_prob" in params:
            self.enforce_phrase_structure_prob = params["enforce_phrase_structure_prob"]
        if "embellishment_prob" in params:
            self.embellishment_prob = params["embellishment_prob"]
        if "enforce_chord_tones_prob" in params:
            self.enforce_chord_tones_prob = params["enforce_chord_tones_prob"]
        if "phrase_repetition_prob" in params:
            self.phrase_repetition_prob = params["phrase_repetition_prob"]
        if "max_repetitions" in params:
            self.max_repetitions = self.note_gen._sanitize_max_repetitions(
                params["max_repetitions"]
            )
            self.note_gen.max_repetitions = self.max_repetitions
        if "repeat_penalty" in params:
            self.repeat_penalty = params["repeat_penalty"]
            self.note_gen.repeat_penalty = params["repeat_penalty"]
        if "motif_variation_prob" in params:
            self.motif_variation_prob = params["motif_variation_prob"]
            self.motif.motif_variation_prob = params["motif_variation_prob"]
        if "enforce_climax" in params:
            self.enforce_climax = params["enforce_climax"]
        if "use_rejection_sampling" in params:
            self.use_rejection_sampling = params["use_rejection_sampling"]
        if "rejection_threshold" in params:
            self.rejection_threshold = params["rejection_threshold"]

    def train_from_melodies(
        self,
        melodies: List[List[Tuple[int, float]]],
        phrase_contours: Optional[List[List[str]]] = None,
        phrase_roles: Optional[List[List[str]]] = None,
        emotion_name: str = "neutral",
        emotion_names: Optional[List[str]] = None,
        chord_sequences: Optional[List[List[str]]] = None,
        root_notes: Optional[List[Optional[int]]] = None,
        scale_intervals_by_melody: Optional[List[Optional[List[int]]]] = None,
        beats_per_bar_by_melody: Optional[List[Optional[float]]] = None,
        bpm_by_melody: Optional[List[Optional[float]]] = None,
    ):
        """Train Markov models and motif library from melodies."""
        return _train_from_melodies(
            self,
            melodies,
            phrase_contours=phrase_contours,
            phrase_roles=phrase_roles,
            emotion_name=emotion_name,
            emotion_names=emotion_names,
            chord_sequences=chord_sequences,
            root_notes=root_notes,
            scale_intervals_by_melody=scale_intervals_by_melody,
            beats_per_bar_by_melody=beats_per_bar_by_melody,
            bpm_by_melody=bpm_by_melody,
        )

    def _recompute_beat_positions(
        self, phrase_melody: List[Tuple[int, float]], start_beat: float
    ) -> List[float]:
        return recompute_beat_positions(phrase_melody, start_beat)

    def generate_with_phrases(
        self,
        phrase_contours: List[str],
        start_degree: int,
        notes_per_phrase: List[int],
        temperature: float = 1.0,
        emotion=None,
        chords: Optional[List[str]] = None,
        roots: Optional[List[int]] = None,
        bass_notes: Optional[List[int]] = None,
        total_beats: Optional[int] = None,
        target_melody_notes: Optional[List[int]] = None,
        *,
        section_role: Optional[str] = None,
        output_channel: int = 2,
        occupied_intervals: Optional[List[Tuple[float, float]]] = None,
        runtime_mode: Optional[str] = None,
        breath_window_by_bar: Optional[List[float]] = None,
        voiced_chords_per_bar: Optional[List[List[int]]] = None,
        bar_intent_by_bar: Optional[List[Dict]] = None,
    ) -> List[Tuple[int, float]]:
        return _generate_with_phrases(
            self,
            phrase_contours,
            start_degree,
            notes_per_phrase,
            temperature=temperature,
            emotion=emotion,
            chords=chords,
            roots=roots,
            bass_notes=bass_notes,
            total_beats=total_beats,
            target_melody_notes=target_melody_notes,
            section_role=section_role,
            output_channel=output_channel,
            occupied_intervals=occupied_intervals,
            runtime_mode=runtime_mode,
            breath_window_by_bar=breath_window_by_bar,
            voiced_chords_per_bar=voiced_chords_per_bar,
            bar_intent_by_bar=bar_intent_by_bar,
        )

    def _enforce_climax(self, melody: List[Tuple[int, float]]) -> List[Tuple[int, float]]:
        """Raise the highest-degree note in the melody to scale degree 6 if it
        isn't already there.  The climax is placed at roughly the 2/3 point of
        the melody (the natural tension peak used by TensionModelMixin).

        This is a simple post-hoc nudge — it only touches the single note
        nearest to the target position, leaving all other notes intact.
        """
        if len(melody) < 3:
            return melody

        target_idx = int(len(melody) * 0.67)
        target_degree = 6

        window = max(1, len(melody) // 6)
        lo = max(0, target_idx - window)
        hi = min(len(melody), target_idx + window + 1)
        peak_idx = max(range(lo, hi), key=lambda i: melody[i][0])

        if melody[peak_idx][0] < target_degree:
            deg, dur = melody[peak_idx]
            melody = list(melody)
            melody[peak_idx] = (target_degree, dur)

        return melody
