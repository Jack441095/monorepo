import random
import unittest
from unittest.mock import MagicMock

from composition.harmonic_rhythm_model import HarmonicRhythmModel
from composition.harmony_manager import CompositionHarmonyManager
from data.music_data import EMOTION_BY_NAME


class TestSharedHrSchedule(unittest.TestCase):
    def test_schedule_is_deterministic_for_same_inputs(self) -> None:
        owner = MagicMock()
        owner.chord_utils.phrase_role = MagicMock(return_value="continuation")
        owner._simplify_chord_for_markov = MagicMock(return_value="maj")
        owner.harmonic_rhythm_model = HarmonicRhythmModel(rng=random.Random(0))
        setattr(owner, "_section_cadence_strength_profile", [])
        setattr(owner, "_section_harmony_function_target_profile", [])
        setattr(owner, "_section_harmonic_motion_profile", None)
        setattr(owner, "_song_blueprint_cadence_style", "")

        emo = EMOTION_BY_NAME.get("neutral")
        self.assertIsNotNone(emo)
        hm = CompositionHarmonyManager(owner)
        chords = ["C", "F", "G", "C"]
        roots = [60, 65, 67, 60]
        kwargs = dict(
            chords=chords,
            roots=roots,
            bars=4,
            beats_per_bar=4.0,
            emotion=emo,
            section_role="a",
            chord_rhythm_mult=1.0,
            chord_motion_mult=1.0,
            chord_rhythm_targets=[1.0] * 4,
            motif_strength_targets=[0.0] * 4,
            tension_targets=[0.85] * 4,
            section_index=2,
        )
        setattr(hm, "_hr_action_hist", [])
        a1 = hm.schedule_section_harmonic_rhythm_actions(**kwargs)
        setattr(hm, "_hr_action_hist", [])
        a2 = hm.schedule_section_harmonic_rhythm_actions(**kwargs)
        self.assertEqual(len(a1), 4)
        self.assertEqual(a1, a2)
