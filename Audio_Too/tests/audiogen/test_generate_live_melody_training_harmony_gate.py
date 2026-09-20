import json
import tempfile
import unittest
from pathlib import Path


def _row(*, emotion: str, melody, chords, accept_score: float = 0.9):
    return {
        "emotion": emotion,
        "melody": melody,
        "chord_sequence": chords,
        "beats_per_bar": 4.0,
        "accept_score": accept_score,
    }


class GenerateLiveMelodyTrainingHarmonyGateTests(unittest.TestCase):
    def test_split_rejects_low_fit_tender_rows(self) -> None:
        from scripts.generate_live_melody_training_jsonl import _split_jsonl_by_accept

        with tempfile.TemporaryDirectory() as td:
            base = Path(td)
            raw = base / "raw.jsonl"
            kept = base / "kept.jsonl"
            rej = base / "rej.jsonl"

            bad_tender = _row(
                emotion="caring",
                melody=[[1, 2.0], [1, 2.0], [1, 2.0], [1, 2.0]],
                chords=["I", "I", "I", "I"],
            )
            good_tender = _row(
                emotion="caring",
                melody=[[0, 2.0], [2, 2.0], [4, 2.0], [0, 2.0]],
                chords=["I", "I", "I", "I"],
            )
            raw.write_text(
                json.dumps(bad_tender) + "\n" + json.dumps(good_tender) + "\n",
                encoding="utf-8",
            )

            kept_n, rej_n = _split_jsonl_by_accept(
                raw_path=raw,
                kept_path=kept,
                rejects_path=rej,
                accept_threshold=0.0,
                dedup_kept=False,
                min_strongbeat_fit=0.0,
                tender_min_strongbeat_fit=0.5,
            )

            self.assertEqual(kept_n, 1)
            self.assertEqual(rej_n, 1)
            kept_rows = [json.loads(line) for line in kept.read_text(encoding="utf-8").splitlines() if line.strip()]
            rej_rows = [json.loads(line) for line in rej.read_text(encoding="utf-8").splitlines() if line.strip()]
            self.assertEqual(kept_rows[0]["emotion"], "caring")
            self.assertEqual(kept_rows[0]["melody"][0][0], 0)
            self.assertTrue(str(rej_rows[0]["split_reject_reason"]).startswith("low_strongbeat_fit:"))

    def test_split_uses_general_floor_for_non_tender_rows(self) -> None:
        from scripts.generate_live_melody_training_jsonl import _split_jsonl_by_accept

        with tempfile.TemporaryDirectory() as td:
            base = Path(td)
            raw = base / "raw.jsonl"
            kept = base / "kept.jsonl"
            rej = base / "rej.jsonl"

            bad_neutral = _row(
                emotion="neutral",
                melody=[[1, 2.0], [1, 2.0], [1, 2.0], [1, 2.0]],
                chords=["I", "I", "I", "I"],
            )
            raw.write_text(json.dumps(bad_neutral) + "\n", encoding="utf-8")

            kept_n, rej_n = _split_jsonl_by_accept(
                raw_path=raw,
                kept_path=kept,
                rejects_path=rej,
                accept_threshold=0.0,
                dedup_kept=False,
                min_strongbeat_fit=0.5,
                tender_min_strongbeat_fit=0.8,
            )

            self.assertEqual(kept_n, 0)
            self.assertEqual(rej_n, 1)


if __name__ == "__main__":
    unittest.main()
