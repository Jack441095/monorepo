# composition/chord_planner_bias.py
"""Leaf-layer bias/weighting helpers for ChordPlanner.

Split 2026-07-14 from the single 2,065-line chord_planner.py
(docs/codebase_scan_12_07.md, "large un-decomposed files"). This file holds
the bottom dependency layer: pure token/bucket helpers and static bias
functions (opening/cadence/section-role/phrase-start biases, cadence
degree/weight lookups, tonal-center drift, handoff pivot scoring). None of
these call into chord_planner_weighting.py, chord_planner_sampling.py, or
chord_planner_progression.py -- they are the leaves other layers build on.

chord_planner.py assembles `_ChordBiasMixin` (this file) together with the
other three mixins into the final `ChordPlanner` class via multiple
inheritance, mirroring the existing composition/mixins/ pattern used for
CompositionGenerator's CachingMixin/PerformanceMixin.
"""

from __future__ import annotations

import math
from typing import FrozenSet, List, Optional, Set

from data.harmony_profiles import harmony_profile_for_emotion
from data.tokens import ChordToken
from audiogen_core.config import resolve_config

from composition.scoring_utils import cadence_symbol_weight


class _ChordBiasMixin:
    """Token helpers and static bias functions used across ChordPlanner."""

    def _markov_token(self, chord: str) -> str:
        """
        Richer harmony token for Markov + vocab construction.

        Format:
          - Roman: "<degree>:<bucket>" e.g. "V:dom", "bVII:maj", "iv:min"
          - Absolute/unknown: "<bucket>" (fallback)

        Buckets intentionally match the existing simplified vocabulary so downstream
        heuristics remain valid.
        """
        s = str(chord or "").strip()
        if not s:
            return ""
        bucket = ""
        try:
            bucket = str(self.owner._simplify_chord_for_markov(s))
        except Exception:
            bucket = "dom"
        tok = ChordToken.from_symbol(s, bucket=bucket)
        return tok.serialize(use_degree=bool(getattr(self, "_use_degree_tokens", False)))

    @staticmethod
    def _token_bucket(token: str) -> str:
        return ChordToken.token_bucket(token)

    @staticmethod
    def _token_degree(token: str) -> str:
        return ChordToken.token_degree(token)

    @staticmethod
    def _replace_root_roman(chord: str, new_root: str) -> str:
        s = (chord or "").strip()
        i = 0
        while i < len(s) and s[i] in {"b", "#"}:
            i += 1
        while i < len(s) and s[i] in {"i", "v", "I", "V"}:
            i += 1
        return f"{new_root}{s[i:]}" if i > 0 else s

    @classmethod
    def _deceptive_cadence_pair(cls, cadence: List[str]) -> List[str]:
        if len(cadence) < 2:
            return cadence
        out = list(cadence[-2:])
        tonic = out[-1]
        if tonic.startswith("I"):
            out[-1] = cls._replace_root_roman(tonic, "vi")
        elif tonic.startswith("i"):
            out[-1] = cls._replace_root_roman(tonic, "VI")
        return out

    @staticmethod
    def opening_bias(emotion_name: str, symbol: str) -> float:
        name = emotion_name.lower()
        profile = harmony_profile_for_emotion(name)
        if symbol == "maj":
            if "opening_maj" in profile:
                return float(profile["opening_maj"])
            if name in {"joy", "excitement", "optimism", "amusement", "admiration", "gratitude", "relief", "pride"}:
                return 2.8
            if name in {"love", "caring", "approval", "neutral", "realization", "curiosity"}:
                return 2.0
            return 1.2
        if symbol == "min":
            if "opening_min" in profile:
                return float(profile["opening_min"])
            if name in {"grief", "sadness", "remorse", "fear", "disappointment", "disgust", "anger", "nervousness"}:
                return 2.6
            if name in {"love", "desire", "caring"}:
                return 1.7
            return 0.9
        if symbol == "dom":
            if "opening_dom" in profile:
                return float(profile["opening_dom"])
            if name in {"surprise", "anger", "realization", "excitement"}:
                return 1.4
            return 0.6
        if symbol in {"dim", "aug"}:
            if "opening_dim" in profile:
                return float(profile["opening_dim"])
            return 0.45
        return 0.8

    @staticmethod
    def cadence_bias(emotion_name: str, symbol: str, is_final_phrase_bar: bool) -> float:
        name = emotion_name.lower()
        profile = harmony_profile_for_emotion(name)
        if is_final_phrase_bar:
            if symbol == "maj" and "cadence_major" in profile:
                return float(profile["cadence_major"])
            if symbol == "min" and "cadence_minor" in profile:
                return float(profile["cadence_minor"])
            if symbol == "dom" and "cadence_dom" in profile:
                return float(profile["cadence_dom"])
            if name in {"grief", "sadness", "remorse", "disappointment"}:
                return 1.6 if symbol == "min" else 0.8 if symbol == "maj" else 1.0
            if name in {"surprise", "realization"}:
                return 1.5 if symbol in {"dom", "maj"} else 0.9
            return 1.8 if symbol == "maj" else 1.2 if symbol == "dom" else 0.85
        if symbol == "maj" and "cadence_major" in profile:
            return max(0.72, float(profile["cadence_major"]) * 0.78)
        if symbol == "min" and "cadence_minor" in profile:
            return max(0.72, float(profile["cadence_minor"]) * 0.82)
        if symbol == "dom" and "cadence_dom" in profile:
            return max(0.72, float(profile["cadence_dom"]) * 0.9)
        return 1.6 if symbol == "dom" else 1.15 if symbol == "maj" else 0.9

    @staticmethod
    def section_harmonic_destination(
        *,
        section_role: Optional[str],
        next_role: Optional[str],
        is_last_section: bool,
    ) -> dict:
        r = str(section_role or "").strip().lower()
        nr = str(next_role or "").strip().lower()
        if r == "pre_chorus" and nr in {"b", "chorus", "hook"}:
            return {"target_degree": 4, "arrival_type": "open", "cadence_bias_mult": 0.88, "deceptive_bias_mult": 1.18}
        if r in {"b", "chorus", "hook", "tag"} and nr in {"a", "verse"}:
            return {"target_degree": 0, "arrival_type": "release", "cadence_bias_mult": 0.96, "deceptive_bias_mult": 0.92}
        if r in {"b", "chorus", "hook", "tag", "outro"} and bool(is_last_section):
            return {"target_degree": 0, "arrival_type": "closed", "cadence_bias_mult": 1.16, "deceptive_bias_mult": 0.84}
        if r in {"a", "verse"} and nr in {"pre_chorus"}:
            return {"target_degree": 4, "arrival_type": "lift", "cadence_bias_mult": 0.94, "deceptive_bias_mult": 1.08}
        if r in {"a_prime"}:
            return {"target_degree": 0, "arrival_type": "return", "cadence_bias_mult": 1.06, "deceptive_bias_mult": 0.96}
        return {"target_degree": None, "arrival_type": "neutral", "cadence_bias_mult": 1.0, "deceptive_bias_mult": 1.0}

    @staticmethod
    def _cadence_degree_for_phrase(*, emotion_name: str, is_last_phrase: bool) -> int:
        """
        Mirror Melody PhrasePlanner cadence targets so harmony + melody resolve together.
        Degrees are diatonic scale degrees: 0=tonic, 4=dominant, 2=mediant, 5=submediant, 6=leading tone.
        """
        if not is_last_phrase:
            return 4  # half-cadence default
        name = (emotion_name or "").lower()
        if name in ("grief", "remorse", "sadness", "disappointment"):
            return 2
        if name in ("fear", "confusion", "nervousness", "annoyance", "disgust"):
            return 6
        if name in ("surprise", "realization"):
            return 5
        if name in ("relief", "gratitude", "love", "joy", "caring", "approval"):
            return 0
        return 0

    @staticmethod
    def _cadence_symbol_weight(*, target_degree: int, symbol: str) -> float:
        # Backwards compatible shim (prefer shared helper).
        return float(cadence_symbol_weight(target_degree=int(target_degree), symbol=str(symbol)))

    def _section_tonal_center_offset(self, *, section_index: int, form_section_count: int) -> int:
        """
        Smooth section-level tonal drift (in semitones).
        Returns 0 when feature is disabled.
        """
        enabled = resolve_config("composition", "tonal_center_drift_enabled", True, bool)
        strength = resolve_config("composition", "tonal_center_drift_strength", 0.55, float)
        max_semi = resolve_config("composition", "tonal_center_drift_max_semitones", 3, int)
        cycle = resolve_config("composition", "tonal_center_drift_cycle_sections", 8, int)
        if (not enabled) or max_semi <= 0 or strength <= 1e-6:
            return 0
        idx = max(0, int(section_index))
        form_n = max(1, int(form_section_count))
        cyc = max(2, int(cycle))
        phase = float(idx % cyc) / float(cyc)
        raw = math.sin(2.0 * math.pi * float(phase))
        drift = float(raw) * float(max_semi) * float(max(0.0, min(1.0, strength)))
        # Converge back to home near the form end for stronger closure.
        if form_n > 1:
            form_pos = float(idx) / float(max(1, form_n - 1))
            drift *= float(max(0.0, 1.0 - 0.70 * max(0.0, form_pos - 0.60) / 0.40))
            if idx >= form_n - 1:
                drift = 0.0
        return int(max(-max_semi, min(max_semi, int(round(drift)))))

    @staticmethod
    def _approx_triad_pitch_classes(symbol: str, key_root_midi: int) -> Set[int]:
        """Rough diatonic spellings for Markov chord buckets in a major-ish local key."""
        r = int(key_root_midi) % 12
        if symbol == "maj":
            return {r, (r + 4) % 12, (r + 7) % 12}
        if symbol == "min":
            return {r, (r + 3) % 12, (r + 7) % 12}
        if symbol == "dom":
            v = (r + 7) % 12
            return {v, (v + 4) % 12, (v + 7) % 12}
        if symbol == "dim":
            v = (r + 11) % 12
            return {v, (v + 3) % 12, (v + 6) % 12}
        if symbol == "aug":
            return {r, (r + 4) % 12, (r + 8) % 12}
        if symbol == "sus":
            return {r, (r + 5) % 12, (r + 7) % 12}
        return {r, (r + 4) % 12, (r + 7) % 12}

    @staticmethod
    def _handoff_pivot_multiplier(
        symbol: str,
        key_root_midi: int,
        prev_pcs: FrozenSet[int],
        pivot_strategy: str = "",
    ) -> float:
        if not prev_pcs:
            return 1.0
        tri = _ChordBiasMixin._approx_triad_pitch_classes(symbol, key_root_midi)
        shared = len(tri & set(prev_pcs))
        p = 1.0
        if shared >= 2:
            p *= 1.48
        elif shared == 1:
            p *= 1.24
        elif (key_root_midi % 12) in prev_pcs:
            p *= 1.12
        ps = str(pivot_strategy or "").strip().lower()
        if ps == "dominant_pivot":
            if str(symbol) == "dom":
                p *= 1.14
            elif str(symbol) == "maj":
                p *= 0.96
        elif ps == "pedal":
            if (key_root_midi % 12) in prev_pcs:
                p *= 1.12
            else:
                p *= 0.96
        elif ps == "chromatic":
            if str(symbol) in {"min", "dim", "dom"}:
                p *= 1.06
        return float(max(0.75, min(2.2, p)))

    @staticmethod
    def phrase_role(phrase_idx: int, total_phrases: int) -> str:
        if total_phrases <= 1 or phrase_idx == 0:
            return "opening"
        if phrase_idx == total_phrases - 1:
            return "cadence"
        if phrase_idx % 2 == 1:
            return "answer"
        return "continuation"

    @staticmethod
    def section_role_harmonic_multiplier(
        section_role: Optional[str],
        symbol: str,
        emotion_name: str,
        *,
        bar_index: int,
        total_bars: int,
        bar_in_phrase: int,
        phrase_length: int,
        is_final_section_bar: bool,
        is_penultimate_section_bar: bool,
        is_first_form_section: bool = False,
        is_last_form_section: bool = False,
    ) -> float:
        """
        Nudge simplified chord weights toward section roles used in arrangement
        (pre-chorus lift to V, chorus/tag tonic closure, outro resolution).
        """
        r = (section_role or "").lower()
        if not r:
            return 1.0
        name = emotion_name.lower()
        sad = name in {"grief", "sadness", "remorse", "disappointment"}
        tense = name in {"surprise", "anger", "fear", "nervousness", "excitement"}
        w = 1.0
        final_phrase_bar = phrase_length >= 1 and bar_in_phrase == phrase_length - 1

        if is_first_form_section and bar_index == 0 and symbol == "dom":
            w *= 0.9
        if is_last_form_section and is_final_section_bar and final_phrase_bar:
            if not sad and symbol == "maj":
                w *= 1.1
            if sad and symbol == "min":
                w *= 1.1

        if r == "intro" and bar_index <= 2 and not is_final_section_bar:
            if symbol == "dom":
                w *= 0.86

        if r == "pre_chorus" and is_final_section_bar and final_phrase_bar:
            if symbol == "dom":
                w *= 1.48
            if symbol == "maj" and not sad:
                w *= 0.76
            if symbol == "min" and not sad:
                w *= 0.9

        if r in {"b", "a_prime", "tag"}:
            # Hook sections: keep bar-0 harmonically stable so the hook reads clearly.
            if int(bar_index) == 0 and not is_final_section_bar:
                if symbol == "dom":
                    w *= 0.82
                if symbol in {"maj", "min"}:
                    w *= 1.06
            if is_penultimate_section_bar and symbol == "dom":
                w *= 1.14
            if is_final_section_bar and final_phrase_bar:
                if not sad:
                    if symbol == "maj":
                        w *= 1.26
                    if symbol == "dom" and not tense:
                        w *= 0.68
                else:
                    if symbol == "min":
                        w *= 1.22
                    if symbol == "maj":
                        w *= 0.82
                    if symbol == "dom" and not tense:
                        w *= 0.75

        if r == "outro" and is_final_section_bar and final_phrase_bar:
            if not sad and symbol == "maj":
                w *= 1.34
            if sad and symbol == "min":
                w *= 1.36
            if symbol == "dom" and not tense:
                w *= 0.55
            if symbol == "maj" and sad:
                w *= 1.05

        return w

    @staticmethod
    def phrase_start_bias(
        emotion_name: str,
        symbol: str,
        role: str,
        previous_phrase_end: str = "",
        section_opening: str = "",
    ) -> float:
        name = emotion_name.lower()
        if role == "opening":
            return _ChordBiasMixin.opening_bias(emotion_name, symbol)

        bias = 1.0
        if role == "answer":
            if previous_phrase_end == "dom":
                if name in {"grief", "sadness", "remorse", "disappointment"}:
                    bias *= 1.7 if symbol == "min" else 0.9 if symbol == "maj" else 1.0
                else:
                    bias *= 1.8 if symbol == "maj" else 1.2 if symbol == "min" else 0.95
            elif previous_phrase_end == "min":
                bias *= 1.35 if symbol in {"maj", "dom"} else 1.0
            elif previous_phrase_end == "maj":
                bias *= 1.25 if symbol in {"min", "dom"} else 1.0
            if section_opening and symbol == section_opening:
                bias *= 0.82
            if symbol in {"dim", "aug"}:
                bias *= 0.65
            return bias

        if role == "cadence":
            if previous_phrase_end == "dom":
                if name in {"grief", "sadness", "remorse", "disappointment"}:
                    bias *= 1.55 if symbol == "min" else 0.95 if symbol == "maj" else 1.0
                else:
                    bias *= 1.75 if symbol == "maj" else 1.15 if symbol == "min" else 0.9
            else:
                bias *= 1.25 if symbol in {"maj", "min"} else 0.95 if symbol == "dom" else 0.75
            return bias

        if role == "continuation":
            if previous_phrase_end == "dom":
                bias *= 1.25 if symbol in {"maj", "min"} else 0.9
            elif previous_phrase_end == "maj":
                bias *= 1.15 if symbol in {"min", "dom"} else 1.0
            return bias

        return bias
