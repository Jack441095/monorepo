# composition/melody_runtime_prepare.py
"""Melody phrase-parameter preparation for MelodyRuntime.

Split 2026-07-14 from the single 1,789-line melody_runtime.py (see
melody_runtime_phrase_plan.py for the full split rationale). This is the
mid-layer: `prepare_melody_parameters` computes note-density targets and the
phrase contour/note-budget plan for a section, calling only into the leaf
layer (`self.get_melody_params`, `self._section_role_density_multiplier`,
`self.diversify_notes_per_phrase`, `self.counter_phrase_contours`,
`self.avoid_recent_phrase_contours`, `self.diversify_phrase_contours`,
`self._align_phrase_plan_lengths`, `self._stabilize_chorus_hook_phrase_plan`,
`self._apply_phrase_state_conditioning`, all accessed via `self.` so mixin
composition order doesn't matter) plus `self.owner` state.
"""

from __future__ import annotations

import random
from typing import List, Optional, Tuple

from audiogen_core.config import resolve_config
from data.melody_emotion_profiles import melody_emotion_profile_for_emotion
from data.melody_note_profiles import melody_note_profile_for_emotion
from data.melody_rhythm_profiles import melody_rhythm_profile_for_emotion
from data.music_data import EmotionProfile


class _MelodyPrepareMixin:
    """Computes phrase contour and note-budget plans ahead of generation."""

    def prepare_melody_parameters(
        self,
        emotion: EmotionProfile,
        bars: int,
        temperature: float,
        target_notes_per_bar: float = 4.0,
        first_phrase_note_scale: float = 1.0,
        melody_total_notes_mult: float = 1.0,
        melody_max_notes_per_phrase: Optional[int] = None,
        *,
        counter_line: bool = False,
        register_last_contours: Optional[bool] = None,
        section_role: Optional[str] = None,
        timeline_density_by_bar: Optional[List[float]] = None,
    ) -> Tuple[List[str], List[int], float, float]:
        emotion_name = (getattr(emotion, "name", "") or "").lower()
        note_profile = melody_note_profile_for_emotion(emotion_name)
        emo_profile = melody_emotion_profile_for_emotion(emotion_name)
        density_factor = 0.3 + emotion.density
        adjusted_target = target_notes_per_bar * density_factor

        temp_mult, density_mult = self.get_melody_params(emotion)
        adjusted_target *= density_mult
        adjusted_target *= max(0.72, min(1.5, float(note_profile.get("note_target_mult", 1.0))))
        adjusted_target *= 1.12

        # Global + per-emotion density shaping.
        mscale = resolve_config("composition", "melody_amount_scale", 1.0, float)
        strict = resolve_config("composition", "emotion_melody_strictness", 0.7, float)
        bias = resolve_config("composition", "emotion_melody_density_bias", 1.0, float)
        strict = max(0.0, min(1.0, strict))
        adjusted_target *= max(0.15, min(3.0, mscale))
        # Log-space blend between neutral (1.0) and emotion profile density_mult.
        emo_density = max(0.2, min(2.5, float(emo_profile.density_mult)))
        blended_density = emo_density ** strict
        adjusted_target *= blended_density
        adjusted_target *= max(0.25, min(2.5, bias))
        # Section-role shaping: make form roles read more intentionally (e.g.
        # intro/outro as setup/release, chorus as payoff).
        role = str(section_role or "").strip().lower()
        role_mult = self._section_role_density_multiplier(section_role, counter_line=counter_line)
        adjusted_target *= float(role_mult)
        md = resolve_config("composition", "melody_role_density", None)
        if md is not None:
            if role == "intro":
                intro_cap = float(getattr(md, "target_intro_npb_max", 0.0) or 0.0)
                adjusted_target = min(float(adjusted_target), max(1.0, float(intro_cap)))
                intro_floor = float(getattr(md, "target_intro_npb_min", 0.0) or 0.0)
                adjusted_target = max(float(adjusted_target), max(0.8, float(intro_floor)))
            elif role in {"a", "verse"}:
                verse_floor = float(getattr(md, "target_verse_npb_min", 0.0) or 0.0)
                adjusted_target = max(float(adjusted_target), max(1.0, float(verse_floor)))
            elif role in {"pre_chorus"}:
                pre_floor = float(getattr(md, "target_prechorus_npb_min", 0.0) or 0.0)
                adjusted_target = max(float(adjusted_target), max(1.0, float(pre_floor)))
            elif role == "outro":
                outro_cap = float(getattr(md, "target_outro_npb_max", 0.0) or 0.0)
                adjusted_target = min(float(adjusted_target), max(0.8, float(outro_cap)))
            elif role in {"b", "chorus", "hook", "tag"}:
                chorus_floor = float(getattr(md, "target_chorus_npb_min", 0.0) or 0.0)
                adjusted_target = max(float(adjusted_target), max(1.0, float(chorus_floor)))
        rhythm_profile = melody_rhythm_profile_for_emotion(emotion_name)
        short_bias = float(rhythm_profile.get("short_bias", 1.0) or 1.0)
        long_bias = float(rhythm_profile.get("long_bias", 1.0) or 1.0)
        if long_bias >= 1.12 and short_bias <= 0.92 and not counter_line:
            if role == "intro":
                breath_cap = 2.9
            elif role == "outro":
                breath_cap = 2.7
            elif role in {"b", "chorus", "hook", "tag"}:
                breath_cap = 4.2
            elif role in {"pre_chorus"}:
                breath_cap = 3.8
            else:
                breath_cap = 3.3
            adjusted_target = min(float(adjusted_target), float(breath_cap))

        total_notes = int(round(bars * adjusted_target * max(0.35, min(1.95, float(melody_total_notes_mult)))))
        base_min_notes = float(note_profile.get("min_notes_per_bar", 1.25))
        emo_min = max(0.5, min(8.0, float(emo_profile.min_notes_per_bar)))
        blended_min = (base_min_notes * (1.0 - strict)) + (emo_min * strict)
        # The newer note profiles encode listening-tuned floors. Do not let
        # older broad emotion profiles collapse those floors into two-note
        # 4-bar phrases; the Markov sampler needs enough note events for
        # contour, motif, and cadence logic to matter.
        min_notes_per_bar = max(float(blended_min), float(base_min_notes) * 0.88)
        min_notes_per_bar = max(1.0, min(8.0, float(min_notes_per_bar)))
        total_notes = max(total_notes, int(round(float(bars) * min_notes_per_bar)))
        rng = getattr(self.owner, "rng", random)
        if total_notes > bars and rng.random() < 0.8:
            jitter = rng.randint(-max(1, bars // 2), max(1, bars))
            total_notes = max(int(round(float(bars) * min_notes_per_bar)), total_notes + jitter)

        # Base allocation by phrase count.
        n_phr = max(1, int(self.owner.phrases_per_section))
        notes_per_phrase = [total_notes // n_phr] * n_phr
        remainder = int(total_notes % n_phr)
        for i in range(remainder):
            notes_per_phrase[i] += 1

        # If the section planner provided a per-bar density curve, distribute phrase
        # note budgets according to the average density in each phrase window.
        try:
            dens = list(timeline_density_by_bar or [])
        except Exception:
            dens = []
        if dens and bars > 0 and n_phr > 0:
            bars_i = int(bars)
            phrase_bars = max(1, int(round(float(bars_i) / float(n_phr))))
            w = []
            for p in range(n_phr):
                s = p * phrase_bars
                e = min(bars_i, (p + 1) * phrase_bars)
                if s >= e:
                    w.append(1.0)
                    continue
                seg = [float(dens[i]) for i in range(s, e) if i < len(dens)]
                w.append(max(0.25, min(2.5, (sum(seg) / max(1, len(seg))) if seg else 1.0)))
            w_sum = float(sum(w)) or 1.0
            # Target per-phrase counts proportional to weights.
            raw = [max(1, int(round(float(total_notes) * (wi / w_sum)))) for wi in w]
            # Renormalize to exact total_notes.
            delta = int(total_notes - sum(raw))
            if delta != 0:
                order = sorted(range(len(raw)), key=lambda i: w[i], reverse=(delta > 0))
                j = 0
                while delta != 0 and j < 10_000:
                    i = order[j % len(order)]
                    if delta > 0:
                        raw[i] += 1
                        delta -= 1
                    else:
                        if raw[i] > 1:
                            raw[i] -= 1
                            delta += 1
                    j += 1
            notes_per_phrase = raw

        notes_per_phrase = self.diversify_notes_per_phrase(notes_per_phrase, total_notes, rng=rng)

        if register_last_contours is None:
            register_last_contours = not counter_line

        if counter_line:
            phrase_contours = self.counter_phrase_contours(int(self.owner.phrases_per_section))
            phrase_contours = self.avoid_recent_phrase_contours(phrase_contours)
        else:
            seed_contour = "static"
            phrase_model = self.owner.emotion_phrase_models.get(
                emotion.name, self.owner.melody_gen.phrase_markov
            )
            phrase_contours = phrase_model.generate(
                [seed_contour], self.owner.phrases_per_section, temperature
            )

            use_pc_override = resolve_config("composition", "use_policy_phrase_contour_override", True, bool)
            # Learned-style contour planner: condition contour choices on emotion+section role+density.
            lcp_enabled = resolve_config("composition", "learned_contour_planner_enabled", True, bool)
            lcp_strength = resolve_config("composition", "learned_contour_planner_strength", 0.75, float)
            lcp_strength = max(0.0, min(1.0, float(lcp_strength)))

            if lcp_enabled and lcp_strength > 1e-6 and hasattr(self.owner, "contour_planner_model"):
                # Compute per-phrase density weights (mean of bar density curve per phrase).
                phrase_density = []
                try:
                    dens = list(timeline_density_by_bar or [])
                except Exception:
                    dens = []
                try:
                    bars_i = int(bars)
                    n_phr = int(self.owner.phrases_per_section)
                except Exception:
                    bars_i = int(bars)
                    n_phr = len(list(phrase_contours)) if phrase_contours else 1
                if dens and bars_i > 0 and n_phr > 0:
                    phrase_bars = max(1, int(round(float(bars_i) / float(n_phr))))
                    for p in range(n_phr):
                        s = p * phrase_bars
                        e = min(bars_i, (p + 1) * phrase_bars)
                        seg = [float(dens[i]) for i in range(s, e) if i < len(dens)] if s < e else []
                        phrase_density.append(
                            max(0.35, min(1.75, (sum(seg) / max(1, len(seg))) if seg else 1.0))
                        )
                else:
                    phrase_density = [1.0 for _ in range(int(self.owner.phrases_per_section))]

                # Generate a contour per phrase using a short Markov history.
                hist = [seed_contour]
                learned = []
                for i in range(int(self.owner.phrases_per_section)):
                    d = phrase_density[i] if i < len(phrase_density) else 1.0
                    c = self.owner.contour_planner_model.next_contour(
                        emotion_name=str(getattr(emotion, "name", "neutral") or "neutral"),
                        section_role=section_role,
                        density=float(d),
                        history=list(hist)[-2:],
                        temperature=float(temperature),
                    )
                    learned.append(str(c))
                    hist.append(str(c))

                # Blend: with probability strength, take learned per-phrase contour, else keep base.
                try:
                    out = []
                    for i, base in enumerate(list(phrase_contours)):
                        if rng.random() < lcp_strength:
                            out.append(learned[i] if i < len(learned) else str(base))
                        else:
                            out.append(str(base))
                    phrase_contours = out
                except Exception:
                    phrase_contours = learned or phrase_contours
            elif use_pc_override:
                contour_override = self.owner.melody_policy.phrase_contours(
                    emotion,
                    self.owner.phrases_per_section,
                    section_role=section_role,
                )
                if contour_override:
                    phrase_contours = contour_override
            phrase_contours = self.diversify_phrase_contours(phrase_contours)
            phrase_contours = self.avoid_recent_phrase_contours(phrase_contours)
            try:
                policy_contours = self.owner.melody_policy.phrase_contours(
                    emotion,
                    self.owner.phrases_per_section,
                    section_role=section_role,
                )
            except Exception:
                policy_contours = []
            try:
                desc_bias = float(getattr(emo_profile, "contour_desc_bias", 1.0) or 1.0)
                asc_bias = float(getattr(emo_profile, "contour_asc_bias", 1.0) or 1.0)
                long_note_bias = float(getattr(emo_profile, "long_note_bias", 1.0) or 1.0)
                short_note_bias = float(getattr(emo_profile, "short_note_bias", 1.0) or 1.0)
            except Exception:
                desc_bias = asc_bias = long_note_bias = short_note_bias = 1.0
            if policy_contours and (
                desc_bias >= max(1.08, asc_bias * 1.08)
                or (long_note_bias >= 1.20 and short_note_bias <= 0.90)
            ):
                blend_p = 0.86 if desc_bias >= 1.25 else 0.62
                blended_contours = []
                for i, base in enumerate(list(phrase_contours)):
                    pc = policy_contours[i] if i < len(policy_contours) else base
                    if rng.random() < blend_p:
                        blended_contours.append(str(pc))
                    else:
                        blended_contours.append(str(base))
                phrase_contours = blended_contours

        if register_last_contours:
            self.owner._last_generated_phrase_contours = list(phrase_contours)

        phrase_contours, notes_per_phrase = self._align_phrase_plan_lengths(
            list(phrase_contours),
            list(notes_per_phrase),
        )

        fps = float(first_phrase_note_scale)
        if abs(fps - 1.0) > 1e-6 and notes_per_phrase:
            old0 = notes_per_phrase[0]
            new0 = max(1, int(round(old0 * fps)))
            diff = old0 - new0
            notes_per_phrase[0] = new0
            if len(notes_per_phrase) > 1 and diff != 0:
                notes_per_phrase[1] = max(1, int(notes_per_phrase[1] + diff))

        cap = melody_max_notes_per_phrase
        if cap is not None and cap >= 1:
            notes_per_phrase = [max(1, min(int(n), int(cap))) for n in notes_per_phrase]
        phrase_contours, notes_per_phrase = self._align_phrase_plan_lengths(
            list(phrase_contours),
            list(notes_per_phrase),
        )

        hook_on = resolve_config("composition", "chorus_hook_composer_enabled", True, bool)
        hook_strength = resolve_config("composition", "chorus_hook_composer_strength", 0.72, float)
        if hook_on:
            phrase_contours, notes_per_phrase = self._stabilize_chorus_hook_phrase_plan(
                list(phrase_contours),
                list(notes_per_phrase),
                section_role=section_role,
                strength=float(hook_strength),
            )
        st_on = resolve_config("composition", "phrase_state_conditioning_enabled", True, bool)
        st_strength = resolve_config("composition", "phrase_state_conditioning_strength", 0.72, float)
        if st_on:
            phrase_contours, notes_per_phrase = self._apply_phrase_state_conditioning(
                list(phrase_contours),
                list(notes_per_phrase),
                section_role=section_role,
                strength=float(st_strength),
            )

        return phrase_contours, notes_per_phrase, temp_mult, density_mult
