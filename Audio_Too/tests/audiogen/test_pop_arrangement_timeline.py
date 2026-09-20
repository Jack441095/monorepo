import statistics
import unittest

from audiogen_core.config import CONFIG
from composition.section_planner import _make_timeline_targets


class PopArrangementTimelineTests(unittest.TestCase):
    def setUp(self) -> None:
        self._pop = float(getattr(CONFIG.composition, "pop_arrangement_strength", 0.0))

    def tearDown(self) -> None:
        try:
            CONFIG.composition.pop_arrangement_strength = self._pop
        except Exception:
            pass

    def test_strength_increases_verse_chorus_melody_density_gap(self) -> None:
        """Second-tier pop multipliers should widen A vs B mean melody_density."""
        curve = {
            "melody_density_mult": 1.0,
            "chord_rhythm_mult": 1.0,
            "motif_prob_mult": 1.0,
            "tension_mult": 1.0,
        }
        CONFIG.composition.pop_arrangement_strength = 0.0
        a0 = _make_timeline_targets("a", 8, dict(curve))
        b0 = _make_timeline_targets("b", 8, dict(curve))
        CONFIG.composition.pop_arrangement_strength = 1.0
        a1 = _make_timeline_targets("a", 8, dict(curve))
        b1 = _make_timeline_targets("b", 8, dict(curve))
        mean_a0 = statistics.mean(a0["melody_density"])
        mean_b0 = statistics.mean(b0["melody_density"])
        mean_a1 = statistics.mean(a1["melody_density"])
        mean_b1 = statistics.mean(b1["melody_density"])
        self.assertGreater(mean_b1 - mean_a1, mean_b0 - mean_a0 + 1e-6)
