# composition/song_generator/forms.py
# Arrangement-form generators (default/pop/pop_ext/rondo/ballad/wave/anthem/ambient).
# Each builds a List[SongSectionSpec] for one song shape, then applies the shared
# emotion-arc and root-motion-arc helpers from `form_helpers.py`.
#
# NOTE: these were originally @staticmethod on `SongGenerator`, calling sibling
# helpers via the hardcoded class name (`SongGenerator._apply_root_motion_arc(...)`).
# That only resolves correctly when the method executes as an attribute of the
# fully-assembled `SongGenerator` class, so moving them into a separate mixin module
# required converting them to @classmethod and rewriting those hardcoded
# `SongGenerator.` call sites to `cls.` — otherwise `SongGenerator` would need to be
# imported into this module, which would be circular (this mixin is a base of that
# same class). `cls` binds correctly via MRO no matter which mixin defines the callee.

from __future__ import annotations

from typing import List, Optional

from data.audit import normalize_emotion_scalars
from data.emotion_aliases import canonical_emotion_name
from data.music_data import EMOTION_BY_NAME

from .models import SongSectionSpec


class FormsMixin:
    """Arrangement-form section-spec builders (default_form, pop_form, ...)."""

    @classmethod
    def default_form(
        cls,
        base_emotion_name: str,
        *,
        bars_per_section: int = 16,
        root_note: int = 60,
    ) -> List[SongSectionSpec]:
        """
        Simple radio-like arc. Matches arrangement form ``default``:
        intro → verse → pre-chorus → chorus → verse → chorus → outro.
        """
        name = canonical_emotion_name(base_emotion_name)
        b = max(4, int(bars_per_section))
        # Target first chorus ("b") at bar 17 (1-indexed): intro + verse + pre = 16 bars.
        intro_b = max(4, min(8, b // 2))
        # Verses are intentionally shorter than choruses so the song moves and
        # chorus returns feel frequent (more "song-like" than loop-like).
        verse_b = max(6, int(b) - 8)
        pre_b = max(4, min(8, int(round(b * 0.5))))
        chorus_b = max(6, b)
        outro_b = max(6, int(round(b * 0.6)))
        t_intro, t_verse, t_pre, t_chorus, t_verse2, t_chorus2, t_outro = cls._default_form_role_targets(name)
        specs = [
            SongSectionSpec(name, bars=intro_b, root_note=root_note, temperature=0.62, target_notes_per_bar=t_intro),   # intro
            SongSectionSpec(name, bars=verse_b, root_note=root_note, temperature=0.66, target_notes_per_bar=t_verse),   # verse
            SongSectionSpec(name, bars=pre_b, root_note=root_note, temperature=0.70, target_notes_per_bar=t_pre),       # pre-chorus
            SongSectionSpec(name, bars=chorus_b, root_note=root_note, temperature=0.73, target_notes_per_bar=t_chorus), # chorus
            SongSectionSpec(name, bars=verse_b, root_note=root_note, temperature=0.67, target_notes_per_bar=t_verse2),  # verse 2
            SongSectionSpec(name, bars=chorus_b, root_note=root_note, temperature=0.74, target_notes_per_bar=t_chorus2),# chorus 2
            SongSectionSpec(name, bars=outro_b, root_note=root_note, temperature=0.58, target_notes_per_bar=t_outro),   # outro
        ]
        return cls._apply_root_motion_arc("default", cls._apply_emotion_arc(name, "default", specs))

    @classmethod
    def pop_form(
        cls,
        base_emotion_name: str,
        *,
        bars_per_section: int = 8,
        root_note: int = 60,
    ) -> List[SongSectionSpec]:
        """
        Verse–chorus–verse–chorus–bridge–final chorus–outro.

        Choruses are slightly shorter and denser; bridge gets more bars and
        harmonic exploration; verses are narrative (moderate density).

        Must match ArrangementPolicy form_mode `dialogue (call and response)` (8 sections).
        """
        name = canonical_emotion_name(base_emotion_name)
        b = max(4, int(bars_per_section))
        intro_b = cls._bars_scaled(b, 0.72, minimum=6)
        verse_b = cls._bars_scaled(b, 1.0, minimum=6)
        chorus_b = cls._bars_scaled(b, 0.74, minimum=6)
        bridge_b = cls._bars_scaled(b, 1.28, minimum=8)
        final_chorus_b = cls._bars_scaled(b, 0.88, minimum=8)
        outro_b = max(6, b // 2)
        specs = [
            SongSectionSpec(
                name, bars=intro_b, root_note=root_note, temperature=0.62, target_notes_per_bar=3.8, melody_style="auto",
            ),
            SongSectionSpec(
                name, bars=verse_b, root_note=root_note, temperature=0.66, target_notes_per_bar=5.6, melody_style="auto",
            ),
            SongSectionSpec(
                name, bars=chorus_b, root_note=root_note, temperature=0.73, target_notes_per_bar=7.0, melody_style="auto",
            ),
            SongSectionSpec(
                name, bars=verse_b, root_note=root_note, temperature=0.66, target_notes_per_bar=5.6, melody_style="auto",
            ),
            SongSectionSpec(
                name, bars=chorus_b, root_note=root_note, temperature=0.73, target_notes_per_bar=7.0, melody_style="auto",
            ),
            SongSectionSpec(
                name, bars=bridge_b, root_note=root_note, temperature=0.77, target_notes_per_bar=6.6, melody_style="auto",
            ),
            SongSectionSpec(
                name, bars=final_chorus_b, root_note=root_note, temperature=0.74, target_notes_per_bar=7.4, melody_style="auto",
            ),
            SongSectionSpec(
                name, bars=outro_b, root_note=root_note, temperature=0.58, target_notes_per_bar=3.2, melody_style="auto",
            ),
        ]
        return cls._apply_root_motion_arc(
            "dialogue (call and response)",
            cls._apply_emotion_arc(name, "dialogue (call and response)", specs),
        )

    @classmethod
    def pop_ext_form(
        cls,
        base_emotion_name: str,
        *,
        bars_per_section: int = 8,
        root_note: int = 60,
        base_tempo_bpm: Optional[float] = None,
        target_seconds: Optional[float] = None,
        max_bars: int = 64,
    ) -> List[SongSectionSpec]:
        """
        Pop form with pre-chorus before each chorus, a hook tag, then outro.

        Must match ArrangementPolicy form_mode ``pop_ext`` (11 sections).
        """
        name = canonical_emotion_name(base_emotion_name)
        # If a time budget is supplied, compute a total bar count and allocate it so the first
        # chorus ("b") arrives relatively early (≈bar 17, 1-indexed) for quicker lift:
        # intro + verse + pre-chorus = 16 bars.
        emotion = EMOTION_BY_NAME.get(name)
        total_bars = None
        if emotion is not None and base_tempo_bpm is not None and target_seconds is not None:
            tempo_m, _, _ = normalize_emotion_scalars(emotion)
            bpm = float(base_tempo_bpm) * float(tempo_m)
            bar_seconds = 4.0 * 60.0 / max(1.0, bpm)
            total_bars = int(round(float(target_seconds) / max(0.01, bar_seconds)))
            total_bars = max(32, min(int(max_bars), total_bars))

        if total_bars is not None:
            # Fixed early arc for "chorus around bar 17".
            intro_b = 4
            verse1_b = 8
            pre1_b = 4
            # Chorus lengths must leave room for the remaining 7 sections.
            # Default to a tight 6-bar chorus for a 2:30-ish target at ~70 BPM.
            chorus1_b = 6
            chorus2_b = 6
            post_b = 2
            verse2_b = 2
            pre2_b = 2
            a_prime_b = 2
            tag_b = 2
            outro_b = 2

            bars_list = [
                intro_b,
                verse1_b,
                pre1_b,
                chorus1_b,
                verse2_b,
                pre2_b,
                chorus2_b,
                post_b,
                a_prime_b,
                tag_b,
                outro_b,
            ]

            # Fix rounding drift to match total_bars exactly (prefer to adjust A'/tag/outro then chorus).
            drift = int(total_bars) - int(sum(bars_list))
            if drift != 0:
                # Keep the "chorus at bar ~25" constraint:
                # intro + verse1 + pre1 must stay exactly 16 bars, so never adjust indices 0..2.
                order = [8, 9, 10, 3, 6, 7, 4, 5]
                step = 1 if drift > 0 else -1
                for i in range(abs(drift)):
                    idx = order[i % len(order)]
                    # Keep every section >= 2 bars; keep verse1 >= 12; keep pre1 >= 4.
                    floor = 2
                    if bars_list[idx] + step >= floor:
                        bars_list[idx] += step

            (intro_b, verse1_b, pre1_b, chorus1_b, verse2_b, pre2_b, chorus2_b, post_b, a_prime_b, tag_b, outro_b) = bars_list
        else:
            # Legacy bar allocation (scaled by bars_per_section).
            b = max(4, int(bars_per_section))
            intro_b = cls._bars_scaled(b, 0.70, minimum=6)
            verse1_b = cls._bars_scaled(b, 1.0, minimum=6)
            pre1_b = max(4, int(round(b * 0.42)))
            chorus1_b = cls._bars_scaled(b, 0.72, minimum=6)
            verse2_b = verse1_b
            pre2_b = pre1_b
            chorus2_b = chorus1_b
            post_b = cls._bars_scaled(b, 1.22, minimum=8)  # formerly "bridge"
            a_prime_b = cls._bars_scaled(b, 0.86, minimum=8)  # formerly "final chorus"
            tag_b = max(4, int(round(b * 0.36)))
            outro_b = max(6, b // 2)

        specs = [
            SongSectionSpec(name, bars=intro_b, root_note=root_note, temperature=0.62, target_notes_per_bar=3.8, melody_style="auto"),
            SongSectionSpec(name, bars=verse1_b, root_note=root_note, temperature=0.66, target_notes_per_bar=5.6, melody_style="auto"),
            SongSectionSpec(name, bars=pre1_b, root_note=root_note, temperature=0.70, target_notes_per_bar=6.2, melody_style="auto"),
            SongSectionSpec(name, bars=chorus1_b, root_note=root_note, temperature=0.73, target_notes_per_bar=7.0, melody_style="auto"),
            SongSectionSpec(name, bars=verse2_b, root_note=root_note, temperature=0.66, target_notes_per_bar=5.6, melody_style="auto"),
            SongSectionSpec(name, bars=pre2_b, root_note=root_note, temperature=0.70, target_notes_per_bar=6.2, melody_style="auto"),
            SongSectionSpec(name, bars=chorus2_b, root_note=root_note, temperature=0.73, target_notes_per_bar=7.0, melody_style="auto"),
            # post-chorus / lift / short contrast (uses "b" curve in policy sequence)
            SongSectionSpec(name, bars=post_b, root_note=root_note, temperature=0.77, target_notes_per_bar=6.6, melody_style="auto"),
            SongSectionSpec(name, bars=a_prime_b, root_note=root_note, temperature=0.74, target_notes_per_bar=7.4, melody_style="auto"),
            SongSectionSpec(name, bars=tag_b, root_note=root_note, temperature=0.72, target_notes_per_bar=7.8, melody_style="auto"),
            SongSectionSpec(name, bars=outro_b, root_note=root_note, temperature=0.58, target_notes_per_bar=3.2, melody_style="auto"),
        ]
        return cls._apply_root_motion_arc("pop_ext", cls._apply_emotion_arc(name, "pop_ext", specs))

    @classmethod
    def rondo_form(
        cls,
        base_emotion_name: str,
        *,
        bars_per_section: int = 8,
        root_note: int = 60,
    ) -> List[SongSectionSpec]:
        """
        Intro + A–B–A'–C–A' + outro (rondo refrains use the A / A' curves).

        Episodes (B, C) are slightly shorter and more contrasting; refrains
        share a stable narrative density; C is given room to develop.

        Must match ArrangementPolicy form_mode `rondo` (7 sections).
        """
        name = canonical_emotion_name(base_emotion_name)
        b = max(4, int(bars_per_section))
        intro_b = cls._bars_scaled(b, 0.65, minimum=6)
        refrain_b = cls._bars_scaled(b, 1.0, minimum=6)
        episode_b = cls._bars_scaled(b, 0.78, minimum=6)
        c_b = cls._bars_scaled(b, 1.12, minimum=8)
        outro_b = max(6, b // 2)
        specs = [
            SongSectionSpec(
                name, bars=intro_b, root_note=root_note, temperature=0.63, target_notes_per_bar=3.6, melody_style="auto",
            ),
            SongSectionSpec(
                name, bars=refrain_b, root_note=root_note, temperature=0.68, target_notes_per_bar=5.8, melody_style="auto",
            ),
            SongSectionSpec(
                name, bars=episode_b, root_note=root_note, temperature=0.74, target_notes_per_bar=6.4, melody_style="auto",
            ),
            SongSectionSpec(
                name, bars=refrain_b, root_note=root_note, temperature=0.69, target_notes_per_bar=6.0, melody_style="auto",
            ),
            SongSectionSpec(
                name, bars=c_b, root_note=root_note, temperature=0.76, target_notes_per_bar=6.8, melody_style="auto",
            ),
            SongSectionSpec(
                name, bars=refrain_b, root_note=root_note, temperature=0.70, target_notes_per_bar=6.2, melody_style="auto",
            ),
            SongSectionSpec(
                name, bars=outro_b, root_note=root_note, temperature=0.58, target_notes_per_bar=3.0, melody_style="auto",
            ),
        ]
        return cls._apply_root_motion_arc("rondo", cls._apply_emotion_arc(name, "rondo", specs))

    @classmethod
    def ballad_form(
        cls,
        base_emotion_name: str,
        *,
        bars_per_section: int = 16,
        root_note: int = 60,
    ) -> List[SongSectionSpec]:
        """
        Intro → verse → chorus → verse → A' → outro. Longer intro/outro, cooler verses,
        warmer lift on first chorus and developed return.

        Must match ArrangementPolicy form_mode ``ballad`` (6 sections).
        """
        name = canonical_emotion_name(base_emotion_name)
        b = max(4, int(bars_per_section))
        intro_b = cls._bars_scaled(b, 1.12, minimum=10)
        verse_b = cls._bars_scaled(b, 0.92, minimum=8)
        chorus_b = cls._bars_scaled(b, 0.88, minimum=8)
        a_prime_b = cls._bars_scaled(b, 1.0, minimum=8)
        outro_b = max(8, int(round(b * 0.55)))
        specs = [
            SongSectionSpec(
                name, bars=intro_b, root_note=root_note, temperature=0.58, target_notes_per_bar=3.2, melody_style="auto",
            ),
            SongSectionSpec(
                name, bars=verse_b, root_note=root_note, temperature=0.64, target_notes_per_bar=4.8, melody_style="auto",
            ),
            SongSectionSpec(
                name, bars=chorus_b, root_note=root_note, temperature=0.70, target_notes_per_bar=6.4, melody_style="auto",
            ),
            SongSectionSpec(
                name, bars=verse_b, root_note=root_note, temperature=0.63, target_notes_per_bar=4.6, melody_style="auto",
            ),
            SongSectionSpec(
                name, bars=a_prime_b, root_note=root_note, temperature=0.68, target_notes_per_bar=6.0, melody_style="auto",
            ),
            SongSectionSpec(
                name, bars=outro_b, root_note=root_note, temperature=0.55, target_notes_per_bar=2.8, melody_style="auto",
            ),
        ]
        return cls._apply_root_motion_arc("ballad", cls._apply_emotion_arc(name, "ballad", specs))

    @classmethod
    def wave_form(
        cls,
        base_emotion_name: str,
        *,
        bars_per_section: int = 8,
        root_note: int = 60,
    ) -> List[SongSectionSpec]:
        """
        Intro → build → drop → breakdown → drop → outro. Short build, tight drops,
        pulled-back middle, final peak.

        Must match ArrangementPolicy form_mode ``wave`` (6 sections).
        """
        name = canonical_emotion_name(base_emotion_name)
        b = max(4, int(bars_per_section))
        intro_b = cls._bars_scaled(b, 0.68, minimum=6)
        build_b = max(4, int(round(b * 0.44)))
        drop_b = cls._bars_scaled(b, 0.72, minimum=6)
        break_b = cls._bars_scaled(b, 0.92, minimum=6)
        outro_b = max(6, b // 2)
        specs = [
            SongSectionSpec(
                name, bars=intro_b, root_note=root_note, temperature=0.60, target_notes_per_bar=3.6, melody_style="auto",
            ),
            SongSectionSpec(
                name, bars=build_b, root_note=root_note, temperature=0.72, target_notes_per_bar=6.4, melody_style="auto",
            ),
            SongSectionSpec(
                name, bars=drop_b, root_note=root_note, temperature=0.78, target_notes_per_bar=7.6, melody_style="auto",
            ),
            SongSectionSpec(
                name, bars=break_b, root_note=root_note, temperature=0.64, target_notes_per_bar=4.9, melody_style="auto",
            ),
            SongSectionSpec(
                name, bars=drop_b, root_note=root_note, temperature=0.76, target_notes_per_bar=7.8, melody_style="auto",
            ),
            SongSectionSpec(
                name, bars=outro_b, root_note=root_note, temperature=0.56, target_notes_per_bar=3.0, melody_style="auto",
            ),
        ]
        return cls._apply_root_motion_arc("wave", cls._apply_emotion_arc(name, "wave", specs))

    @classmethod
    def anthem_form(
        cls,
        base_emotion_name: str,
        *,
        bars_per_section: int = 8,
        root_note: int = 60,
    ) -> List[SongSectionSpec]:
        """
        Cinematic-pop longform with two lift cycles and a final payoff.

        Form (13 sections):
        intro → a → pre → b → tag → a → pre → b → a_prime → pre → b → tag → outro

        Must match ArrangementPolicy form_mode ``anthem``.
        """
        name = canonical_emotion_name(base_emotion_name)
        b = max(4, int(bars_per_section))
        intro_b = cls._bars_scaled(b, 0.70, minimum=6)
        verse_b = cls._bars_scaled(b, 1.0, minimum=6)
        pre_b = cls._bars_scaled(b, 0.60, minimum=4)
        chorus_b = cls._bars_scaled(b, 0.78, minimum=6)
        tag_b = cls._bars_scaled(b, 0.46, minimum=4)
        bridge_b = cls._bars_scaled(b, 1.18, minimum=8)
        final_chorus_b = cls._bars_scaled(b, 0.92, minimum=8)
        outro_b = max(6, int(round(b * 0.55)))

        specs = [
            SongSectionSpec(name, bars=intro_b, root_note=root_note, temperature=0.60, target_notes_per_bar=3.6, melody_style="auto"),
            SongSectionSpec(name, bars=verse_b, root_note=root_note, temperature=0.66, target_notes_per_bar=5.4, melody_style="auto"),
            SongSectionSpec(name, bars=pre_b, root_note=root_note, temperature=0.70, target_notes_per_bar=6.1, melody_style="auto"),
            SongSectionSpec(name, bars=chorus_b, root_note=root_note, temperature=0.74, target_notes_per_bar=7.0, melody_style="auto"),
            SongSectionSpec(name, bars=tag_b, root_note=root_note, temperature=0.72, target_notes_per_bar=7.8, melody_style="auto"),
            SongSectionSpec(name, bars=verse_b, root_note=root_note, temperature=0.67, target_notes_per_bar=5.6, melody_style="auto"),
            SongSectionSpec(name, bars=pre_b, root_note=root_note, temperature=0.71, target_notes_per_bar=6.3, melody_style="auto"),
            SongSectionSpec(name, bars=chorus_b, root_note=root_note, temperature=0.75, target_notes_per_bar=7.2, melody_style="auto"),
            SongSectionSpec(name, bars=bridge_b, root_note=root_note, temperature=0.78, target_notes_per_bar=6.6, melody_style="auto"),
            SongSectionSpec(name, bars=pre_b, root_note=root_note, temperature=0.73, target_notes_per_bar=6.5, melody_style="auto"),
            SongSectionSpec(name, bars=final_chorus_b, root_note=root_note, temperature=0.76, target_notes_per_bar=7.6, melody_style="auto"),
            SongSectionSpec(name, bars=tag_b, root_note=root_note, temperature=0.74, target_notes_per_bar=8.0, melody_style="auto"),
            SongSectionSpec(name, bars=outro_b, root_note=root_note, temperature=0.57, target_notes_per_bar=3.1, melody_style="auto"),
        ]
        return cls._apply_root_motion_arc("anthem", cls._apply_emotion_arc(name, "anthem", specs))

    @classmethod
    def ambient_form(
        cls,
        base_emotion_name: str,
        *,
        root_note: int = 60,
        base_tempo_bpm: float = 70.0,
        target_seconds: float = 150.0,
        max_bars: int = 64,
    ) -> List[SongSectionSpec]:
        """
        Ambient form with a strict time/bars budget.

        Strategy:
        - Compute a total bar count from the target duration and tempo.
        - Allocate bars across 5 sections (intro, A, B, A', outro) with long
          A/A' development and a short contrasting B.
        - Keep melody sparse (lower target_notes_per_bar) and temperature modest.
        """
        base_name = canonical_emotion_name(base_emotion_name)
        emotion = EMOTION_BY_NAME.get(base_name)
        if emotion is None:
            raise ValueError(f"Unknown emotion '{base_emotion_name}' (canonical '{base_name}')")

        tempo_m, _, _ = normalize_emotion_scalars(emotion)
        bpm = float(base_tempo_bpm) * float(tempo_m)
        bar_seconds = 4.0 * 60.0 / max(1.0, bpm)
        total_bars = int(round(float(target_seconds) / max(0.01, bar_seconds)))
        total_bars = max(16, min(int(max_bars), total_bars))

        # Allocate across roles: intro 15%, A 30%, B 15%, A' 30%, outro 10%
        weights = [0.15, 0.30, 0.15, 0.30, 0.10]
        raw = [max(1, int(round(total_bars * w))) for w in weights]
        # Fix rounding drift
        drift = total_bars - sum(raw)
        if drift != 0:
            # distribute drift mostly into A/A'
            order = [1, 3, 0, 2, 4]
            step = 1 if drift > 0 else -1
            for i in range(abs(drift)):
                raw[order[i % len(order)]] = max(1, raw[order[i % len(order)]] + step)

        # Enforce pleasant minimums/maximums for ambient pacing
        intro = max(4, min(12, raw[0]))
        outro = max(4, min(10, raw[4]))
        remaining = max(8, total_bars - intro - outro)
        a = max(8, int(round(remaining * 0.38)))
        b = max(6, int(round(remaining * 0.20)))
        a_prime = max(8, remaining - a - b)

        # Re-adjust to exact total_bars
        sections_bars = [intro, a, b, a_prime, outro]
        fix = total_bars - sum(sections_bars)
        if fix != 0:
            # Prefer to adjust A' then A
            for idx in ([3, 1, 2, 0, 4] if fix > 0 else [3, 1, 2, 4, 0]):
                if fix == 0:
                    break
                delta = 1 if fix > 0 else -1
                if sections_bars[idx] + delta >= 4:
                    sections_bars[idx] += delta
                    fix -= delta

        name = base_name
        # Ambient: sparse melody and gentle exploration
        specs = [
            SongSectionSpec(name, bars=sections_bars[0], root_note=root_note, temperature=0.62, target_notes_per_bar=3.0, melody_style="auto"),
            SongSectionSpec(name, bars=sections_bars[1], root_note=root_note, temperature=0.66, target_notes_per_bar=3.6, melody_style="auto"),
            SongSectionSpec(name, bars=sections_bars[2], root_note=root_note, temperature=0.70, target_notes_per_bar=3.8, melody_style="auto"),
            SongSectionSpec(name, bars=sections_bars[3], root_note=root_note, temperature=0.66, target_notes_per_bar=3.4, melody_style="auto"),
            SongSectionSpec(name, bars=sections_bars[4], root_note=root_note, temperature=0.58, target_notes_per_bar=2.6, melody_style="auto"),
        ]
        return cls._apply_root_motion_arc("default", cls._apply_emotion_arc(name, "default", specs))
