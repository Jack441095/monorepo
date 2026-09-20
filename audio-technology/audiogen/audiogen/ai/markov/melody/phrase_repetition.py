# ai/markov/melody/phrase_repetition.py
# Project module `phrase_repetition` (ai).

# phrase_repetition.py
import random
from typing import Dict, List, Tuple


class PhraseRepetitionMixin:
    def __init__(self, phrase_repetition_prob=0.3, max_phrase_memory=100, rng=random):
        self.phrase_repetition_prob = phrase_repetition_prob
        self.max_phrase_memory = max_phrase_memory
        self.phrase_memory: Dict[Tuple, List[Tuple[int, float]]] = {}
        self.rng = rng

    def _maybe_repeat_phrase(self, phrase: List[Tuple[int, float]],
                            contour: str, emotion_name: str) -> List[Tuple[int, float]]:
        key = (emotion_name, contour, len(phrase))
        if self.rng.random() < self.phrase_repetition_prob and key in self.phrase_memory:
            stored = self.phrase_memory[key]
            var_type = self.rng.choice(['transpose', 'augment', 'diminish', 'invert', 'retrograde'])
            return self._vary_phrase(stored, var_type)
        # Always update the stored phrase for this key so the memory stays
        # fresh (previously only new keys were stored, freezing the first
        # phrase of each type forever).
        if key in self.phrase_memory or len(self.phrase_memory) < self.max_phrase_memory:
            self.phrase_memory[key] = phrase
        return phrase

    def _section_form_probability(self, phrase_idx: int, total_phrases: int) -> float:
        if total_phrases <= 1 or phrase_idx == 0:
            return 0.0
        if phrase_idx == total_phrases - 1:
            return 0.7
        if phrase_idx % 2 == 1:
            return 0.45
        return 0.3

    def _section_form_source_index(self, phrase_idx: int, total_phrases: int) -> int:
        if phrase_idx <= 0:
            return -1
        if phrase_idx == total_phrases - 1 and total_phrases >= 3:
            return 0
        if phrase_idx >= 2:
            return phrase_idx - 2
        return phrase_idx - 1

    @staticmethod
    def _phrase_role(phrase_idx: int, total_phrases: int) -> str:
        if total_phrases <= 1 or phrase_idx == 0:
            return "opening"
        if phrase_idx == total_phrases - 1:
            return "cadence"
        if phrase_idx % 2 == 1:
            return "answer"
        return "continuation"

    @staticmethod
    def _circular_distance(a: int, b: int) -> int:
        return min(abs(a - b), 7 - abs(a - b))

    @staticmethod
    def _best_degree_shift(current: int, target: int) -> int:
        best_shift = 0
        best_distance = None
        for shift in range(-3, 4):
            shifted = (current + shift) % 7
            distance = PhraseRepetitionMixin._circular_distance(shifted, target)
            if best_distance is None or distance < best_distance:
                best_distance = distance
                best_shift = shift
        return best_shift

    def _response_variation_candidates(self, contour: str, emotion_name: str, role: str) -> List[str]:
        emotion_name = emotion_name.lower()
        if role == "cadence":
            if contour == "arch":
                return ["invert", "transpose", "retrograde"]
            if contour == "desc":
                return ["invert", "retrograde", "transpose"]
            return ["transpose", "invert", "retrograde"]
        if role == "answer":
            if contour == "desc" or emotion_name in {"grief", "sadness", "remorse", "fear"}:
                return ["retrograde", "invert", "transpose"]
            if contour == "asc":
                return ["transpose", "sequence", "invert"]
            return ["invert", "transpose", "retrograde"]
        if contour == "asc":
            return ["transpose", "invert"]
        if contour == "arch":
            return ["invert", "retrograde"]
        return ["transpose", "retrograde"]

    def _retarget_phrase_to_plan(
        self,
        phrase: List[Tuple[int, float]],
        contour: str,
        plan,
        role: str,
    ) -> List[Tuple[int, float]]:
        if not phrase or plan is None:
            return phrase

        target_end = plan.cadence_degree if role == "cadence" else plan.pre_cadence_degree
        if target_end is None:
            target_end = plan.cadence_degree

        retargeted = list(phrase)
        if target_end is not None:
            end_shift = self._best_degree_shift(retargeted[-1][0], target_end)
            retargeted = [((deg + end_shift) % 7, dur) for deg, dur in retargeted]

        if plan.target_climax is not None and contour in {"asc", "arch"} and retargeted:
            peak_idx = max(range(len(retargeted)), key=lambda idx: retargeted[idx][0])
            peak_deg, peak_dur = retargeted[peak_idx]
            peak_shift = self._best_degree_shift(peak_deg, plan.target_climax)
            retargeted[peak_idx] = ((peak_deg + peak_shift) % 7, peak_dur)

        if len(retargeted) >= 2 and target_end is not None:
            prev_deg, prev_dur = retargeted[-2]
            if role == "cadence" and plan.pre_cadence_degree is not None:
                approach = plan.pre_cadence_degree
                approach_shift = self._best_degree_shift(prev_deg, approach)
                retargeted[-2] = ((prev_deg + approach_shift) % 7, prev_dur)
            elif role == "answer" and plan.entry_degree is not None:
                approach_shift = self._best_degree_shift(prev_deg, plan.entry_degree)
                retargeted[-2] = ((prev_deg + approach_shift) % 7, prev_dur)

            final_deg, final_dur = retargeted[-1]
            final_shift = self._best_degree_shift(final_deg, target_end)
            retargeted[-1] = ((final_deg + final_shift) % 7, final_dur)

        return retargeted

    def _adapt_phrase_to_contour(
        self,
        phrase: List[Tuple[int, float]],
        target_contour: str,
    ) -> List[Tuple[int, float]]:
        if not phrase:
            return phrase
        if target_contour == "static":
            anchor = phrase[0][0]
            return [(anchor if i % 2 == 0 else deg, dur) for i, (deg, dur) in enumerate(phrase)]
        if target_contour == "desc":
            descending = sorted(phrase, key=lambda item: item[0], reverse=True)
            return [(deg, phrase[i][1]) for i, (deg, _) in enumerate(descending)]
        if target_contour == "asc":
            ascending = sorted(phrase, key=lambda item: item[0])
            return [(deg, phrase[i][1]) for i, (deg, _) in enumerate(ascending)]
        return phrase

    def _maybe_apply_section_form(
        self,
        phrase: List[Tuple[int, float]],
        prior_phrases: List[List[Tuple[int, float]]],
        phrase_idx: int,
        total_phrases: int,
        contour: str,
        emotion_name: str,
        plan=None,
    ) -> List[Tuple[int, float]]:
        if not phrase or not prior_phrases:
            return phrase
        base_p = float(self._section_form_probability(phrase_idx, total_phrases))
        emo_lc = str(emotion_name or "").strip().lower()
        if emo_lc in {"sadness", "remorse", "disappointment", "grief", "love", "caring", "relief", "embarrassment"}:
            if phrase_idx == total_phrases - 1:
                base_p = max(base_p, 0.82)
            elif phrase_idx % 2 == 1:
                base_p = max(base_p, 0.58)
            else:
                base_p = max(base_p, 0.36)
        if self.rng.random() >= float(min(0.95, max(0.0, base_p))):
            return phrase

        source_idx = self._section_form_source_index(phrase_idx, total_phrases)
        if source_idx < 0 or source_idx >= len(prior_phrases):
            return phrase

        source = prior_phrases[source_idx]
        if len(source) != len(phrase):
            return phrase

        role = self._phrase_role(phrase_idx, total_phrases)
        variation_candidates = self._response_variation_candidates(contour, emotion_name, role)
        var_type = self.rng.choice(variation_candidates)

        response = self._vary_phrase(source, var_type)
        response = self._adapt_phrase_to_contour(response, contour)
        response = self._retarget_phrase_to_plan(response, contour, plan, role)
        return response

    def _apply_explicit_restatement_schedule(
        self,
        phrase: List[Tuple[int, float]],
        prior_phrases: List[List[Tuple[int, float]]],
        *,
        phrase_idx: int,
        total_phrases: int,
        contour: str,
        emotion_name: str,
        plan=None,
    ) -> List[Tuple[int, float]]:
        """
        Deterministic, role-aware restatement schedule.

        Goal: in hook-like sections, restate the opening phrase idea (A -> A') on
        subsequent phrases so melody identity is more recognizable than purely
        probabilistic repetition.
        """
        if not phrase or not prior_phrases:
            return phrase

        try:
            from audiogen_core.config import CONFIG

            enabled = bool(getattr(CONFIG.composition, "chorus_hook_composer_enabled", True))
            strength = float(getattr(CONFIG.composition, "chorus_hook_composer_strength", 0.72) or 0.72)
        except Exception:
            enabled = True
            strength = 0.72

        if not enabled or float(strength) <= 1e-9:
            return phrase

        try:
            section_role = str(getattr(plan, "section_role", "") or "").strip().lower() if plan is not None else ""
        except Exception:
            section_role = ""
        tender_emotion = emotion_name in {"sadness", "remorse", "disappointment", "grief", "love", "caring", "relief", "embarrassment"}
        verseish_tender = tender_emotion and section_role in {"a", "verse", "intro"}
        if section_role not in {"b", "chorus", "hook", "tag", "a_prime"} and not verseish_tender:
            return phrase

        try:
            phrase_role = str(getattr(plan, "phrase_role", "") or "").strip().lower() if plan is not None else ""
        except Exception:
            phrase_role = ""

        # Prefer keeping rhythm shape stable: only use transforms that preserve length.
        def _pick_var(role: str) -> str:
            r = (role or "").strip().lower()
            # Hook-like: mostly transpose; allow rare invert for contrast.
            if r in {"b", "chorus", "hook", "tag"}:
                # Keep inversion very rare: it can read as a different idea rather than a restatement.
                return "invert" if self.rng.random() < 0.05 * float(strength) else "transpose"
            # Bridge-like: more contrast, but still keep it readable.
            return "invert" if self.rng.random() < 0.25 else "transpose"

        # Subtle schedule:
        # - Hooks: usually restate only the first answer phrase (phrase_idx==1) and only when
        #   it's not the cadence phrase. This keeps identity without sounding looped.
        # - a_prime: optional light coherence (rare restatement).
        if phrase_idx <= 0 or phrase_idx >= total_phrases:
            return phrase

        if section_role in {"b", "chorus", "hook", "tag"}:
            want = (phrase_idx == 1) and (phrase_idx < total_phrases - 1) and (phrase_role != "cadence")
            # Strength scales the probability, but keep this a nudge rather than a lock.
            p = 0.40 * float(strength) if want else 0.0
            source_idx = 0
        elif verseish_tender:
            want = phrase_idx in {1, total_phrases - 1} and phrase_role != "cadence"
            p = 0.26 * float(strength) if want else (0.18 * float(strength) if phrase_idx == total_phrases - 1 else 0.0)
            source_idx = 0
        else:  # a_prime
            want = (phrase_idx == 1) and (phrase_idx < total_phrases - 1) and (phrase_role != "cadence")
            p = 0.18 * float(strength) if want else 0.0
            source_idx = 0

        if p <= 1e-9 or self.rng.random() >= float(p):
            return phrase

        if source_idx < 0 or source_idx >= len(prior_phrases):
            return phrase
        source = prior_phrases[source_idx]
        if len(source) != len(phrase):
            return phrase

        var_type = _pick_var(section_role)
        restated = self._vary_phrase(source, var_type)
        restated = self._adapt_phrase_to_contour(restated, contour)
        role = self._phrase_role(phrase_idx, total_phrases)
        restated = self._retarget_phrase_to_plan(restated, contour, plan, role)
        return restated

    def _vary_phrase(self, phrase: List[Tuple[int, float]], var_type: str) -> List[Tuple[int, float]]:
        if var_type == 'transpose':
            shift = self.rng.randint(-2, 2)
            return [((deg + shift) % 7, dur) for deg, dur in phrase]
        elif var_type == 'augment':
            return [(deg, dur * 2) for deg, dur in phrase]
        elif var_type == 'diminish':
            return [(deg, dur * 0.5) for deg, dur in phrase]
        elif var_type == 'invert':
            if len(phrase) < 2:
                return phrase
            first_deg = phrase[0][0]
            new_phrase = [(first_deg, phrase[0][1])]
            for i in range(1, len(phrase)):
                step = phrase[i][0] - phrase[i-1][0]
                new_deg = (new_phrase[-1][0] - step) % 7
                new_phrase.append((new_deg, phrase[i][1]))
            return new_phrase
        elif var_type == 'retrograde':
            return phrase[::-1]
        else:
            return phrase
