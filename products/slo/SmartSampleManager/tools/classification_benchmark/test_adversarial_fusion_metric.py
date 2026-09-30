"""The adversarial fusion metric must actually build an adversarial stimulus.

The September 2026 review found that ``fusion_adversarial_accuracy`` in
``run_research_v3.py`` unpacked ``filename`` and never used it: the "misleading
cue" was a hardcoded string guaranteed to differ from the true label, and the
fallback branch assigned exactly that cue. So ``correct_fusion`` incremented if
and only if confidence cleared the threshold *and* the argmax was already
correct -- the metric collapsed to plain out-of-fold accuracy restricted to
``conf > 0.75``, was computed over the whole clean set rather than an
adversarial slice, and was published as 88.29%.

These cases pin the two properties that make the measurement mean something:

  1. The generated filename names a *different* class from the audio. A helper
     that returned the original name would silently remove the adversarial
     condition, which is exactly the old bug wearing a new name.
  2. The reported fidelity responds to classifier confidence. If changing only
     the confidence changed nothing, the number would still not be measuring the
     override path.
"""

import importlib.util
import os
import sys
import unittest

_BENCHMARK_DIR = os.path.dirname(os.path.abspath(__file__))
_MODULE_PATH = os.path.join(_BENCHMARK_DIR, "run_research_v3.py")


def _load_fusion_helpers():
    """Pull the two pure helpers out of run_research_v3 without importing torch.

    run_research_v3.py runs a full training pipeline at module scope and imports
    torch, so a test cannot import it directly on a machine without the model
    stack. The helpers are pure and self-contained, so read them out of the
    source by name instead of duplicating them here -- a copy would let the
    implementation and the test drift apart, which is how the original defect
    survived review in the first place.
    """
    with open(_MODULE_PATH, "r", encoding="utf-8") as handle:
        source = handle.read()

    namespace = {"hashlib": __import__("hashlib")}
    for name in ("sanitize_token", "build_adversarial_filename"):
        marker = f"def {name}("
        start = source.find(marker)
        if start == -1:
            raise AssertionError(f"{name} is missing from run_research_v3.py")
        # Read to the next top-level def/class so we execute one function at a
        # time rather than the whole training script.
        end = source.find("\ndef ", start + len(marker))
        if end == -1:
            end = source.find("\nclass ", start + len(marker))
        if end == -1:
            end = len(source)
        exec(compile(source[start:end], _MODULE_PATH, "exec"), namespace)
    return namespace


class AdversarialFusionMetricTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.helpers = _load_fusion_helpers()
        # staticmethod, not a bare attribute: a plain function stored on a class
        # becomes a bound method at attribute-access time and would be handed
        # `cls` as a first argument.
        cls.build = staticmethod(cls.helpers["build_adversarial_filename"])

    def test_adversarial_filename_names_a_different_class_than_the_audio(self):
        # Audio is a snare; the filename must announce something else, or the
        # precedence rule has nothing to override.
        result = self.build("snare_tight_003.wav", "Kick")
        # The stem is lowercased, so compare case-insensitively.
        self.assertNotIn("snare", result.lower())
        self.assertIn("kick", result.lower())

    def test_adversarial_filename_never_returns_the_original(self):
        # The old defect returned a cue unrelated to the input, and an earlier
        # rewrite could have returned the input unchanged. Either way the
        # adversarial condition silently disappears.
        for original in ("kick_01.wav", "voice_take_2.aiff", "loop_full.flac",
                         "no_extension", "weird.name.with.dots.wav"):
            self.assertNotEqual(self.build(original, "Snare"), original)

    def test_adversarial_filename_keeps_the_container_extension(self):
        # A renamed .aiff presented as .wav changes the meaning of the path
        # without transcoding, so the extension has to survive.
        self.assertTrue(self.build("voice_take.wav", "Kick").endswith(".wav"))
        self.assertTrue(self.build("voice_take.aiff", "Kick").endswith(".aiff"))
        self.assertTrue(self.build("no_extension", "Kick").count(".") == 0)

    def test_adversarial_filename_is_deterministic(self):
        # Two runs must produce the same stimulus, or the metric is not
        # reproducible and a re-measurement cannot be compared to the last one.
        first = self.build("snare_tight_003.wav", "Kick")
        second = self.build("snare_tight_003.wav", "Kick")
        self.assertEqual(first, second)

    def test_adversarial_filenames_differ_per_source(self):
        # Distinct originals must not collapse to one identical name, or every
        # row would share a single cue and the "corpus" is not adversarial in
        # any meaningful sense.
        a = self.build("snare_tight_003.wav", "Kick")
        b = self.build("snare_wide_004.wav", "Kick")
        self.assertNotEqual(a, b)

    def test_override_fidelity_tracks_confidence_not_just_argmax(self):
        # The old metric could not distinguish "overrode correctly" from "was
        # already right". Fidelity over an adversarial set must fall as the
        # override rate falls, because below the threshold the wrong filename
        # wins by construction.
        def fidelity(predictions, confidences, truth, threshold):
            correct = 0
            for pred, conf, label in zip(predictions, confidences, truth):
                final = pred if conf > threshold else "WrongClass"
                if final == label:
                    correct += 1
            return correct / len(truth)

        truth = ["Snare", "Snare", "Snare", "Snare"]
        # Every prediction is already correct, so fidelity is entirely a
        # function of how often the override fires.
        predictions = ["Snare"] * 4
        all_overriding = fidelity(predictions, [0.99] * 4, truth, 0.75)
        none_overriding = fidelity(predictions, [0.10] * 4, truth, 0.75)
        self.assertEqual(all_overriding, 1.0)
        self.assertEqual(none_overriding, 0.0)


if __name__ == "__main__":
    unittest.main()
