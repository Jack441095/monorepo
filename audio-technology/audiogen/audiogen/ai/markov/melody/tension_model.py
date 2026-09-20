# ai/markov/melody/tension_model.py
# Project module `tension_model` (ai).

import numpy as np

from .harmony_symbol import simplify_harmony_function


class TensionModelMixin:
    """Computes tension based on position in section and modulates biases."""

    @staticmethod
    def _simplify_harmony_function(chord_symbol: str) -> str:
        return simplify_harmony_function(chord_symbol)

    def _compute_tension(self, beat: float, total_beats: int, emotion) -> float:
        """Return tension value 0-1."""
        if total_beats == 0:
            return 0.5
        pos = beat / total_beats
        # Simple arch: rise to 2/3 then fall
        if pos < 0.67:
            tension = pos / 0.67
        else:
            tension = 1.0 - (pos - 0.67) / 0.33
        # Emotion modifier
        if emotion:
            name = emotion.name.lower()
            if 'joy' in name or 'excitement' in name:
                tension *= 1.2
            elif 'sad' in name or 'grief' in name:
                tension *= 0.7
        return float(np.clip(tension, 0.1, 1.0))

    def _apply_tension_biases(self, interval_probs: dict, tension: float):
        """Modify interval probabilities based on tension."""
        # Higher tension favours larger leaps, lower tension favours steps
        for interval in list(interval_probs.keys()):
            if abs(interval) <= 1:
                interval_probs[interval] *= (1.0 - tension * 0.5)  # reduce steps
            else:
                interval_probs[interval] *= (1.0 + tension * 0.5)  # increase leaps
        total = sum(interval_probs.values())
        if total > 0:
            for k in interval_probs:
                interval_probs[k] /= total

    def _compute_phrase_tension(self, pos: float, plan, emotion) -> float:
        """Return a phrase-local tension curve that rises to a planned peak then releases."""
        if plan is None:
            return 0.5

        peak = float(np.clip(getattr(plan, "tension_peak_position", 0.62), 0.15, 0.9))
        peak_weight = max(0.4, float(getattr(plan, "tension_peak_weight", 1.0)))
        release_strength = max(0.5, float(getattr(plan, "cadence_release_strength", 1.0)))
        cadence_zone = float(np.clip(getattr(plan, "cadence_zone_start", 0.75), 0.4, 0.95))
        pos = float(np.clip(pos, 0.0, 1.0))

        if pos <= peak:
            local = pos / max(peak, 1e-6)
        elif pos < cadence_zone:
            settle_span = max(cadence_zone - peak, 1e-6)
            local = 1.0 - ((pos - peak) / settle_span) * 0.2
        else:
            release_span = max(1.0 - cadence_zone, 1e-6)
            release_progress = (pos - cadence_zone) / release_span
            local = 0.8 - release_progress * 0.6 * release_strength

        if emotion is not None:
            name = emotion.name.lower()
            if name in {"joy", "excitement", "anger", "surprise", "amusement", "curiosity"}:
                local *= 1.08
            elif name in {"grief", "sadness", "remorse", "disappointment", "love", "relief", "caring"}:
                local *= 0.88

        return float(np.clip(local * peak_weight, 0.1, 1.0))

    def _compute_harmonic_tension(self, chord_symbol: str, pos: float, plan=None) -> float:
        """Return a harmonic tension scalar based on chord function and phrase position."""
        function = self._simplify_harmony_function(chord_symbol)
        base = {
            "maj": 0.82,
            "min": 0.92,
            "dom": 1.22,
            "dim": 1.18,
            "aug": 1.14,
            "sus": 1.02,
        }.get(function, 1.0)

        cadence_zone = getattr(plan, "cadence_zone_start", 0.75) if plan is not None else 0.75
        if pos >= cadence_zone:
            if function in {"maj", "min"}:
                base *= 0.9
            elif function in {"dom", "dim", "aug"}:
                base *= 1.08

        return float(np.clip(base, 0.7, 1.35))
