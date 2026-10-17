import unittest


class AbletonLikeArpModeTests(unittest.TestCase):
    def test_updown_excl_cycle_no_repeated_endpoints(self):
        from composition.arpeggiator_engine import Arpeggiator

        tones = [60, 64, 67]
        cycle = Arpeggiator._build_mode_cycle(tones, "updown_excl")
        self.assertEqual(cycle, [60, 64, 67, 64])

    def test_updown_excl_two_tones_alternates(self):
        from composition.arpeggiator_engine import Arpeggiator

        tones = [60, 64]
        cycle = Arpeggiator._build_mode_cycle(tones, "updown_excl")
        self.assertEqual(cycle, [60, 64, 60])

    def test_tones_source_voiced_uses_voiced_chord_without_symbol_lookup(self):
        """
        Regression guard: when tones_source='voiced' and voiced_chord is provided,
        `_chord_tones_in_lane` should be able to build tones without requiring any
        chord-symbol parsing on the owner.
        """
        from composition.arpeggiator_engine import Arpeggiator

        class DummyOwner:
            pass

        arp = Arpeggiator(owner=DummyOwner())

        voiced = [60, 64, 67]  # C major triad, low register

        voiced_lane = arp._chord_tones_in_lane(
            chord="THIS_SHOULD_NOT_BE_PARSED",
            root=60,
            lane_center=72,
            channel=2,
            lane_half_width=12,
            voiced_chord=voiced,
            tones_source="voiced",
        )

        self.assertTrue(voiced_lane)
        self.assertTrue(all(isinstance(n, int) for n in voiced_lane))


if __name__ == "__main__":
    unittest.main()

