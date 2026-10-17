import unittest

from app_controller import AppController


class _FakeEmotion:
    def __init__(self, name):
        self.name = name


class _FakePlayer:
    def __init__(self):
        self.root = 60
        self.emotion = _FakeEmotion("neutral")
        self.loaded = []
        self.fx_transitions = []

    def load_emotion(self, idx, root):
        self.loaded.append((int(idx), int(root)))
        self.root = int(root)

    def queue_fx_preset_transition(self, **kwargs):
        self.fx_transitions.append(dict(kwargs or {}))


class _FakeComp:
    def __init__(self):
        self.default_tempo = 70.0
        self.arranged_song_mode = "default"
        self.arranged_songs_default = False
        self.instrument_source = "sampler"
        self.swing_enabled = False
        self.swing_amount = 0.0
        self.melody_swing_enabled = False
        self.melody_swing_amount = 0.08


class _FakeConfig:
    def __init__(self):
        self.composition = _FakeComp()
        self.active_style_profile = "default"
        self.active_post_process_preset = "calm"
        self.style_profiles = {"default": {}}
        self.post_process_presets = {"calm": {}, "dreamy": {}, "gritty": {}}
        self.rebuild_calls = 0
        self._style_set = []
        self._fx_set = []

    def set_style_profile(self, name):
        if name not in self.style_profiles:
            raise ValueError(name)
        self.active_style_profile = name
        self._style_set.append(name)

    def set_post_process_preset(self, name):
        if name not in self.post_process_presets:
            raise ValueError(name)
        self.active_post_process_preset = name
        self._fx_set.append(name)

    def rebuild_samplers(self):
        self.rebuild_calls += 1


class _FakeContainer:
    def __init__(self):
        self.apply_calls = 0

    def apply_audio_config(self, _cfg):
        self.apply_calls += 1


