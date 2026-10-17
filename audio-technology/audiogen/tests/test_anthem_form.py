import unittest


class AnthemFormTests(unittest.TestCase):
    def test_anthem_form_matches_role_count(self) -> None:
        from composition.policies import ArrangementPolicy
        from composition.song_generator import SongGenerator

        specs = SongGenerator.anthem_form("neutral", bars_per_section=8, root_note=60)
        seq = ArrangementPolicy._FORM_SEQUENCES.get("anthem")

        self.assertIsNotNone(seq)
        self.assertEqual(len(specs), len(seq))
        self.assertGreaterEqual(len(specs), 10)


if __name__ == "__main__":
    unittest.main()
