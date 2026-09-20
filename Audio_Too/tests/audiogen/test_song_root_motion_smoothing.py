import unittest


class SongRootMotionSmoothingTests(unittest.TestCase):
    def test_default_form_keeps_prechorus_and_chorus_lift_close(self):
        from composition.song_generator import SongGenerator

        specs = SongGenerator.default_form("neutral", bars_per_section=8, root_note=60)
        roots = [int(s.root_note) for s in specs]

        self.assertGreaterEqual(len(roots), 4)
        # intro, verse, pre, chorus
        self.assertEqual(roots[0], 60)
        self.assertEqual(roots[1], 60)
        self.assertEqual(roots[2], 62)
        self.assertEqual(roots[3], 62)

    def test_pop_ext_prechorus_to_chorus_does_not_snap_back_to_tonic(self):
        from composition.song_generator import SongGenerator

        specs = SongGenerator.pop_ext_form("neutral", bars_per_section=8, root_note=60)
        roots = [int(s.root_note) for s in specs]

        self.assertGreaterEqual(len(roots), 7)
        # intro, verse1, pre1, chorus1, verse2, pre2, chorus2
        self.assertEqual(roots[2], 62)
        self.assertEqual(roots[3], 62)
        self.assertEqual(roots[5], 62)
        self.assertEqual(roots[6], 62)


if __name__ == "__main__":
    unittest.main()
