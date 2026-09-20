import unittest
from collections import OrderedDict
import json
import threading
from pathlib import Path
from unittest.mock import patch

import numpy as np

from audio.engine import EVENT_BUS
from audio.engine.reverb import RoomReverb
from audio.engine.master_bus import MasterBus, MasterBusSettings, lookahead_limiter_mono_gain
from audio.engine.mixer import AudioMixer
from audio.RT_player.renderer import AudioRenderer
from audio.RT_player.drone_manager import DroneManager
from audio.RT_player.render_pipeline import RenderPipeline
from audio.audio_container import AudioContainer
from sampler.sampler import Sampler, VelocityLayer
from sampler.engine import SamplerEngine
from sampler.utils import build_looping_audio
from composition.engine import CompositionGenerator
from audiogen_core.config import CONFIG, ConfigurationManager
from audiogen_core.mixer_config import default_mixer_strips
from data.conversation_presets import USER_PRESETS_PATH
from data.music_data import EMOTIONS
from sampler.adsr import ADSREnvelope

_DEFAULT_MIXER_STRIPS = default_mixer_strips()


class FakeSynthesisEngine:
    def __init__(self):
        self.monophonic_calls = []
        self.chord_calls = []

    def render_monophonic_channel(self, channel, events, bar_samples, tempo, out=None, **kwargs):
        self.monophonic_calls.append((channel, list(events), bar_samples, tempo))
        value = 0.1 * (channel + 1)
        bs = int(max(0, bar_samples))
        if out is not None:
            out.fill(float(value))
            return out
        return np.full((bs, 2), value, dtype=np.float32)

    def render_chord(self, note_notes, velocity, duration_sec, channel=1):
        self.chord_calls.append((list(note_notes), velocity, duration_sec, channel))
        samples = max(1, int(duration_sec * 100))
        return np.full((samples, 2), 0.25, dtype=np.float32)


class FakePrefetchSynthesisEngine(FakeSynthesisEngine):
    def __init__(self):
        super().__init__()
        self.prefetch_calls = []

    def prefetch_events(self, events, *, tempo, default_velocity=80):
        self.prefetch_calls.append((list(events), float(tempo), int(default_velocity)))


class FakeMixer:
    def __init__(self):
        self.last_channel_audio = None
        self.last_reverb = None

    def mix_audio(self, channel_audio, reverb_processor=None):
        self.last_channel_audio = {
            ch: audio.copy() for ch, audio in channel_audio.items()
        }
        self.last_reverb = reverb_processor
        max_len = max(len(audio) for audio in channel_audio.values())
        mixed = np.zeros((max_len, 2), dtype=np.float32)
        for audio in channel_audio.values():
            mixed[:len(audio)] += audio
        z = np.zeros((max_len, 2), dtype=np.float32)
        return mixed, z.copy(), z.copy(), z.copy()

    def set_master_volume(self, volume):
        self.master_volume = volume

    def set_master_reverb(self, wet):
        self.master_reverb_wet = wet

    def set_master_distortion(self, enabled, drive, mix):
        self.master_distortion = (enabled, drive, mix)

class DummySampler:
    def __init__(self):
        self.calls = 0

    def render_note(self, midi, velocity, duration_sec):
        self.calls += 1
        samples = max(1, int(duration_sec * 100))
        level = midi / 127.0
        return np.full((samples, 2), level, dtype=np.float32)


class MockSamplerEngine(SamplerEngine):
    def __init__(self):
        self._sample_rate = 100
        self._chord_cache = OrderedDict()
        self._chord_cache_maxsize = 16
        self._fake_sampler = DummySampler()
        self.samplers = {}
        self._mono_renderers = {}

    def _get_sampler(self, name):
        return self._fake_sampler

    def _channel_to_sampler(self, channel: int) -> str:
        return 'chords'


class SelectivePreloadSamplerEngine(SamplerEngine):
    def __init__(self):
        self.loaded = []
        self.config = type(
            "Cfg",
            (),
            {
                "samplers": [
                    type("SamplerCfg", (), {"name": "bass"})(),
                    type("SamplerCfg", (), {"name": "chords"})(),
                    type("SamplerCfg", (), {"name": "melody"})(),
                    type("SamplerCfg", (), {"name": "drone"})(),
                ]
            },
        )()
        self.samplers = {}
        self._mono_renderers = {}
        self._load_lock = None
        self._sample_rate = 100

    def _get_sampler(self, name: str):
        self.loaded.append(name)
        self.samplers[name] = DummySampler()
        return self.samplers[name]


