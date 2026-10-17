import unittest
from types import SimpleNamespace


def _movement_rate(tokens):
    degrees = [int(d) % 7 for d, _dur in tokens if int(d) >= 0]
    intervals = [((degrees[i] - degrees[i - 1] + 3) % 7) - 3 for i in range(1, len(degrees))]
    return sum(1 for iv in intervals if iv != 0) / float(max(1, len(intervals)))


def _max_static_run(tokens):
    degrees = [int(d) % 7 for d, _dur in tokens if int(d) >= 0]
    run = 1
    max_run = 1
    for prev, cur in zip(degrees, degrees[1:]):
        if prev == cur:
            run += 1
        else:
            max_run = max(max_run, run)
            run = 1
    return max(max_run, run)


class PhraseStaticMotionRepairTests(unittest.TestCase):
    def test_falling_emotion_tilts_balanced_phrase_downward(self) -> None:
        from ai.markov.melody.generation.phrase_generation import _tilt_falling_motion_for_emotion

        phrase = [(0, 1.0), (1, 1.0), (1, 1.0), (2, 2.0)]
        out = _tilt_falling_motion_for_emotion(phrase, emotion=SimpleNamespace(name="sadness"))
        degrees = [d for d, _dur in out]
        intervals = [int(degrees[i]) - int(degrees[i - 1]) for i in range(1, len(degrees))]

        self.assertGreater(sum(1 for iv in intervals if iv < 0), sum(1 for iv in intervals if iv > 0))
        self.assertEqual([dur for _d, dur in out], [dur for _d, dur in phrase])

    def test_low_leap_emotion_smooths_large_interior_jump(self) -> None:
        from ai.markov.melody.generation.phrase_generation import _smooth_unwanted_large_leaps

        phrase = [(4, 1.0), (0, 1.0), (1, 2.0)]
        out = _smooth_unwanted_large_leaps(phrase, emotion=SimpleNamespace(name="relief"))
        degrees = [d for d, _dur in out]
        intervals = [int(degrees[i]) - int(degrees[i - 1]) for i in range(1, len(degrees))]

        self.assertFalse(any(abs(iv) >= 4 for iv in intervals))
        self.assertEqual([dur for _d, dur in out], [dur for _d, dur in phrase])

    def test_low_leap_emotion_preserves_final_cadence_target(self) -> None:
        from ai.markov.melody.generation.phrase_generation import _smooth_unwanted_large_leaps

        phrase = [(2, 1.0), (6, 1.0), (0, 2.0)]
        out = _smooth_unwanted_large_leaps(phrase, emotion=SimpleNamespace(name="sadness"))
        degrees = [d for d, _dur in out]
        intervals = [int(degrees[i]) - int(degrees[i - 1]) for i in range(1, len(degrees))]

        self.assertEqual(out[-1][0], 0)
        self.assertFalse(any(abs(iv) >= 4 for iv in intervals))

    def test_fear_signature_adds_large_leap_when_missing(self) -> None:
        from ai.markov.melody.generation.phrase_generation import _apply_signature_leap_if_needed

        phrase = [(0, 0.5), (1, 0.5), (2, 0.5), (1, 1.0), (0, 2.0)]
        out = _apply_signature_leap_if_needed(phrase, emotion=SimpleNamespace(name="fear"))
        degrees = [d for d, _dur in out]
        intervals = [int(degrees[i]) - int(degrees[i - 1]) for i in range(1, len(degrees))]

        self.assertTrue(any(abs(iv) >= 4 for iv in intervals))
        self.assertEqual([dur for _d, dur in out], [dur for _d, dur in phrase])

    def test_long_breathed_emotion_merges_repeated_short_notes(self) -> None:
        from ai.markov.melody.generation.phrase_generation import _merge_repeated_short_notes_for_long_breath

        phrase = [(4, 0.25), (4, 0.25), (4, 0.75), (2, 2.0)]
        merged = _merge_repeated_short_notes_for_long_breath(
            phrase,
            emotion=SimpleNamespace(name="love"),
        )

        self.assertEqual(merged, [(4, 1.25), (2, 2.0)])
        self.assertAlmostEqual(sum(d for _degree, d in merged), sum(d for _degree, d in phrase))

    def test_repairs_flat_ascending_phrase_without_changing_durations_or_cadence(self) -> None:
        from ai.markov.melody.generation.phrase_generation import _repair_static_phrase_motion
        from ai.markov.melody.phrase_planner import PhrasePlan

        phrase = [(4, 0.25), (4, 0.25), (4, 0.25), (4, 0.25), (4, 0.75), (0, 2.0)]
        plan = PhrasePlan(
            contour="asc",
            entry_degree=0,
            target_climax=5,
            pre_cadence_degree=6,
            cadence_degree=0,
            arc_waypoints=[(0.04, 0, 1.1), (0.50, 5, 1.4), (0.82, 6, 1.2), (0.96, 0, 1.5)],
        )

        repaired = _repair_static_phrase_motion(phrase, plan=plan, emotion=SimpleNamespace(name="joy"))

        self.assertEqual([dur for _d, dur in repaired], [dur for _d, dur in phrase])
        self.assertEqual(repaired[-1][0], 0)
        self.assertGreaterEqual(_movement_rate(repaired), 0.40)
        self.assertLessEqual(_max_static_run(repaired), 3)

    def test_descending_emotion_prefers_falling_motion(self) -> None:
        from ai.markov.melody.generation.phrase_generation import _repair_static_phrase_motion
        from ai.markov.melody.phrase_planner import PhrasePlan

        phrase = [(4, 0.5), (4, 0.5), (4, 0.5), (4, 0.5), (2, 2.0)]
        plan = PhrasePlan(
            contour="desc",
            entry_degree=5,
            target_climax=3,
            pre_cadence_degree=1,
            cadence_degree=2,
            arc_waypoints=[(0.04, 5, 1.1), (0.45, 3, 1.3), (0.80, 1, 1.2), (0.96, 2, 1.5)],
        )

        repaired = _repair_static_phrase_motion(phrase, plan=plan, emotion=SimpleNamespace(name="grief"))
        degrees = [d for d, _dur in repaired]
        intervals = [((degrees[i] - degrees[i - 1] + 3) % 7) - 3 for i in range(1, len(degrees))]

        self.assertEqual(repaired[-1][0], 2)
        self.assertGreater(sum(1 for iv in intervals if iv < 0), sum(1 for iv in intervals if iv > 0))
        self.assertGreaterEqual(_movement_rate(repaired), 0.40)


if __name__ == "__main__":
    unittest.main()
