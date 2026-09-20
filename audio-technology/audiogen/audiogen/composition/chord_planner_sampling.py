# composition/chord_planner_sampling.py
"""Chord sampling and extension-restoration for ChordPlanner.

Split 2026-07-14 from the single 2,065-line chord_planner.py (see
chord_planner_bias.py for the full split rationale). This layer sits above
chord_planner_weighting.py: `sample_next_simplified_chord` calls
`self.build_chord_candidate_weights` (weighting layer) plus leaf-layer bias
helpers, and `restore_chord_extension` calls leaf-layer token helpers plus
`self.owner._simplify_chord_for_markov`.
"""

from __future__ import annotations

import random
from typing import List, Optional

from audiogen_core.config import resolve_config

from composition.intent_context import IntentContext
from composition.scoring_utils import blend_probs, cadence_symbol_weight
from data.music_data import EMOTIONS


class _ChordSamplingMixin:
    """Samples the next simplified chord symbol and restores extensions."""

    def sample_next_simplified_chord(
        self,
        context: List[str],
        simplified_vocab: List[str],
        history: List[str],
        temperature: float,
        repeat_penalty: float,
        bar_in_phrase: int,
        phrase_length: int,
        force_change: bool = False,
        greedy: bool = False,
        k_samples: int = 1,
        change_bonus: float = 0.0,
        cadence_bonus: float = 0.0,
        emotion_name: str = "",
        is_section_start: bool = False,
        is_final_phrase_bar: bool = False,
        phrase_idx: int = 0,
        total_phrases: int = 1,
        previous_phrase_end: str = "",
        section_opening: str = "",
        section_role: Optional[str] = None,
        bar_index: int = 0,
        total_bars: int = 1,
        is_penultimate_section_bar: bool = False,
        is_first_form_section: bool = False,
        is_last_form_section: bool = False,
        cadence_target_degree: Optional[int] = None,
        intent: Optional[IntentContext] = None,
        target_function: Optional[str] = None,
        target_function_strength: float = 0.0,
    ) -> str:
        if intent is not None:
            try:
                if cadence_target_degree is None:
                    cadence_target_degree = int(getattr(intent, "cadence_degree", 0))
            except Exception:
                pass
        markov_probs = self.owner.chord_markov_probabilities(
            context,
            temperature,
            bar_index=int(bar_index),
            section_role=section_role,
        )
        # Optional: blend in phrase-role conditioned chord Markov.
        alpha = resolve_config("composition", "chord_phrase_role_markov_blend", 0.0, float)
        if alpha > 1e-6 and intent is not None:
            try:
                role = str(getattr(intent, "phrase_role", "") or "").strip().lower()
            except Exception:
                role = ""
            role_models = getattr(self.owner, "chord_markov_role_models", {}) or {}
            rm = role_models.get(role)
            if rm is not None:
                try:
                    rp = rm.get_probabilities(context, temperature)
                except Exception:
                    rp = {}
                if rp:
                    markov_probs = blend_probs(markov_probs, rp, float(alpha))
        symbols, weights = self.build_chord_candidate_weights(
            markov_probs,
            simplified_vocab,
            history,
            repeat_penalty,
            bar_in_phrase,
            phrase_length,
            force_change=force_change,
            emotion_name=emotion_name,
            is_section_start=is_section_start,
            phrase_idx=phrase_idx,
            total_phrases=total_phrases,
            previous_phrase_end=previous_phrase_end,
            section_opening=section_opening,
            is_final_section_bar=is_final_phrase_bar,
            section_role=section_role,
            bar_index=bar_index,
            total_bars=total_bars,
            is_penultimate_section_bar=is_penultimate_section_bar,
            is_first_form_section=is_first_form_section,
            is_last_form_section=is_last_form_section,
            target_function=target_function,
            target_function_strength=target_function_strength,
        )
        # Harmony anti-stuck: extra penalty for repeating the last chord token.
        # This is a lightweight complement to repeat_penalty and helps avoid
        # over-long static harmonic runs during joint compositional tests.
        antistuck = resolve_config("composition", "harmony_antistuck_enabled", True, bool)
        rep_mult = resolve_config("composition", "harmony_repeat_penalty_mult", 0.65, float)
        if antistuck and history and symbols and weights:
            try:
                last_tok = str(history[-1] or "")
            except Exception:
                last_tok = ""
            if last_tok:
                updated = list(weights)
                for i, sym in enumerate(symbols):
                    if str(sym) == last_tok:
                        updated[i] = float(updated[i]) * max(0.0, min(1.0, float(rep_mult)))
                total = float(sum(updated))
                if total > 1e-12:
                    weights = [float(w) / total for w in updated]
        if symbols and bar_in_phrase == phrase_length - 1:
            weights = [
                weight * self.cadence_bias(emotion_name, sym, is_final_phrase_bar)
                for sym, weight in zip(symbols, weights)
            ]
            if cadence_target_degree is not None:
                weights = [
                    float(w) * float(cadence_symbol_weight(target_degree=int(cadence_target_degree), symbol=sym))
                    for sym, w in zip(symbols, weights)
                ]
            total = sum(weights)
            if total > 0:
                weights = [weight / total for weight in weights]
        if not symbols:
            candidates = [c for c in simplified_vocab if (not force_change or not history or c != history[-1])]
            if not candidates:
                candidates = simplified_vocab
            rng = getattr(self.owner, "rng", random)
            return rng.choice(candidates)
        if greedy:
            return symbols[max(range(len(symbols)), key=lambda i: weights[i])]

        rng = getattr(self.owner, "rng", random)
        k = max(1, int(k_samples))
        oq_on = resolve_config("composition", "offline_quality_render_enabled", False, bool)
        oq_scale = resolve_config("composition", "offline_quality_k_scale", 1.6, float)
        if oq_on:
            k = max(1, int(round(float(k) * max(1.0, float(oq_scale)))))
        if k == 1:
            return rng.choices(symbols, weights=weights)[0]

        # K-sample rerank: draw a few candidates from the current distribution and pick
        # the one that best fits simple musical objectives (motion + cadence strength).
        last = history[-1] if history else None
        role = self.phrase_role(int(phrase_idx), int(total_phrases))
        if intent is not None:
            try:
                role = str(getattr(intent, "phrase_role", "") or role)
            except Exception:
                pass
        is_cadence = role == "cadence" or bool(is_final_phrase_bar) or (bar_in_phrase == phrase_length - 1)

        def score(sym: str) -> float:
            try:
                p = float(weights[symbols.index(sym)])
            except Exception:
                p = 0.0
            s = p
            if last is not None and sym != last:
                s += float(change_bonus)
            if is_cadence and sym in {"maj", "dom"}:
                s += float(cadence_bonus)
            if is_cadence and cadence_target_degree is not None:
                s += 0.04 * float(cadence_symbol_weight(target_degree=int(cadence_target_degree), symbol=sym))
            return s

        candidates = rng.choices(symbols, weights=weights, k=k)
        best = max(candidates, key=score)
        return best

    def restore_chord_extension(
        self,
        base_chord: str,
        emotion_name: str,
        section_role: Optional[str] = None,
    ) -> str:
        # Backwards compatibility: `base_chord` used to be a simplified bucket.
        # Now we also accept rich tokens like "V:dom" or "bVII:maj".
        token = str(base_chord or "").strip()
        bucket = self._token_bucket(token)
        degree = self._token_degree(token)

        emotion_vocab = []
        for emo in EMOTIONS:
            if emo.name.lower() == emotion_name.lower():
                for progression in emo.chord_progressions:
                    for chord in progression:
                        try:
                            if degree:
                                if self._markov_token(chord) == token:
                                    emotion_vocab.append(chord)
                            else:
                                if self.owner._simplify_chord_for_markov(chord) == bucket:
                                    emotion_vocab.append(chord)
                        except Exception:
                            continue
                break

        role_lc = str(section_role or "").strip().lower()
        pop_clean_role = role_lc in {"intro", "a", "pre_chorus", "b", "a_prime", "tag", "outro"}
        stable_emotion = str(emotion_name or "").strip().lower() in {
            "neutral",
            "calm",
            "relief",
            "love",
            "admiration",
            "gratitude",
            "caring",
            "sadness",
            "grief",
            "remorse",
            "disappointment",
            "realization",
            "desire",
            "embarrassment",
        }
        prefer_pop_clean = bool(pop_clean_role or stable_emotion)

        if emotion_vocab:
            counts = {}
            for chord in emotion_vocab:
                counts[chord] = counts.get(chord, 0) + 1
            choices = list(counts.keys())
            weights = list(counts.values())
            adjusted_weights = []
            for chord, weight in zip(choices, weights):
                adjusted = float(weight)
                if bucket == "maj":
                    if "maj7" in chord and "maj13" not in chord and "maj9" not in chord:
                        adjusted *= 1.22
                    if "maj9" in chord or "6" in chord or "add9" in chord:
                        adjusted *= 1.18
                    if "maj13" in chord:
                        adjusted *= 1.08
                    if "7#11" in chord:
                        adjusted *= 0.95
                elif bucket == "min":
                    if "min9" in chord or "min11" in chord:
                        adjusted *= 1.2
                    if "maj7" in chord:
                        adjusted *= 0.8
                elif bucket == "dom":
                    if "13" in chord or "9" in chord:
                        adjusted *= 1.15
                    if "b9" in chord or "#9" in chord:
                        adjusted *= 1.05
                if prefer_pop_clean:
                    ch_l = str(chord).lower()
                    if bucket == "maj":
                        if "add9" in ch_l or "6/9" in ch_l or "maj7" in ch_l or "6" in ch_l:
                            adjusted *= 1.22
                        if "maj13" in ch_l or "#11" in ch_l:
                            adjusted *= 0.76
                    elif bucket == "min":
                        if "11" in ch_l:
                            adjusted *= 0.82
                        if "9" in ch_l or "7" in ch_l:
                            adjusted *= 1.12
                        if "(maj7)" in ch_l:
                            adjusted *= 0.74
                    elif bucket == "dom":
                        if "sus" in ch_l or ch_l.endswith("7") or "9" in ch_l:
                            adjusted *= 1.16
                        if "13" in ch_l:
                            adjusted *= 0.96
                        if "b9" in ch_l or "#9" in ch_l or "#11" in ch_l or "b5" in ch_l or "#5" in ch_l:
                            adjusted *= 0.58
                adjusted_weights.append(adjusted)
            rng = getattr(self.owner, "rng", random)
            return rng.choices(choices, weights=adjusted_weights)[0]

        # Fallback defaults:
        # - legacy: when no degree token is provided, preserve the old fixed roman defaults
        # - rich tokens: synthesize the extension on the requested degree
        if not degree:
            default_extensions = {
                "maj": ["Imaj7", "Iadd9", "I6", "I6/9", "Imaj9"] if prefer_pop_clean else ["Imaj7", "Imaj9", "Imaj13", "I6", "I6/9", "Imaj7#11"],
                "min": ["i7", "i9", "i6"] if prefer_pop_clean else ["i7", "i9", "i11", "i6", "i(maj7)"],
                "dom": ["V7", "V9", "Vsus4", "V7sus4"] if prefer_pop_clean else ["V7", "V9", "V13", "V7b9", "V7#9", "V7#11", "V7b5", "V7#5"],
                "dim": ["vii°7", "iiø7"],
                "aug": ["Iaug7"],
                "sus": ["Vsus4", "V7sus4", "V9sus4"],
            }
            allowed = default_extensions.get(bucket, [bucket])
        else:
            root = degree
            default_extensions = {
                "maj": [f"{root}maj7", f"{root}add9", f"{root}6", f"{root}6/9", f"{root}maj9"] if prefer_pop_clean else [f"{root}maj7", f"{root}maj9", f"{root}maj13", f"{root}6", f"{root}6/9", f"{root}maj7#11"],
                "min": [f"{root}7", f"{root}9", f"{root}6"] if prefer_pop_clean else [f"{root}7", f"{root}9", f"{root}11", f"{root}6", f"{root}(maj7)"],
                "dom": [f"{root}7", f"{root}9", f"{root}sus4", f"{root}7sus4"] if prefer_pop_clean else [f"{root}7", f"{root}9", f"{root}13", f"{root}7b9", f"{root}7#9", f"{root}7#11", f"{root}7b5", f"{root}7#5"],
                "dim": [f"{root}°7", f"{root}ø7"],
                "aug": [f"{root}aug7"],
                "sus": [f"{root}sus4", f"{root}7sus4", f"{root}9sus4"],
            }
            allowed = default_extensions.get(bucket, [bucket])
        rng = getattr(self.owner, "rng", random)
        return rng.choice(allowed)