class AudioRendererTests(unittest.TestCase):
    def test_render_bar_routes_monophonic_and_chord_events(self):
        synthesis_engine = FakeSynthesisEngine()
        mixer = FakeMixer()
        renderer = AudioRenderer(
            synthesis_engine=synthesis_engine,
            mixer=mixer,
            sample_rate=100,
        )

        events = [
            (2, 64, 90, 0.0, 1.0, [64]),
            (0, 36, 70, 0.0, 4.0, [36]),
            (1, 0, 85, 0.0, 2.0, [60, 64, 67]),
        ]
        audio = renderer.render_bar(events, tempo=120.0, bar_samples=400)

        self.assertEqual(audio.shape, (400, 2))
        self.assertEqual(sorted(call[0] for call in synthesis_engine.monophonic_calls), [0, 2])
        self.assertEqual(len(synthesis_engine.chord_calls), 1)
        self.assertEqual(synthesis_engine.chord_calls[0][0], [60, 64, 67])
        self.assertGreater(np.max(np.abs(audio)), 0.0)

    def test_render_bar_does_not_sync_prefetch_chords_by_default(self):
        synthesis_engine = FakePrefetchSynthesisEngine()
        mixer = FakeMixer()
        renderer = AudioRenderer(
            synthesis_engine=synthesis_engine,
            mixer=mixer,
            sample_rate=100,
        )

        events = [(1, 0, 85, 0.0, 2.0, [60, 64, 67])]
        audio = renderer.render_bar(events, tempo=120.0, bar_samples=400)

        self.assertEqual(audio.shape, (400, 2))
        self.assertEqual(len(synthesis_engine.chord_calls), 1)
        self.assertEqual(synthesis_engine.prefetch_calls, [])

    def test_render_bar_routes_counter_melody_on_channel_five(self):
        synthesis_engine = FakeSynthesisEngine()
        mixer = FakeMixer()
        renderer = AudioRenderer(
            synthesis_engine=synthesis_engine,
            mixer=mixer,
            sample_rate=100,
        )
        events = [
            (5, 64, 80, 0.0, 1.0, [64]),
        ]
        audio = renderer.render_bar(events, tempo=120.0, bar_samples=200)
        mono_chs = sorted(c[0] for c in synthesis_engine.monophonic_calls)
        self.assertIn(5, mono_chs)
        self.assertEqual(audio.shape, (200, 2))
        self.assertGreater(float(np.max(np.abs(audio))), 0.0)

    def test_sampler_engine_can_preload_selected_samplers(self):
        engine = SelectivePreloadSamplerEngine()

        engine.preload_samplers(["drone", "melody"])

        self.assertEqual(set(engine.loaded), {"drone", "melody"})

    def test_render_bar_ignores_malformed_polyphonic_events(self):
        synthesis_engine = FakeSynthesisEngine()
        mixer = FakeMixer()
        renderer = AudioRenderer(
            synthesis_engine=synthesis_engine,
            mixer=mixer,
            sample_rate=100,
        )

        events = [
            (1, 0, 90, 0.0, 1.0, ["bad", "data"]),
            (1, 0, 90, 0.0, 1.0, [15, 200]),
        ]
        audio = renderer.render_bar(events, tempo=120.0, bar_samples=100)

        self.assertEqual(len(synthesis_engine.chord_calls), 0)
        self.assertEqual(audio.shape, (100, 2))
        self.assertTrue(np.allclose(audio, 0.0))

    def test_render_bar_stem_sink_none_by_default_leaves_mix_unchanged(self):
        events = [
            (2, 64, 90, 0.0, 1.0, [64]),
            (0, 36, 70, 0.0, 4.0, [36]),
            (1, 0, 85, 0.0, 2.0, [60, 64, 67]),
        ]
        renderer_a = AudioRenderer(
            synthesis_engine=FakeSynthesisEngine(), mixer=FakeMixer(), sample_rate=100
        )
        renderer_b = AudioRenderer(
            synthesis_engine=FakeSynthesisEngine(), mixer=FakeMixer(), sample_rate=100
        )

        without_sink = renderer_a.render_bar(list(events), tempo=120.0, bar_samples=400)
        with_sink = renderer_b.render_bar(
            list(events), tempo=120.0, bar_samples=400, stem_sink={}
        )

        self.assertTrue(np.array_equal(without_sink, with_sink))

    def test_render_bar_stem_sink_captures_per_channel_buffers(self):
        synthesis_engine = FakeSynthesisEngine()
        mixer = FakeMixer()
        renderer = AudioRenderer(
            synthesis_engine=synthesis_engine, mixer=mixer, sample_rate=100
        )
        events = [
            (2, 64, 90, 0.0, 1.0, [64]),
            (0, 36, 70, 0.0, 4.0, [36]),
        ]
        sink: dict = {}

        renderer.render_bar(events, tempo=120.0, bar_samples=400, stem_sink=sink)

        self.assertIn(0, sink)
        self.assertIn(2, sink)
        self.assertEqual(sink[0][0].shape, (400, 2))
        self.assertGreater(float(np.max(np.abs(sink[0][0]))), 0.0)
        self.assertGreater(float(np.max(np.abs(sink[2][0]))), 0.0)

    def test_render_bar_stem_sink_entries_are_copies_not_reused_buffers(self):
        synthesis_engine = FakeSynthesisEngine()
        mixer = FakeMixer()
        renderer = AudioRenderer(
            synthesis_engine=synthesis_engine, mixer=mixer, sample_rate=100
        )
        sink: dict = {}

        renderer.render_bar(
            [(0, 36, 70, 0.0, 4.0, [36])], tempo=120.0, bar_samples=50, stem_sink=sink
        )
        first_bar_channel_zero = sink[0][0].copy()

        # A second bar with no channel-0 events would zero/reuse the cached
        # buffer in place if stem_sink held a reference instead of a copy.
        renderer.render_bar([], tempo=120.0, bar_samples=50, stem_sink=sink)

        self.assertTrue(np.array_equal(sink[0][0], first_bar_channel_zero))
        self.assertEqual(len(sink[0]), 2)
        self.assertTrue(np.allclose(sink[0][1], 0.0))


