import unittest


class SongQualityReportTests(unittest.TestCase):
    def test_quality_report_detects_hook_and_static_bass_risk(self):
        from composition.evaluation import quality_report

        events = [
            # verse lead + static bass
            (0, 36, 82, 0.0, 4.0, [36]),
            (2, 60, 90, 0.0, 1.0, [60]),
            (2, 62, 90, 1.0, 1.0, [62]),
            (0, 36, 82, 4.0, 4.0, [36]),
            (2, 64, 90, 4.0, 1.0, [64]),
            # chorus lead + static bass
            (0, 36, 82, 8.0, 4.0, [36]),
            (2, 67, 92, 8.0, 1.0, [67]),
            (2, 69, 92, 9.0, 1.0, [69]),
            (2, 67, 92, 10.0, 1.0, [67]),
            (0, 36, 82, 12.0, 4.0, [36]),
            (2, 72, 92, 12.0, 1.0, [72]),
        ]
        report = quality_report(
            events,
            section_roles=["a", "b"],
            section_bars=[2, 2],
            metadata={
                "motif_development": [
                    {
                        "role": "b",
                        "slot_count": 1,
                        "variants": {"statement": 1},
                    }
                ]
            },
            beats_per_bar=4.0,
            bars=4,
        )
        self.assertTrue(report["checks"]["memorable_hook"])
        self.assertTrue(report["checks"]["chorus_stronger_than_verse"])
        self.assertFalse(report["checks"]["bass_not_static"])
        self.assertIn("add stepwise bass motion", " ".join(report["recommendations"]))


if __name__ == "__main__":
    unittest.main()
