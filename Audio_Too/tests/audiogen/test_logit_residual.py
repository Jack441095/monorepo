import json
import pickle
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2] / "studio" / "audiogen" / "audiogen"


class LogitResidualTests(unittest.TestCase):
    def test_apply_zero_weights_preserves_ratios(self):
        import numpy as np

        from ai.markov.melody.logit_residual import apply_interval_logit_residual, clear_residual_weight_cache

        clear_residual_weight_cache()
        with tempfile.TemporaryDirectory() as td:
            path = Path(td) / "w.npz"
            np.savez_compressed(
                str(path),
                W=np.zeros((13, 9), dtype=np.float32),
                order=np.int32(6),
                version=np.int32(1),
                feature_dim=np.int32(9),
            )
            probs = {-1: 0.25, 0: 0.25, 1: 0.5}
            out = apply_interval_logit_residual(
                dict(probs),
                interval_context_tail=[0, 0, 0, 0, 0, 0],
                phrase_pos=0.4,
                emotion_name="neutral",
                strength=1.0,
                weight_path=str(path),
                order=6,
            )
            self.assertAlmostEqual(sum(out.values()), 1.0, places=6)
            for k in probs:
                self.assertIn(k, out)
                self.assertAlmostEqual(out[k], probs[k], places=5)

    def test_train_script_produces_weights(self):
        lines = []
        for _ in range(40):
            lines.append(
                json.dumps(
                    {
                        "melody": [[0, 0.5], [1, 0.5], [2, 0.5], [3, 0.5]],
                        "accept_score": 1.0,
                        "emotion": "neutral",
                    }
                )
            )
        with tempfile.TemporaryDirectory() as td:
            td = Path(td)
            jl = td / "in.jsonl"
            jl.write_text("\n".join(lines) + "\n", encoding="utf-8")
            outp = td / "out.npz"
            cmd = [
                sys.executable,
                str(ROOT / "scripts" / "train_melody_logit_residual.py"),
                str(jl),
                "-o",
                str(outp),
            ]
            subprocess.check_call(cmd, cwd=str(ROOT))
            self.assertTrue(outp.is_file())


class MelodyEvalGateTests(unittest.TestCase):
    def test_gate_passes_clean_corpus(self):
        rows = []
        for _ in range(5):
            rows.append(
                json.dumps(
                    {
                        "melody": [[0, 0.5], [1, 0.5], [2, 0.5]],
                        "accept_score": 0.9,
                    }
                )
            )
        with tempfile.TemporaryDirectory() as td:
            p = Path(td) / "c.jsonl"
            p.write_text("\n".join(rows) + "\n", encoding="utf-8")
            cmd = [
                sys.executable,
                str(ROOT / "scripts" / "melody_eval_gate.py"),
                str(p),
                "--min-lines",
                "1",
                "--max-rest-rate",
                "1.0",
                "--min-mean-accept",
                "0.0",
            ]
            subprocess.check_call(cmd, cwd=str(ROOT))

    def test_gate_checks_metadata_balance_when_requested(self):
        rows = []
        for emotion, role in (("joy", "a"), ("grief", "b")):
            rows.append(
                json.dumps(
                    {
                        "melody": [[0, 0.5], [1, 0.5], [2, 0.5], [3, 0.5]],
                        "accept_score": 0.9,
                        "emotion": emotion,
                        "section_role": role,
                        "phrase_contours": ["asc"],
                        "phrase_roles": ["opening"],
                        "chord_sequence": ["Imaj7"],
                    }
                )
            )
        with tempfile.TemporaryDirectory() as td:
            p = Path(td) / "c.jsonl"
            p.write_text("\n".join(rows) + "\n", encoding="utf-8")
            cmd = [
                sys.executable,
                str(ROOT / "scripts" / "melody_eval_gate.py"),
                str(p),
                "--min-lines",
                "1",
                "--max-rest-rate",
                "1.0",
                "--min-mean-accept",
                "0.0",
                "--min-emotions",
                "2",
                "--min-section-roles",
                "2",
                "--max-emotion-share",
                "0.75",
                "--require-metadata",
            ]
            subprocess.check_call(cmd, cwd=str(ROOT))