class SamplerEngineTests(unittest.TestCase):
    def test_sampler_engine_allows_other_sampler_loads_while_one_is_in_progress(self):
        bass_started = threading.Event()
        allow_bass_finish = threading.Event()

        class FakeSamplerForConcurrency:
            def __init__(self, config, sample_rate):
                self.config = config
                self.sample_rate = sample_rate
                self.layers = []
                self._raw_cache = []
                if config.name == "bass":
                    bass_started.set()
                    allow_bass_finish.wait(timeout=2.0)

        class FakeMonoRenderer:
            def __init__(self, sampler, sample_rate):
                self.sampler = sampler
                self.sample_rate = sample_rate

        config = type(
            "Cfg",
            (),
            {
                "audio": type("Audio", (), {"sample_rate": 100})(),
                "samplers": [
                    type("SamplerCfg", (), {"name": "bass"})(),
                    type("SamplerCfg", (), {"name": "chords"})(),
                ],
            },
        )()
        engine = SamplerEngine(config)
        loaded = {}

        def load_bass():
            loaded["bass"] = engine._get_sampler("bass")

        with patch("sampler.engine.Sampler", FakeSamplerForConcurrency), patch(
            "sampler.engine.MonophonicRenderer", FakeMonoRenderer
        ):
            bass_thread = threading.Thread(target=load_bass)
            bass_thread.start()
            self.assertTrue(bass_started.wait(timeout=1.0))

            chords_sampler = engine._get_sampler("chords")

            allow_bass_finish.set()
            bass_thread.join(timeout=1.0)

        self.assertEqual(chords_sampler.config.name, "chords")
        self.assertIn("bass", loaded)

    def test_render_chord_uses_cache_for_repeat_call(self):
        engine = MockSamplerEngine()

        first = engine.render_chord([60, 64, 67], velocity=80, duration_sec=1.0, spread=0.3)
        second = engine.render_chord([60, 64, 67], velocity=80, duration_sec=1.0, spread=0.3)

        self.assertEqual(engine._fake_sampler.calls, 3)
        self.assertTrue(np.array_equal(first, second))

    def test_render_chord_spread_changes_left_right_balance(self):
        engine = MockSamplerEngine()

        mono = engine.render_chord([60, 64], velocity=80, duration_sec=1.0, spread=0.0)
        wide = engine.render_chord([60, 64], velocity=80, duration_sec=1.0, spread=1.0)

        self.assertTrue(np.allclose(mono[:, 0], mono[:, 1]))
        self.assertFalse(np.allclose(wide[:, 0], wide[:, 1]))

    def test_render_chord_lazily_bootstraps_helper_for_test_double(self):
        engine = MockSamplerEngine()

        audio = engine.render_chord([60, 64, 67], velocity=80, duration_sec=0.5, spread=0.2)

        self.assertEqual(audio.shape[1], 2)
        self.assertTrue(hasattr(engine, "chord_renderer"))
        self.assertIs(engine.chord_renderer.cache, engine._chord_cache)

    def test_velocity_layer_selection_crossfades_between_adjacent_ranges(self):
        sampler = Sampler.__new__(Sampler)
        sampler.layers = [
            VelocityLayer(file_path="", root_midi=60, lo_vel=0, hi_vel=63),
            VelocityLayer(file_path="", root_midi=60, lo_vel=64, hi_vel=127),
        ]
        sampler.use_velocity_crossfade = True

        lower, upper, w_low, w_up = sampler._select_layers_for_velocity(64)

        self.assertIs(lower, sampler.layers[0])
        self.assertIs(upper, sampler.layers[1])
        self.assertGreater(w_low, 0.0)
        self.assertGreater(w_up, 0.0)
        self.assertAlmostEqual(w_low + w_up, 1.0)

    def test_sampler_render_note_reuses_rendered_note_cache(self):
        sampler = Sampler.__new__(Sampler)
        sampler.sample_rate = 100
        sampler.name = "melody"
        sampler._cache_lock = __import__("threading").Lock()
        sampler._note_cache = OrderedDict()
        sampler.NOTE_CACHE_MAXSIZE = 16
        layer = type(
            "Layer",
            (),
            {
                "file_path": Path("samples/default/melody.wav"),
                "root_midi": 60,
                "envelope_curve": "linear",
                "adsr_attack": 0.01,
                "adsr_decay": 0.1,
                "adsr_sustain": 0.7,
                "adsr_release": 0.2,
            },
        )()
        sampler.layers = [layer]
        sampler.adsr_attack = 0.01
        sampler.adsr_decay = 0.1
        sampler.adsr_sustain = 0.7
        sampler.adsr_release = 0.2
        sampler.envelope_curve = "linear"
        sampler._select_layers_for_velocity = lambda velocity: (layer, layer, 1.0, 0.0)
        call_counter = {"count": 0}

        def render_layer(*args, **kwargs):
            call_counter["count"] += 1
            return np.ones((20, 2), dtype=np.float32)

        sampler._render_layer = render_layer

        original_apply = ADSREnvelope.apply
        ADSREnvelope.apply = lambda self, audio, release_after=None: audio
        try:
            first = sampler.render_note(60, 90, 0.2)
            second = sampler.render_note(60, 90, 0.2)
        finally:
            ADSREnvelope.apply = original_apply

        self.assertEqual(call_counter["count"], 1)
        self.assertTrue(np.array_equal(first, second))

    def test_sampler_render_note_uses_layer_adsr_settings(self):
        sampler = Sampler.__new__(Sampler)
        sampler.sample_rate = 100
        sampler.name = "melody"
        sampler._cache_lock = __import__("threading").Lock()
        sampler._note_cache = OrderedDict()
        sampler.NOTE_CACHE_MAXSIZE = 16
        layer = type(
            "Layer",
            (),
            {
                "file_path": Path("samples/default/melody.wav"),
                "root_midi": 60,
                "envelope_curve": "exponential",
                "adsr_attack": 0.23,
                "adsr_decay": 0.45,
                "adsr_sustain": 0.61,
                "adsr_release": 0.87,
            },
        )()
        sampler.layers = [layer]
        sampler.adsr_attack = 0.01
        sampler.adsr_decay = 0.1
        sampler.adsr_sustain = 0.7
        sampler.adsr_release = 0.2
        sampler.envelope_curve = "linear"
        sampler._select_layers_for_velocity = lambda velocity: (layer, layer, 1.0, 0.0)
        sampler._render_layer = lambda *args, **kwargs: np.ones((20, 2), dtype=np.float32)

        captured = {}
        original_init = ADSREnvelope.__init__
        original_apply = ADSREnvelope.apply

        def capture_init(self, attack, decay, sustain, release, sample_rate=44100, curve="linear"):
            captured["attack"] = attack
            captured["decay"] = decay
            captured["sustain"] = sustain
            captured["release"] = release
            captured["curve"] = curve
            original_init(self, attack, decay, sustain, release, sample_rate=sample_rate, curve=curve)

        ADSREnvelope.__init__ = capture_init
        ADSREnvelope.apply = lambda self, audio, release_after=None: audio
        try:
            sampler.render_note(60, 90, 0.2)
        finally:
            ADSREnvelope.__init__ = original_init
            ADSREnvelope.apply = original_apply

        self.assertEqual(captured["attack"], 0.23)
        self.assertEqual(captured["decay"], 0.45)
        self.assertEqual(captured["sustain"], 0.61)
        self.assertEqual(captured["release"], 0.87)
        self.assertEqual(captured["curve"], "exponential")

    def test_adsr_release_starts_from_current_envelope_level(self):
        env = ADSREnvelope(
            attack=0.2,
            decay=0.2,
            sustain=0.4,
            release=0.2,
            sample_rate=100,
            curve="linear",
        )
        audio = np.ones(40, dtype=np.float32)

        shaped = env.apply(audio, release_after=10)

        self.assertGreater(shaped[9], 0.0)
        self.assertAlmostEqual(shaped[10], shaped[9], places=4)
        self.assertLess(shaped[11], shaped[10])
        self.assertAlmostEqual(shaped[-1], 0.0, places=5)

    def test_chord_renderer_pan_gains_match_equal_power_endpoints(self):
        from sampler.chord_renderer import ChordRenderer

        left = ChordRenderer.pan_gains(-1.0)
        center = ChordRenderer.pan_gains(0.0)
        right = ChordRenderer.pan_gains(1.0)

        self.assertEqual(left, (1.0, 0.0))
        self.assertAlmostEqual(center[0], center[1])
        self.assertEqual(right, (0.0, 1.0))

    def test_chord_renderer_cache_key_canonicalizes_unspread_note_order(self):
        from sampler.chord_renderer import ChordRenderer

        k1 = ChordRenderer.build_cache_key([67, 60, 64], 80, 1.0, 1, ["b", "a"], 0.0, "fast")
        k2 = ChordRenderer.build_cache_key([60, 64, 67], 80, 1.0, 1, ["a", "b"], 0.0, "fast")
        self.assertEqual(k1, k2)

        k3 = ChordRenderer.build_cache_key([67, 60, 64], 80, 1.0, 1, ["a", "b"], 0.8, "fast")
        k4 = ChordRenderer.build_cache_key([60, 64, 67], 80, 1.0, 1, ["a", "b"], 0.8, "fast")
        self.assertNotEqual(k3, k4)

    def test_chord_renderer_cache_separates_transposition_modes(self):
        from sampler.chord_renderer import ChordRenderer

        class _Owner:
            _sample_rate = 100

        class _Sampler:
            def __init__(self):
                self.mode = "fast"
                self.calls = 0
                self.config = type(
                    "Cfg", (), {"random_start_within_loop": False, "shimmer_enabled": False}
                )()

            def _transposition_mode_cache_token(self):
                return self.mode

            def render_note(self, midi, velocity, duration_sec):
                self.calls += 1
                lvl = 0.1 if self.mode == "fast" else 0.2
                n = int(max(1, duration_sec * 100))
                return np.full((n, 2), lvl, dtype=np.float32)

        cr = ChordRenderer(_Owner(), maxsize=16)
        smp = _Sampler()
        a = cr.render(smp, [60, 64, 67], 80, 0.5, channel=1, spread=0.0)
        calls_after_fast = smp.calls
        smp.mode = "hq"
        b = cr.render(smp, [60, 64, 67], 80, 0.5, channel=1, spread=0.0)

        self.assertGreater(smp.calls, calls_after_fast)
        self.assertGreater(float(np.max(np.abs(b - a))), 1e-6)

    def test_chord_renderer_evicts_using_byte_budget(self):
        from sampler.chord_renderer import ChordRenderer

        class _Owner:
            _sample_rate = 100

        cr = ChordRenderer(_Owner(), maxsize=16, max_bytes=64)
        a = np.zeros((8, 2), dtype=np.float32)  # 64 bytes
        b = np.ones((8, 2), dtype=np.float32)   # 64 bytes
        cr.store(("a",), a)
        cr.store(("b",), b)

        self.assertIsNone(cr.get_cached(("a",)))
        self.assertIsNotNone(cr.get_cached(("b",)))

    def test_high_quality_pitch_shift_returns_expected_length(self):
        sampler = Sampler.__new__(Sampler)
        sampler.quality_mode = CONFIG.samplers[0].quality_mode.__class__.HIGH
        audio = np.linspace(-1.0, 1.0, 128, dtype=np.float32)

        shifted = sampler.pitch_shift(audio, 12.0)

        self.assertEqual(len(shifted), 64)

    def test_sampler_transposition_quality_mode_auto_tracks_quality_mode(self):
        sampler = Sampler.__new__(Sampler)
        enum = CONFIG.samplers[0].quality_mode.__class__
        sampler.transposition_quality_mode = "auto"
        sampler.quality_mode = enum.MEDIUM
        self.assertFalse(sampler._use_hq_transposition())
        sampler.quality_mode = enum.HIGH
        self.assertTrue(sampler._use_hq_transposition())

    def test_variable_rate_read_hq_mode_uses_distinct_interpolation_path(self):
        sampler = Sampler.__new__(Sampler)
        sampler.transposition_quality_mode = "fast"
        sampler.quality_mode = CONFIG.samplers[0].quality_mode.__class__.HIGH
        mono = np.sin(np.linspace(0.0, np.pi * 8.0, 240, dtype=np.float32))
        raw = np.column_stack([mono, mono]).astype(np.float32)

        fast = sampler._variable_rate_read(raw, step=1.37, loop_start=0, loop_end=0, max_samples=128)
        sampler.transposition_quality_mode = "hq"
        hq = sampler._variable_rate_read(raw, step=1.37, loop_start=0, loop_end=0, max_samples=128)

        self.assertEqual(fast.shape, hq.shape)
        self.assertGreater(float(np.max(np.abs(hq - fast))), 1e-5)

    def test_build_looping_audio_preserves_target_length_with_crossfade(self):
        source = np.ones((32, 2), dtype=np.float32)
        source[0] = 0.0
        source[-1] = 0.0

        looped = build_looping_audio(
            source,
            target_samples=96,
            loop_start=8,
            loop_end=24,
            crossfade_ms=5.0,
            sample_rate=1000,
            use_zero_crossing=False,
        )

        self.assertEqual(looped.shape, (96, 2))
        self.assertFalse(np.isnan(looped).any())


