import unittest


class SongBlueprintScoringTests(unittest.TestCase):
    def test_scoring_emits_blueprint_adherence_bonus(self):
        from composition.song_generator import SongGenerator, SongRender, SongSectionSpec

        sections = [
            SongSectionSpec("neutral", bars=4, root_note=60),
            SongSectionSpec("neutral", bars=4, root_note=60),
            SongSectionSpec("neutral", bars=4, root_note=62),
            SongSectionSpec("neutral", bars=4, root_note=62),
        ]
        events = [
            # intro
            (1, 0, 80, 0.0, 4.0, [60, 64, 67]),
            (2, 60, 90, 3.5, 0.5, [60]),
            # a
            (1, 0, 80, 16.0, 4.0, [60, 64, 67]),
            (2, 62, 90, 31.5, 0.5, [62]),
            # pre
            (1, 0, 80, 32.0, 4.0, [62, 65, 69]),
            (2, 64, 90, 47.5, 0.5, [64]),
            # b
            (1, 0, 80, 48.0, 4.0, [62, 66, 69]),
            (2, 72, 92, 63.5, 0.5, [72]),
            (3, 67, 78, 60.0, 1.0, [67]),
        ]
        song = SongRender(
            sections=sections,
            events=events,
            tempo_map=[(0.0, 70.0)],
            metadata={
                "song_blueprint": {
                    "motif_stages": ["introduce", "state", "build", "payoff"],
                    "cadence_styles": ["authentic", "authentic", "open", "closed"],
                }
            },
        )
        _score, details = SongGenerator._score_candidate_song(song, arrangement_form="default")
        self.assertIn("blueprint_adherence_bonus", details)
        self.assertGreaterEqual(float(details.get("blueprint_adherence_bonus", 0.0)), 0.0)


if __name__ == "__main__":
    unittest.main()