class MelodyJsonlRetrainTests(unittest.TestCase):
    def test_retrain_script_writes_pickle(self):
        lines = []
        for _ in range(5):
            lines.append(
                json.dumps(
                    {
                        "melody": [[i % 7, 0.5] for i in range(8)],
                        "accept_score": 0.95,
                    }
                )
            )
        with tempfile.TemporaryDirectory() as td:
            td = Path(td)
            jl = td / "m.jsonl"
            jl.write_text("\n".join(lines) + "\n", encoding="utf-8")
            outp = td / "mm.pkl"
            cmd = [
                sys.executable,
                str(ROOT / "scripts" / "melody_jsonl_retrain.py"),
                str(jl),
                "-o",
                str(outp),
            ]
            subprocess.check_call(cmd, cwd=str(ROOT))
            self.assertTrue(outp.is_file())

    def test_retrain_script_uses_exported_metadata(self):
        rows = []
        for idx, emotion in enumerate(("joy", "grief", "joy", "grief", "joy", "grief")):
            base = idx % 3
            rows.append(
                json.dumps(
                    {
                        "melody": [[(base + i) % 7, 0.5] for i in range(8)],
                        "accept_score": 0.95,
                        "emotion": emotion,
                        "phrase_contours": ["asc", "desc"],
                        "phrase_roles": ["opening", "cadence"],
                        "chord_sequence": ["Imaj7", "V7"],
                        "beats_per_bar": 4.0,
                    }
                )
            )
        with tempfile.TemporaryDirectory() as td:
            td = Path(td)
            jl = td / "m.jsonl"
            jl.write_text("\n".join(rows) + "\n", encoding="utf-8")
            outp = td / "mm.pkl"
            cmd = [
                sys.executable,
                str(ROOT / "scripts" / "melody_jsonl_retrain.py"),
                str(jl),
                "-o",
                str(outp),
            ]
            subprocess.check_call(cmd, cwd=str(ROOT))
            with outp.open("rb") as f:
                model = pickle.load(f)

            self.assertTrue(model.use_chord_conditioned)
            self.assertTrue(model.function_interval_models)
            self.assertTrue(model.role_interval_models["opening"]._vocab_list)
            self.assertTrue(model.role_interval_models["cadence"]._vocab_list)
            self.assertTrue(model.phrase._vocab_list)
            self.assertEqual(model.training_metadata["emotion_counts"], {"grief": 3, "joy": 3})
            self.assertEqual(model.training_metadata["rows_with_chord_sequences"], 6)
            manifest = json.loads(outp.with_suffix(outp.suffix + ".manifest.json").read_text(encoding="utf-8"))
            self.assertEqual(manifest["dataset_sha256"], model.training_metadata["dataset_sha256"])
            self.assertEqual(manifest["rows"], 6)

    def test_retrain_script_can_write_grouped_bundle(self):
        rows = []
        emotions = ["joy", "joy", "joy", "joy", "grief", "grief", "grief", "grief"]
        for idx, emotion in enumerate(emotions):
            base = idx % 4
            rows.append(
                json.dumps(
                    {
                        "melody": [[(base + i) % 7, 0.5] for i in range(8)],
                        "accept_score": 0.95,
                        "emotion": emotion,
                        "phrase_contours": ["asc", "desc"],
                        "phrase_roles": ["opening", "cadence"],
                        "chord_sequence": ["Imaj7", "V7"],
                        "beats_per_bar": 4.0,
                    }
                )
            )
        with tempfile.TemporaryDirectory() as td:
            td = Path(td)
            jl = td / "m.jsonl"
            jl.write_text("\n".join(rows) + "\n", encoding="utf-8")
            outp = td / "bundle.pkl"
            cmd = [
                sys.executable,
                str(ROOT / "scripts" / "melody_jsonl_retrain.py"),
                str(jl),
                "-o",
                str(outp),
                "--grouped",
                "both",
                "--min-group-melodies",
                "4",
            ]
            subprocess.check_call(cmd, cwd=str(ROOT))
            with outp.open("rb") as f:
                bundle = pickle.load(f)
            self.assertEqual(bundle["kind"], "melody_markov_bundle")
            self.assertIn("joy", bundle["emotion_models"])
            self.assertIn("grief", bundle["emotion_models"])
            self.assertIn("energetic", bundle["family_models"])
            self.assertIn("sad", bundle["family_models"])
            self.assertIs(bundle["emotion_models"]["joy"].global_fallback, bundle["global"])

    def test_main_offline_train_markov_dispatch(self):
        rows = []
        emotions = ["joy", "joy", "grief", "grief"]
        for idx, emotion in enumerate(emotions):
            rows.append(
                json.dumps(
                    {
                        "melody": [[(idx + i) % 7, 0.5] for i in range(8)],
                        "accept_score": 0.95,
                        "emotion": emotion,
                        "section_role": "b" if emotion == "joy" else "a",
                        "phrase_contours": ["asc", "desc"],
                        "phrase_roles": ["opening", "cadence"],
                        # `chord_jsonl_retrain` default --min-len is 4 tokens.
                        "chord_sequence": ["Imaj7", "V7", "vi7", "Imaj7"],
                        "beats_per_bar": 4.0,
                    }
                )
            )
        with tempfile.TemporaryDirectory() as td:
            td = Path(td)
            jl = td / "m.jsonl"
            out_dir = td / "offline_training"
            jl.write_text("\n".join(rows) + "\n", encoding="utf-8")
            cmd = [
                sys.executable,
                str(ROOT / "main.py"),
                "--offline-train",
                "markov",
                "--offline-train-jsonl",
                str(jl),
                "--offline-train-dir",
                str(out_dir),
                "--offline-train-tag",
                "Unit Markov",
                "--offline-train-grouped",
                "both",
                "--offline-train-min-group-melodies",
                "2",
                "--offline-train-skip-eval",
            ]
            subprocess.check_call(cmd, cwd=str(ROOT))
            run_dir = out_dir / "unit_markov"
            self.assertTrue((run_dir / "unit_markov_melody_markov.pkl").is_file())
            manifest = json.loads((run_dir / "unit_markov_offline_training_manifest.json").read_text(encoding="utf-8"))
            self.assertEqual(manifest["tag"], "unit_markov")
            self.assertEqual(manifest["job"], "markov")
            self.assertIn("markov_pickle", manifest["outputs"])

    def test_main_offline_promote_dispatch(self):
        with tempfile.TemporaryDirectory() as td:
            td = Path(td)
            run_dir = td / "offline_training" / "unit"
            run_dir.mkdir(parents=True)
            markov = run_dir / "unit_melody_markov.pkl"
            logit = run_dir / "unit_melody_logit_residual.npz"
            markov.write_bytes(b"markov")
            logit.write_bytes(b"logit")
            (run_dir / "unit_offline_training_manifest.json").write_text(
                json.dumps(
                    {
                        "schema_version": 1,
                        "tag": "unit",
                        "job": "all",
                        "run_dir": str(run_dir),
                        "outputs": {
                            "markov_pickle": str(markov),
                            "logit_residual": str(logit),
                        },
                    },
                    indent=2,
                )
                + "\n",
                encoding="utf-8",
            )
            active_dir = td / "active"
            subprocess.check_call(
                [
                    sys.executable,
                    str(ROOT / "main.py"),
                    "--offline-promote-run",
                    str(run_dir),
                    "--offline-promote-dir",
                    str(active_dir),
                    "--offline-promote-kind",
                    "all",
                ],
                cwd=str(ROOT),
            )
            self.assertEqual((active_dir / "melody_markov.pkl").read_bytes(), b"markov")
            self.assertEqual((active_dir / "melody_logit_residual.npz").read_bytes(), b"logit")
            active_manifest = json.loads((active_dir / "active_manifest.json").read_text(encoding="utf-8"))
            st = (active_manifest.get("stages") or {}).get("active") or {}
            self.assertEqual(st.get("source_tag"), "unit")
            self.assertEqual(len(active_manifest.get("artifacts") or []), 2)