class MixerStripOptimizationTests(unittest.TestCase):
    def test_default_mixer_strips_expose_channel_filters(self):
        strips = default_mixer_strips()

        for ch_idx, strip in strips.items():
            self.assertTrue(hasattr(strip, "filter_enabled"), ch_idx)
            self.assertTrue(hasattr(strip, "highpass_hz"), ch_idx)
            self.assertTrue(hasattr(strip, "lowpass_hz"), ch_idx)
            self.assertTrue(hasattr(strip, "filter_slope_db_per_oct"), ch_idx)

        self.assertGreater(strips[0].highpass_hz, 0.0)
        self.assertGreater(strips[2].lowpass_hz, strips[2].highpass_hz)

    def test_channel_highpass_filter_reduces_dc_energy(self):
        mixer = AudioMixer(num_channels=1, sample_rate=2000)
        ch = mixer.get_channel(0)
        ch.volume = 1.0
        ch.filter_enabled = True
        ch.highpass_hz = 120.0
        ch.lowpass_hz = 0.0
        ch.filter_slope_db_per_oct = 12.0

        audio = np.ones((4096, 2), dtype=np.float32) * 0.25
        processed = mixer.process_channel(audio.copy(), 0)

        self.assertLess(float(np.mean(np.abs(processed[-512:]))), 0.03)

    def test_channel_lowpass_filter_reduces_high_frequency_energy(self):
        mixer = AudioMixer(num_channels=1, sample_rate=8000)
        ch = mixer.get_channel(0)
        ch.volume = 1.0
        ch.filter_enabled = True
        ch.highpass_hz = 0.0
        ch.lowpass_hz = 500.0
        ch.filter_slope_db_per_oct = 12.0

        t = np.arange(4096, dtype=np.float32) / 8000.0
        wave = np.sin(2.0 * np.pi * 2500.0 * t).astype(np.float32)
        audio = np.column_stack([wave, wave]).astype(np.float32)
        processed = mixer.process_channel(audio.copy(), 0)

        self.assertLess(float(np.sqrt(np.mean(processed[-1024:] * processed[-1024:]))), 0.15)

    def test_set_channel_filters_runtime_api(self):
        mixer = AudioMixer(num_channels=1, sample_rate=2000)

        mixer.set_channel_filters(0, highpass_hz=80.0, lowpass_hz=900.0, slope_db_per_oct=24.0, enabled=True)
        ch = mixer.get_channel(0)

        self.assertTrue(ch.filter_enabled)
        self.assertEqual(ch.highpass_hz, 80.0)
        self.assertEqual(ch.lowpass_hz, 900.0)
        self.assertEqual(ch.filter_slope_db_per_oct, 24.0)

    def test_channel_eq_zero_gains_bypass_dsp(self):
        mixer = AudioMixer(num_channels=1, sample_rate=4000)
        ch = mixer.get_channel(0)
        ch.volume = 1.0
        ch.filter_enabled = False
        ch.eq_enabled = True
        ch.eq_low_gain_db = 0.0
        ch.eq_mid_gain_db = 0.0
        ch.eq_high_gain_db = 0.0

        rng = np.random.default_rng(123)
        audio = rng.normal(0.0, 0.1, size=(256, 2)).astype(np.float32)
        processed = mixer.process_channel(audio.copy(), 0)

        self.assertTrue(np.allclose(processed, audio, atol=1e-7))

    def test_channel_eq_active_band_changes_signal(self):
        mixer = AudioMixer(num_channels=1, sample_rate=8000)
        ch = mixer.get_channel(0)
        ch.volume = 1.0
        ch.filter_enabled = False
        ch.eq_enabled = True
        ch.eq_mid_gain_db = 6.0
        ch.eq_mid_freq = 900.0

        t = np.arange(512, dtype=np.float32) / 8000.0
        wave = np.sin(2.0 * np.pi * 900.0 * t).astype(np.float32) * 0.1
        audio = np.column_stack([wave, wave]).astype(np.float32)
        processed = mixer.process_channel(audio.copy(), 0)

        self.assertEqual(processed.shape, audio.shape)
        self.assertFalse(np.isnan(processed).any())
        self.assertGreater(float(np.max(np.abs(processed - audio))), 1e-4)

    def test_pre_fader_sends_reuse_post_strip_signal_when_volume_nonzero(self):
        mixer = AudioMixer(num_channels=1, sample_rate=1000)
        ch = mixer.get_channel(0)
        ch.volume = 0.5
        ch.sends_pre_fader = True
        ch.reverb_send = 1.0
        ch.eq_enabled = True
        ch.eq_mid_gain_db = 3.0

        # If this gets called, we lost the intended optimization.
        mixer._pre_fader_signal = lambda *_args, **_kwargs: (_ for _ in ()).throw(
            AssertionError("_pre_fader_signal should not be called for nonzero volume")
        )

        audio = np.ones((64, 2), dtype=np.float32) * 0.1
        dry, rev, _dly, _dst = mixer.mix_audio({0: audio})
        expected_pre = (dry / float(ch.volume)).astype(np.float32, copy=False)

        self.assertEqual(dry.shape, (64, 2))
        self.assertTrue(np.allclose(rev[:64], expected_pre, atol=1e-5))

    def test_pre_fader_sends_fall_back_to_pre_signal_when_volume_zero(self):
        mixer = AudioMixer(num_channels=1, sample_rate=1000)
        ch = mixer.get_channel(0)
        ch.volume = 0.0
        ch.sends_pre_fader = True
        ch.reverb_send = 0.8

        marker = np.full((32, 2), 0.25, dtype=np.float32)
        mixer._pre_fader_signal = lambda *_args, **_kwargs: marker.copy()

        _dry, rev, _dly, _dst = mixer.mix_audio({0: np.ones((32, 2), dtype=np.float32)})
        self.assertTrue(np.allclose(rev[:32], marker * 0.8, atol=1e-6))


