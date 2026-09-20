"""SLO evaluation contract (P2-5): split labels + uncertainty on every number.

Problem it solves: the estate once quoted 96.5% (leaky benchmark), 62.9%
(cross-vendor fused), 30.2% (audio-only) and 0% (adversarial) interchangeably
because accuracy logs carried no split label and no uncertainty. Rule: every
accuracy number a benchmark script prints or writes must carry
  (a) its evidence split (audio-only / full-evidence|fused / filename-only /
      folder-only / adversarial), and
  (b) a 95% Wilson confidence interval plus the raw hits/n.

Stdlib only (no sklearn/numpy): benchmark harnesses run on machines without
the research venv. `python3 eval_contract.py` runs the self-tests.
"""

import math
import re
import unittest

# Canonical split labels. missing_splits() matches case-insensitively and
# accepts the known aliases so reports are not forced into awkward phrasing.
REQUIRED_SPLIT_LABELS = ("audio-only", "adversarial")
REQUIRED_SPLIT_ALIASES = {
    "audio-only": ("audio-only", "audio only", "audio_only"),
    "adversarial": ("adversarial",),
    "full-evidence": ("full-evidence", "full evidence", "fused", "full_evidence"),
}


def wilson_ci(hits, n, z=1.96):
    """95% Wilson score interval for a binomial proportion. Returns (lo, hi).

    Empty sample (n == 0) returns (0.0, 0.0): no data, no interval, and the
    caller must still print the split with n=0 rather than dropping it.
    """
    if n <= 0:
        return (0.0, 0.0)
    hits = min(max(hits, 0), n)
    p = hits / n
    denom = 1.0 + z * z / n
    centre = p + z * z / (2.0 * n)
    margin = z * math.sqrt(p * (1.0 - p) / n + z * z / (4.0 * n * n))
    return (max(0.0, (centre - margin) / denom),
            min(1.0, (centre + margin) / denom))


def split_line(label, hits, n):
    """One contract-formatted accuracy line, e.g.
    'Audio-only accuracy: 30.2% (187/620, 95% CI 26.7-34.0%)'."""
    lo, hi = wilson_ci(hits, n)
    pct = 100.0 * hits / n if n > 0 else 0.0
    return (f"{label}: {pct:.1f}% ({hits}/{n}, "
            f"95% CI {100.0 * lo:.1f}-{100.0 * hi:.1f}%)")


def missing_splits(report_text, required=("audio-only", "adversarial", "full-evidence")):
    """Splits from `required` absent from report_text (case-insensitive,
    alias-aware). Empty list = contract satisfied."""
    lowered = report_text.lower()
    missing = []
    for split in required:
        aliases = REQUIRED_SPLIT_ALIASES.get(split, (split,))
        if not any(a.lower() in lowered for a in aliases):
            missing.append(split)
    return missing


def has_ci(report_text):
    """True when the text carries an explicit uncertainty statement."""
    lowered = report_text.lower()
    return ("95% ci" in lowered or "confidence interval" in lowered
            or "wilson" in lowered)


class EvalContractTests(unittest.TestCase):
    def test_wilson_spot_values(self):
        lo, hi = wilson_ci(629, 1000)
        self.assertTrue(0.59 < lo < 0.62 and 0.64 < hi < 0.67)
        lo, hi = wilson_ci(0, 10)
        self.assertEqual(lo, 0.0)
        self.assertTrue(0.25 < hi < 0.30)
        lo, hi = wilson_ci(10, 10)
        self.assertTrue(0.70 < lo < 0.75)
        self.assertEqual(hi, 1.0)
        self.assertEqual(wilson_ci(0, 0), (0.0, 0.0))
        self.assertEqual(wilson_ci(5, 4), wilson_ci(4, 4))  # clamped

    def test_split_line_format(self):
        line = split_line("Audio-only accuracy", 187, 620)
        self.assertIn("187/620", line)
        self.assertIn("95% CI", line)
        self.assertRegex(line, r"\d+\.\d% \(\d+/\d+, 95% CI \d+\.\d+-\d+\.\d+%\)")

    def test_missing_splits(self):
        self.assertEqual(missing_splits("Audio-only 30% and adversarial 0% and fused 63%"), [])
        self.assertEqual(missing_splits("Audio only 30% plus full evidence 63%"), ["adversarial"])
        self.assertEqual(missing_splits("overall accuracy 96.5%"), list(("audio-only", "adversarial", "full-evidence")))
        self.assertEqual(missing_splits("", required=()), [])

    def test_has_ci(self):
        self.assertTrue(has_ci("30.2% (95% CI 26.7-34.0%)"))
        self.assertTrue(has_ci("Wilson interval"))
        self.assertFalse(has_ci("accuracy 96.5%"))

    def test_required_labels_nonempty(self):
        self.assertTrue(len(REQUIRED_SPLIT_LABELS) >= 2)
        self.assertIn("audio-only", REQUIRED_SPLIT_LABELS)
        self.assertIn("adversarial", REQUIRED_SPLIT_LABELS)


if __name__ == "__main__":
    unittest.main()
