import random
import unittest


class CadenceControlBiasTests(unittest.TestCase):
    def test_cadence_strength_reduces_volatile_hr_actions(self) -> None:
        from composition.harmonic_rhythm_model import HarmonicRhythmModel

        low_volatile = 0
        high_volatile = 0
        trials = 600
        for seed in range(trials):
            model_low = HarmonicRhythmModel(rng=random.Random(seed))
            model_high = HarmonicRhythmModel(rng=random.Random(seed))

            a_low = model_low.next_action(
                role="continuation",
                history=["half", "anticipate"],
                temperature=1.0,
                bar_target=1.15,
                motif_strength=0.0,
                tension=1.0,
                cadence_strength=0.0,
                harmony_function_target="PD",
                allow_sus=True,
                cadence_style="avoid",
            )
            a_high = model_high.next_action(
                role="continuation",
                history=["half", "anticipate"],
                temperature=1.0,
                bar_target=1.15,
                motif_strength=0.0,
                tension=1.0,
                cadence_strength=1.2,
                harmony_function_target="T",
                allow_sus=True,
                cadence_style="authentic",
            )
            low_volatile += int(str(a_low) in {"anticipate", "sus"})
            high_volatile += int(str(a_high) in {"anticipate", "sus"})

        self.assertGreater(low_volatile, high_volatile)


if __name__ == "__main__":
    unittest.main()