class MasterBusTests(unittest.TestCase):
    def test_lookahead_limiter_caps_peak(self):
        n = 8000
        x = np.zeros((n, 2), dtype=np.float32)
        x[1000:3000, 0] = 1.5
        x[4000:5000, 1] = -1.4
        y = lookahead_limiter_mono_gain(
            x.copy(), sample_rate=44100, threshold=0.9, lookahead_ms=5.0, release=0.999
        )
        self.assertLessEqual(float(np.max(np.abs(y))), 0.91)

    def test_master_bus_soft_clip_bounded(self):
        bus = MasterBus(1000, MasterBusSettings(limiter_enabled=False, soft_clip_enabled=True))
        bus.distortion.enabled = False
        bus.master_volume = 1.0
        x = np.full((500, 2), 3.0, dtype=np.float32)
        y = bus.process(x)
        self.assertTrue(np.all(np.abs(y) < 1.01))

    def test_fast_path_still_mixes_reverb_and_delay_returns(self):
        """Regression: RT fast_master must not silence send buses (room + delay)."""

        class DummyRev:
            def process(self, audio, wet=1.0, quality_tier="high"):
                return np.ones_like(audio, dtype=np.float32) * 0.2 * float(wet)

        bus = MasterBus(1000, MasterBusSettings(limiter_enabled=False, soft_clip_enabled=False))
        bus.distortion.enabled = False
        bus.reverb_return_wet = 1.0
        bus.delay_enabled = True
        bus.delay_return_level = 0.5
        bus.delay_time_ms = 50.0
        bus.delay_feedback = 0.0
        bus.master_volume = 1.0
        dry = np.zeros((200, 2), dtype=np.float32)
        rs = np.ones((200, 2), dtype=np.float32) * 0.3
        ds = np.ones((200, 2), dtype=np.float32) * 0.1
        y = bus.process(
            dry,
            rs,
            ds,
            None,
            reverb_processor=DummyRev(),
            fast_path=True,
            fx_return_scale=1.0,
            reverb_quality_tier="safe",
        )
        self.assertGreater(float(np.max(np.abs(y))), 0.05)

    def test_realtime_limiter_skips_true_peak_oversampling_by_default(self):
        bus = MasterBus(1000, MasterBusSettings(limiter_enabled=True, soft_clip_enabled=False))
        bus.distortion.enabled = False
        bus.master_volume = 1.0
        bus.master_true_peak_enabled = True
        bus.master_true_peak_oversample_factor = 2
        bus.master_true_peak_realtime_enabled = False

        x = np.zeros((500, 2), dtype=np.float32)
        x[100:300, :] = 1.5

        with patch("audio.engine.master_bus._oversample_stereo", side_effect=AssertionError("oversample")):
            y = bus.process(x, realtime=True)

        self.assertLessEqual(float(np.max(np.abs(y))), 0.91)

    def test_realtime_reused_buffers_grow_after_small_warmup(self):
        class DummyRev:
            def process(self, audio, wet=1.0, quality_tier="high"):
                return np.asarray(audio, dtype=np.float32) * np.float32(wet)

        bus = MasterBus(1000, MasterBusSettings(limiter_enabled=False, soft_clip_enabled=False))
        bus.distortion.enabled = False
        bus.reverb_return_wet = 0.5
        bus.delay_enabled = True
        bus.delay_return_level = 0.1
        bus.delay_time_ms = 20.0
        bus.delay_feedback = 0.0
        small = np.ones((64, 2), dtype=np.float32) * 0.01
        large = np.ones((512, 2), dtype=np.float32) * 0.01

        _ = bus.process(
            small,
            small,
            small,
            None,
            reverb_processor=DummyRev(),
            realtime=True,
            reuse_rt_buffers=True,
            reverb_quality_tier="safe",
        )
        y = bus.process(
            large,
            large,
            large,
            None,
            reverb_processor=DummyRev(),
            realtime=True,
            reuse_rt_buffers=True,
            reverb_quality_tier="safe",
        )

        self.assertEqual(y.shape, (512, 2))
        self.assertGreaterEqual(bus._rt_send_caps.get("reverb", 0), 512)
        self.assertGreaterEqual(bus._rt_send_caps.get("delay", 0), 512)

    def test_master_bus_passes_reverb_quality_tier(self):
        class CaptureRev:
            def __init__(self):
                self.last_tier = None

            def process(self, audio, wet=1.0, quality_tier="high"):
                self.last_tier = str(quality_tier)
                return np.zeros_like(audio, dtype=np.float32)

        bus = MasterBus(1000, MasterBusSettings(limiter_enabled=False, soft_clip_enabled=False))
        bus.reverb_return_wet = 1.0
        rev = CaptureRev()
        dry = np.zeros((64, 2), dtype=np.float32)
        rs = np.ones((64, 2), dtype=np.float32) * 0.1

        _ = bus.process(dry, rs, None, None, reverb_processor=rev, reverb_quality_tier="emergency")
        self.assertEqual(rev.last_tier, "emergency")

    def test_audio_container_exposes_master_bus(self):
        container = AudioContainer.create_from_config(CONFIG)
        self.assertIsNotNone(container.master_bus)
        self.assertEqual(container.master_bus.sample_rate, container.sample_rate)


