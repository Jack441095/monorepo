import unittest


class ChordVoicingGuardrailTests(unittest.TestCase):
    def test_voicing_candidates_avoid_low_clusters_for_maj9(self):
        """
        Regression: chord voicing enumeration should avoid tightly-clustered stacks
        (especially in the low register) for common extended chords like maj9.
        """
        from composition.engine import CompositionGenerator

        gen = CompositionGenerator(enable_perf_monitoring=False)
        vle = gen.voice_leading_engine

        # C major-ish: Imaj9 root at 60.
        chord = "Imaj9"
        root = 60
        candidates = vle.get_possible_notes_for_part("chord", chord, root, prev_notes=None, emotion_name="neutral")
        self.assertTrue(candidates)

        # Assert: at least one candidate is a 4-note voicing (pop comping) and
        # none of the returned candidates have adjacent < 3 semitone gaps below ~E3.
        found_4 = False
        for v in candidates:
            nn = sorted(int(n) for n in v)
            if len(nn) >= 4:
                found_4 = True
            for a, b in zip(nn, nn[1:]):
                if a < 52 or b < 52:
                    self.assertGreaterEqual(b - a, 3)
        self.assertTrue(found_4)


if __name__ == "__main__":
    unittest.main()

