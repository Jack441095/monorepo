import json
import tempfile
import unittest
from pathlib import Path


class JointCompositionDiagnosticsFastTests(unittest.TestCase):
    def test_analyze_fast_reports_joint_fit_metrics(self) -> None:
        from scripts.joint_composition_diagnostics_fast import analyze_fast

        # Two bars: I then V; melody hits chord tones on beat 0.
        row = {
            "emotion": "admiration",
            "beats_per_bar": 4.0,
            "chord_sequence": ["Imaj7", "V7"],
            "chord_markov_tokens": ["I:maj", "V:dom"],
            "roots": [60, 67],
            "cadence_targets": [{"cadence_degree": 4}],
            # Melody: degree 0 at t=0 (I tone), degree 4 at t=4 (V tone).
            "melody": [[0, 4.0], [4, 4.0]],
        }
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "joint.jsonl"
            path.write_text(json.dumps(row), encoding="utf-8")
            rep = analyze_fast(path, min_rows=1)

        emo = rep["emotions"]["admiration"]
        self.assertGreaterEqual(emo["strong_beat_chord_tone_rate"], 0.9)
        self.assertGreaterEqual(emo["cadence_agreement_n"], 1)


if __name__ == "__main__":
    unittest.main()

