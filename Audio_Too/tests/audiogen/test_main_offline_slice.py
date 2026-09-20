import unittest


class MainOfflineSliceTests(unittest.TestCase):
    def test_slice_events_for_bar_clips_overlap(self) -> None:
        import main

        events = [
            # Crosses bar 0 -> bar 1 boundary.
            (2, 60, 90, 3.5, 1.5, [60]),
            # Fully in bar 1.
            (2, 62, 90, 4.25, 0.5, [62]),
        ]
        out = main._slice_events_for_bar(events, bar_index=1, beats_per_bar=4.0)

        self.assertEqual(len(out), 2)
        starts = sorted(float(ev[3]) for ev in out)
        durs = sorted(float(ev[4]) for ev in out)
        self.assertAlmostEqual(starts[0], 0.0, places=6)
        self.assertAlmostEqual(starts[1], 0.25, places=6)
        self.assertAlmostEqual(durs[0], 0.5, places=6)
        self.assertAlmostEqual(durs[1], 1.0, places=6)


if __name__ == "__main__":
    unittest.main()
