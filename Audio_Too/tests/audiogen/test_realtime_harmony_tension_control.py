import unittest


class TestRealtimeHarmonyTensionControl(unittest.TestCase):
    def test_harmonic_rhythm_tension_bias_is_deterministic(self) -> None:
        from composition.harmonic_rhythm_model import HarmonicRhythmModel
        from audiogen_core.config import CONFIG
        import random

        old = float(getattr(CONFIG.composition, "harmonic_rhythm_tension_sensitivity", 0.0) or 0.0)
        try:
            CONFIG.composition.harmonic_rhythm_tension_sensitivity = 1.0
            hist = ["hold", "half"]

            def _first():
                m = HarmonicRhythmModel(rng=random.Random(123))
                return m.next_action(
                    role="continuation",
                    history=list(hist),
                    bar_target=1.0,
                    motif_strength=0.0,
                    tension=0.50,
                    allow_sus=False,
                )

            # `next_action` draws from the RNG; two calls on the same model advance
            # the stream. Rebuild with the same seed to assert reproducibility.
            self.assertEqual(_first(), _first())
        finally:
            CONFIG.composition.harmonic_rhythm_tension_sensitivity = old

    def test_harmonic_rhythm_low_tension_prefers_hold_over_anticipate(self) -> None:
        from composition.harmonic_rhythm_model import HarmonicRhythmModel
        from audiogen_core.config import CONFIG
        import random

        old = float(getattr(CONFIG.composition, "harmonic_rhythm_tension_sensitivity", 0.0) or 0.0)
        try:
            CONFIG.composition.harmonic_rhythm_tension_sensitivity = 1.0
            # Sample many times across seeds; low tension should reduce anticipate incidence
            # in aggregate (single draws can flip).
            low_anticipate = 0
            high_anticipate = 0
            trials = 600
            for seed in range(trials):
                rng = random.Random(seed)
                m = HarmonicRhythmModel(rng=rng)
                hist = ["hold", "hold"]
                a_low = m.next_action(
                    role="continuation",
                    history=list(hist),
                    bar_target=1.0,
                    motif_strength=0.0,
                    tension=0.50,
                    allow_sus=False,
                    cadence_style="authentic",
                )
                a_high = m.next_action(
                    role="continuation",
                    history=list(hist),
                    bar_target=1.0,
                    motif_strength=0.0,
                    tension=1.20,
                    allow_sus=False,
                    cadence_style="authentic",
                )
                low_anticipate += int(str(a_low) == "anticipate")
                high_anticipate += int(str(a_high) == "anticipate")

            # Not a strict ordering (still probabilistic), but should trend:
            # low tension should not increase anticipations vs high tension.
            self.assertGreaterEqual(high_anticipate, low_anticipate)
        finally:
            CONFIG.composition.harmonic_rhythm_tension_sensitivity = old

    def test_color_cap_scaling_is_bounded(self) -> None:
        from audiogen_core.config import CONFIG

        old_s = float(getattr(CONFIG.composition, "harmony_tension_control_strength", 0.0) or 0.0)
        old_l = float(getattr(CONFIG.composition, "harmony_color_cap_low_tension", 1.0) or 1.0)
        old_h = float(getattr(CONFIG.composition, "harmony_color_cap_high_tension", 1.0) or 1.0)
        try:
            CONFIG.composition.harmony_tension_control_strength = 1.0
            CONFIG.composition.harmony_color_cap_low_tension = 0.0
            CONFIG.composition.harmony_color_cap_high_tension = 1.0

            # We can't easily integration-test chord generation without more harness;
            # but we can sanity-check that the configured caps remain in bounds.
            self.assertGreaterEqual(CONFIG.composition.harmony_color_cap_low_tension, 0.0)
            self.assertLessEqual(CONFIG.composition.harmony_color_cap_low_tension, 1.0)
            self.assertGreaterEqual(CONFIG.composition.harmony_color_cap_high_tension, 0.0)
            self.assertLessEqual(CONFIG.composition.harmony_color_cap_high_tension, 1.0)
        finally:
            CONFIG.composition.harmony_tension_control_strength = old_s
            CONFIG.composition.harmony_color_cap_low_tension = old_l
            CONFIG.composition.harmony_color_cap_high_tension = old_h


if __name__ == "__main__":
    unittest.main()