class RenderPipelineTests(unittest.TestCase):
    def test_extract_polyphonic_notes_filters_non_midi_payload_values(self):
        notes = RenderPipeline.extract_polyphonic_notes(0, [60, 64, "up", 0.25, 200, 18])
        self.assertEqual(notes, [60, 64])

    def test_apply_drone_and_velocity_scales_non_drone_only(self):
        channel_audio = {
            i: np.ones((4, 2), dtype=np.float32)
            for i in range(7)
        }
        drone = np.full((4, 2), 3.0, dtype=np.float32)

        RenderPipeline.apply_drone_and_velocity(channel_audio, drone, 4, 0.5)

        self.assertTrue(np.allclose(channel_audio[0], 0.5))
        self.assertTrue(np.allclose(channel_audio[3], 0.5))
        self.assertTrue(np.allclose(channel_audio[5], 0.5))
        self.assertTrue(np.allclose(channel_audio[6], 0.5))
        # Drone slice is mixed onto any existing ch4 content (was 1.0).
        self.assertTrue(np.allclose(channel_audio[4], 4.0))


class DroneManagerTests(unittest.TestCase):
    def test_get_slice_does_not_mutate_source_loop_when_wrapping(self):
        loop = np.ones((8, 2), dtype=np.float32)
        manager = DroneManager(loop.copy(), sample_rate=1000, volume=1.0)
        manager.pos = 6

        _ = manager.get_slice(4)

        self.assertTrue(np.allclose(manager.drone_loop, loop))


