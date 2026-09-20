import unittest
from types import SimpleNamespace


class PhraseArcScaffoldingTests(unittest.TestCase):
    def test_generate_plans_adds_ordered_arc_waypoints(self) -> None:
        from ai.markov.melody.phrase_planner import PhrasePlanner

        planner = PhrasePlanner()
        emotion = SimpleNamespace(name="joy")
        plans = planner.generate_plans(["asc", "desc"], 2, emotion)

        self.assertEqual(len(plans), 2)
        for plan in plans:
            waypoints = list(plan.arc_waypoints or [])
            self.assertEqual(len(waypoints), 5)
            self.assertEqual([p for p, _d, _s in waypoints], sorted(p for p, _d, _s in waypoints))
            self.assertEqual(int(waypoints[-1][1]) % 7, int(plan.cadence_degree) % 7)

    def test_apply_plan_bias_uses_current_arc_waypoint(self) -> None:
        from ai.markov.melody.phrase_planner import PhrasePlan, PhrasePlanner

        planner = PhrasePlanner()
        plan = PhrasePlan(
            contour="asc",
            entry_degree=0,
            target_climax=4,
            pre_cadence_degree=3,
            cadence_degree=0,
            arc_waypoints=[
                (0.04, 0, 1.10),
                (0.34, 2, 1.25),
                (0.62, 4, 1.60),
                (0.70, 3, 1.25),
                (0.96, 0, 1.50),
            ],
        )
        probs = {-1: 1.0, 0: 1.0, 1: 1.0, 2: 1.0}
        planner.apply_plan_bias(probs, [(2, 1.0)], plan, 0.62)

        # From degree 2 at the peak waypoint, +2 lands on target degree 4.
        self.assertGreater(probs[2], probs[0])
        self.assertGreater(probs[2], probs[-1])


if __name__ == "__main__":
    unittest.main()
