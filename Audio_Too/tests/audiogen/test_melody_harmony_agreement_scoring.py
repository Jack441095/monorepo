import unittest


def _mk_events(chord_notes, melody_notes):
    evs = []
    # 2 bars, 4/4. Chords each beat.
    for bar in range(2):
        for beat in range(4):
            st = float(bar * 4 + beat)
            evs.append((1, 0, 72, st, 1.0, list(chord_notes)))
    # Melody on each beat + phrase-end pickup at 3.5 in bar 2.
    for i, n in enumerate(melody_notes):
        evs.append((2, int(n), 90, float(i), 0.5, [int(n)]))
    evs.append((2, int(melody_notes[-1]), 88, 7.5, 0.5, [int(melody_notes[-1])]))
    return evs


class MelodyHarmonyAgreementScoringTests(unittest.TestCase):
    def test_chord_tone_aligned_melody_scores_higher(self):
        from composition.section_scoring import score_section

        # C major triad chord bed.
        chord = [60, 64, 67]
        good = _mk_events(chord, [60, 64, 67, 72, 60, 64, 67, 72])
        bad = _mk_events(chord, [61, 66, 70, 73, 61, 66, 70, 73])

        targets = {
            "cadence_window": [0.0, 1.0],
        }

        s_good = score_section(
            good,
            beats_per_bar=4.0,
            bars=2,
            timeline_targets=targets,
            section_role="b",
        )
        s_bad = score_section(
            bad,
            beats_per_bar=4.0,
            bars=2,
            timeline_targets=targets,
            section_role="b",
        )

        self.assertGreater(
            float(s_good.details.get("mh_strongbeat_chord_tone_frac", 0.0)),
            float(s_bad.details.get("mh_strongbeat_chord_tone_frac", 0.0)),
        )
        self.assertGreater(
            float(s_good.details.get("mh_agreement_score", 0.0)),
            float(s_bad.details.get("mh_agreement_score", 0.0)),
        )
        self.assertGreater(float(s_good.score), float(s_bad.score))

    def test_chorus_role_penalizes_weak_agreement_more_than_verse(self):
        from composition.section_scoring import score_section

        chord = [60, 64, 67]
        weak = _mk_events(chord, [61, 66, 70, 73, 61, 66, 70, 73])
        targets = {"cadence_window": [0.0, 1.0]}

        s_verse = score_section(
            weak,
            beats_per_bar=4.0,
            bars=2,
            timeline_targets=targets,
            section_role="a",
        )
        s_chorus = score_section(
            weak,
            beats_per_bar=4.0,
            bars=2,
            timeline_targets=targets,
            section_role="b",
        )

        self.assertLess(
            float(s_chorus.details.get("mh_agreement_bonus", 0.0)),
            float(s_verse.details.get("mh_agreement_bonus", 0.0)),
        )

    def test_optimism_and_joy_are_stricter_than_love_on_weak_chorus_alignment(self):
        from composition.section_scoring import score_section

        chord = [60, 64, 67]
        weak = _mk_events(chord, [61, 66, 70, 73, 61, 66, 70, 73])
        targets = {"cadence_window": [0.0, 1.0]}

        s_love = score_section(
            weak,
            beats_per_bar=4.0,
            bars=2,
            timeline_targets=targets,
            section_role="b",
            emotion_name="love",
        )
        s_opt = score_section(
            weak,
            beats_per_bar=4.0,
            bars=2,
            timeline_targets=targets,
            section_role="b",
            emotion_name="optimism",
        )
        s_joy = score_section(
            weak,
            beats_per_bar=4.0,
            bars=2,
            timeline_targets=targets,
            section_role="b",
            emotion_name="joy",
        )

        self.assertLess(
            float(s_opt.details.get("mh_agreement_bonus", 0.0)),
            float(s_love.details.get("mh_agreement_bonus", 0.0)),
        )
        self.assertLess(
            float(s_joy.details.get("mh_agreement_bonus", 0.0)),
            float(s_love.details.get("mh_agreement_bonus", 0.0)),
        )

    def test_preset_tight_vs_loose_changes_penalty_strength(self):
        from audiogen_core.config import CONFIG
        from composition.section_scoring import score_section

        chord = [60, 64, 67]
        weak = _mk_events(chord, [61, 66, 70, 73, 61, 66, 70, 73])
        targets = {"cadence_window": [0.0, 1.0]}

        prev = getattr(CONFIG.composition, "melody_harmony_agreement_preset", "balanced")
        try:
            setattr(CONFIG.composition, "melody_harmony_agreement_preset", "tight")
            s_tight = score_section(
                weak,
                beats_per_bar=4.0,
                bars=2,
                timeline_targets=targets,
                section_role="b",
                emotion_name="optimism",
            )

            setattr(CONFIG.composition, "melody_harmony_agreement_preset", "balanced")
            s_bal = score_section(
                weak,
                beats_per_bar=4.0,
                bars=2,
                timeline_targets=targets,
                section_role="b",
                emotion_name="optimism",
            )

            setattr(CONFIG.composition, "melody_harmony_agreement_preset", "loose")
            s_loose = score_section(
                weak,
                beats_per_bar=4.0,
                bars=2,
                timeline_targets=targets,
                section_role="b",
                emotion_name="optimism",
            )
        finally:
            setattr(CONFIG.composition, "melody_harmony_agreement_preset", prev)

        self.assertLess(
            float(s_tight.details.get("mh_agreement_bonus", 0.0)),
            float(s_bal.details.get("mh_agreement_bonus", 0.0)),
        )
        self.assertLess(
            float(s_bal.details.get("mh_agreement_bonus", 0.0)),
            float(s_loose.details.get("mh_agreement_bonus", 0.0)),
        )


if __name__ == "__main__":
    unittest.main()
