# ai/markov/melody/ensemble/model_set.py
from typing import Dict, List, Optional, Tuple

from data.music_theory import CHORD_VOICINGS

from ...core.models import IntervalMarkov, PhraseMarkov, RhythmMarkov

from .bucketing import (
    GESTURE_KEYS,
    NUM_PREV_DURATION_BUCKETS,
    phrase_gesture_from_position,
    prev_note_duration_bucket,
)

class MarkovModelSet:
    """Container for all Markov models used in melody generation."""

    def __init__(
        self,
        interval_order: int = 6,
        rhythm_order: int = 4,
        phrase_order: int = 2,
        smoothing: float = 0.01,
        *,
        backoff_decay: float = 0.7,
        use_chord_conditioned: bool = False,
        rng=None,
    ):
        rng = rng or __import__("random")
        self.interval = IntervalMarkov(order=interval_order, smoothing=smoothing, backoff_decay=float(backoff_decay), rng=rng)
        self.rhythm = RhythmMarkov(order=rhythm_order, smoothing=smoothing, backoff_decay=float(backoff_decay), rng=rng)
        self.phrase = PhraseMarkov(order=phrase_order, smoothing=smoothing, backoff_decay=float(backoff_decay), rng=rng)
        self.chord_interval_models: Dict[str, IntervalMarkov] = {}
        # Function-conditioned interval models keyed by (function, phrase_role, bar_in_phrase).
        self.function_interval_models: Dict[Tuple[str, str, int], IntervalMarkov] = {}
        # Function-conditioned rhythm models keyed by (function, phrase_role, bar_in_phrase).
        self.function_rhythm_models: Dict[Tuple[str, str, int], RhythmMarkov] = {}
        self.interval_order = interval_order
        self.rhythm_order = rhythm_order
        self.smoothing = smoothing
        self.backoff_decay = float(backoff_decay)
        self.use_chord_conditioned = use_chord_conditioned
        # Optional global fallback model for blending.
        self.global_fallback: Optional["MarkovModelSet"] = None

        # NEW: contour‑specific interval models
        self.contour_interval_models = {
            'asc': IntervalMarkov(order=interval_order, smoothing=smoothing, backoff_decay=float(backoff_decay), rng=rng),
            'desc': IntervalMarkov(order=interval_order, smoothing=smoothing, backoff_decay=float(backoff_decay), rng=rng),
            'arch': IntervalMarkov(order=interval_order, smoothing=smoothing, backoff_decay=float(backoff_decay), rng=rng),
            'static': IntervalMarkov(order=interval_order, smoothing=smoothing, backoff_decay=float(backoff_decay), rng=rng),
        }

        # NEW: phrase-role interval models (opening/continuation/answer/cadence)
        self.role_interval_models = {
            'opening': IntervalMarkov(order=interval_order, smoothing=smoothing, backoff_decay=float(backoff_decay), rng=rng),
            'continuation': IntervalMarkov(order=interval_order, smoothing=smoothing, backoff_decay=float(backoff_decay), rng=rng),
            'answer': IntervalMarkov(order=interval_order, smoothing=smoothing, backoff_decay=float(backoff_decay), rng=rng),
            'cadence': IntervalMarkov(order=interval_order, smoothing=smoothing, backoff_decay=float(backoff_decay), rng=rng),
        }

        # NEW: phrase-role rhythm models (opening/continuation/answer/cadence)
        self.role_rhythm_models = {
            'opening': RhythmMarkov(order=rhythm_order, smoothing=smoothing, backoff_decay=float(backoff_decay), rng=rng),
            'continuation': RhythmMarkov(order=rhythm_order, smoothing=smoothing, backoff_decay=float(backoff_decay), rng=rng),
            'answer': RhythmMarkov(order=rhythm_order, smoothing=smoothing, backoff_decay=float(backoff_decay), rng=rng),
            'cadence': RhythmMarkov(order=rhythm_order, smoothing=smoothing, backoff_decay=float(backoff_decay), rng=rng),
        }

        # Phase 2a: interval Markov conditioned on preceding note duration bucket.
        self.interval_prev_duration_models: Dict[int, IntervalMarkov] = {
            b: IntervalMarkov(
                order=interval_order,
                smoothing=smoothing,
                backoff_decay=float(backoff_decay),
                rng=rng,
            )
            for b in range(NUM_PREV_DURATION_BUCKETS)
        }

        # Phase 2c: P(next_interval | phrase gesture: opening / middle / cadence).
        self.gesture_interval_models: Dict[str, IntervalMarkov] = {
            g: IntervalMarkov(
                order=interval_order,
                smoothing=smoothing,
                backoff_decay=float(backoff_decay),
                rng=rng,
            )
            for g in GESTURE_KEYS
        }

        # Beat-strength conditioning: downbeat vs offbeat transition models.
        self.beat_interval_models: Dict[str, IntervalMarkov] = {
            "downbeat": IntervalMarkov(order=interval_order, smoothing=smoothing, backoff_decay=float(backoff_decay), rng=rng),
            "offbeat": IntervalMarkov(order=interval_order, smoothing=smoothing, backoff_decay=float(backoff_decay), rng=rng),
        }
        self.beat_rhythm_models: Dict[str, RhythmMarkov] = {
            "downbeat": RhythmMarkov(order=rhythm_order, smoothing=smoothing, backoff_decay=float(backoff_decay), rng=rng),
            "offbeat": RhythmMarkov(order=rhythm_order, smoothing=smoothing, backoff_decay=float(backoff_decay), rng=rng),
        }

        # Register-band conditioning: low / mid / high.
        self.register_interval_models: Dict[str, IntervalMarkov] = {
            "low": IntervalMarkov(order=interval_order, smoothing=smoothing, backoff_decay=float(backoff_decay), rng=rng),
            "mid": IntervalMarkov(order=interval_order, smoothing=smoothing, backoff_decay=float(backoff_decay), rng=rng),
            "high": IntervalMarkov(order=interval_order, smoothing=smoothing, backoff_decay=float(backoff_decay), rng=rng),
        }
        self.register_rhythm_models: Dict[str, RhythmMarkov] = {
            "low": RhythmMarkov(order=rhythm_order, smoothing=smoothing, backoff_decay=float(backoff_decay), rng=rng),
            "mid": RhythmMarkov(order=rhythm_order, smoothing=smoothing, backoff_decay=float(backoff_decay), rng=rng),
            "high": RhythmMarkov(order=rhythm_order, smoothing=smoothing, backoff_decay=float(backoff_decay), rng=rng),
        }

    def train_intervals_and_rhythms(self,
                                    interval_sequences: List[List[int]],
                                    rhythm_sequences: List[List[float]],
                                    sequence_weights: Optional[List[float]] = None):
        if interval_sequences:
            self.interval.train(interval_sequences, sequence_weights=sequence_weights)
        if rhythm_sequences:
            self.rhythm.train(rhythm_sequences, sequence_weights=sequence_weights)

    def train_phrase_contours(self, phrase_contour_sequences: List[List[str]],
                              sequence_weights: Optional[List[float]] = None):
        if phrase_contour_sequences:
            self.phrase.train(phrase_contour_sequences, sequence_weights=sequence_weights)

    # NEW: train contour‑specific interval models
    def train_contour_intervals(self, contour_interval_sequences: Dict[str, List[List[int]]],
                                contour_sequence_weights: Optional[Dict[str, List[float]]] = None):
        for contour, seqs in contour_interval_sequences.items():
            if contour in self.contour_interval_models and seqs:
                weights = None
                if contour_sequence_weights is not None:
                    weights = contour_sequence_weights.get(contour)
                self.contour_interval_models[contour].train(seqs, sequence_weights=weights)

    def train_role_intervals(
        self,
        role_interval_sequences: Dict[str, List[List[int]]],
        role_sequence_weights: Optional[Dict[str, List[float]]] = None,
    ):
        for role, seqs in role_interval_sequences.items():
            if role in self.role_interval_models and seqs:
                weights = None
                if role_sequence_weights is not None:
                    weights = role_sequence_weights.get(role)
                self.role_interval_models[role].train(seqs, sequence_weights=weights)

    def train_role_rhythms(
        self,
        role_rhythm_sequences: Dict[str, List[List[float]]],
        role_sequence_weights: Optional[Dict[str, List[float]]] = None,
    ):
        for role, seqs in role_rhythm_sequences.items():
            if role in self.role_rhythm_models and seqs:
                weights = None
                if role_sequence_weights is not None:
                    weights = role_sequence_weights.get(role)
                self.role_rhythm_models[role].train(seqs, sequence_weights=weights)

    def train_intervals_by_prev_duration_bucket(
        self,
        bucket_to_sequences: Dict[int, List[List[int]]],
        sequence_weights: Optional[Dict[int, List[float]]] = None,
    ) -> None:
        """Train one IntervalMarkov per preceding-duration bucket."""
        for b, seqs in (bucket_to_sequences or {}).items():
            bi = int(b)
            if bi < 0 or bi >= NUM_PREV_DURATION_BUCKETS or not seqs:
                continue
            m = self.interval_prev_duration_models.get(bi)
            if m is None:
                continue
            w = None
            if sequence_weights is not None:
                w = sequence_weights.get(bi)
            m.train(seqs, sequence_weights=w)

    def train_gesture_intervals(
        self,
        gesture_to_sequences: Dict[str, List[List[int]]],
        sequence_weights: Optional[Dict[str, List[float]]] = None,
    ) -> None:
        """Train one IntervalMarkov per phrase-gesture bucket (Phase 2c)."""
        for g, seqs in (gesture_to_sequences or {}).items():
            if g not in self.gesture_interval_models or not seqs:
                continue
            m = self.gesture_interval_models.get(g)
            if m is None:
                continue
            w = None
            if sequence_weights is not None:
                w = sequence_weights.get(g)
            m.train(seqs, sequence_weights=w)

    def get_interval_probs_for_prev_duration_bucket(
        self,
        prev_note_duration: float,
        context: List[int],
        temperature: float = 1.0,
        top_k: Optional[int] = None,
    ) -> Dict[int, float]:
        """P(next_interval | context) from transitions whose preceding note duration matched this bucket."""
        b = prev_note_duration_bucket(prev_note_duration)
        model = self.interval_prev_duration_models.get(b)
        if model is None:
            return {}

        def _sparse(m) -> bool:
            try:
                from audiogen_core.config import CONFIG

                min_ctx = int(getattr(CONFIG.composition, "markov_condition_min_contexts", 24) or 24)
                min_v = int(getattr(CONFIG.composition, "markov_condition_min_vocab", 6) or 6)
            except Exception:
                min_ctx, min_v = 24, 6
            try:
                vocab = int(len(getattr(m, "_vocab_list", []) or []))
            except Exception:
                vocab = 0
            try:
                totals = getattr(m, "totals", {}) or {}
                ctx = int(sum(len(v or {}) for v in totals.values()))
            except Exception:
                ctx = 0
            return bool(vocab < min_v or ctx < min_ctx)

        if _sparse(model):
            return {}
        return model.get_probabilities(context, temperature, top_k)

    def get_interval_probs_for_gesture(
        self,
        phrase_pos: float,
        context: List[int],
        temperature: float = 1.0,
        top_k: Optional[int] = None,
    ) -> Dict[int, float]:
        """P(next_interval | context) from the gesture bucket for normalized phrase position."""
        g = phrase_gesture_from_position(phrase_pos)
        model = self.gesture_interval_models.get(g)
        if model is None:
            return {}

        def _sparse(m) -> bool:
            try:
                from audiogen_core.config import CONFIG

                min_ctx = int(getattr(CONFIG.composition, "markov_condition_min_contexts", 24) or 24)
                min_v = int(getattr(CONFIG.composition, "markov_condition_min_vocab", 6) or 6)
            except Exception:
                min_ctx, min_v = 24, 6
            try:
                vocab = int(len(getattr(m, "_vocab_list", []) or []))
            except Exception:
                vocab = 0
            try:
                totals = getattr(m, "totals", {}) or {}
                ctx = int(sum(len(v or {}) for v in totals.values()))
            except Exception:
                ctx = 0
            return bool(vocab < min_v or ctx < min_ctx)

        if _sparse(model):
            return {}
        return model.get_probabilities(context, temperature, top_k)

    def get_interval_probs(self, context: List[int], temperature: float = 1.0,
                           top_k: Optional[int] = None) -> Dict[int, float]:
        return self.interval.get_probabilities(context, temperature, top_k)

    # NEW: get interval probabilities for a specific contour
    def get_interval_probs_for_contour(self, contour: str, context: List[int],
                                       temperature: float = 1.0) -> Dict[int, float]:
        model = self.contour_interval_models.get(contour, self.interval)
        return model.get_probabilities(context, temperature)

    def get_interval_probs_for_role(
        self,
        role: str,
        context: List[int],
        temperature: float = 1.0,
    ) -> Dict[int, float]:
        model = self.role_interval_models.get(role, self.interval)
        return model.get_probabilities(context, temperature)

    def get_rhythm_probs_for_role(
        self,
        role: str,
        context: List[float],
        temperature: float = 1.0,
    ) -> Dict[float, float]:
        model = self.role_rhythm_models.get(role, self.rhythm)
        return model.get_probabilities(context, temperature)

    def train_beat_conditioned_intervals(
        self,
        beat_interval_sequences: Dict[str, List[List[int]]],
        beat_sequence_weights: Optional[Dict[str, List[float]]] = None,
    ) -> None:
        for k, seqs in (beat_interval_sequences or {}).items():
            kk = str(k or "").strip().lower()
            if kk not in self.beat_interval_models or not seqs:
                continue
            w = None
            if beat_sequence_weights is not None:
                w = beat_sequence_weights.get(kk)
            self.beat_interval_models[kk].train(seqs, sequence_weights=w)

    def train_beat_conditioned_rhythms(
        self,
        beat_rhythm_sequences: Dict[str, List[List[float]]],
        beat_sequence_weights: Optional[Dict[str, List[float]]] = None,
    ) -> None:
        for k, seqs in (beat_rhythm_sequences or {}).items():
            kk = str(k or "").strip().lower()
            if kk not in self.beat_rhythm_models or not seqs:
                continue
            w = None
            if beat_sequence_weights is not None:
                w = beat_sequence_weights.get(kk)
            self.beat_rhythm_models[kk].train(seqs, sequence_weights=w)

    def get_interval_probs_for_beat_bin(
        self,
        beat_bin: str,
        context: List[int],
        temperature: float = 1.0,
        top_k: Optional[int] = None,
    ) -> Dict[int, float]:
        model = self.beat_interval_models.get(str(beat_bin or "").strip().lower())
        if model is None:
            return {}
        # Reuse existing sparse guard logic from duration/gesture paths.
        try:
            from audiogen_core.config import CONFIG

            min_ctx = int(getattr(CONFIG.composition, "markov_condition_min_contexts", 24) or 24)
            min_v = int(getattr(CONFIG.composition, "markov_condition_min_vocab", 6) or 6)
        except Exception:
            min_ctx, min_v = 24, 6
        try:
            vocab = int(len(getattr(model, "_vocab_list", []) or []))
        except Exception:
            vocab = 0
        try:
            totals = getattr(model, "totals", {}) or {}
            ctx_n = int(sum(len(v or {}) for v in totals.values()))
        except Exception:
            ctx_n = 0
        if vocab < min_v or ctx_n < min_ctx:
            return {}
        return model.get_probabilities(context, temperature, top_k)

    def get_rhythm_probs_for_beat_bin(
        self,
        beat_bin: str,
        context: List[float],
        temperature: float = 1.0,
        top_k: Optional[int] = None,
    ) -> Dict[float, float]:
        model = self.beat_rhythm_models.get(str(beat_bin or "").strip().lower())
        if model is None:
            return {}
        try:
            from audiogen_core.config import CONFIG

            min_ctx = int(getattr(CONFIG.composition, "markov_condition_min_contexts", 24) or 24)
            min_v = int(getattr(CONFIG.composition, "markov_condition_min_vocab", 6) or 6)
        except Exception:
            min_ctx, min_v = 24, 6
        try:
            vocab = int(len(getattr(model, "_vocab_list", []) or []))
        except Exception:
            vocab = 0
        try:
            totals = getattr(model, "totals", {}) or {}
            ctx_n = int(sum(len(v or {}) for v in totals.values()))
        except Exception:
            ctx_n = 0
        if vocab < min_v or ctx_n < min_ctx:
            return {}
        return model.get_probabilities(context, temperature, top_k)

    def train_register_conditioned_intervals(
        self,
        register_interval_sequences: Dict[str, List[List[int]]],
        register_sequence_weights: Optional[Dict[str, List[float]]] = None,
    ) -> None:
        for k, seqs in (register_interval_sequences or {}).items():
            kk = str(k or "").strip().lower()
            if kk not in self.register_interval_models or not seqs:
                continue
            w = None
            if register_sequence_weights is not None:
                w = register_sequence_weights.get(kk)
            self.register_interval_models[kk].train(seqs, sequence_weights=w)

    def train_register_conditioned_rhythms(
        self,
        register_rhythm_sequences: Dict[str, List[List[float]]],
        register_sequence_weights: Optional[Dict[str, List[float]]] = None,
    ) -> None:
        for k, seqs in (register_rhythm_sequences or {}).items():
            kk = str(k or "").strip().lower()
            if kk not in self.register_rhythm_models or not seqs:
                continue
            w = None
            if register_sequence_weights is not None:
                w = register_sequence_weights.get(kk)
            self.register_rhythm_models[kk].train(seqs, sequence_weights=w)

    def get_interval_probs_for_register_bin(
        self,
        register_bin: str,
        context: List[int],
        temperature: float = 1.0,
        top_k: Optional[int] = None,
    ) -> Dict[int, float]:
        model = self.register_interval_models.get(str(register_bin or "").strip().lower())
        if model is None:
            return {}
        # Same sparse guard used elsewhere.
        try:
            from audiogen_core.config import CONFIG

            min_ctx = int(getattr(CONFIG.composition, "markov_condition_min_contexts", 24) or 24)
            min_v = int(getattr(CONFIG.composition, "markov_condition_min_vocab", 6) or 6)
        except Exception:
            min_ctx, min_v = 24, 6
        try:
            vocab = int(len(getattr(model, "_vocab_list", []) or []))
        except Exception:
            vocab = 0
        try:
            totals = getattr(model, "totals", {}) or {}
            ctx_n = int(sum(len(v or {}) for v in totals.values()))
        except Exception:
            ctx_n = 0
        if vocab < min_v or ctx_n < min_ctx:
            return {}
        return model.get_probabilities(context, temperature, top_k)

    def get_rhythm_probs_for_register_bin(
        self,
        register_bin: str,
        context: List[float],
        temperature: float = 1.0,
        top_k: Optional[int] = None,
    ) -> Dict[float, float]:
        model = self.register_rhythm_models.get(str(register_bin or "").strip().lower())
        if model is None:
            return {}
        try:
            from audiogen_core.config import CONFIG

            min_ctx = int(getattr(CONFIG.composition, "markov_condition_min_contexts", 24) or 24)
            min_v = int(getattr(CONFIG.composition, "markov_condition_min_vocab", 6) or 6)
        except Exception:
            min_ctx, min_v = 24, 6
        try:
            vocab = int(len(getattr(model, "_vocab_list", []) or []))
        except Exception:
            vocab = 0
        try:
            totals = getattr(model, "totals", {}) or {}
            ctx_n = int(sum(len(v or {}) for v in totals.values()))
        except Exception:
            ctx_n = 0
        if vocab < min_v or ctx_n < min_ctx:
            return {}
        return model.get_probabilities(context, temperature, top_k)

    def get_rhythm_probs(self, context: List[float], temperature: float = 1.0,
                         top_k: Optional[int] = None) -> Dict[float, float]:
        return self.rhythm.get_probabilities(context, temperature, top_k)

    def get_global_interval_probs(self, context: List[int], temperature: float = 1.0) -> Dict[int, float]:
        gf = getattr(self, "global_fallback", None)
        if gf is None:
            return {}
        try:
            return gf.interval.get_probabilities(context, temperature)
        except Exception:
            return {}

    def get_global_rhythm_probs(self, context: List[float], temperature: float = 1.0) -> Dict[float, float]:
        gf = getattr(self, "global_fallback", None)
        if gf is None:
            return {}
        try:
            return gf.rhythm.get_probabilities(context, temperature)
        except Exception:
            return {}

    def get_phrase_probs(self, context: List[str], temperature: float = 1.0,
                         top_k: Optional[int] = None) -> Dict[str, float]:
        return self.phrase.get_probabilities(context, temperature, top_k)

    def get_chord_conditioned_interval_probs(self, chord_quality: str,
                                             context: List[int],
                                             temperature: float = 1.0) -> Dict[int, float]:
        if chord_quality in self.chord_interval_models:
            return self.chord_interval_models[chord_quality].get_probabilities(context, temperature)
        return self.get_interval_probs(context, temperature)

    def train_chord_conditioned_from_sequences(self, chord_quality: str,
                                               interval_sequences: List[List[int]],
                                               sequence_weights: Optional[List[float]] = None):
        if chord_quality not in self.chord_interval_models:
            self.chord_interval_models[chord_quality] = IntervalMarkov(
                order=self.interval.order,
                smoothing=self.smoothing,
                backoff_decay=float(getattr(self, "backoff_decay", 0.7)),
                rng=getattr(self.interval, "rng", None),
            )
        self.chord_interval_models[chord_quality].train(interval_sequences, sequence_weights=sequence_weights)

    @staticmethod
    def extract_chord_quality(chord_symbol: str) -> str:
        for quality in sorted(CHORD_VOICINGS.keys(), key=len, reverse=True):
            if quality in chord_symbol:
                return quality
        return 'maj'  # Default to major if no specific quality is found

    @staticmethod
    def extract_harmonic_function(chord_symbol: str) -> str:
        """
        Functional classifier from parsed Roman numeral/root when available.
        Returns: tonic|predom|dom|other
        """
        s = (chord_symbol or "").strip()
        if not s:
            return "other"
        try:
            from data.chord_parser import parse_chord_symbol

            parsed = parse_chord_symbol(s)
            root = str(getattr(parsed, "root", "") or "")
            if root and getattr(parsed, "is_roman", None) and parsed.is_roman():
                r = root.lower()
                # Dominant family: V, VII°
                if r.startswith("v") or r.startswith("vii"):
                    return "dom"
                # Predominant: II, IV
                if r.startswith(("ii", "iv")):
                    return "predom"
                # Tonic family: I, VI, III
                if r.startswith(("i", "vi", "iii")):
                    return "tonic"
                return "other"
        except Exception:
            pass
        # Fallback: treat explicit dominant-quality chords as dominant-ish.
        try:
            from data.chord_parser import parse_chord_symbol

            q = str(getattr(parse_chord_symbol(s), "quality", "") or "")
            if "dom" in q or q.startswith("7"):
                return "dom"
        except Exception:
            pass
        return "other"

    @staticmethod
    def extract_harmonic_feature_key(chord_symbol: str) -> str:
        """
        Richer harmonic conditioning key.

        Encodes (roman root when available) + quality + secondary dominant target (when present)
        into a stable string, e.g.:
          - "dom|V|7|sec:II"
          - "predom|II|min|sec:none"
          - "tonic|I|maj|sec:none"
          - "other|C|maj7|sec:none"

        This is used for function-conditioned interval/rhythm models so they can
        distinguish V/V from V/ii, etc.
        """
        s = (chord_symbol or "").strip()
        if not s:
            return "other|?|maj|sec:none"
        func = "other"
        root = "?"
        quality = "maj"
        sec = "none"
        try:
            from data.chord_parser import parse_chord_symbol

            parsed = parse_chord_symbol(s)
            root = str(getattr(parsed, "root", "") or "?")
            quality = str(getattr(parsed, "quality", "") or "maj")
            func = MarkovModelSet.extract_harmonic_function(s)
        except Exception:
            # Best-effort fallback: keep stringy classification.
            func = MarkovModelSet.extract_harmonic_function(s)
            root = (s.split(":", 1)[0] if ":" in s else s.split("/", 1)[0]).strip() or "?"
            quality = "maj"

        # Secondary dominants: detect roman target after a slash (V/ii, V7/IV, etc).
        # Note: chord_parser intentionally does NOT treat '/ii' as a bass note.
        try:
            import re

            m = re.search(r"/\s*([#b]?[IiVv]+)", s)
            if m:
                sec = str(m.group(1) or "").strip().upper()
        except Exception:
            pass
        return f"{func}|{root}|{quality}|sec:{sec}"

    def train_function_conditioned_from_sequences(
        self,
        key: Tuple[str, str, int],
        interval_sequences: List[List[int]],
        *,
        sequence_weights: Optional[List[float]] = None,
    ) -> None:
        if key not in self.function_interval_models:
            self.function_interval_models[key] = IntervalMarkov(
                order=self.interval.order,
                smoothing=self.smoothing,
                backoff_decay=float(getattr(self, "backoff_decay", 0.7)),
                rng=getattr(self.interval, "rng", None),
            )
        self.function_interval_models[key].train(interval_sequences, sequence_weights=sequence_weights)

    def get_interval_probs_for_function_key(
        self,
        key: Tuple[str, str, int],
        context: List[int],
        temperature: float = 1.0,
    ) -> Dict[int, float]:
        def _sparse(m) -> bool:
            try:
                from audiogen_core.config import CONFIG

                min_ctx = int(getattr(CONFIG.composition, "markov_condition_min_contexts", 24) or 24)
                min_v = int(getattr(CONFIG.composition, "markov_condition_min_vocab", 6) or 6)
            except Exception:
                min_ctx, min_v = 24, 6
            try:
                vocab = int(len(getattr(m, "_vocab_list", []) or []))
            except Exception:
                vocab = 0
            try:
                totals = getattr(m, "totals", {}) or {}
                ctx = int(sum(len(v or {}) for v in totals.values()))
            except Exception:
                ctx = 0
            return bool(vocab < min_v or ctx < min_ctx)

        model = self.function_interval_models.get(key)
        if model is None or _sparse(model):
            # Hierarchical backoff: feature_key -> function -> unconditioned
            try:
                feat, role, bar_in_phrase = key
                func = str(feat).split("|", 1)[0]
                model2 = self.function_interval_models.get((str(func), str(role), int(bar_in_phrase)))
                if model2 is not None and (not _sparse(model2)):
                    model = model2
            except Exception:
                model = None
        if model is None:
            return {}
        return model.get_probabilities(context, temperature)

    def train_function_conditioned_rhythm_from_sequences(
        self,
        key: Tuple[str, str, int],
        rhythm_sequences: List[List[float]],
        *,
        sequence_weights: Optional[List[float]] = None,
    ) -> None:
        if key not in self.function_rhythm_models:
            self.function_rhythm_models[key] = RhythmMarkov(
                order=self.rhythm.order,
                smoothing=self.smoothing,
                backoff_decay=float(getattr(self, "backoff_decay", 0.7)),
                rng=getattr(self.rhythm, "rng", None),
            )
        self.function_rhythm_models[key].train(rhythm_sequences, sequence_weights=sequence_weights)

    def get_rhythm_probs_for_function_key(
        self,
        key: Tuple[str, str, int],
        context: List[float],
        temperature: float = 1.0,
    ) -> Dict[float, float]:
        def _sparse(m) -> bool:
            try:
                from audiogen_core.config import CONFIG

                min_ctx = int(getattr(CONFIG.composition, "markov_condition_min_contexts", 24) or 24)
                min_v = int(getattr(CONFIG.composition, "markov_condition_min_vocab", 6) or 6)
            except Exception:
                min_ctx, min_v = 24, 6
            try:
                vocab = int(len(getattr(m, "_vocab_list", []) or []))
            except Exception:
                vocab = 0
            try:
                totals = getattr(m, "totals", {}) or {}
                ctx = int(sum(len(v or {}) for v in totals.values()))
            except Exception:
                ctx = 0
            return bool(vocab < min_v or ctx < min_ctx)

        model = self.function_rhythm_models.get(key)
        if model is None or _sparse(model):
            try:
                feat, role, bar_in_phrase = key
                func = str(feat).split("|", 1)[0]
                model2 = self.function_rhythm_models.get((str(func), str(role), int(bar_in_phrase)))
                if model2 is not None and (not _sparse(model2)):
                    model = model2
            except Exception:
                model = None
        if model is None:
            return {}
        return model.get_probabilities(context, temperature)