class EndToEndAudioTests(unittest.TestCase):
    def test_configuration_manager_switches_sample_pack(self):
        cfg = ConfigurationManager()
        default_paths = {sampler.name: sampler.file_path for sampler in cfg.samplers}

        cfg.set_sample_pack("shimmer")
        shimmer_paths = {sampler.name: sampler.file_path for sampler in cfg.samplers}

        self.assertEqual(cfg.active_sample_pack, "shimmer")
        self.assertNotEqual(default_paths["chords"], shimmer_paths["chords"])
        self.assertEqual(shimmer_paths["chords"], "samples/chords_shimmer.wav")

    def test_configuration_manager_falls_back_for_missing_pack_channels(self):
        cfg = ConfigurationManager()
        cfg.sample_packs["partial_test"] = {
            "melody": {"file_path": "samples/arp.wav", "root_midi": 60},
        }

        cfg.set_sample_pack("partial_test")
        sampler_paths = {sampler.name: sampler.file_path for sampler in cfg.samplers}

        self.assertEqual(sampler_paths["melody"], "samples/arp.wav")
        self.assertEqual(sampler_paths["bass"], "samples/default/bass.wav")
        self.assertEqual(sampler_paths["drone"], "samples/default/drone.wav")

    def test_configuration_manager_infers_conventional_pack_file_names(self):
        cfg = ConfigurationManager()
        cfg.sample_packs["custom"] = {
            "bass": {"root_midi": 29},
            "chords": {"root_midi": 60},
            "melody": {"root_midi": 60},
            "drone": {"root_midi": 60},
        }

        cfg.set_sample_pack("custom")
        sampler_paths = {sampler.name: sampler.file_path for sampler in cfg.samplers}

        self.assertEqual(sampler_paths["bass"], "samples/bass_custom.wav")
        self.assertEqual(sampler_paths["melody"], "samples/melody_custom.wav")

    def test_configuration_manager_scaffolds_pack_with_expected_roots(self):
        cfg = ConfigurationManager()

        scaffold = cfg.scaffold_sample_pack("glassy")
        cfg.set_sample_pack("glassy")
        sampler_paths = {sampler.name: sampler.file_path for sampler in cfg.samplers}
        sampler_roots = {sampler.name: sampler.root_midi for sampler in cfg.samplers}

        self.assertEqual(set(scaffold.keys()), set(cfg.SAMPLER_ORDER))
        self.assertEqual(sampler_paths["bass"], "samples/glassy/bass.wav")
        self.assertEqual(sampler_paths["drone"], "samples/glassy/drone.wav")
        self.assertEqual(sampler_roots["bass"], 29)
        self.assertTrue(all(root == 60 for name, root in sampler_roots.items() if name != "bass"))

    def test_configuration_manager_prefers_directory_style_when_present(self):
        cfg = ConfigurationManager()
        cfg.sample_packs["folderpack"] = {
            "bass": {"root_midi": 29},
            "chords": {"root_midi": 60},
            "melody": {"root_midi": 60},
            "drone": {"root_midi": 60},
        }

        samples_dir = Path("samples/folderpack")
        samples_dir.mkdir(parents=True, exist_ok=True)
        try:
            cfg.set_sample_pack("folderpack")
            sampler_paths = {sampler.name: sampler.file_path for sampler in cfg.samplers}
            self.assertEqual(sampler_paths["bass"], "samples/folderpack/bass.wav")
            self.assertEqual(sampler_paths["melody"], "samples/folderpack/melody.wav")
        finally:
            samples_dir.rmdir()

    def test_conversation_preset_applies_pack_tempo_and_mix(self):
        cfg = ConfigurationManager()

        user_preset_path = USER_PRESETS_PATH
        original = user_preset_path.read_text(encoding="utf-8") if user_preset_path.exists() else None
        try:
            cfg.save_conversation_preset("__tmp_test_opening_like__")
            cfg.update_conversation_preset_field("__tmp_test_opening_like__", "sample_pack", "ambient")
            cfg.update_conversation_preset_field("__tmp_test_opening_like__", "composition.default_tempo", 62.0)
            cfg.update_conversation_preset_field("__tmp_test_opening_like__", "audio.reverb_wet", 0.32)
            cfg.update_conversation_preset_field(
                "__tmp_test_opening_like__",
                "emotion_pool",
                ["admiration", "curiosity", "gratitude", "neutral", "optimism"],
            )
            cfg.update_conversation_preset_field("__tmp_test_opening_like__", "emotion_weights.optimism", 3.0)
            cfg.update_conversation_preset_field("__tmp_test_opening_like__", "emotion_weights.curiosity", 2.5)
            cfg.update_conversation_preset_field("__tmp_test_opening_like__", "emotion_weights.admiration", 2.0)
            cfg.update_conversation_preset_field("__tmp_test_opening_like__", "emotion_weights.gratitude", 1.5)
            cfg.update_conversation_preset_field("__tmp_test_opening_like__", "emotion_weights.neutral", 1.0)
            cfg.update_conversation_preset_field("__tmp_test_opening_like__", "root_pool", [57, 60, 64, 67])
            cfg.update_conversation_preset_field("__tmp_test_opening_like__", "root_weights.60", 3.0)
            cfg.update_conversation_preset_field("__tmp_test_opening_like__", "root_weights.64", 2.2)
            cfg.update_conversation_preset_field("__tmp_test_opening_like__", "root_weights.57", 1.4)
            cfg.update_conversation_preset_field("__tmp_test_opening_like__", "root_weights.67", 1.0)

            cfg.set_conversation_preset("__tmp_test_opening_like__")

            self.assertEqual(cfg.active_conversation_preset, "__tmp_test_opening_like__")
            self.assertEqual(cfg.active_sample_pack, "ambient")
            self.assertEqual(cfg.composition.default_tempo, 62.0)
            self.assertEqual(cfg.audio.channel_mix[3]["volume"], _DEFAULT_MIXER_STRIPS[3].volume)
            self.assertEqual(cfg.audio.reverb_wet, 0.32)
            self.assertIn("optimism", cfg.conversation_presets["__tmp_test_opening_like__"]["emotion_pool"])
            self.assertGreater(cfg.conversation_presets["__tmp_test_opening_like__"]["emotion_weights"]["optimism"], 1.0)
            self.assertEqual(cfg.conversation_presets["__tmp_test_opening_like__"]["root_pool"], [57, 60, 64, 67])
            self.assertGreater(cfg.conversation_presets["__tmp_test_opening_like__"]["root_weights"][60], 1.0)
        finally:
            if original is None:
                user_preset_path.unlink(missing_ok=True)
            else:
                user_preset_path.write_text(original, encoding="utf-8")

    def test_style_profile_applies_pack_tempo_and_mix(self):
        cfg = ConfigurationManager()

        cfg.set_style_profile("ambient")

        self.assertEqual(cfg.active_style_profile, "ambient")
        # Conversation preset ``default_ambient_01`` merges after style and wins on overlap.
        self.assertEqual(cfg.active_sample_pack, "default")
        self.assertEqual(cfg.composition.default_tempo, 70.0)
        self.assertEqual(cfg.audio.channel_mix[4]["volume"], _DEFAULT_MIXER_STRIPS[4].volume)
        self.assertEqual(cfg.audio.reverb_wet, 0.80)

    def test_conversation_preset_overrides_style_profile_when_both_active(self):
        cfg = ConfigurationManager()

        user_preset_path = USER_PRESETS_PATH
        original = user_preset_path.read_text(encoding="utf-8") if user_preset_path.exists() else None
        try:
            cfg.set_style_profile("dark")
            cfg.save_conversation_preset("__tmp_test_opening_like__")
            cfg.update_conversation_preset_field("__tmp_test_opening_like__", "sample_pack", "ambient")
            cfg.update_conversation_preset_field("__tmp_test_opening_like__", "composition.default_tempo", 62.0)
            cfg.set_conversation_preset("__tmp_test_opening_like__")

            self.assertEqual(cfg.active_style_profile, "dark")
            self.assertEqual(cfg.active_conversation_preset, "__tmp_test_opening_like__")
            self.assertEqual(cfg.active_sample_pack, "ambient")
            self.assertEqual(cfg.composition.default_tempo, 62.0)
        finally:
            if original is None:
                user_preset_path.unlink(missing_ok=True)
            else:
                user_preset_path.write_text(original, encoding="utf-8")

    def test_configuration_manager_can_save_user_conversation_preset(self):
        cfg = ConfigurationManager()
        user_preset_path = USER_PRESETS_PATH
        original = user_preset_path.read_text(encoding="utf-8") if user_preset_path.exists() else None

        try:
            cfg.save_conversation_preset("__tmp_test_copy__")

            self.assertIn("__tmp_test_copy__", cfg.conversation_presets)
            saved = json.loads(user_preset_path.read_text(encoding="utf-8"))
            self.assertIn("__tmp_test_copy__", saved)
        finally:
            if original is None:
                user_preset_path.unlink(missing_ok=True)
            else:
                user_preset_path.write_text(original, encoding="utf-8")

    def test_configuration_manager_can_update_user_conversation_preset_field(self):
        cfg = ConfigurationManager()
        user_preset_path = USER_PRESETS_PATH
        original = user_preset_path.read_text(encoding="utf-8") if user_preset_path.exists() else None

        try:
            cfg.save_conversation_preset("__tmp_test_edit__")
            cfg.update_conversation_preset_field("__tmp_test_edit__", "composition.default_tempo", 54.0)
            cfg.update_conversation_preset_field("__tmp_test_edit__", "sample_pack", "dark")

            updated = cfg.conversation_presets["__tmp_test_edit__"]
            self.assertEqual(updated["composition"]["default_tempo"], 54.0)
            self.assertEqual(updated["sample_pack"], "dark")
        finally:
            if original is None:
                user_preset_path.unlink(missing_ok=True)
            else:
                user_preset_path.write_text(original, encoding="utf-8")

    def test_audio_container_wires_event_bus_into_mixer_and_delay_sample_rate(self):
        container = AudioContainer.create_from_config(CONFIG)
        mixer = container.mixer
        original_volume = mixer.get_channel(2).volume
        EVENT_BUS.publish("set_channel_volume", {"index": 2, "volume": 0.25})
        EVENT_BUS.publish("set_master_volume", {"volume": 0.33})

        self.assertNotEqual(original_volume, mixer.get_channel(2).volume)
        self.assertEqual(mixer.get_channel(2).volume, 0.25)
        self.assertEqual(mixer.get_channel(2)._delay.sample_rate, container.sample_rate)
        self.assertAlmostEqual(container.master_bus.reverb_return_wet, CONFIG.audio.reverb_wet)
        self.assertAlmostEqual(container.master_bus.master_volume, 0.33)

    def test_audio_container_applies_default_mix_staging(self):
        container = AudioContainer.create_from_config(CONFIG)
        mixer = container.mixer

        self.assertAlmostEqual(mixer.get_channel(1).pan, -0.12)
        self.assertAlmostEqual(mixer.get_channel(2).pan, 0.10)
        self.assertAlmostEqual(mixer.get_channel(3).volume, _DEFAULT_MIXER_STRIPS[3].volume)
        self.assertGreater(mixer.get_channel(1).reverb_send, 0.0)
        self.assertGreater(mixer.get_channel(2).reverb_send, 0.0)
        self.assertLess(mixer.get_channel(4).volume, 1.0)

    def test_configuration_manager_switches_post_process_presets(self):
        cfg = ConfigurationManager()

        cfg.set_post_process_preset("ambient")

        self.assertEqual(cfg.active_post_process_preset, "ambient")
        self.assertAlmostEqual(cfg.audio.reverb_rt60, 10.0)
        self.assertAlmostEqual(cfg.audio.distortion_mix, 0.03)

        cfg.set_post_process_preset("aggressive")

        self.assertEqual(cfg.active_post_process_preset, "aggressive")
        self.assertAlmostEqual(cfg.audio.distortion_drive, 2.8)
        self.assertAlmostEqual(cfg.audio.reverb_rt60, 10.0)
        self.assertAlmostEqual(cfg.audio.reverb_wet, 0.12)

    def test_audio_container_applies_post_process_settings_to_master_bus(self):
        cfg = ConfigurationManager()
        cfg.set_post_process_preset("aggressive")

        container = AudioContainer.create_from_config(cfg)
        bus = container.master_bus

        self.assertTrue(bus.distortion.enabled)
        self.assertAlmostEqual(bus.distortion.drive, cfg.audio.distortion_drive)
        self.assertAlmostEqual(bus.distortion_return_level, cfg.audio.distortion_mix)
        self.assertAlmostEqual(bus.reverb_return_wet, cfg.audio.reverb_wet)

    def test_audio_container_can_update_live_post_process_settings(self):
        cfg = ConfigurationManager()
        container = AudioContainer.create_from_config(cfg)

        cfg.set_post_process_preset("ambient")
        container.apply_audio_config(cfg)

        self.assertAlmostEqual(container.reverb.rt60, cfg.audio.reverb_rt60)
        self.assertAlmostEqual(container.reverb.damping, cfg.audio.reverb_damping)
        self.assertAlmostEqual(container.master_bus.distortion_return_level, cfg.audio.distortion_mix)

    def test_reverb_preserves_stereo_differences_in_wet_signal(self):
        reverb = RoomReverb(sample_rate=1000, wet=1.0)
        audio = np.zeros((64, 2), dtype=np.float32)
        audio[0, 0] = 1.0

        wet = reverb.process(audio)

        self.assertEqual(wet.shape, audio.shape)
        self.assertFalse(np.allclose(wet[:, 0], wet[:, 1]))

    def test_reverb_emergency_tier_collapses_wet_to_mono(self):
        reverb = RoomReverb(sample_rate=1000, wet=1.0)
        audio = np.zeros((64, 2), dtype=np.float32)
        audio[0, 0] = 1.0
        audio[1, 1] = 1.0

        wet = reverb.process(audio, quality_tier="emergency")

        self.assertEqual(wet.shape, audio.shape)
        self.assertTrue(np.allclose(wet[:, 0], wet[:, 1], atol=1e-6))

    def test_reverb_rt60_can_reach_ten_seconds(self):
        reverb = RoomReverb(sample_rate=1000, wet=1.0)
        reverb.set_rt60(10.0)
        self.assertAlmostEqual(float(reverb.rt60), 10.0)

    def test_reverb_predelay_pushes_late_tail_back(self):
        audio = np.zeros((160, 2), dtype=np.float32)
        audio[0, 0] = 1.0

        reverb_no_predelay = RoomReverb(
            sample_rate=1000,
            wet=1.0,
            highpass_hz=0.0,
            predelay_ms=0.0,
            early_reflections_enabled=False,
        )
        reverb_with_predelay = RoomReverb(
            sample_rate=1000,
            wet=1.0,
            highpass_hz=0.0,
            predelay_ms=30.0,
            early_reflections_enabled=False,
        )

        wet_no = reverb_no_predelay.process(audio, quality_tier="high")
        wet_pd = reverb_with_predelay.process(audio, quality_tier="high")

        nz_no = np.where(np.abs(wet_no[:, 0]) > 1e-8)[0]
        nz_pd = np.where(np.abs(wet_pd[:, 0]) > 1e-8)[0]

        self.assertGreater(len(nz_no), 0)
        self.assertGreater(len(nz_pd), 0)
        self.assertGreaterEqual(int(nz_pd[0]), int(nz_no[0]) + 20)

    def test_reverb_early_reflections_active_in_high_but_not_safe(self):
        audio = np.zeros((160, 2), dtype=np.float32)
        audio[0, 0] = 1.0

        reverb = RoomReverb(
            sample_rate=1000,
            wet=1.0,
            highpass_hz=0.0,
            predelay_ms=0.0,
            early_reflections_enabled=True,
            early_reflections_level=0.8,
        )

        wet_high = reverb.process(audio, quality_tier="high")
        # New instance avoids carry-over state from the high-tier process call.
        reverb2 = RoomReverb(
            sample_rate=1000,
            wet=1.0,
            highpass_hz=0.0,
            predelay_ms=0.0,
            early_reflections_enabled=True,
            early_reflections_level=0.8,
        )
        wet_safe = reverb2.process(audio, quality_tier="safe")

        nz_high = np.where(np.abs(wet_high[:, 0]) > 1e-8)[0]
        nz_safe = np.where(np.abs(wet_safe[:, 0]) > 1e-8)[0]

        self.assertGreater(len(nz_high), 0)
        self.assertGreater(len(nz_safe), 0)
        self.assertLess(int(nz_high[0]), int(nz_safe[0]))

    def test_generate_section_and_render_one_real_bar(self):
        # CI environments for this repo do not necessarily ship sample packs.
        # When no sampler WAVs are present, the sampler engine correctly falls back to silence,
        # so this end-to-end "nonzero audio" assertion is not meaningful.
        from pathlib import Path

        repo_root = Path(__file__).resolve().parents[2] / "studio" / "audiogen" / "audiogen"
        sampler_paths = []
        for s in getattr(CONFIG, "samplers", []) or []:
            p = Path(str(getattr(s, "file_path", "") or ""))
            if not p:
                continue
            sampler_paths.append(p if p.is_absolute() else (repo_root / p))
        if sampler_paths and not any(p.exists() for p in sampler_paths):
            self.skipTest("sample pack WAVs not present (skipping end-to-end render assertion)")

        emotion = next(e for e in EMOTIONS if e.name.lower() == "joy")
        container = AudioContainer.create_from_config(CONFIG)
        synthesis_engine = SamplerEngine(CONFIG)
        synthesis_engine.preload_all_samplers()
        renderer = AudioRenderer(
            synthesis_engine=synthesis_engine,
            mixer=container.mixer,
            sample_rate=container.sample_rate,
            reverb_processor=container.reverb,
            master_bus=container.master_bus,
        )
        generator = CompositionGenerator(use_global_model=False)

        events = generator.generate_section(emotion, root_note=60, bars=1, temperature=0.8)
        tempo = 70 * emotion.tempo_multiplier
        bar_samples = int((4.0 * 60.0 / tempo) * container.sample_rate)
        audio = renderer.render_bar(events, tempo, bar_samples)

        self.assertTrue(events)
        self.assertEqual(audio.shape, (bar_samples, 2))
        self.assertEqual(audio.dtype, np.float32)
        self.assertGreater(float(np.max(np.abs(audio))), 0.0)


if __name__ == "__main__":
    unittest.main()
