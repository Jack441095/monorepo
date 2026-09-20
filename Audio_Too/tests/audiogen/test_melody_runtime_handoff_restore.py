import unittest
from types import SimpleNamespace


class _ExplodingMelodyGen:
    def __init__(self):
        self._transition_handoff_context = {"existing": True}

    def generate_with_phrases(self, **_kwargs):
        raise RuntimeError("boom")


class MelodyRuntimeHandoffRestoreTests(unittest.TestCase):
    def test_transition_handoff_context_restored_after_generation_failure(self):
        from composition.melody_runtime import MelodyRuntime

        owner = SimpleNamespace(
            melody_gen=_ExplodingMelodyGen(),
            _emotion_transition_handoff_ctx={"previous_lead_pc": 4},
        )
        runtime = MelodyRuntime(owner)
        emotion = SimpleNamespace(name="joy", scale_intervals=[0, 2, 4, 5, 7, 9, 11])

        with self.assertRaises(RuntimeError):
            runtime.generate_markov_melody(
                emotion=emotion,
                chords=["C"],
                roots=[60],
                bars=1,
                temperature=1.0,
                phrase_contours=["asc"],
                notes_per_phrase=[2],
                temp_mult=1.0,
            )

        self.assertEqual(owner.melody_gen._transition_handoff_context, {"existing": True})


if __name__ == "__main__":
    unittest.main()
