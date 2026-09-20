import unittest
from pathlib import Path


SOURCE = Path(__file__).with_name("classification_benchmark_main.cpp")
BENCH_DIR = Path(__file__).parent


class ClassificationBenchmarkReceiptContractTests(unittest.TestCase):
    def test_scan_receipt_preserves_path_identity(self):
        source = SOURCE.read_text(encoding="utf-8")
        scan_source = source[source.index('if (mode == "scan")'):source.index('else if (mode == "perf")')]
        self.assertIn(
            '"filePath\\": \\"" << juce::File(s.filePath).getFullPathName()',
            scan_source,
        )
        self.assertIn(
            '"fileName\\": \\"" << juce::File(s.filePath).getFileName()',
            scan_source,
        )
        self.assertNotIn(
            '"filePath\\": \\"" << juce::File(s.filePath).getFileName()',
            scan_source,
        )
        self.assertIn("stagingFile", scan_source)
        self.assertIn("moveFileTo(outFile)", scan_source)
        self.assertNotIn("outFile.deleteFile()", scan_source)


class EvalContractTests(unittest.TestCase):
    """P2-5: every accuracy-reporting benchmark script must emit evidence-split
    labels plus uncertainty. A bare 'accuracy: N%' with no split and no CI is
    how 96.5% / 62.9% / 30.2% / 0% got quoted interchangeably -- fail closed."""

    def _read(self, name):
        return (BENCH_DIR / name).read_text(encoding="utf-8")

    def test_eval_contract_helper_sane(self):
        import eval_contract
        self.assertIn("audio-only", eval_contract.REQUIRED_SPLIT_LABELS)
        self.assertIn("adversarial", eval_contract.REQUIRED_SPLIT_LABELS)
        lo, hi = eval_contract.wilson_ci(629, 1000)
        self.assertTrue(0.59 < lo < hi < 0.67)
        self.assertEqual(
            eval_contract.missing_splits("Audio-only 30% adversarial 0% fused 63%"), [])

    def test_golden_report_carries_splits_and_ci(self):
        source = self._read("run_benchmark.py")
        lowered = source.lower()
        for label in ("audio only accuracy", "adversarial accuracy",
                      "filename only accuracy", "folder only accuracy",
                      "full evidence accuracy"):
            self.assertIn(label, lowered, f"missing split label: {label}")
        self.assertIn("eval_contract", source)
        self.assertTrue("wilson" in lowered or "95% ci" in lowered,
                        "golden report has no uncertainty statement")

    def test_real_corpus_reports_carry_splits_and_ci(self):
        for name in ("run_real_corpus_benchmark.py",
                     "run_real_corpus_v2_benchmark.py"):
            source = self._read(name)
            lowered = source.lower()
            self.assertIn("audio-only accuracy", lowered, f"{name}: audio-only split")
            self.assertIn("full-evidence accuracy", lowered, f"{name}: full-evidence split")
            self.assertIn("eval_contract", source, f"{name}: contract helper")
            self.assertTrue("wilson" in lowered or "95% ci" in lowered,
                            f"{name}: no uncertainty statement")


class OodRecalibrationContractTests(unittest.TestCase):
    """P2-3: the recalibration harness must observe without touching. The
    shipped gate reads diagMlNearestCentroid from scan receipts; the harness
    may only write proposal artifacts, never Source/."""

    def test_scan_receipt_carries_nearest_centroid(self):
        source = (BENCH_DIR / "classification_benchmark_main.cpp").read_text(encoding="utf-8")
        # C++-escaped in source (\\"key\\"), so match the bare identifier.
        self.assertIn("diagMlNearestCentroid", source)

    def test_harness_writes_artifacts_only(self):
        import re
        source = (BENCH_DIR / "ood_recalibrate.py").read_text(encoding="utf-8")
        self.assertNotRegex(source, r"open\([^)]*\.h[^)]*,\s*[\"']w[\"']")
        self.assertIn("PROPOSAL_ONLY_REQUIRES_OWNER_AUTH", source)
        self.assertIn("def write_artifact", source)

    def test_harness_selfcheck_green(self):
        import subprocess
        import sys
        result = subprocess.run(
            [sys.executable, str(BENCH_DIR / "ood_recalibrate.py"), "--selfcheck"],
            capture_output=True, text=True, timeout=300)
        self.assertEqual(result.returncode, 0, result.stderr[-2000:])
        self.assertIn("OK", result.stderr)


if __name__ == "__main__":
    unittest.main()
