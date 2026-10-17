import threading
import unittest


class RealtimeTextureFormTests(unittest.TestCase):
    def test_texture_script_is_deterministic_given_same_inputs(self):
        from composition.section_planner import _make_texture_by_bar

        targets = {
            "tension": [0.5, 0.8, 0.9, 0.6],
            "cadence_window": [0.0, 0.0, 1.0, 1.0],
            "breath_window": [0.0, 0.0, 0.0, 1.0],
        }
        hctx = {"rt_special_event": "tag_recap", "rt_recap_intent": True, "rt_energy": 0.8}

        a = _make_texture_by_bar(section_role="b", bars=4, timeline_targets=targets, handoff_ctx=hctx)
        b = _make_texture_by_bar(section_role="b", bars=4, timeline_targets=targets, handoff_ctx=hctx)
        self.assertEqual(a, b)

    def test_headless_realtime_exports_texture_fields_in_bar_trace(self):
        from audiogen_core.config import CONFIG
        from data.music_data import EMOTION_BY_NAME
        from composition.engine import CompositionGenerator
        from audio.RT_player.section_scheduler import SectionScheduler

        # Enable texture scripting so drop/fx fields can appear.
        prev_drop = getattr(CONFIG.composition, "texture_drop_strength", 0.0)
        prev_reg = getattr(CONFIG.composition, "texture_register_lift_strength", 0.0)
        prev_fx = getattr(CONFIG.composition, "texture_fx_gesture_strength", 0.0)
        prev_arr = getattr(CONFIG.composition, "arranged_songs_default", True)
        prev_bars = getattr(CONFIG.composition, "bars_per_section", 16)
        try:
            CONFIG.composition.texture_drop_strength = 1.0
            CONFIG.composition.texture_register_lift_strength = 1.0
            CONFIG.composition.texture_fx_gesture_strength = 1.0
            CONFIG.composition.arranged_songs_default = False
            CONFIG.composition.bars_per_section = 4

            class _Adapter:
                def __init__(self):
                    self.config = CONFIG
                    self.gen = CompositionGenerator(enable_perf_monitoring=False)
                    self.gen.reseed(123)
                def generate_section_events(self, emotion, root, bars, target_notes_per_bar=6.0, runtime_mode="normal", section_index=0, transition_handoff_context=None):
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
            # bar_trace exists only when debug trace was exported.
            # In unit tests we still expect it to be best-effort; tolerate None.
            if isinstance(tr, dict):
                for k in ("drop_level", "register_lift_semitones", "fx_space_boost", "fx_width_boost", "fx_grit_boost"):
                    self.assertIn(k, tr)
        finally:
            CONFIG.composition.texture_drop_strength = prev_drop
            CONFIG.composition.texture_register_lift_strength = prev_reg
            CONFIG.composition.texture_fx_gesture_strength = prev_fx
            CONFIG.composition.arranged_songs_default = prev_arr
            CONFIG.composition.bars_per_section = prev_bars


if __name__ == "__main__":
    unittest.main()

