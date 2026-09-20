# composition/melody_runtime_rhythm.py
"""Post-generation rhythm/target/fill shaping for MelodyRuntime.

Split 2026-07-14 from the single 1,789-line melody_runtime.py (see
melody_runtime_phrase_plan.py for the full split rationale). This layer sits
parallel to melody_runtime_prepare.py (both depend only on the leaf layer,
not on each other): bar-intent bridging, phrase rhythm template selection
and application, onset-step planning, phrase mid/end target enforcement,
cadence contract enforcement, and phrase-boundary fills. These only call
`self.owner` state and `cls._choose_phrase_rhythm_template` (same file) --
nothing here calls into melody_runtime_phrase_plan.py or
melody_runtime_prepare.py.
"""

from __future__ import annotations

import random
from typing import List, Optional, Tuple

from audiogen_core.config import resolve_config
from data.melody_emotion_profiles import melody_emotion_profile_for_emotion
from data.melody_rhythm_profiles import melody_rhythm_profile_for_emotion
from data.music_data import EmotionProfile


class _MelodyRhythmMixin:
    """Shapes generated melody token rhythm, targets, cadences, and fills."""

    def _bar_intent_rows_for_current_section(self, *, chords: Optional[List[str]] = None) -> Optional[List[dict]]:
        """
        Best-effort composition→Markov intent bridge.

        SectionPlanner stores compact per-bar intent arrays on the composition owner;
        we expose them to the Markov generator as a list of dicts (one per bar).
        """
        owner = self.owner
        try:
            n = int(len(list(chords or [])) or 0)
        except Exception:
            n = 0
        if n <= 0:
            return None
        try:
            hf = getattr(owner, "_section_harmony_function_target_profile", None)
            hf = list(hf) if isinstance(hf, list) else []
        except Exception:
            hf = []
        try:
            cad = getattr(owner, "_section_cadence_strength_profile", None)
            cad = list(cad) if isinstance(cad, list) else []
        except Exception:
            cad = []
        try:
            ten = getattr(owner, "_section_tension_profile", None)
            ten = list(ten) if isinstance(ten, list) else []
        except Exception:
            ten = []
        try:
            md = getattr(owner, "_section_melody_density_profile", None)
            md = list(md) if isinstance(md, list) else []
        except Exception:
            md = []

        out: List[dict] = []
        for i in range(int(n)):
            row = {}
            if i < len(hf):
                try:
                    row["harmony_function_target"] = str(hf[i] or "").strip().upper()
                except Exception:
                    pass
            if i < len(cad):
                try:
                    row["cadence_strength"] = float(cad[i])
                except Exception:
                    pass
            if i < len(ten):
                try:
                    row["tension"] = float(ten[i])
                except Exception:
                    pass
            if i < len(md):
                try:
                    row["melody_activity_target"] = float(md[i])
                except Exception:
                    pass
            out.append(row)
        return out if any(bool(r) for r in out) else None

    @staticmethod
    def _choose_phrase_rhythm_template(
        *,
        contour: str,
        emotion: EmotionProfile,
        notes_in_phrase: int,
        half_index: int = 0,
        rng=random,
    ) -> List[float]:
        """
        Return a bar-length template (sums to 4 beats) that will be tiled across the phrase.
        CPU-cheap + stable groove: pick once per phrase, then repeat with small variation.
        """
        density = float(getattr(emotion, "density", 0.5) or 0.5)
        name = (getattr(emotion, "name", "") or "").lower()
        n = int(max(1, notes_in_phrase))

        # Core templates (each sums to 4.0)
        templates: List[List[float]] = [
            [1.0, 1.0, 1.0, 1.0],                           # quarter pulse
            [0.5, 0.5, 1.0, 1.0, 0.5, 0.5],                 # 8ths + quarters
            [0.5] * 8,                                      # straight 8ths
            [1.0, 0.5, 0.5, 1.0, 0.5, 0.5],                 # light syncopation
            [0.75, 0.25, 0.5, 0.5, 1.0, 1.0],               # pickup-ish
        ]

        # Bias: excitement/optimism → more 8ths; sadness/grief → longer notes.
        w = [1.0] * len(templates)
        profile = melody_rhythm_profile_for_emotion(name)
        short_bias = max(0.55, min(1.5, float(profile.get("short_bias", 1.0))))
        sync_bias = max(0.6, min(1.4, float(profile.get("syncopation_bias", 1.0))))
        long_bias = max(0.65, min(1.6, float(profile.get("long_bias", 1.0))))

        # Per-emotion melody profile can further nudge rhythm selection.
        emo_profile = melody_emotion_profile_for_emotion(name)
        strict = resolve_config("composition", "emotion_melody_strictness", 0.7, float)
        strict = max(0.0, min(1.0, strict))
        eb_sync = max(0.5, min(1.8, float(emo_profile.syncopation_bias)))
        eb_short = max(0.5, min(1.8, float(emo_profile.short_note_bias)))
        eb_long = max(0.5, min(1.8, float(emo_profile.long_note_bias)))
        # Blend by raising to strictness (keeps 1.0 as neutral).
        sync_bias *= eb_sync ** strict
        short_bias *= eb_short ** strict
        long_bias *= eb_long ** strict

        w[1] *= short_bias
        w[2] *= short_bias
        w[3] *= sync_bias
        w[4] *= sync_bias
        w[0] *= long_bias

        # 16-bar sections often read like "4-bar loop x4" if each phrase uses the same
        # groove template. Nudge the second half toward a different feel (more motion /
        # syncopation) without increasing generation attempts or CPU.
        try:
            hi = int(half_index)
        except Exception:
            hi = 0
        if hi >= 1:
            w[3] *= 1.18
            w[4] *= 1.22
            w[0] *= 0.78

        if density >= 0.62:
            w[2] *= 1.55
            w[1] *= 1.25
            w[0] *= 0.65
        if "sad" in name or "grief" in name or "remorse" in name or "relief" in name or "love" in name:
            w[0] *= 1.65
            w[2] *= 0.55
            w[4] *= 0.85
        if "joy" in name or "excit" in name or "optim" in name or "amuse" in name:
            w[2] *= 1.45
            w[3] *= 1.15
            w[0] *= 0.7
        if (contour or "") == "static":
            w[0] *= 1.2
            w[4] *= 0.9
        elif (contour or "") in {"asc", "arch"}:
            w[1] *= 1.1
            w[3] *= 1.15

        # If the phrase has very few notes, prefer longer templates.
        if n <= 4:
            w[0] *= 1.8
            w[2] *= 0.5
        elif n >= 10:
            w[2] *= 1.35

        t = rng.choices(templates, weights=w, k=1)[0]
        return list(t)

    @classmethod
    def _apply_phrase_rhythm_templates(
        cls,
        melody_tokens: List[Tuple[int, float]],
        *,
        emotion: EmotionProfile,
        phrase_contours: List[str],
        notes_per_phrase: List[int],
        total_beats: Optional[int],
        rng=random,
        beats_per_bar: float = 4.0,
    ) -> List[Tuple[int, float]]:
        """
        Replace the Markov-generated durations with a phrase-stable rhythm template.
        Degrees/rests remain unchanged; only duration values are adjusted.
        """
        if not melody_tokens or not notes_per_phrase or not phrase_contours:
            return melody_tokens
        if total_beats is None or total_beats <= 0:
            return melody_tokens

        # If the model already produced many 16ths, don't fight it.
        # (Keeps fast arps snappy.)
        short_count = sum(1 for _, d in melody_tokens if float(d) <= 0.25 + 1e-9)
        if short_count >= max(6, len(melody_tokens) // 4):
            return melody_tokens

        out = list(melody_tokens)
        idx = 0
        phrase_beats = float(total_beats) / max(1, len(list(notes_per_phrase)))
        phrase_bars = max(1, int(round(phrase_beats / float(beats_per_bar))))
        phrase_beats = float(phrase_bars) * float(beats_per_bar)

        allowed = (0.25, 0.5, 0.75, 1.0, 1.5, 2.0, 3.0, 4.0)

        def _snap(d: float) -> float:
            return float(min(allowed, key=lambda a: abs(float(a) - float(d))))

        for p_idx, n in enumerate(list(notes_per_phrase)):
            if idx >= len(out):
                break
            n = int(n)
            if n <= 0:
                continue
            end = min(len(out), idx + n)
            if end <= idx:
                idx = end
                continue

            contour = phrase_contours[p_idx] if p_idx < len(phrase_contours) else "arch"
            half_index = 0
            try:
                half_index = 1 if int(p_idx) >= (len(list(notes_per_phrase)) // 2) else 0
            except Exception:
                half_index = 0
            template_bar = cls._choose_phrase_rhythm_template(
                contour=str(contour),
                emotion=emotion,
                notes_in_phrase=(end - idx),
                half_index=int(half_index),
                rng=rng,
            )
            # Tile across bars in this phrase, then truncate/extend.
            template = list(template_bar) * phrase_bars

            # Build exactly (end-idx) durations that sum to phrase_beats.
            desired_len = end - idx
            durs: List[float] = []
            pos = 0
            while len(durs) < desired_len and pos < len(template) * 4:
                durs.append(float(template[pos % len(template)]))
                pos += 1

            # Fix sum to match phrase_beats by adjusting the last duration.
            s = float(sum(durs))
            if s <= 1e-6:
                idx = end
                continue
            # Scale gently when far off (keeps groove feel).
            if abs(s - phrase_beats) > 0.75:
                scale = phrase_beats / s
                durs = [max(0.25, _snap(d * scale)) for d in durs]
                s = float(sum(durs))

            # Final exact-fit adjustment on the last note.
            remainder = float(phrase_beats - (s - durs[-1]))
            remainder = max(0.25, min(4.0, remainder))
            durs[-1] = _snap(remainder)

            # Apply back.
            for j, dur in enumerate(durs):
                deg, _old = out[idx + j]
                out[idx + j] = (deg, float(dur))

            idx = end

        return out

    @classmethod
    def plan_phrase_rhythm_onset_steps_by_bar(
        cls,
        *,
        emotion: EmotionProfile,
        phrase_contours: List[str],
        notes_per_phrase: List[int],
        bars: int,
        beats_per_bar: float = 4.0,
        grid: float = 0.25,
        rng=random,
    ) -> List[List[int]]:
        """
        Plan a deterministic per-bar onset-step pattern derived from the same phrase
        rhythm templates used in `_apply_phrase_rhythm_templates`.

        Returns a list of length `bars`, where each entry is a sorted list of step
        indices (0..steps_per_bar-1) corresponding to note onsets in that bar.
        """
        try:
            bars_i = int(bars)
        except Exception:
            bars_i = 0
        if bars_i <= 0 or beats_per_bar <= 1e-9 or grid <= 1e-9:
            return []
        if not phrase_contours or not notes_per_phrase:
            return [[] for _ in range(bars_i)]

        steps_per_bar = max(1, int(round(float(beats_per_bar) / float(grid))))
        onsets_by_bar: List[List[int]] = [[] for _ in range(bars_i)]

        # Reuse the same phrase bar sizing as `_apply_phrase_rhythm_templates`.
        total_beats = float(bars_i) * float(beats_per_bar)
        phrase_beats = float(total_beats) / max(1, len(list(notes_per_phrase)))
        phrase_bars = max(1, int(round(phrase_beats / float(beats_per_bar))))
        phrase_beats = float(phrase_bars) * float(beats_per_bar)

        idx = 0
        beat_cursor = 0.0
        for p_idx, n in enumerate(list(notes_per_phrase)):
            if idx >= sum(int(x) for x in list(notes_per_phrase) if int(x) > 0):
                break
            n = int(n)
            if n <= 0:
                continue

            contour = phrase_contours[p_idx] if p_idx < len(phrase_contours) else "arch"
            half_index = 0
            try:
                half_index = 1 if int(p_idx) >= (len(list(notes_per_phrase)) // 2) else 0
            except Exception:
                half_index = 0
            template_bar = cls._choose_phrase_rhythm_template(
                contour=str(contour),
                emotion=emotion,
                notes_in_phrase=int(n),
                half_index=int(half_index),
                rng=rng,
            )
            template = list(template_bar) * int(phrase_bars)

            # Build n durations (best-effort) and derive onset positions.
            durs: List[float] = []
            pos = 0
            while len(durs) < int(n) and pos < len(template) * 4:
                durs.append(float(template[pos % len(template)]))
                pos += 1
            s = float(sum(durs)) if durs else 0.0
            if s > 1e-6 and abs(s - float(phrase_beats)) > 0.75:
                scale = float(phrase_beats) / float(s)
                durs = [max(0.25, float(d) * float(scale)) for d in durs]

            # Emit onsets for each duration inside the section timeline.
            t = float(beat_cursor)
            for dur in durs:
                bar = int(t // float(beats_per_bar))
                if bar < 0 or bar >= bars_i:
                    break
                bar_pos = float(t - float(bar) * float(beats_per_bar))
                step = int(round(float(bar_pos) / float(grid)))
                step = max(0, min(int(steps_per_bar) - 1, int(step)))
                onsets_by_bar[bar].append(int(step))
                t += float(dur)
                idx += 1
                if idx >= sum(int(x) for x in list(notes_per_phrase) if int(x) > 0):
                    break
            beat_cursor += float(phrase_beats)
            if beat_cursor >= total_beats - 1e-9:
                break

        # De-dup + sort.
        for b in range(bars_i):
            if onsets_by_bar[b]:
                onsets_by_bar[b] = sorted(set(int(s) for s in onsets_by_bar[b]))
        return onsets_by_bar

    @staticmethod
    def _enforce_phrase_mid_targets(
        melody_tokens: List[Tuple[int, float]],
        *,
        emotion: EmotionProfile,
        phrase_contours: List[str],
        notes_per_phrase: List[int],
    ) -> List[Tuple[int, float]]:
        """
        Enforce a mid-phrase "goal note" (PhrasePlan.target_climax) near the planned climax position.
        This makes phrases feel directed before the cadence pull takes over.
        """
        if not melody_tokens or not notes_per_phrase or not phrase_contours:
            return melody_tokens

        try:
            from ai.markov.melody.phrase_planner import PhrasePlanner

            planner = PhrasePlanner()
            plans = planner.generate_plans(list(phrase_contours), len(list(notes_per_phrase)), emotion)
        except Exception:
            return melody_tokens

        out = list(melody_tokens)
        idx = 0
        for phrase_idx, n in enumerate(list(notes_per_phrase)):
            if idx >= len(out):
                break
            n = int(n)
            if n <= 0:
                continue
            end = min(len(out), idx + n)
            if end - idx <= 2:
                idx = end
                continue

            plan = plans[phrase_idx] if phrase_idx < len(plans) else None
            target = getattr(plan, "target_climax", None) if plan is not None else None
            if target is None:
                idx = end
                continue
            target = int(target)
            pos = float(getattr(plan, "climax_position", 0.67) if plan is not None else 0.67)
            pos = max(0.25, min(0.85, pos))

            mid_i = idx + int(round(pos * float((end - idx) - 1)))
            # Find nearest non-rest around mid_i within a small window.
            win = max(1, int(round((end - idx) * 0.12)))
            cand = None
            for r in range(win + 1):
                for j in (mid_i - r, mid_i + r):
                    if j < idx or j >= end:
                        continue
                    deg = out[j][0]
                    if isinstance(deg, int) and deg >= 0:
                        cand = j
                        break
                if cand is not None:
                    break

            if cand is not None:
                deg, dur = out[cand]
                if int(deg) != target:
                    out[cand] = (target, dur)

            idx = end

        return out

    @staticmethod
    def _enforce_phrase_targets(
        melody_tokens: List[Tuple[int, float]],
        *,
        emotion: EmotionProfile,
        phrase_contours: List[str],
        notes_per_phrase: List[int],
        enforce_last: bool = True,
        enforce_pre_cadence: bool = True,
    ) -> List[Tuple[int, float]]:
        """
        Make melodies more goal-directed by *guaranteeing* phrase-end targets.

        The Markov generator already biases toward phrase-plan cadence degrees, but
        it can miss them after post-processing (rests, embellishments, repetition).
        This pass corrects the final 1–2 melodic degrees per phrase with minimal edits.
        """
        if not melody_tokens or not notes_per_phrase or not phrase_contours:
            return melody_tokens

        try:
            from ai.markov.melody.phrase_planner import PhrasePlanner

            planner = PhrasePlanner()
            plans = planner.generate_plans(list(phrase_contours), len(list(notes_per_phrase)), emotion)
        except Exception:
            return melody_tokens

        out = list(melody_tokens)
        idx = 0
        for phrase_idx, n in enumerate(list(notes_per_phrase)):
            if idx >= len(out):
                break
            if n <= 0:
                continue
            end = min(len(out), idx + int(n))
            if end - idx <= 0:
                idx = end
                continue

            plan = plans[phrase_idx] if phrase_idx < len(plans) else None
            if plan is None:
                idx = end
                continue

            # Find last non-rest note within this phrase slice.
            last_i = None
            for j in range(end - 1, idx - 1, -1):
                deg = out[j][0]
                if isinstance(deg, int) and deg >= 0:
                    last_i = j
                    break

            if last_i is None:
                idx = end
                continue

            # Optionally enforce pre-cadence on the previous non-rest note.
            if enforce_pre_cadence and (end - idx) >= 2 and getattr(plan, "pre_cadence_degree", None) is not None:
                pre_target = int(plan.pre_cadence_degree)
                prev_i = None
                for j in range(last_i - 1, idx - 1, -1):
                    deg = out[j][0]
                    if isinstance(deg, int) and deg >= 0:
                        prev_i = j
                        break
                if prev_i is not None:
                    prev_deg, prev_dur = out[prev_i]
                    if isinstance(prev_deg, int) and prev_deg != pre_target:
                        out[prev_i] = (pre_target, prev_dur)

            if enforce_last and getattr(plan, "cadence_degree", None) is not None:
                target = int(plan.cadence_degree)
                # Phrase "question/answer" behavior:
                # non-final phrases should more often avoid full tonic closure.
                try:
                    phrase_role = str(getattr(plan, "phrase_role", "") or "").lower()
                except Exception:
                    phrase_role = ""
                if phrase_role in {"opening", "answer"} and target == 0:
                    # Prefer a non-tonic landing (scale degrees 4 or 6 read as half-cadence-ish).
                    target = int(getattr(plan, "pre_cadence_degree", 4) or 4)
                deg, dur = out[last_i]
                if isinstance(deg, int) and deg != target:
                    out[last_i] = (target, dur)

            idx = end

        return out

    @staticmethod
    def _enforce_cadence_contracts(
        melody_tokens: List[Tuple[int, float]],
        *,
        emotion: EmotionProfile,
        phrase_contours: List[str],
        notes_per_phrase: List[int],
        section_role: Optional[str] = None,
        strength: float = 0.76,
    ) -> List[Tuple[int, float]]:
        """
        Strengthen phrase-end contracts:
        - explicit approach degree -> cadence degree near phrase boundary
        - minimum cadence hold duration by phrase role
        """
        if not melody_tokens or not notes_per_phrase or not phrase_contours:
            return list(melody_tokens)
        s = max(0.0, min(1.0, float(strength)))
        if s <= 1e-6:
            return list(melody_tokens)

        try:
            from ai.markov.melody.phrase_planner import PhrasePlanner

            planner = PhrasePlanner()
            plans = planner.generate_plans(list(phrase_contours), len(list(notes_per_phrase)), emotion, section_role=section_role)
        except Exception:
            return list(melody_tokens)

        out = list(melody_tokens)
        idx = 0
        role_lc = str(section_role or "").strip().lower()
        chorusish = role_lc in {"b", "chorus", "hook", "tag", "outro", "ending"}
        for p_idx, n in enumerate(list(notes_per_phrase)):
            if idx >= len(out):
                break
            n = max(0, int(n))
            end = min(len(out), idx + n)
            if end - idx <= 0:
                idx = end
                continue
            plan = plans[p_idx] if p_idx < len(plans) else None
            if plan is None:
                idx = end
                continue

            voiced_idx = [j for j in range(idx, end) if isinstance(out[j][0], int) and int(out[j][0]) >= 0]
            if not voiced_idx:
                idx = end
                continue
            last_i = int(voiced_idx[-1])
            prev_i = int(voiced_idx[-2]) if len(voiced_idx) >= 2 else None

            cadence_target = int(getattr(plan, "cadence_degree", 0) or 0) % 7
            pre_target = getattr(plan, "pre_cadence_degree", None)
            if pre_target is not None:
                pre_target = int(pre_target) % 7

            # Harder landing in chorus/outro cadences.
            if chorusish and str(getattr(plan, "phrase_role", "") or "").lower() == "cadence":
                cadence_target = int(cadence_target)

            deg, dur = out[last_i]
            if s >= 0.5 and int(deg) != int(cadence_target):
                out[last_i] = (int(cadence_target), float(dur))

            if prev_i is not None and pre_target is not None and s >= 0.35:
                pdeg, pdur = out[prev_i]
                if int(pdeg) != int(pre_target):
                    out[prev_i] = (int(pre_target), float(pdur))

            # Cadence hold contract: give phrase endings enough sustain.
            try:
                cur_last_dur = float(out[last_i][1])
            except Exception:
                cur_last_dur = 0.25
            phrase_role = str(getattr(plan, "phrase_role", "") or "").lower()
            min_hold = 0.45 + 0.35 * s
            if phrase_role == "cadence":
                min_hold += 0.20 * s
            if chorusish and phrase_role == "cadence":
                min_hold += 0.15 * s
            min_hold = max(0.5, min(2.0, float(min_hold)))
            if cur_last_dur + 1e-9 < float(min_hold) and prev_i is not None:
                try:
                    prev_dur = float(out[prev_i][1])
                except Exception:
                    prev_dur = 0.25
                borrow = min(max(0.0, prev_dur - 0.25), float(min_hold) - float(cur_last_dur))
                if borrow > 1e-9:
                    out[prev_i] = (int(out[prev_i][0]), float(max(0.25, prev_dur - borrow)))
                    out[last_i] = (int(out[last_i][0]), float(cur_last_dur + borrow))

            idx = end

        return out

    @staticmethod
    def _apply_phrase_boundary_fills(
        melody_tokens: List[Tuple[int, float]],
        *,
        emotion: EmotionProfile,
        phrase_contours: List[str],
        notes_per_phrase: List[int],
        fill_beats: float = 0.5,
        min_last_hold_beats: float = 1.0,
    ) -> List[Tuple[int, float]]:
        """
        Add a tiny stepwise pickup into phrase-end cadences when there's space.

        This is intentionally conservative:
        - only when the final cadence note is held long enough (>= min_last_hold_beats)
        - does NOT change token count (important for downstream assumptions/tests)
        - reuses an existing rest right before cadence as the pickup slot when available
        - preserves total phrase duration by borrowing time from the last note
        """
        if not melody_tokens or not notes_per_phrase or not phrase_contours:
            return melody_tokens

        try:
            from ai.markov.melody.phrase_planner import PhrasePlanner

            planner = PhrasePlanner()
            plans = planner.generate_plans(list(phrase_contours), len(list(notes_per_phrase)), emotion)
        except Exception:
            return melody_tokens

        fb = max(0.25, float(fill_beats))
        min_hold = max(fb + 1e-6, float(min_last_hold_beats))

        out: List[Tuple[int, float]] = list(melody_tokens)
        idx = 0
        phrase_i = 0
        for n in list(notes_per_phrase):
            if idx >= len(out):
                break
            n = int(n)
            if n <= 0:
                phrase_i += 1
                continue
            end = min(len(out), idx + n)
            if end - idx <= 2:
                idx = end
                phrase_i += 1
                continue

            plan = plans[phrase_i] if phrase_i < len(plans) else None
            target = int(getattr(plan, "cadence_degree", 0) if plan is not None else 0)
            pre = getattr(plan, "pre_cadence_degree", None) if plan is not None else None
            approach = int(pre) if pre is not None else int((target - 1) % 7)
            if approach == target:
                approach = int((target + 1) % 7)

            # Find last non-rest note in phrase slice.
            last_i = None
            for j in range(end - 1, idx - 1, -1):
                deg = out[j][0]
                if isinstance(deg, int) and deg >= 0:
                    last_i = j
                    break
            if last_i is None:
                idx = end
                phrase_i += 1
                continue

            last_deg, last_dur = out[last_i]
            try:
                last_dur = float(last_dur)
            except Exception:
                last_dur = 0.0
            if last_dur < min_hold:
                idx = end
                phrase_i += 1
                continue

            # Reuse a rest slot near the cadence, if present.
            # Search backwards from the last note for a rest token inside this phrase.
            rest_i = None
            for j in range(last_i - 1, max(idx - 1, last_i - 4), -1):
                deg = out[j][0]
                if isinstance(deg, int) and deg < 0:
                    rest_i = j
                    break
            if rest_i is None:
                idx = end
                phrase_i += 1
                continue

            # Borrow time from the last note and assign it to the rest slot,
            # turning that rest into an approach tone.
            new_last_dur = max(0.25, last_dur - fb)
            if new_last_dur >= last_dur - 1e-9:
                idx = end
                phrase_i += 1
                continue
            out[last_i] = (int(last_deg), float(new_last_dur))
            _rest_deg, rest_dur = out[rest_i]
            try:
                rest_dur = float(rest_dur)
            except Exception:
                rest_dur = fb
            out[rest_i] = (int(approach), float(max(0.25, min(rest_dur + fb, 4.0))))

            # Shift indices: we inserted one token inside this phrase slice.
            idx = end
            phrase_i += 1

        return out
