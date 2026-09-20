import importlib.util
import hashlib
import sqlite3
import struct
import tempfile
import unittest
from pathlib import Path

import numpy as np


MODULE_PATH = Path(__file__).with_name("run_research_v3.py")
SPEC = importlib.util.spec_from_file_location("run_research_v3", MODULE_PATH)
MODULE = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(MODULE)


class ResearchV3ReportingTests(unittest.TestCase):
    def test_manifest_lookup_resolves_duplicate_basenames_by_path(self):
        manifest = [
            {
                "filename": "kick.wav",
                "local_relative_path": "vendor_a/kick.wav",
                "expected_subcategory": "Kick",
            },
            {
                "filename": "kick.wav",
                "local_relative_path": "vendor_b/kick.wav",
                "expected_subcategory": "Kick",
            },
        ]
        lookup = MODULE.build_manifest_lookup(manifest)

        item = MODULE.find_manifest_item("/scan/vendor_b/kick.wav", lookup)

        self.assertEqual(item["local_relative_path"], "vendor_b/kick.wav")

    def test_manifest_lookup_rejects_ambiguous_basename(self):
        manifest = [
            {"filename": "kick.wav", "expected_subcategory": "Kick"},
            {"filename": "kick.wav", "expected_subcategory": "Impact"},
        ]
        lookup = MODULE.build_manifest_lookup(manifest)

        with self.assertRaisesRegex(RuntimeError, "basename ambiguity"):
            MODULE.find_manifest_item("/scan/kick.wav", lookup)

    def test_manifest_lookup_skips_ambiguous_out_of_scope_row(self):
        manifest = [
            {"filename": "kick.wav", "expected_subcategory": "Kick"},
            {"filename": "kick.wav", "expected_subcategory": "Impact"},
        ]
        lookup = MODULE.build_manifest_lookup(manifest)

        self.assertIsNone(
            MODULE.find_manifest_item(
                "/scan/unlabelled/kick.wav",
                lookup,
                reject_ambiguous_basename=False,
            )
        )

    def test_manifest_lookup_requires_path_for_superset_cache(self):
        manifest = [
            {
                "filename": "kick.wav",
                "source_path": "/labelled/vendor_a/kick.wav",
                "expected_subcategory": "Kick",
            }
        ]
        lookup = MODULE.build_manifest_lookup(manifest)

        self.assertIsNone(
            MODULE.find_manifest_item(
                "/scan/unlabelled/kick.wav",
                lookup,
                reject_ambiguous_basename=False,
                allow_basename_fallback=False,
            )
        )

    def test_manifest_lookup_can_use_declared_content_hash(self):
        with tempfile.TemporaryDirectory() as directory:
            audio = Path(directory) / "native-name.wav"
            audio.write_bytes(b"fixture audio bytes")
            digest = hashlib.sha256(audio.read_bytes()).hexdigest()
            manifest = [{
                "filename": "opaque-fixture-name.wav",
                "sha256": digest,
                "expected_subcategory": "Kick",
            }]
            lookup = MODULE.build_manifest_lookup(manifest)
            hash_lookup = MODULE.build_manifest_hash_lookup(manifest)

            item = MODULE.find_manifest_item(
                str(audio),
                lookup,
                reject_ambiguous_basename=False,
                allow_basename_fallback=False,
                content_hash_lookup=hash_lookup,
            )

            self.assertIs(item, manifest[0])

    def test_manifest_lookup_prefers_canonical_path_over_duplicate_hash(self):
        with tempfile.TemporaryDirectory() as directory:
            audio = Path(directory) / "native-name.wav"
            audio.write_bytes(b"fixture audio bytes")
            digest = hashlib.sha256(audio.read_bytes()).hexdigest()
            manifest = [
                {"path": str(audio), "filename": "native-name.wav", "sha256": digest},
                {"path": str(Path(directory) / "other-name.wav"),
                 "filename": "other-name.wav", "sha256": digest},
            ]
            item = MODULE.find_manifest_item(
                str(audio),
                MODULE.build_manifest_lookup(manifest),
                reject_ambiguous_basename=False,
                allow_basename_fallback=False,
                content_hash_lookup=MODULE.build_manifest_hash_lookup(manifest),
            )
            self.assertIs(item, manifest[0])

    def test_manifest_lookup_rejects_duplicate_content_hash(self):
        with tempfile.TemporaryDirectory() as directory:
            audio = Path(directory) / "native-name.wav"
            audio.write_bytes(b"fixture audio bytes")
            digest = hashlib.sha256(audio.read_bytes()).hexdigest()
            manifest = [
                {"filename": "one.wav", "sha256": digest},
                {"filename": "two.wav", "sha256": digest},
            ]
            with self.assertRaisesRegex(RuntimeError, "content-hash ambiguity"):
                MODULE.find_manifest_item(
                    str(audio),
                    MODULE.build_manifest_lookup(manifest),
                    reject_ambiguous_basename=False,
                    allow_basename_fallback=False,
                    content_hash_lookup=MODULE.build_manifest_hash_lookup(manifest),
                )

    def test_manifest_coverage_rejects_missing_declared_rows(self):
        manifest = [
            {"filename": "kick.wav", "expected_subcategory": "Kick"},
            {"filename": "snare.wav", "expected_subcategory": "Snare"},
        ]

        with self.assertRaisesRegex(RuntimeError, "1 declared rows"):
            MODULE.validate_manifest_coverage(manifest, {id(manifest[0])})

    def test_cache_schema_rejects_legacy_table_shape(self):
        with tempfile.NamedTemporaryFile(suffix=".sqlite3") as handle:
            with sqlite3.connect(handle.name) as conn:
                with self.assertRaisesRegex(RuntimeError, "missing sample_cache table"):
                    MODULE.validate_cache_schema(conn, handle.name)

    def test_cache_embedding_rejects_wrong_dimension(self):
        legacy_2048 = struct.pack("2048f", *([1.0] + [0.0] * 2047))

        with self.assertRaisesRegex(RuntimeError, "expected 512 float32 values"):
            MODULE.decode_cache_embedding(legacy_2048, "legacy-v5c-cache")

    def test_cache_embedding_rejects_zero_vector(self):
        zero_512 = struct.pack("512f", *([0.0] * 512))

        with self.assertRaisesRegex(RuntimeError, "finite and nonzero"):
            MODULE.decode_cache_embedding(zero_512, "zero-cache-row")

    def test_research_metadata_rejects_single_vendor_and_mixed_family(self):
        with self.assertRaisesRegex(RuntimeError, "at least two vendors"):
            MODULE.validate_research_metadata(
                ["Kick"],
                ["family"],
                ["vendor"],
                ["vendor"],
                {"Kick"},
            )

    def test_runtime_weight_export_is_opt_in(self):
        args = MODULE.build_argument_parser().parse_args([])

        self.assertIsNone(args.weights_output)

    def test_default_research_output_is_outside_source_tree(self):
        base_dir = str(MODULE_PATH.parent)
        project_dir = str(MODULE_PATH.parents[2])

        output_dir = MODULE.resolve_output_dir(base_dir, project_dir)

        self.assertNotEqual(Path(output_dir).resolve(), Path(project_dir).resolve())
        self.assertNotIn(Path(project_dir).resolve(), Path(output_dir).resolve().parents)

    def test_research_output_rejects_source_tree(self):
        base_dir = str(MODULE_PATH.parent)
        project_dir = str(MODULE_PATH.parents[2])

        with self.assertRaisesRegex(ValueError, "outside the SmartSampleManager source tree"):
            MODULE.resolve_output_dir(base_dir, project_dir, project_dir)

    def test_temperature_is_always_positive(self):
        scaler = MODULE.TemperatureScaler()
        scaler.raw_temperature.data.fill_(-100.0)

        self.assertGreater(scaler.temperature.item(), 0.0)
        self.assertTrue(
            np.isfinite(scaler(MODULE.torch.tensor([[1.0, -1.0]])).detach().numpy()).all()
        )

    def test_abstention_rows_report_known_and_ood_rates(self):
        rows = MODULE.build_abstention_rows(
            known_predictions=np.array([0, 1, 0, 1]),
            known_labels=np.array([0, 1, 1, 1]),
            known_confidences=np.array([0.9, 0.8, 0.7, 0.4]),
            ood_confidences=np.array([0.9, 0.6]),
            thresholds=(0.75, 0.9),
        )

        self.assertEqual(rows[0]["accepted_known_count"], 2)
        self.assertEqual(rows[0]["abstention_count"], 2)
        self.assertAlmostEqual(rows[0]["coverage"], 0.5)
        self.assertAlmostEqual(rows[0]["abstention_rate"], 0.5)
        self.assertAlmostEqual(rows[0]["accepted_known_accuracy"], 1.0)
        self.assertEqual(rows[0]["false_known_ood_count"], 1)
        self.assertAlmostEqual(rows[0]["false_known_ood_rate"], 0.5)

        self.assertEqual(rows[1]["accepted_known_count"], 1)
        self.assertEqual(rows[1]["false_known_ood_count"], 1)

    def test_empty_ood_population_is_explicit(self):
        rows = MODULE.build_abstention_rows(
            known_predictions=np.array([0]),
            known_labels=np.array([0]),
            known_confidences=np.array([0.8]),
            ood_confidences=np.empty(0),
            thresholds=(0.75,),
        )

        self.assertIsNone(rows[0]["false_known_ood_rate"])
        self.assertEqual(rows[0]["ood_count"], 0)

    def test_energy_score_is_stable_and_has_known_direction(self):
        logits = np.array([[10000.0, 9998.0], [1.0, 1.0]], dtype=np.float64)
        energy = MODULE.calculate_energy(logits, 2.0)

        self.assertTrue(np.isfinite(energy).all())
        self.assertLess(energy[0], energy[1])
        self.assertGreater((-energy[0]), (-energy[1]))

    def test_energy_score_rejects_invalid_inputs(self):
        with self.assertRaisesRegex(ValueError, "two-dimensional"):
            MODULE.calculate_energy(np.array([1.0, 2.0]), 1.0)
        with self.assertRaisesRegex(ValueError, "finite"):
            MODULE.calculate_energy(np.array([[np.nan, 1.0]]), 1.0)
        with self.assertRaisesRegex(ValueError, "positive"):
            MODULE.calculate_energy(np.array([[1.0, 2.0]]), 0.0)


if __name__ == "__main__":
    unittest.main()
