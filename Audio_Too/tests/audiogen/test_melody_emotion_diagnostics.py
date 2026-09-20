import json
import tempfile
import unittest
from pathlib import Path


class MelodyEmotionDiagnosticsTests(unittest.TestCase):
    def test_analyze_reports_emotion_shape_metrics(self) -> None:
        from scripts.melody_emotion_diagnostics import analyze

        rows = [
            {
                "emotion": "grief",
                "section_role": "verse",
                "phrase_roles": ["opening"],
                "phrase_contours": ["desc"],
                "melody": [[5, 2.0], [4, 2.0], [3, 4.0]],
                "accept_score": 0.7,
                "lyrical_score": 0.6,
            },
            {
                "emotion": "joy",
                "section_role": "chorus",
                "phrase_roles": ["hook"],
                "phrase_contours": ["asc"],
                "melody": [[0, 0.5], [2, 0.5], [4, 1.0], [5, 0.5]],
                "accept_score": 0.8,
                "lyrical_score": 0.65,
            },
        ]
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "melodies.jsonl"
            path.write_text("\n".join(json.dumps(row) for row in rows), encoding="utf-8")
            report = analyze(path, min_rows=1)

        grief = report["emotions"]["grief"]
        joy = report["emotions"]["joy"]
        self.assertEqual(report["rows_with_melody"], 2)
        self.assertGreater(grief["descending_rate"], grief["ascending_rate"])
        self.assertGreater(grief["long_duration_rate"], joy["long_duration_rate"])
        self.assertGreater(joy["ascending_rate"], joy["descending_rate"])
        self.assertGreater(joy["movement_rate"], 0.0)
        self.assertGreater(joy["true_step_rate"], 0.0)
        self.assertEqual(joy["static_run_max"], 1)
        self.assertIn("verse", grief["section_roles"])

    def test_analyze_distinguishes_static_repetition_from_true_steps(self) -> None:
        from scripts.melody_emotion_diagnostics import analyze

        row = {
            "emotion": "joy",
            "melody": [[0, 0.5], [0, 0.5], [0, 0.5], [1, 0.5], [1, 0.5]],
            "accept_score": 0.7,
            "lyrical_score": 0.6,
        }
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "melodies.jsonl"
            path.write_text(json.dumps(row), encoding="utf-8")
            report = analyze(path, min_rows=1)

        joy = report["emotions"]["joy"]
        self.assertGreater(joy["stepwise_rate"], joy["true_step_rate"])
        self.assertGreater(joy["static_step_rate"], 0.0)
        self.assertEqual(joy["static_run_max"], 3)


if __name__ == "__main__":
    unittest.main()
