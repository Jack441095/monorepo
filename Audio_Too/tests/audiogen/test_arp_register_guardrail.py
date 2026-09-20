import unittest


class ArpRegisterGuardrailTests(unittest.TestCase):
    def test_arp_lane_guardrail_lifts_pinned_low_lane(self):
        """
        Regression: when `chosen_melody` lane collapses low, the arp shouldn't
        stay stuck at the bottom of its range for the whole section.
        """
        from composition.arpeggiator_engine import Arpeggiator
        from composition.engine import CompositionGenerator
        from data.music_data import EMOTIONS
        from midi.midi_range_limiter import RANGE_LIMITER

        gen = CompositionGenerator(enable_perf_monitoring=False)
        arp = Arpeggiator(owner=gen)
        emotion = EMOTIONS[0]
        chords = ["Imaj7"] * 8
        roots = [60] * 8

        # Simulate a pinned-low lane; the arpeggiator itself will clamp into channel-3 range,
        # but the planner guardrail should lift the *center* into preferred midband.
        lane = [48] * 8
        events = arp.generate_from_chords(
            emotion=emotion,
            chords=chords,
            roots=roots,
            bars=8,
            beats_per_bar=4.0,
            target_notes_per_bar=8.0,
            channel=3,
            chosen_lane=lane,
            voiced_chords=None,
            lead_events=None,
            section_role="a",
        )
        arp_notes = [int(ev[1]) for ev in events if len(ev) == 6 and int(ev[0]) == 3 and isinstance(ev[1], int)]
        self.assertTrue(arp_notes)
        info = RANGE_LIMITER.get_range_info(3) or {}
        pref_min = int(info.get("preferred_min", 60))
        # Median arp pitch should not sit below preferred_min for long.
        xs = sorted(arp_notes)
        med = xs[len(xs) // 2]
        self.assertGreaterEqual(int(med), int(pref_min) - 1)


if __name__ == "__main__":
    unittest.main()

