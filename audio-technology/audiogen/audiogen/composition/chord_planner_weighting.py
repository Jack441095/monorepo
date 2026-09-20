# composition/chord_planner_weighting.py
"""Chord candidate weighting for ChordPlanner.

Split 2026-07-14 from the single 2,065-line chord_planner.py (see
chord_planner_bias.py for the full split rationale). This is the mid-layer:
`build_chord_candidate_weights` turns a Markov distribution + history into
final sampling weights, calling only into the leaf layer
(`_ChordBiasMixin.phrase_role` / `.section_role_harmonic_multiplier` /
`.phrase_start_bias`, all accessed via `self.` so mixin composition order
doesn't matter) plus `self.owner` state.
"""

from __future__ import annotations

from typing import List, Optional, Tuple

from audiogen_core.config import resolve_config


class _ChordWeightingMixin:
    """Builds sampling weights for the next simplified chord symbol."""

    def build_chord_candidate_weights(
        self,
        markov_probs: dict,
        simplified_vocab: List[str],
        history: List[str],
        repeat_penalty: float,
        bar_in_phrase: int,
        phrase_length: int,
        force_change: bool = False,
        emotion_name: str = "",
        is_section_start: bool = False,
        phrase_idx: int = 0,
        total_phrases: int = 1,
        previous_phrase_end: str = "",
        section_opening: str = "",
        is_final_section_bar: bool = False,
        section_role: Optional[str] = None,
        bar_index: int = 0,
        total_bars: int = 1,
        is_penultimate_section_bar: bool = False,
        is_first_form_section: bool = False,
        is_last_form_section: bool = False,
        target_function: Optional[str] = None,
        target_function_strength: float = 0.0,
    ) -> Tuple[List[str], List[float]]:
        if markov_probs:
            symbols = list(markov_probs.keys())
            weights = [float(markov_probs[sym]) for sym in symbols]
        else:
            symbols = list(simplified_vocab)
            if not symbols:
                return [], []
            uniform = 1.0 / len(symbols)
            weights = [uniform] * len(symbols)

        if history:
            last = history[-1]
            for i, sym in enumerate(symbols):
                if sym == last:
                    weights[i] *= 0.0 if force_change else repeat_penalty

            # Function diversity guardrail: avoid getting stuck in a single simplified bucket
            # over longer spans (e.g. 16-bar sections). This is intentionally lightweight
            # and only nudges when the recent window is highly repetitive.
            div_enabled = resolve_config("composition", "harmony_function_diversity_guardrail_enabled", True, bool)
            win = resolve_config("composition", "harmony_function_diversity_window", 4, int)
            strength = resolve_config("composition", "harmony_function_diversity_strength", 0.35, float)
            win = max(3, min(8, int(win)))
            strength = max(0.0, min(1.0, float(strength)))
            if div_enabled and strength > 1e-6 and len(history) >= win and not is_final_section_bar:
                try:
                    recent = list(history[-win:])
                    uniq = set(recent)
                    if len(uniq) == 1:
                        # Extremely stuck: heavily penalize repeating the same bucket again.
                        stuck = recent[-1]
                        for i, sym in enumerate(symbols):
                            if sym == stuck:
                                weights[i] *= (1.0 - 0.85 * strength)
                    elif len(uniq) == 2:
                        # Mildly stuck: downweight the dominant symbol a bit.
                        counts = {s: recent.count(s) for s in uniq}
                        dom = max(counts.items(), key=lambda kv: kv[1])[0]
                        if counts.get(dom, 0) >= win - 1:
                            for i, sym in enumerate(symbols):
                                if sym == dom:
                                    weights[i] *= (1.0 - 0.55 * strength)
                except Exception:
                    pass

            if last in self.owner.CHORD_FUNCTION_WEIGHTS:
                func_weights = self.owner.CHORD_FUNCTION_WEIGHTS[last]
                for i, sym in enumerate(symbols):
                    weights[i] *= func_weights.get(sym, 1.0)

            # ------------------------------------------------------------------
            # Functional harmony state machine (T / PD / D).
            #
            # The existing CHORD_FUNCTION_WEIGHTS operate directly on simplified
            # chord buckets ("maj/min/dom/..."). This adds a lightweight tonal
            # function layer that improves long-range progression feel:
            #   T -> PD -> D -> T
            #
            # This is intentionally heuristic (we don't have full roman numerals
            # for the simplified buckets), but it strongly helps cadences and
            # reduces "random walk" harmony.
            # ------------------------------------------------------------------
            def _func(sym: str) -> str:
                s = (sym or "").strip().lower()
                if s in {"dom", "sus", "dim"}:
                    return "D"
                if s in {"aug"}:
                    return "D"
                if s in {"min"}:
                    # Minor can function as tonic-like in emotional beds; treat as T by default.
                    return "T"
                if s in {"maj"}:
                    return "T"
                return "T"

            # Where are we in the phrase/section?
            pr = self.phrase_role(int(phrase_idx), int(total_phrases))
            in_opening = bool(pr == "opening")
            in_cadence_phrase = bool(pr == "cadence")
            is_penult_phrase_bar = bool(phrase_length >= 2 and bar_in_phrase == phrase_length - 2)
            is_final_phrase_bar = bool(phrase_length >= 1 and bar_in_phrase == phrase_length - 1)

            prev_f = _func(last)

            # Base transition weights (can be tuned later).
            trans = {
                "T": {"T": 0.95, "PD": 1.25, "D": 0.85},
                "PD": {"T": 0.85, "PD": 0.85, "D": 1.35},
                "D": {"T": 1.45, "PD": 0.65, "D": 0.60},
            }

            # Phrase-role nudges:
            # - opening: prefer tonic stability
            # - continuation/answer: encourage motion through PD -> D
            # - cadence: encourage D -> T resolution
            role_mult = {"T": 1.0, "PD": 1.0, "D": 1.0}
            if in_opening:
                role_mult = {"T": 1.18, "PD": 0.92, "D": 0.78}
            elif in_cadence_phrase:
                role_mult = {"T": 1.05, "PD": 0.95, "D": 1.18}

            # Bar-position nudges inside the phrase:
            # - penultimate bar: set up dominant
            # - final bar: resolve (unless the section role wants openness; handled elsewhere)
            if is_penult_phrase_bar:
                role_mult["D"] *= 1.18
                role_mult["PD"] *= 0.92
            if is_final_phrase_bar:
                role_mult["T"] *= 1.22
                role_mult["D"] *= 0.72

            for i, sym in enumerate(symbols):
                f = _func(sym)
                weights[i] *= trans.get(prev_f, {}).get(f, 1.0) * role_mult.get(f, 1.0)

            # ------------------------------------------------------------------
            # Phrase-function scaffolding (external target).
            # If a target function is provided, nudge simplified chord buckets toward it.
            # This keeps pre-chorus endings dominant-leaning and choruses more tonic,
            # without removing Markov variety.
            # ------------------------------------------------------------------
            try:
                tf = (target_function or "").strip().upper()
            except Exception:
                tf = ""
            try:
                strength = float(target_function_strength)
            except Exception:
                strength = 0.0
            strength = max(0.0, min(1.0, float(strength)))
            if tf in {"T", "PD", "D"} and strength > 1e-6:
                contracts_on = resolve_config("composition", "harmony_function_contracts_enabled", True, bool)
                contracts_strength = resolve_config("composition", "harmony_function_contract_strength", 0.72, float)
                contracts_strength = max(0.0, min(1.0, float(contracts_strength)))
                if contracts_on:
                    strength = max(float(strength), float(contracts_strength))

                # Heuristic mapping from simplified buckets to T/PD/D.
                # PD is approximated as minor-ish motion (min) in this simplified vocabulary.
                def _match(sym: str) -> bool:
                    s = self._token_bucket(sym)
                    s = (s or "").strip().lower()
                    if tf == "T":
                        return s in {"maj", "min"}
                    if tf == "PD":
                        return s in {"min", "sus"}
                    if tf == "D":
                        return s in {"dom", "dim", "sus", "aug"}
                    return False

                for i, sym in enumerate(symbols):
                    bucket = (self._token_bucket(sym) or "").strip().lower()
                    if _match(sym):
                        # Stronger pull near phrase boundaries under contracts.
                        boost = 0.85
                        if contracts_on:
                            if bar_in_phrase == phrase_length - 1:
                                boost = 1.35
                            elif bar_in_phrase == phrase_length - 2:
                                boost = 1.10
                        weights[i] *= (1.0 + boost * strength)
                    else:
                        suppress = 0.55
                        if contracts_on:
                            if bar_in_phrase == phrase_length - 1:
                                suppress = 0.72
                            elif bar_in_phrase == phrase_length - 2:
                                suppress = 0.62
                        weights[i] *= max(0.06, (1.0 - suppress * strength))
                    # Prevent unstable cadential colors when contracts are active.
                    if contracts_on and bar_in_phrase == phrase_length - 1 and tf in {"T", "D"} and bucket in {"aug", "dim"}:
                        weights[i] *= 0.58

        if is_section_start:
            recent_openings = set(getattr(self.owner, "recent_section_openings", ()))
            for i, sym in enumerate(symbols):
                weights[i] *= self.phrase_start_bias(
                    emotion_name,
                    sym,
                    self.phrase_role(phrase_idx, total_phrases),
                    previous_phrase_end=previous_phrase_end,
                    section_opening=section_opening,
                )
                if sym in recent_openings:
                    weights[i] *= 0.55

        if phrase_length >= 3 and bar_in_phrase == phrase_length - 2:
            for i, sym in enumerate(symbols):
                if sym == "dom":
                    weights[i] *= 1.18

        if bar_in_phrase == phrase_length - 1:
            for i, sym in enumerate(symbols):
                if sym in ("maj", "dom"):
                    weights[i] *= 1.5
                weights[i] *= self.cadence_bias(emotion_name, sym, is_final_section_bar)

        for i, sym in enumerate(symbols):
            weights[i] *= self.section_role_harmonic_multiplier(
                section_role,
                sym,
                emotion_name,
                bar_index=bar_index,
                total_bars=total_bars,
                bar_in_phrase=bar_in_phrase,
                phrase_length=phrase_length,
                is_final_section_bar=is_final_section_bar,
                is_penultimate_section_bar=is_penultimate_section_bar,
                is_first_form_section=is_first_form_section,
                is_last_form_section=is_last_form_section,
            )

        total = sum(weights)
        if total <= 0.0:
            return [], []
        return symbols, [w / total for w in weights]
