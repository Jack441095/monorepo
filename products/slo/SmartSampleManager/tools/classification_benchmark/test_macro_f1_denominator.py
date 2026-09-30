"""Macro F1 must average over the classes a slice actually contains.

The September 2026 review found three benchmark scripts dividing macro F1 by
``len(labels)`` -- the full taxonomy -- rather than the classes present in
``y_true``. A class the slice does not contain scores 0.0 and drags the average
down, so a three-class slice evaluated against a sixteen-label list could report
a macro F1 at most 3/16 of its real value, and read as though it had failed on
classes it never saw. The V2 report's 0.073 audio-only macro F1 sits next to a
17.5% accuracy, which is exactly the shape a deflated denominator produces.

These cases pin the arithmetic, not the benchmark: no models, no corpus.
"""

import ast
import importlib.util
import os
import unittest

_BENCHMARK_DIR = os.path.dirname(os.path.abspath(__file__))


def _macro_f1_over_present(labels, metrics, y_true):
    """The corrected formula, inlined so all three scripts are pinned at once."""
    present = [label for label in labels if any(t == label for t in y_true)]
    if not present:
        return 0.0
    return sum(metrics[label] for label in present) / len(present)


class MacroF1DenominatorTests(unittest.TestCase):
    LABELS = ["Kick", "Snare", "Hi-Hat", "Clap", "Percussion", "Bass One-Shot"]

    def test_absent_class_no_longer_dilutes_the_average(self):
        # Only Kick and Snare are present. Their F1s are 1.0 and 0.5.
        y_true = ["Kick", "Kick", "Snare", "Snare", "Snare"]
        metrics = {"Kick": 1.0, "Snare": 0.5, "Hi-Hat": 0.0,
                   "Clap": 0.0, "Percussion": 0.0, "Bass One-Shot": 0.0}

        correct = _macro_f1_over_present(self.LABELS, metrics, y_true)
        self.assertAlmostEqual(correct, 0.75)

        # The old formula divided by all six labels and returned 0.25.
        old = sum(metrics.values()) / len(self.LABELS)
        self.assertAlmostEqual(old, 0.25)
        self.assertGreater(correct, old)

    def test_full_coverage_is_unchanged(self):
        # When every class is present the two formulas must agree, so the fix
        # cannot quietly change a full-taxonomy number that was already right.
        y_true = ["Kick", "Snare", "Hi-Hat", "Clap", "Percussion", "Bass One-Shot"]
        metrics = {label: 0.75 for label in self.LABELS}
        self.assertAlmostEqual(_macro_f1_over_present(self.LABELS, metrics, y_true),
                               sum(metrics.values()) / len(self.LABELS))

    def test_empty_slice_reports_zero_rather_than_dividing_by_zero(self):
        self.assertEqual(_macro_f1_over_present(self.LABELS, {}, []), 0.0)

    def test_every_benchmark_script_uses_the_present_class_denominator(self):
        # Guards against one of the three regressing back, which is how the same
        # bug reached three files in the first place.
        for script in ("run_benchmark.py",
                       "run_real_corpus_v2_benchmark.py",
                       "run_research_v3.py"):
            path = os.path.join(_BENCHMARK_DIR, script)
            with open(path, "r", encoding="utf-8") as handle:
                source = handle.read()
            ast.parse(source)  # also proves the file still parses
            self.assertNotIn(
                "/ len(labels)",
                source,
                f"{script} divides macro F1 by len(labels) again; use the "
                f"classes present in y_true")
            self.assertIn(
                "present",
                source,
                f"{script} no longer computes a present-class set")


if __name__ == "__main__":
    unittest.main()
