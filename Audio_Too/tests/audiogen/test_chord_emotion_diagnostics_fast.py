import json
import tempfile
import unittest
from pathlib import Path


class ChordEmotionDiagnosticsFastTests(unittest.TestCase):
    def test_analyze_fast_reports_basic_harmony_metrics(self) -> None:
        from scripts.chord_emotion_diagnostics_fast import analyze_fast

        rows = [
            {
                "emotion": "joy",
                "chord_sequence": ["Imaj7", "V7", "Imaj7", "Imaj7"],
                "chord_markov_tokens": ["I:maj", "V:dom", "I:maj", "I:maj"],
                "melody": [[0, 1.0], [2, 1.0], [4, 2.0]],
                "beats_per_bar": 4.0,
            },
            {
                "emotion": "joy",
                "chord_sequence": ["Imaj7", "vi7", "V7", "Imaj7"],
                "chord_markov_tokens": ["I:maj", "vi:min", "V:dom", "I:maj"],
                "melody": [[4, 1.0], [3, 1.0], [2, 2.0]],
                "beats_per_bar": 4.0,
            },
        ]
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "joint.jsonl"
            path.write_text("\n".join(json.dumps(r) for r in rows), encoding="utf-8")
            rep = analyze_fast(path, min_rows=1)

        self.assertEqual(rep["rows_used"], 2)
        joy = rep["emotions"]["joy"]
        self.assertIn("token_entropy_bits", joy)
        self.assertIn("repeat_rate", joy)
        self.assertGreaterEqual(joy["unique_tokens"], 3)


if __name__ == "__main__":
    unittest.main()

