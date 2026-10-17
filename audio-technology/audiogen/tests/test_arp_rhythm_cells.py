import unittest


class ArpRhythmCellsTests(unittest.TestCase):
    def test_arpeggiator_honors_onset_steps_by_bar(self):
        from composition.engine import CompositionGenerator
        from data.music_data import EMOTIONS

        gen = CompositionGenerator(enable_perf_monitoring=False)
        arp = gen.melody_manager.arpeggiator
        emotion = EMOTIONS[0]

        chords = ["Imaj7"] * 2
        roots = [60] * 2
        bars = 2
        bpb = 4.0
        # 16th grid -> 16 steps per bar
        arp_plan = {
            "onset_steps_by_bar": [
                [0, 4, 8, 12],   # quarters on 16th grid
                [2, 6, 10, 14],  # shifted pattern
            ]
        }

        evs = arp.generate_from_chords(
            emotion,
            chords,
            roots,
            bars,
            bpb,
            target_notes_per_bar=8.0,
            phrase_contours=None,
            channel=3,
            arp_plan=arp_plan,
        )
        self.assertTrue(evs)

        # Collect start times for arp channel only.
        starts = [float(e[3]) for e in evs if isinstance(e, tuple) and len(e) == 6 and int(e[0]) == 3]
        self.assertTrue(starts)

        # Expect at least one onset on each requested step (within a small epsilon).
        eps = 1e-6
        expected = set()
        for bar_i, steps in enumerate(arp_plan["onset_steps_by_bar"]):
            for s in steps:
                expected.add(float(bar_i) * bpb + float(s) * 0.25)

        got = set()
        for st in starts:
            # Snap to grid (quarter-beat = 16th at 4/4).
            snapped = round(st / 0.25) * 0.25
            got.add(float(snapped))

        # We don't require a perfect match (arp can still add extra notes),
        # but the requested onsets must be represented.
        missing = [t for t in sorted(expected) if all(abs(t - g) > eps for g in got)]
        self.assertFalse(missing, f"missing expected onsets: {missing}")


if __name__ == "__main__":
    unittest.main()

