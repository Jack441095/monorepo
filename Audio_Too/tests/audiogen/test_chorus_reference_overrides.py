import unittest

from composition.section_planner.chorus_reference import (
    chorus_reference_arp_overrides,
    chorus_reference_melody_overrides,
)


class TestChorusReferenceOverrides(unittest.TestCase):
    def test_non_chorus_role_returns_empty(self) -> None:
        self.assertEqual(
            chorus_reference_arp_overrides(emotion_name="joy", section_role="intro"),
            {},
        )
        self.assertEqual(
            chorus_reference_melody_overrides(emotion_name="joy", section_role="a"),
            {},
        )

    def test_chorusish_role_empty_when_flags_disabled(self) -> None:
        from audiogen_core.config import CONFIG

        c = CONFIG.composition
        a = bool(getattr(c, "chorus_reference_arp_enabled", False))
        m = bool(getattr(c, "chorus_reference_melody_enabled", False))
        try:
            c.chorus_reference_arp_enabled = False
            c.chorus_reference_melody_enabled = False
            self.assertEqual(
                chorus_reference_arp_overrides(emotion_name="joy", section_role="b"),
                {},
            )
            self.assertEqual(
                chorus_reference_melody_overrides(emotion_name="joy", section_role="hook"),
                {},
            )
        finally:
            try:
                c.chorus_reference_arp_enabled = a
                c.chorus_reference_melody_enabled = m
            except Exception:
                pass
