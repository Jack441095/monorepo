import unittest


class ScoringNewTargetsTests(unittest.TestCase):
    def test_scoring_rewards_chorus_register_lift_and_modulation_flag(self):
        from composition.song_generator import SongGenerator, SongRender, SongSectionSpec

        # Minimal default-form subset: intro -> a -> pre_chorus -> b
        sections = [
            SongSectionSpec("neutral", bars=4, root_note=60),
            SongSectionSpec("neutral", bars=4, root_note=60),
            SongSectionSpec("neutral", bars=4, root_note=65),
            SongSectionSpec("neutral", bars=4, root_note=62),  # lifted chorus
        ]

        # Build minimal events: chords (ch=1) and lead (ch=2).
        # Verse lead sits low; chorus lead sits higher (late note near bar end).
        intro_a_pre = [
            (1, 0, 80, 0.0, 4.0, [60, 64, 67]),
            (2, 60, 90, 3.5, 0.5, [60]),
            # Verse section starts at beat 16.
            (1, 0, 80, 16.0, 4.0, [60, 64, 67]),
            (2, 60, 90, 31.5, 0.5, [60]),
            # Pre-chorus starts at beat 32.
            (1, 0, 80, 32.0, 4.0, [65, 69, 72]),
            (2, 62, 90, 47.5, 0.5, [62]),
        ]
        chorus_events = [
            # Chorus starts at beat 48.
            (1, 0, 80, 48.0, 4.0, [62, 66, 69]),
            (2, 74, 90, 63.5, 0.5, [74]),
        ]
        song = SongRender(
            sections=sections,
            events=intro_a_pre + chorus_events,
            tempo_map=[(0.0, 70.0)],
            metadata={"modulation_lift_applied": True, "modulation_lift_semitones": 2},
        )

        score, details = SongGenerator._score_candidate_song(song, arrangement_form="default")
        self.assertIsInstance(score, float)
        self.assertIn("score", details)
        # The register lift should be positive (chorus higher than verse).
        self.assertGreaterEqual(int(details.get("register_lift_semitones", 0) or 0), 1)


if __name__ == "__main__":
    unittest.main()

