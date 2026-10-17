import unittest
from types import SimpleNamespace


class SongBlueprintTargetsTests(unittest.TestCase):
    def test_blueprint_targets_bias_cadence_and_layers(self):
        from composition.section_planner.planner import SectionPlanner

        targets = {
            "cadence_window": [0.0, 0.0, 0.0, 0.2],
            "tension": [0.3, 0.4, 0.5, 0.5],
            "motif_strength": [0.7, 0.7, 0.7, 0.7],
            "melody_density": [1.0, 1.0, 1.0, 1.0],
            "harmony_function_target_by_bar": ["T", "PD", "D", "D"],
            "layer_presence_targets": {
                "bass": [0.5, 0.5, 0.5, 0.5],
                "chords": [0.5, 0.5, 0.5, 0.5],
                "melody": [0.5, 0.5, 0.5, 0.5],
                "arp": [0.5, 0.5, 0.5, 0.5],
                "counter": [0.5, 0.5, 0.5, 0.5],
            },
        }
        bp = SimpleNamespace(
            motif_stage="payoff",
            cadence_style="closed",
            cadence_strength_mult=1.1,
            target_register_offset=3,
            target_tension=0.9,
            layer_contract={"bass": 0.9, "chords": 0.85, "melody": 0.8, "arp": 0.95, "counter": 0.7},
            harmony_function_hint="T",
        )
        out, curve = SectionPlanner._apply_song_blueprint_targets(
            targets,
            curve={},
            section_blueprint=bp,
            strength=0.8,
        )
        self.assertGreater(float(out["cadence_window"][-1]), 0.8)
        self.assertAlmostEqual(float(curve.get("melody_lane_center_offset", 0)), 2.0, delta=2.0)
        self.assertGreater(float(out["layer_presence_targets"]["arp"][-1]), 0.7)
        self.assertEqual(str(out["harmony_function_target_by_bar"][-1]), "T")


if __name__ == "__main__":
    unittest.main()