class AppControllerSceneTests(unittest.TestCase):
    def _build_controller(self):
        emotions = [_FakeEmotion("neutral"), _FakeEmotion("joy"), _FakeEmotion("sadness")]
        by_name = {e.name.lower(): i for i, e in enumerate(emotions)}
        return AppController(
            player=_FakePlayer(),
            config=_FakeConfig(),
            emotions=emotions,
            container=_FakeContainer(),
            root_default=60,
            emotion_index_by_name=lambda n: by_name.get(str(n).strip().lower(), 0),
        )

    def test_apply_scene_applies_all_controls(self):
        c = self._build_controller()

        out = c.apply_scene(
            {
                "tempo": 96,
                "emotion": "joy",
                "arrangement_type": "ambient",
                "instrument_source": "piano",
                "style": "jazz",
                "fx_preset": "dreamy",
                "swing": True,
            }
        )

        self.assertTrue(bool(out.get("ok")))
        self.assertEqual(c.config.composition.default_tempo, 96.0)
        self.assertEqual(c.config.composition.arranged_song_mode, "ambient")
        self.assertEqual(c.config.composition.instrument_source, "piano")
        self.assertTrue(c.config.composition.arranged_songs_default)
        self.assertTrue(c.config.composition.swing_enabled)
        self.assertTrue(c.config.composition.melody_swing_enabled)
        self.assertEqual(c.config.active_style_profile, "default")
        self.assertEqual(c.config.active_post_process_preset, "dreamy")
        self.assertEqual(c.player.loaded[-1][0], 1)
        self.assertEqual(c.container.apply_calls, 1)
        self.assertEqual(c.config.rebuild_calls, 1)
        self.assertEqual(str(out.get("applied", {}).get("swing", "")), "medium")
        self.assertTrue(bool(c.player.fx_transitions))

    def test_apply_scene_style_macro_works_without_style_profile(self):
        c = self._build_controller()
        # No "pop" profile in fake config; should still apply via architecture macro.
        out = c.apply_scene({"style": "pop"})

        self.assertTrue(bool(out.get("ok")))
        self.assertEqual(str(out.get("applied", {}).get("style", "")), "pop")
        self.assertGreaterEqual(float(c.config.composition.melody_amount_scale), 0.9)
        self.assertFalse(bool(c.config.composition.swing_enabled))

    def test_apply_scene_swing_off_zeroes_amounts(self):
        c = self._build_controller()
        c.config.composition.swing_amount = 0.12
        c.config.composition.melody_swing_amount = 0.16

        out = c.apply_scene({"swing": False})

        self.assertTrue(bool(out.get("ok")))
        self.assertFalse(c.config.composition.swing_enabled)
        self.assertFalse(c.config.composition.melody_swing_enabled)
        self.assertEqual(c.config.composition.swing_amount, 0.0)
        self.assertEqual(c.config.composition.melody_swing_amount, 0.0)
        self.assertEqual(str(out.get("applied", {}).get("swing", "")), "off")

    def test_apply_scene_swing_levels_set_expected_amounts(self):
        c = self._build_controller()
        out = c.apply_scene({"swing": "heavy"})

        self.assertTrue(bool(out.get("ok")))
        self.assertTrue(bool(c.config.composition.swing_enabled))
        self.assertTrue(bool(c.config.composition.melody_swing_enabled))
        self.assertGreaterEqual(float(c.config.composition.swing_amount), 0.12)
        self.assertGreaterEqual(float(c.config.composition.melody_swing_amount), 0.14)
        self.assertEqual(str(out.get("applied", {}).get("swing", "")), "heavy")

    def test_get_scene_snapshot_returns_expected_shape(self):
        c = self._build_controller()
        snap = c.get_scene_snapshot()
        self.assertIn("tempo", snap)
        self.assertIn("emotion", snap)
        self.assertIn("arrangement_type", snap)
        self.assertIn("instrument_source", snap)
        self.assertIn("style", snap)
        self.assertIn("fx_preset", snap)
        self.assertIn("swing", snap)
        self.assertIn(str(snap.get("swing", "")), {"off", "light", "medium", "heavy"})

    def test_get_ui_schema_contains_control_keys(self):
        c = self._build_controller()
        schema = c.get_ui_schema()
        self.assertIn("tempo", schema)
        self.assertIn("emotion", schema)
        self.assertIn("arrangement_type", schema)
        self.assertIn("instrument_source", schema)
        self.assertIn("style", schema)
        self.assertIn("fx_preset", schema)
        self.assertIn("swing", schema)
        self.assertIn("jazz", schema["style"]["options"])
        self.assertIn("pop", schema["style"]["options"])
        self.assertEqual(schema["swing"]["type"], "choice")
        self.assertIn("heavy", schema["swing"]["options"])

    def test_scene_contract_exposes_versioned_mapping(self):
        c = self._build_controller()
        contract = c.get_scene_contract()
        self.assertEqual(int(contract.get("version", 0)), 1)
        self.assertEqual(str(contract.get("scene_semantics", "")), "partial_update")
        self.assertIn("controls", contract)
        self.assertIn("instrument_source", contract["controls"])

    def test_gui_adapter_maps_setters_to_scene_updates(self):
        from gui_scene_adapter import GuiSceneAdapter

        c = self._build_controller()
        gui = GuiSceneAdapter(c)
        out = gui.set_tempo(88)
        self.assertTrue(bool(out.get("ok")))
        self.assertEqual(float(c.config.composition.default_tempo), 88.0)
        out2 = gui.set_swing("light")
        self.assertTrue(bool(out2.get("ok")))
        self.assertEqual(str(c.get_scene_snapshot().get("swing", "")), "light")

    def test_execute_command_health_unknown_log_path_does_not_crash(self):
        c = self._build_controller()
        keep_running = c.execute_command("health /tmp/does-not-exist-runtime-log.txt")
        self.assertTrue(bool(keep_running))


if __name__ == "__main__":
    unittest.main()
