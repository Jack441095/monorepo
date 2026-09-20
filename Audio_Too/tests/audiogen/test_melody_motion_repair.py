import unittest
from types import SimpleNamespace


class MelodyMotionRepairTests(unittest.TestCase):
    def test_motion_repair_penalizes_repeated_static_degree(self) -> None:
        from ai.markov.melody.note_generator._interval import _apply_emotion_motion_repair

        probs = {-1: 0.2, 0: 0.6, 1: 0.2}
        out = _apply_emotion_motion_repair(
            probs,
            current_degree=3,
            melody=[(3, 0.5), (3, 0.5), (3, 1.0), (3, 0.5)],
            emotion=SimpleNamespace(name="joy"),
            pos=0.5,
        )

        self.assertLess(out[0], probs[0])
        self.assertGreater(out[1], probs[1])
        self.assertAlmostEqual(sum(out.values()), 1.0, places=6)

    def test_motion_repair_respects_descending_emotion_prior(self) -> None:
        from ai.markov.melody.note_generator._interval import _apply_emotion_motion_repair

        probs = {-1: 0.25, 0: 0.50, 1: 0.25}
        out = _apply_emotion_motion_repair(
            probs,
            current_degree=4,
            melody=[(5, 1.0), (4, 1.0), (4, 1.0), (4, 1.0)],
            emotion=SimpleNamespace(name="grief"),
            pos=0.55,
        )

        self.assertGreater(out[-1], out[1])
        self.assertLess(out[0], probs[0])
        self.assertAlmostEqual(sum(out.values()), 1.0, places=6)

    def test_static_run_prefers_directional_true_step_over_repeat(self) -> None:
        from ai.markov.melody.note_generator._interval import _apply_emotion_motion_repair

        probs = {-2: 0.16, -1: 0.16, 0: 0.36, 1: 0.16, 2: 0.16}
        out = _apply_emotion_motion_repair(
            probs,
            current_degree=2,
            melody=[(2, 0.5), (2, 0.5), (2, 0.5), (2, 0.5)],
            emotion=SimpleNamespace(name="joy"),
            pos=0.5,
        )

        self.assertGreater(out[1], out[0])
        self.assertGreater(out[1], out[-1])
        self.assertGreater(out[1], out[2])
        self.assertLess(out[0], 0.05)
        self.assertAlmostEqual(sum(out.values()), 1.0, places=6)


if __name__ == "__main__":
    unittest.main()
