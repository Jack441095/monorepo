# composition/melody_runtime_phrase_plan.py
"""Leaf-layer phrase-contour/note-budget helpers for MelodyRuntime.

Split 2026-07-14 from the single 1,789-line melody_runtime.py
(docs/codebase_scan_12_07.md, "large un-decomposed files"). This file holds
the bottom dependency layer: phrase-state sequencing, contour
diversification/anti-repeat, phrase-length alignment, chorus-hook phrase
stabilization/composition, the transition-pickup writer, and the
counter-line Markov parameter context manager. None of these call into
melody_runtime_prepare.py, melody_runtime_rhythm.py, or the top-level
melody_runtime.py -- they are the leaves other layers build on.

melody_runtime.py assembles this mixin together with the prepare/rhythm
mixins into the final `MelodyRuntime` class via multiple inheritance,
mirroring the ChordPlanner split done earlier in this same session and the
existing composition/mixins/ pattern used for CompositionGenerator's
CachingMixin/PerformanceMixin.
"""

from __future__ import annotations

import random
from contextlib import contextmanager
from typing import List, Optional, Tuple

from audiogen_core.config import resolve_config
from data.music_data import EmotionProfile


class _MelodyPhrasePlanMixin:
    """Phrase-contour and note-budget shaping helpers shared across MelodyRuntime."""

    def get_melody_params(self, emotion: EmotionProfile) -> Tuple[float, float]:
        return self.owner.melody_policy.melody_params(emotion)

    @staticmethod
    def _section_role_density_multiplier(section_role: Optional[str], *, counter_line: bool = False) -> float:
        """
        Role-aware melody-density multiplier for Markov lead planning.

        Counter lines intentionally ignore this role map because they have their
        own sparse scheduler later in section planning.
        """
        if bool(counter_line):
            return 1.0
        role = str(section_role or "").strip().lower()
        if not role:
            return 1.0
        md = resolve_config("composition", "melody_role_density", None)
        if md is not None:
            mapping = {
                "intro": getattr(md, "mult_intro", 0.72),
                "a": getattr(md, "mult_verse", 0.92),
                "verse": getattr(md, "mult_verse", 0.92),
                "pre_chorus": getattr(md, "mult_prechorus", 1.04),
                "b": getattr(md, "mult_chorus", 1.10),
                "chorus": getattr(md, "mult_chorus", 1.10),
                "hook": getattr(md, "mult_chorus", 1.10),
                "tag": getattr(md, "mult_tag", 1.06),
                "a_prime": getattr(md, "mult_aprime", 1.02),
                "outro": getattr(md, "mult_outro", 0.68),
            }
            v = float(mapping.get(role, 1.0))
        else:
            fallback = {
                "intro": 0.72,
                "a": 0.92,
                "verse": 0.92,
                "pre_chorus": 1.04,
                "b": 1.10,
                "chorus": 1.10,
                "hook": 1.10,
                "tag": 1.06,
                "a_prime": 1.02,
                "outro": 0.68,
            }
            v = float(fallback.get(role, 1.0))
        return max(0.35, min(1.85, float(v)))

    @staticmethod
    def _phrase_state_sequence(n_phrases: int, section_role: Optional[str] = None) -> List[str]:
        n = max(1, int(n_phrases))
        role = str(section_role or "").strip().lower()
        chorusish = role in {"b", "chorus", "hook", "tag"}
        out: List[str] = []
        for i in range(n):
            if i == 0:
                out.append("opening")
            elif i == (n - 1):
                out.append("cadence")
            elif chorusish:
                # Hook-forward chorus plan: opening-like statement, then answer.
                out.append("opening" if (i % 2 == 0) else "answer")
            else:
                out.append("answer" if (i % 2 == 1) else "continuation")
        return out

    @classmethod
    def _apply_phrase_state_conditioning(
        cls,
        phrase_contours: List[str],
        notes_per_phrase: List[int],
        *,
        section_role: Optional[str] = None,
        strength: float = 0.72,
    ) -> Tuple[List[str], List[int]]:
        if not phrase_contours or not notes_per_phrase:
            return list(phrase_contours), list(notes_per_phrase)
        s = max(0.0, min(1.0, float(strength)))
        if s <= 1e-6:
            return list(phrase_contours), list(notes_per_phrase)

        n = min(len(list(phrase_contours)), len(list(notes_per_phrase)))
        contours = list(phrase_contours[:n])
        counts = [max(1, int(v)) for v in list(notes_per_phrase[:n])]
        states = cls._phrase_state_sequence(n, section_role=section_role)
        role = str(section_role or "").strip().lower()
        chorusish = role in {"b", "chorus", "hook", "tag"}

        pref_contours = {
            "opening": "arch" if chorusish else "asc",
            "continuation": "static",
            "answer": "desc",
            "cadence": "desc",
        }
        for i in range(n):
            cur = str(contours[i] or "arch")
            pref = str(pref_contours.get(str(states[i]), "arch"))
            if cur not in {"asc", "arch", "desc", "static"}:
                cur = "arch"
            if cur != pref:
                if s >= 0.67:
                    contours[i] = pref
                elif s >= 0.33:
                    contours[i] = pref if i % 2 == 0 else cur

        # Phrase-state budget shaping (renormalized to keep exact total).
        if chorusish:
            state_mult = {
                "opening": 1.06,
                "continuation": 0.98,
                "answer": 1.10,
                "cadence": 0.84,
            }
        else:
            state_mult = {
                "opening": 0.94,
                "continuation": 1.05,
                "answer": 1.02,
                "cadence": 0.90,
            }
        total = int(sum(counts))
        target = []
        for i, c in enumerate(counts):
            mult = float(state_mult.get(str(states[i]), 1.0))
            shaped = float(c) * ((1.0 - s) + s * mult)
            target.append(max(1, int(round(shaped))))
        delta = int(total - sum(target))
        order = list(range(len(target)))
        # Keep cadence phrase stable first; adjust interior phrases before cadence when possible.
        if len(order) >= 2:
            order = [i for i in order if i != (len(order) - 1)] + [len(order) - 1]
        j = 0
        while delta != 0 and j < 10000 and order:
            idx = int(order[j % len(order)])
            if delta > 0:
                target[idx] += 1
                delta -= 1
            else:
                if target[idx] > 1:
                    target[idx] -= 1
                    delta += 1
            j += 1
        return contours, target

    def diversify_phrase_contours(self, phrase_contours: List[str]) -> List[str]:
        if len(phrase_contours) <= 1:
            return list(phrase_contours)

        diversified = list(phrase_contours)
        if len(set(diversified)) == 1:
            fallback_cycle = ["asc", "arch", "desc", "static"]
            diversified = [fallback_cycle[i % len(fallback_cycle)] for i in range(len(diversified))]

        rng = getattr(self.owner, "rng", random)
        if rng.random() < 0.65:
            rotation = rng.randint(0, len(diversified) - 1)
            diversified = diversified[rotation:] + diversified[:rotation]

        for idx in range(1, len(diversified)):
            if diversified[idx] == diversified[idx - 1] and rng.random() < 0.6:
                alternatives = [c for c in ("asc", "arch", "desc", "static") if c != diversified[idx]]
                diversified[idx] = rng.choice(alternatives)
        return diversified

    def avoid_recent_phrase_contours(self, phrase_contours: List[str]) -> List[str]:
        recent_signatures = set(getattr(self.owner, "recent_phrase_contour_signatures", ()))
        if not phrase_contours or tuple(phrase_contours) not in recent_signatures:
            return phrase_contours

        rng = getattr(self.owner, "rng", random)
        alternatives = ["asc", "arch", "desc", "static"]
        diversified = list(phrase_contours)
        for idx in range(len(diversified)):
            choices = [c for c in alternatives if c != diversified[idx]]
            diversified[idx] = rng.choice(choices)
            if tuple(diversified) not in recent_signatures:
                return diversified
        return self.diversify_phrase_contours(diversified)

    @staticmethod
    def _align_phrase_plan_lengths(
        phrase_contours: List[str],
        notes_per_phrase: List[int],
    ) -> Tuple[List[str], List[int]]:
        """Keep contour and note-budget arrays aligned without dropping notes."""

        counts = [max(1, int(v)) for v in list(notes_per_phrase or [])]
        if not counts:
            return list(phrase_contours or []), []
        contours = [str(c or "static") for c in list(phrase_contours or [])]
        if not contours:
            contours = ["static"]
        while len(contours) < len(counts):
            contours.append(contours[-1])
        if len(contours) > len(counts):
            contours = contours[: len(counts)]
        return contours, counts

    @staticmethod
    def diversify_notes_per_phrase(notes_per_phrase: List[int], total_notes: int, rng=random) -> List[int]:
        if len(notes_per_phrase) <= 1 or total_notes <= len(notes_per_phrase):
            return list(notes_per_phrase)

        diversified = list(notes_per_phrase)
        moves = min(len(diversified), max(1, total_notes // 6))
        for _ in range(moves):
            donors = [i for i, count in enumerate(diversified) if count > 1]
            receivers = [i for i in range(len(diversified))]
            if not donors or not receivers:
                break
            donor = rng.choice(donors)
            receiver_choices = [i for i in receivers if i != donor]
            if not receiver_choices:
                break
            receiver = rng.choice(receiver_choices)
            diversified[donor] -= 1
            diversified[receiver] += 1
        return diversified

    def counter_phrase_contours(self, n_phrases: int) -> List[str]:
        """Phrase shapes biased for a secondary line (less mirror of lead contours)."""
        n = max(1, int(n_phrases))
        cycle = ("static", "desc", "arch", "static")
        base = [cycle[i % len(cycle)] for i in range(n)]
        return self.diversify_phrase_contours(base)

    @staticmethod
    def _is_chorusish_role(section_role: Optional[str]) -> bool:
        return str(section_role or "").strip().lower() in {"b", "chorus", "hook", "tag"}

    @classmethod
    def _stabilize_chorus_hook_phrase_plan(
        cls,
        phrase_contours: List[str],
        notes_per_phrase: List[int],
        *,
        section_role: Optional[str] = None,
        strength: float = 0.72,
    ) -> Tuple[List[str], List[int]]:
        if not cls._is_chorusish_role(section_role):
            return list(phrase_contours), list(notes_per_phrase)
        if not phrase_contours or not notes_per_phrase:
            return list(phrase_contours), list(notes_per_phrase)
        s = max(0.0, min(1.0, float(strength)))
        if s <= 1e-6:
            return list(phrase_contours), list(notes_per_phrase)

        contours = list(phrase_contours)
        counts = [max(1, int(n)) for n in list(notes_per_phrase)]

        base = str(contours[0] or "arch")
        if base not in {"asc", "arch", "desc", "static"}:
            base = "arch"
        answer = "arch" if base != "arch" else "asc"

        for i in range(len(contours)):
            if i == 0:
                contours[i] = base
            elif i == len(contours) - 1:
                contours[i] = base if len(contours) <= 2 else answer
            else:
                contours[i] = base if (i % 2 == 1) else answer

        total = int(sum(counts))
        anchor = int(round(sum(int(n) for n in counts) / max(1, len(counts))))
        smoothed = []
        for i, n in enumerate(counts):
            target = anchor
            if i == len(counts) - 1:
                target = max(1, int(round(0.92 * float(anchor))))
            blended = int(round((1.0 - s) * float(n) + s * float(target)))
            smoothed.append(max(1, int(blended)))

        delta = int(total - sum(smoothed))
        order = list(range(len(smoothed)))
        if len(smoothed) >= 2:
            order = [0, 1] + [i for i in range(2, len(smoothed))]
        j = 0
        while delta != 0 and j < 10000 and order:
            idx = order[j % len(order)]
            if delta > 0:
                smoothed[idx] += 1
                delta -= 1
            else:
                if smoothed[idx] > 1:
                    smoothed[idx] -= 1
                    delta += 1
            j += 1

        return contours, smoothed

    @classmethod
    def _apply_chorus_hook_composer(
        cls,
        melody_tokens: List[Tuple[int, float]],
        *,
        notes_per_phrase: List[int],
        section_role: Optional[str] = None,
        strength: float = 0.72,
    ) -> List[Tuple[int, float]]:
        if not cls._is_chorusish_role(section_role):
            return list(melody_tokens)
        if not melody_tokens or not notes_per_phrase or len(notes_per_phrase) < 2:
            return list(melody_tokens)
        s = max(0.0, min(1.0, float(strength)))
        if s <= 1e-6:
            return list(melody_tokens)

        out = list(melody_tokens)
        spans: List[Tuple[int, int]] = []
        idx = 0
        for n in list(notes_per_phrase):
            end = min(len(out), idx + max(0, int(n)))
            spans.append((idx, end))
            idx = end
            if idx >= len(out):
                break
        if len(spans) < 2:
            return out

        src_s, src_e = spans[0]
        source = list(out[src_s:src_e])
        if len(source) < 2:
            return out

        for p_idx in range(1, len(spans)):
            tgt_s, tgt_e = spans[p_idx]
            if tgt_e <= tgt_s:
                continue
            keep_tail = 1 if p_idx == (len(spans) - 1) else 0
            tgt_len = max(0, tgt_e - tgt_s - keep_tail)
            if tgt_len <= 0:
                continue
            for j in range(tgt_len):
                src_deg, src_dur = source[j % len(source)]
                cur_deg, cur_dur = out[tgt_s + j]
                deg = src_deg if s >= 0.5 else cur_deg
                dur = src_dur if s >= 0.85 else cur_dur
                out[tgt_s + j] = (deg, dur)
        return out

    @classmethod
    def _apply_transition_pickup_writer(
        cls,
        melody_tokens: List[Tuple[int, float]],
        *,
        notes_per_phrase: List[int],
        section_role: Optional[str] = None,
        next_role: Optional[str] = None,
        hook_anchor_degree: Optional[int] = None,
        strength: float = 0.72,
    ) -> List[Tuple[int, float]]:
        out = list(melody_tokens)
        if not out or not notes_per_phrase:
            return out
        s = max(0.0, min(1.0, float(strength)))
        if s <= 1e-6:
            return out

        r = str(section_role or "").strip().lower()
        nr = str(next_role or "").strip().lower()
        if not ((r in {"a", "verse"} and nr == "pre_chorus") or (r == "pre_chorus" and nr in {"b", "chorus", "hook", "tag"})):
            return out

        start = max(0, len(out) - max(0, int(notes_per_phrase[-1])))
        voiced = [i for i in range(start, len(out)) if isinstance(out[i][0], int) and int(out[i][0]) >= 0]
        if not voiced:
            return out

        target = 2 if nr == "pre_chorus" else (int(hook_anchor_degree) % 7 if hook_anchor_degree is not None else 0)
        last_i = int(voiced[-1])
        prev_i = int(voiced[-2]) if len(voiced) >= 2 else None
        last_deg, last_dur = out[last_i]
        last_deg = int(last_deg)
        last_dur = float(last_dur)

        # Write the section-ending note as a short approach into the next section's target.
        if last_dur > 0.75:
            new_last_dur = 0.5 if s >= 0.5 else max(0.25, float(last_dur) - 0.25)
            borrowed = float(last_dur - new_last_dur)
            out[last_i] = (int(last_deg), float(new_last_dur))
            if prev_i is not None and borrowed > 1e-6:
                prev_deg, prev_dur = out[prev_i]
                out[prev_i] = (int(prev_deg), float(prev_dur) + float(borrowed))

        if prev_i is None:
            source = int(last_deg)
        else:
            source = int(out[prev_i][0])
        up = int((target - 1) % 7)
        down = int((target + 1) % 7)

        def _dist(a: int, b: int) -> int:
            d = abs(int(a) - int(b))
            return min(d, 7 - d)

        approach = int(up if _dist(source, up) <= _dist(source, down) else down)
        if approach == int(last_deg) and s < 0.85:
            return out
        out[last_i] = (int(approach), float(out[last_i][1]))
        return out

    @contextmanager
    def _counter_line_markov_context(self):
        mg = self.owner.melody_gen
        ng = mg.note_gen
        mt = mg.motif
        state = {
            "rest_prob": mg.rest_prob,
            "embellishment_prob": mg.embellishment_prob,
            "enforce_climax": mg.enforce_climax,
            "motif_prob": mt.motif_prob,
            "phrase_repetition_prob": mg.phrase_repetition_prob,
            "chord_tone_multiplier": ng.chord_tone_multiplier,
            "stepwise_boost_base": ng.stepwise_boost_base,
            "downbeat_chord_multiplier": ng.downbeat_chord_multiplier,
        }
        try:
            mg.rest_prob = max(0.02, mg.rest_prob * 0.48)
            mg.embellishment_prob = max(0.04, mg.embellishment_prob * 0.42)
            mg.enforce_climax = False
            mt.motif_prob = max(0.06, mt.motif_prob * 0.32)
            mg.phrase_repetition_prob = max(0.04, mg.phrase_repetition_prob * 0.40)
            ng.chord_tone_multiplier *= 1.16
            mg.chord_tone_multiplier = ng.chord_tone_multiplier
            ng.stepwise_boost_base *= 1.14
            mg.stepwise_boost_base = ng.stepwise_boost_base
            ng.downbeat_chord_multiplier *= 0.90
            mg.downbeat_chord_multiplier = ng.downbeat_chord_multiplier
            yield
        finally:
            mg.rest_prob = state["rest_prob"]
            mg.embellishment_prob = state["embellishment_prob"]
            mg.enforce_climax = state["enforce_climax"]
            mt.motif_prob = state["motif_prob"]
            mg.phrase_repetition_prob = state["phrase_repetition_prob"]
            ng.chord_tone_multiplier = state["chord_tone_multiplier"]
            mg.chord_tone_multiplier = state["chord_tone_multiplier"]
            ng.stepwise_boost_base = state["stepwise_boost_base"]
            mg.stepwise_boost_base = state["stepwise_boost_base"]
            ng.downbeat_chord_multiplier = state["downbeat_chord_multiplier"]
            mg.downbeat_chord_multiplier = state["downbeat_chord_multiplier"]
