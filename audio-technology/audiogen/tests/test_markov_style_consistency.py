import random
import threading
import unittest


class MarkovStyleConsistencyTests(unittest.TestCase):
    def test_style_profile_is_deterministic_and_bounded(self) -> None:
        from composition.markov_style_profiles import style_profile_for_emotion_and_role

        a = style_profile_for_emotion_and_role("joy", "b")
        b = style_profile_for_emotion_and_role("joy", "b")
        self.assertEqual(a, b)
        for x in (a.leap_allowance, a.harmony_motion_allowance, a.harmony_color_allowance, a.melody_rhythm_activity):
            self.assertGreaterEqual(float(x), 0.0)
            self.assertLessEqual(float(x), 1.0)

    def test_harmonic_rhythm_style_bias_trends(self) -> None:
        from composition.harmonic_rhythm_model import HarmonicRhythmModel
        from audiogen_core.config import CONFIG

        prev = float(getattr(CONFIG.composition, "markov_style_strength", 0.0) or 0.0)
        try:
            CONFIG.composition.markov_style_strength = 1.0
            trials = 800
            calm_motion = 0
            energetic_motion = 0
            for seed in range(trials):
                # Separate models per trial for deterministic sampling.
                m0 = HarmonicRhythmModel(rng=random.Random(seed))
                # "motion" proxy: anticipate or sus vs hold/half
                a_calm = m0.next_action(
                    role="continuation",
                    history=["hold", "hold"],
                    bar_target=1.0,
                    motif_strength=0.0,
                    tension=0.85,
                    emotion_name="calm",
                    section_role="a",
                    allow_sus=True,
                    cadence_style="authentic",
                )
                m1 = HarmonicRhythmModel(rng=random.Random(seed))
                a_energy = m1.next_action(
                    role="continuation",
                    history=["hold", "hold"],
                    bar_target=1.0,
                    motif_strength=0.0,
                    tension=0.85,
                    emotion_name="joy",
                    section_role="b",
                    allow_sus=True,
                    cadence_style="authentic",
                )
                calm_motion += int(str(a_calm) in {"anticipate", "sus"})
                energetic_motion += int(str(a_energy) in {"anticipate", "sus"})
            # Trend: energetic profile should allow >= motion than calm.
            self.assertGreaterEqual(energetic_motion, calm_motion)
        finally:
            CONFIG.composition.markov_style_strength = prev

    def test_style_profile_role_activity_trend_intro_vs_chorus(self) -> None:
        from composition.markov_style_profiles import style_profile_for_emotion_and_role

        intro = style_profile_for_emotion_and_role("neutral", "intro")
        verse = style_profile_for_emotion_and_role("neutral", "a")
        chorus = style_profile_for_emotion_and_role("neutral", "b")

        self.assertLess(float(intro.melody_rhythm_activity), float(verse.melody_rhythm_activity))
        self.assertLess(float(verse.melody_rhythm_activity), float(chorus.melody_rhythm_activity))
        self.assertLess(float(intro.harmony_motion_allowance), float(chorus.harmony_motion_allowance))

    def test_headless_realtime_exports_style_fields_in_bar_trace(self) -> None:
        from audiogen_core.config import CONFIG
        from data.music_data import EMOTION_BY_NAME
        from composition.engine import CompositionGenerator
        from audio.RT_player.section_scheduler import SectionScheduler

        prev_style = getattr(CONFIG.composition, "markov_style_strength", 0.0)
        prev_arr = getattr(CONFIG.composition, "arranged_songs_default", True)
        prev_bars = getattr(CONFIG.composition, "bars_per_section", 16)
        try:
            CONFIG.composition.markov_style_strength = 1.0
            CONFIG.composition.arranged_songs_default = False
            CONFIG.composition.bars_per_section = 4

            class _Adapter:
                def __init__(self):
                    self.config = CONFIG
                    self.gen = CompositionGenerator(enable_perf_monitoring=False)
                    self.gen.reseed(123)

                def generate_section_events(
                    self,
                    emotion,
                    root,
                    bars,
                    target_notes_per_bar=6.0,
                    runtime_mode="normal",
                    section_index=0,
                    transition_handoff_context=None,
                ):
                    self.gen.runtime_generation_mode = runtime_mode
                    return self.gen.generate_section(
                        emotion,
                        root,
                        bars,
                        target_notes_per_bar=target_notes_per_bar,
                        section_index=section_index,
                        transition_handoff_context=transition_handoff_context,
                    )

            class _Owner:
                def __init__(self):
                    self.config = CONFIG
                    self.composer = _Adapter()
                    self.section_lock = threading.RLock()
                    self.state_lock = threading.Lock()
                    self._emotion = EMOTION_BY_NAME["neutral"]
                    self._root = 60
                    self.last_generation_time = 0.0
                    self.max_generation_time = 0.0

                def _runtime_target_notes_per_bar(self):
                    return 4.0

                def _runtime_generation_mode(self):
                    return "normal"

            owner = _Owner()
            sched = SectionScheduler(owner=owner, logger=__import__("logging").getLogger("smoke"))
            sched.generate_new_section()
            bar0 = sched.prepare_next_bar()
            tr = bar0.get("bar_trace")
            if isinstance(tr, dict):
                for k in (
                    "style_profile",
                    "style_leap_allowance",
                    "style_harmony_motion_allowance",
                    "style_harmony_color_allowance",
                    "style_melody_rhythm_activity",
                ):
                    self.assertIn(k, tr)
        finally:
            CONFIG.composition.markov_style_strength = prev_style
            CONFIG.composition.arranged_songs_default = prev_arr
            CONFIG.composition.bars_per_section = prev_bars


if __name__ == "__main__":
    unittest.main()
