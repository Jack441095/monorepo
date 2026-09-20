import unittest

from composition.section_planner.motif_bus import (
    cross_lane_motif_bus_from_melody,
    motif_hook_from_cross_lane_bus,
)
from composition.section_planner.planner import SectionPlanner


class TestMotifBus(unittest.TestCase):
    def test_empty_melody_returns_none(self) -> None:
        self.assertIsNone(
            cross_lane_motif_bus_from_melody([], bars=4, beats_per_bar=4.0, section_role="a")
        )
        self.assertIsNone(
            SectionPlanner._cross_lane_motif_bus_from_melody(
                [], bars=4, beats_per_bar=4.0, section_role="a"
            )
        )

    def test_hook_rejects_non_dict(self) -> None:
        self.assertIsNone(motif_hook_from_cross_lane_bus(None))  # type: ignore[arg-type]
        self.assertIsNone(motif_hook_from_cross_lane_bus("nope"))  # type: ignore[arg-type]
        self.assertIsNone(SectionPlanner._motif_hook_from_cross_lane_bus(None))

    def test_module_matches_planner_delegates(self) -> None:
        ev = [
            (2, 60, 100, 0.0, 0.5, [60]),
            (2, 62, 100, 0.5, 0.5, [62]),
            (2, 64, 100, 1.0, 0.5, [64]),
        ]
        bus = cross_lane_motif_bus_from_melody(ev, bars=4, beats_per_bar=4.0, section_role="a")
        bus2 = SectionPlanner._cross_lane_motif_bus_from_melody(
            ev, bars=4, beats_per_bar=4.0, section_role="a"
        )
        self.assertEqual(bus, bus2)
        if bus:
            h = motif_hook_from_cross_lane_bus(bus)
            h2 = SectionPlanner._motif_hook_from_cross_lane_bus(bus)
            self.assertEqual(
                (h.intervals, h.rhythms, h.contour) if h is not None else None,
                (h2.intervals, h2.rhythms, h2.contour) if h2 is not None else None,
            )


if __name__ == "__main__":
    unittest.main()