class EmotionDatasetExportTests(unittest.TestCase):
    def test_export_emotion_dataset_writes_structured_files(self):
        with tempfile.TemporaryDirectory() as td:
            out_dir = Path(td) / "dataset"
            cmd = [
                sys.executable,
                str(ROOT / "scripts" / "export_emotion_dataset.py"),
                "--out-dir",
                str(out_dir),
            ]
            subprocess.check_call(cmd, cwd=str(ROOT))
            profiles = json.loads((out_dir / "emotion_profiles.json").read_text(encoding="utf-8"))
            rows = [
                json.loads(line)
                for line in (out_dir / "harmony_progressions.jsonl").read_text(encoding="utf-8").splitlines()
                if line.strip()
            ]
            manifest = json.loads((out_dir / "manifest.json").read_text(encoding="utf-8"))
            self.assertGreaterEqual(len(profiles), 20)
            self.assertGreaterEqual(len(rows), 300)
            self.assertEqual(manifest["emotion_count"], len(profiles))
            self.assertIn("schemas", manifest)
            report_path = out_dir / "validation_report.json"
            subprocess.check_call(
                [
                    sys.executable,
                    str(ROOT / "scripts" / "validate_emotion_dataset.py"),
                    str(out_dir),
                    "--report",
                    str(report_path),
                ],
                cwd=str(ROOT),
            )
            report = json.loads(report_path.read_text(encoding="utf-8"))
            self.assertEqual(report["emotion_count"], len(profiles))
            self.assertEqual(report["progression_rows"], len(rows))
            self.assertEqual(report["errors"], [])
