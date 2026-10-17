import unittest


class RegisterArcOffsetTests(unittest.TestCase):
    def test_role_based_lane_center_offset_shifts_planned_melody_lane(self):
        from composition.section_plan import SectionPlan
        from composition.section_planner import SectionPlanner
        from data.music_data import EMOTIONS

        emotion = EMOTIONS[0]

        def _plan(offset: int) -> SectionPlan:
            p = SectionPlan(emotion=emotion, root_note=60, bars=4, beats_per_bar=4.0)
            p.timeline_targets = {"melody_density": [1.0, 1.0, 1.0, 1.0]}
            p.arrangement_curve = {"melody_lane_center_offset": int(offset)}
            # Start below the default lane; offset should pull it upward via clamping.
            p.chosen_melody = [60, 60, 60, 60]
            p.chosen_bass = [36, 36, 36, 36]
            p.chosen_chord = [[60, 64, 67]] * 4
            return p

        p0 = SectionPlanner._apply_timeline_targets_to_voicing(_plan(0))
        p6 = SectionPlanner._apply_timeline_targets_to_voicing(_plan(6))

        self.assertTrue(p0.chosen_melody and p6.chosen_melody)
        self.assertGreater(sum(p6.chosen_melody) / len(p6.chosen_melody), sum(p0.chosen_melody) / len(p0.chosen_melody))


if __name__ == "__main__":
    unittest.main()

