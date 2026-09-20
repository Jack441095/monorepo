import threading
import unittest

import numpy as np

from audio.RT_player.buffer_controller import PlaybackBufferController
from audio.RT_player.player import PolyphonicPlayer
from audio.RT_player.section_scheduler import SectionScheduler
from audio.RT_player.telemetry import PlaybackTelemetry
from data.delay_profiles import delay_feedback_scale_for_emotion
from data.music_data import EMOTIONS
from midi.midi_range_limiter import RANGE_LIMITER


class FakeMixerChannel:
    def __init__(self):
        self.delay_feedback = 0.0


class FakeComposer:
    def __init__(self):
        self.calls = []
        self.gen = None

    def generate_section_events(self, emotion, root, bars):
        self.calls.append((emotion.name, root, bars))
        return [
            (0, 36, 70, 0.0, 4.0, [36]),
            (1, 0, 80, 0.0, 4.0, [60, 64, 67]),
            (2, 64, 90, 0.0, 2.0, [64]),
        ]


class FakeMixer:
    def __init__(self):
        self.channel_volumes = {}
        self.channels = {2: FakeMixerChannel(), 3: FakeMixerChannel(), 5: FakeMixerChannel()}

    def set_channel_volume(self, channel, volume):
        self.channel_volumes[channel] = volume

    def get_channel(self, channel):
        return self.channels.get(channel)


class FakeContainer:
    def __init__(self, sample_rate=100):
        self.sample_rate = sample_rate
        self.mixer = FakeMixer()
        self.reverb = None


class FakeRenderer:
    def __init__(self):
        self.calls = []

    def render_bar(self, events, tempo, samples, drone=None, velocity_multiplier=1.0):
        self.calls.append((list(events), tempo, samples, None if drone is None else drone.shape))
        return np.full((samples, 2), 0.25, dtype=np.float32)


class FakeDrone:
    def __init__(self):
        self.calls = []

    def get_slice(self, samples):
        self.calls.append(samples)
        return np.zeros((samples, 2), dtype=np.float32)


class FakeSynthesisEngine:
    def __init__(self):
        self.prewarmed = []

    def prewarm_notes(self, notes):
        self.prewarmed.append(list(notes))


class RecordingLock:
    def __init__(self, name, log):
        self.name = name
        self.log = log

    def __enter__(self):
        self.log.append(self.name)
        return self

    def __exit__(self, exc_type, exc, tb):
        return False


class FakeOutputStream:
    def __init__(self):
        self.stream = None
        self.failed = True
        self.recovery_requested = False

    def start(self):
        self.failed = False

    def stop(self):
        self.stream = None

    def request_recovery(self):
        self.recovery_requested = True


class FakeStatus:
    def __init__(self, output_underflow=False, priming_output=False):
        self.output_underflow = output_underflow
        self.priming_output = priming_output

    def __bool__(self):
        return True


class PlayerRuntimeTests(unittest.TestCase):
    def _make_player(self):
        player = PolyphonicPlayer.__new__(PolyphonicPlayer)
        player.config = type(
            "Cfg",
            (),
            {
                "composition": type("Comp", (), {"bars_per_section": 4})(),
                "audio": type(
                    "Audio",
                    (),
                    {
                        "sample_rate": 100,
                        "underrun_auto_buffer_boost_enabled": True,
                        "underrun_auto_buffer_boost_trigger_count": 2,
                        "underrun_auto_buffer_boost_step_bars": 2,
                        "underrun_auto_buffer_boost_max_extra_bars": 6,
                        "underrun_auto_buffer_boost_decay_seconds": 1000.0,
                        "channel_delay": {
                            2: {"enabled": True, "feedback": 0.33},
                            3: {"enabled": True, "feedback": 0.33},
                        },
                    },
                )(),
            },
        )()
        player.container = FakeContainer(sample_rate=100)
        player.composer = FakeComposer()
        player.synthesis_engine = FakeSynthesisEngine()
        player.renderer = FakeRenderer()
        player.drone = FakeDrone()

        player.state_lock = threading.Lock()
        player.section_lock = threading.RLock()
        player._emotion = None
        player._root = 60
        player._paused = False
        player._running = False
        player._playing = False

        player.telemetry = PlaybackTelemetry(buffer_capacity=32, logger=__import__("logging").getLogger("test"))
        player.buffer_controller = PlaybackBufferController(capacity=32, telemetry=player.telemetry)
        player.buffer = player.buffer_controller.buffer
        player._startup_preroll_bars = 1
        player._target_buffer_bars = 8
        player._base_startup_preroll_bars = 1
        player._base_target_buffer_bars = 8
        player._rt_extra_buffer_bars = 0
        player._rt_last_underflow_time = 0.0
        player._rt_last_buffer_decay_time = 0.0
        player._rt_underflow_burst_count = 0
        player._telemetry_target_buffer_bars = int(player._target_buffer_bars)
        player._emotion_transition_boundary_bars = 4
        player._transition_boundary_bars = 4
        player._emotion_handoff_crossfade_scale = 0.48
        player._emotion_handoff_crossfade_max_seconds = 0.32
        player._transition_queue_cap_bars = 4
        player._transition_overlap_ratio = 0.25
        player._transition_max_overlap_seconds = 1.5
        player.section_scheduler = SectionScheduler(owner=player, logger=__import__("logging").getLogger("test"))
        player.section_scheduler.current_section_events = []
        player.section_scheduler.current_section_bars = 0
        player.section_scheduler.next_bar_index = 0
        player.section_scheduler.next_section_events = None
        player.section_scheduler.next_section_bars = 0
        player.section_scheduler.next_section_ready = False
        player.section_scheduler.next_section_emotion = None
        player.section_scheduler.next_section_root = None
        player.section_scheduler.pre_generation_running = False
        player.section_scheduler.pending_emotion = None
        player.section_scheduler.pending_root = None
        player.section_scheduler.bars_played_this_section = 0
        player._crossfade_pending = False
        player._transition_crossfade_samples = 8
        player._last_generated_audio = None

        player.total_bars_played = 0
        player.chunks_generated = 0
        player.last_bar_render_time = 0.0
        player.max_bar_render_time = 0.0
        player.last_section_compose_time = 0.0
        player.last_generation_time = 0.0
        player.max_generation_time = 0.0
        player._emergency_active = False
        player._emergency_reason = ""
        player._rt_mode_stable = "normal"

        player._last_recovery_attempt_time = 0.0
        player._last_portaudio_underflow_log_ts = 0.0
        player.output_stream = FakeOutputStream()
        player.stream = None
        player._background_preload_started = False
        player._sampler_load_thread = None
        return player

    def test_runtime_reverb_quality_tier_mapping(self):
        self.assertEqual(PolyphonicPlayer._runtime_reverb_quality_tier_static("normal"), "high")
        self.assertEqual(PolyphonicPlayer._runtime_reverb_quality_tier_static("balanced"), "balanced")
        # Low CPU mode allows the lighter safe floor; high mode restores the balanced floor.
        self.assertEqual(PolyphonicPlayer._runtime_reverb_quality_tier_static("safe"), "safe")
        self.assertEqual(PolyphonicPlayer._runtime_reverb_quality_tier_static("emergency"), "safe")

    def test_load_emotion_applies_ranges_clears_buffer_and_generates_section(self):
        player = self._make_player()
        player.buffer.write("old")

        player.load_emotion(0, 64)

        self.assertEqual(player.emotion.name, EMOTIONS[0].name)
        self.assertEqual(player.root, 64)
        self.assertEqual(len(player.buffer), 0)
        # Fast cold start: generates a short preview (see CONFIG.audio.cold_start_preview_bars).
        self.assertEqual(player.section_scheduler.current_section_bars, 1)
        self.assertTrue(player.section_scheduler.current_section_events)
        # Background pre-generation can enqueue quickly; assert the preview call occurred.
        self.assertIn((EMOTIONS[0].name, 64, 1), player.composer.calls)
        stats = player.get_stats()
        self.assertIn("last_emotion_switch_latency_ms", stats)
        self.assertGreaterEqual(float(stats.get("last_emotion_switch_latency_ms", 0.0)), 0.0)
        self.assertEqual(str(stats.get("last_emotion_switch_stage", "")), "cold_start")

    def test_cold_start_preview_uses_preview_runtime_overrides(self):
        player = self._make_player()
        player.config.audio.cold_start_preview_runtime_mode = "preview"
        player.config.audio.cold_start_preview_planner_effort = "minimal"
        player.config.audio.cold_start_defer_pregen_until_first_bar = True

        def fake_generate_section_events(
            emotion,
            root,
            bars,
            target_notes_per_bar=6.0,
            runtime_mode="normal",
            planner_effort=None,
            section_index=0,
            transition_handoff_context=None,
        ):
            player.composer.calls.append(
                ("section", emotion.name, root, bars, runtime_mode, planner_effort)
            )
            return [(2, 64, 90, 0.0, 2.0, [64])]

        player.composer.generate_section_events = fake_generate_section_events

        player.load_emotion(0, 64)

        self.assertIn(
            ("section", EMOTIONS[0].name, 64, 1, "preview", "minimal"),
            player.composer.calls,
        )
        self.assertFalse(player.section_scheduler.should_pre_generate())
        player.section_scheduler.next_bar_index = 1
        self.assertTrue(player.section_scheduler.should_pre_generate())

    def test_emotion_switch_latency_records_on_pregen_commit(self):
        player = self._make_player()
        # Cold start (sets initial emotion)
        player.load_emotion(0, 60)
        # Queue a transition
        player.load_emotion(1, 64)
        sch = player.section_scheduler
        self.assertIsNotNone(sch.pending_emotion)
        # Run pre-generation synchronously (unit-test mode)
        sch.pre_generate_next_section()
        self.assertTrue(sch.next_section_ready)
        stats = player.get_stats()
        self.assertIn("last_emotion_switch_latency_ms", stats)
        self.assertGreaterEqual(float(stats.get("last_emotion_switch_latency_ms", 0.0)), 0.0)
        self.assertEqual(str(stats.get("last_emotion_switch_stage", "")), "transition_pregen_commit")

    def test_load_emotion_arranged_mode_uses_arranged_preview_not_tiny_section_preview(self):
        player = self._make_player()
        player.config.composition.arranged_songs_default = True
        player.config.composition.arranged_realtime_full_timeline = False
        player.config.composition.arranged_emotion_switch_preview_sections = 1
        player.config.audio.cold_start_preview_runtime_mode = "preview"

        def fake_arranged_preview(emotion, root, runtime_mode="normal", preview_sections=2):
            player.composer.calls.append(("arranged_preview", emotion.name, root, runtime_mode, preview_sections))
            return ([(0, 36, 70, 0.0, 4.0, [36]), (0, 38, 70, 4.0, 4.0, [38])], 2)

        player.composer.generate_arranged_preview_events = fake_arranged_preview

        player.load_emotion(0, 64)

        # Low-latency cold preview may use one arranged section; high mode restores two.
        self.assertEqual(player.section_scheduler.current_section_bars, 2)
        self.assertIn(("arranged_preview", EMOTIONS[0].name, 64, "preview", 1), player.composer.calls)

    def test_load_emotion_arranged_full_timeline_calls_generate_arranged_song_events(self):
        player = self._make_player()
        player.config.composition.arranged_songs_default = True
        player.config.composition.arranged_realtime_full_timeline = True
        calls = player.composer.calls

        def fake_full(emotion, root, runtime_mode="normal"):
            calls.append(("arranged_song", emotion.name, root, runtime_mode))
            return [(0, 36, 70, float(i * 4.0), 4.0, [36]) for i in range(8)], 8

        player.composer.generate_arranged_song_events = fake_full

        player.load_emotion(0, 64)

        self.assertEqual(player.section_scheduler.current_section_bars, 8)
        self.assertTrue(
            any(
                isinstance(c, tuple)
                and len(c) >= 3
                and c[0] == "arranged_song"
                and c[1] == EMOTIONS[0].name
                and c[2] == 64
                for c in calls
            ),
        )

    def test_arranged_song_completion_snapshot_is_captured_for_cli_actions(self):
        player = self._make_player()
        player.config.composition.arranged_songs_default = True
        player.config.composition.arranged_song_end_fade_min_total_bars = 0
        sch = player.section_scheduler
        events = [(2, 64, 90, 0.0, 1.0, [64])]
        render = object()
        sch.current_section_events = list(events)
        sch.current_section_bars = 1
        sch.next_bar_index = 1
        sch.bars_played_this_section = 1
        sch.current_arrangement_segments = [
            {"role": "outro", "role_label": "Outro", "start_bar": 0, "end_bar": 1, "bars": 1}
        ]
        sch.current_arranged_song_render = render
        sch._arranged_completion_armed = True

        sch.prepare_next_bar()

        self.assertEqual(sch.completed_arranged_song_count, 1)
        self.assertEqual(sch.last_completed_arranged_song_events, events)
        self.assertEqual(sch.last_completed_arranged_song_bars, 1)
        self.assertIs(sch.last_completed_arranged_song_render, render)

    def test_load_emotion_uses_shared_midi_ranges_for_all_emotions(self):
        player = self._make_player()
        default_melody = RANGE_LIMITER.default_configs[2]

        player.load_emotion(next(i for i, e in enumerate(EMOTIONS) if e.name.lower() == "joy"), 60)
        joy_range = RANGE_LIMITER.get_range_info(2)
        self.assertEqual(
            (joy_range["min_note"], joy_range["max_note"]),
            (default_melody.min_note, default_melody.max_note),
        )

        player.load_emotion(next(i for i, e in enumerate(EMOTIONS) if e.name.lower() == "neutral"), 60)
        neutral_range = RANGE_LIMITER.get_range_info(2)
        self.assertEqual(
            (neutral_range["min_note"], neutral_range["max_note"]),
            (default_melody.min_note, default_melody.max_note),
        )

    def test_delay_feedback_scale_is_global_across_emotions(self):
        self.assertEqual(
            delay_feedback_scale_for_emotion("excitement"),
            delay_feedback_scale_for_emotion("pride"),
        )
        self.assertEqual(
            delay_feedback_scale_for_emotion("excitement"),
            delay_feedback_scale_for_emotion("relief"),
        )

    def test_load_emotion_keeps_global_delay_identity_across_emotions(self):
        player = self._make_player()
        excitement_index = next(i for i, e in enumerate(EMOTIONS) if e.name.lower() == "excitement")
        relief_index = next(i for i, e in enumerate(EMOTIONS) if e.name.lower() == "relief")

        player.load_emotion(excitement_index, 60)
        excitement_feedback = player.container.mixer.get_channel(2).delay_feedback

        player._apply_emotion_runtime_state(EMOTIONS[relief_index], reset_mixer_filters=False)
        relief_feedback = player.container.mixer.get_channel(2).delay_feedback

        self.assertEqual(excitement_feedback, relief_feedback)
        self.assertEqual(
            player.container.mixer.get_channel(5).delay_feedback,
            relief_feedback,
        )

    def test_generate_next_bar_slices_section_and_renders_audio(self):
        player = self._make_player()
        player.load_emotion(0, 60)

        chunk = player._generate_next_bar()
        expected_samples = int((4.0 * 60.0 / (70 * EMOTIONS[0].tempo_multiplier)) * player.container.sample_rate)

        self.assertEqual(chunk.bar_index, 0)
        self.assertEqual(chunk.root_note, 60)
        self.assertEqual(chunk.audio.shape, (expected_samples, 2))
        self.assertEqual(len(player.renderer.calls), 1)
        rendered_events, tempo, samples, drone_shape = player.renderer.calls[0]
        self.assertAlmostEqual(tempo, 70 * EMOTIONS[0].tempo_multiplier)
        self.assertEqual(samples, expected_samples)
        self.assertEqual(drone_shape, (expected_samples, 2))
        self.assertTrue(all(0.0 <= ev[3] < 4.0 for ev in rendered_events))

    def test_generate_next_bar_suppresses_drone_for_relief(self):
        player = self._make_player()
        relief_index = next(i for i, emotion in enumerate(EMOTIONS) if emotion.name.lower() == "relief")
        player.load_emotion(relief_index, 60)

        chunk = player._generate_next_bar()

        self.assertEqual(chunk.emotion_name.lower(), "relief")
        self.assertEqual(len(player.renderer.calls), 1)
        _events, _tempo, _samples, drone_shape = player.renderer.calls[0]
        self.assertIsNone(drone_shape)
        self.assertEqual(player.drone.calls, [])

    def test_pre_generate_pending_emotion_with_arranged_uses_single_section_not_full_song(self):
        """Queued emotion change must not block on generate_arranged_song_events (very slow)."""
        player = self._make_player()
        player.config.composition.arranged_songs_default = True
        sch = player.section_scheduler
        sch.current_section_events = [(0, 36, 70, 0.0, 4.0, [36])]
        sch.current_section_bars = 64
        sch.next_bar_index = 2
        sch.pending_emotion = EMOTIONS[1]
        sch.pending_root = 62
        sch.pre_generation_running = False
        sch.next_section_ready = False

        sch.pre_generate_next_section()

        self.assertTrue(sch.next_section_ready)
        self.assertEqual(sch.next_section_bars, 4)
        self.assertEqual(player.composer.calls[-1], (EMOTIONS[1].name, 62, 4))

    def test_pre_generate_next_section_populates_ready_state(self):
        import time

        player = self._make_player()
        player.load_emotion(0, 60)

        # Cold start may already have kicked async pregen via ensure_pregen_enqueued.
        if not player.section_scheduler.next_section_ready:
            player._pre_generate_next_section()
        for _ in range(200):
            if player.section_scheduler.next_section_ready:
                break
            time.sleep(0.002)

        self.assertTrue(player.section_scheduler.next_section_ready)
        self.assertEqual(player.section_scheduler.next_section_bars, 4)
        self.assertTrue(player.section_scheduler.next_section_events)

    def test_load_emotion_acquires_section_lock_before_state_lock(self):
        player = self._make_player()
        order = []
        player.section_lock = RecordingLock("section", order)
        player.state_lock = RecordingLock("state", order)

        player.load_emotion(0, 60)

        self.assertEqual(order[:2], ["section", "state"])

    def test_load_emotion_queues_change_without_clearing_active_audio(self):
        player = self._make_player()
        player.load_emotion(0, 60)
        existing_events = list(player.section_scheduler.current_section_events)
        player.buffer.write("chunk")
        player._playing = True

        player.load_emotion(1, 64)

        self.assertEqual(player.section_scheduler.pending_emotion, EMOTIONS[1])
        self.assertEqual(player.section_scheduler.pending_root, 64)
        self.assertEqual(player.section_scheduler.current_section_events, existing_events)
        self.assertEqual(len(player.buffer), 1)

    def test_load_emotion_preserves_queued_bars_during_transition(self):
        player = self._make_player()
        player.load_emotion(0, 60)
        player._playing = True
        player._schedule_transition_pre_generation = lambda: None
        for idx in range(7):
            player.buffer.write(f"chunk-{idx}")

        player.load_emotion(1, 64)

        self.assertEqual(len(player.buffer), 7)
        self.assertEqual(player.section_scheduler.pending_emotion, EMOTIONS[1])

    def test_compute_target_buffer_bars_is_capped_while_transition_pending(self):
        player = self._make_player()
        player.load_emotion(0, 60)
        player.last_bar_render_time = 9.0
        player.max_bar_render_time = 9.0
        player.last_generation_time = 9.0
        player.max_generation_time = 9.0
        player.section_scheduler.pending_emotion = EMOTIONS[1]

        target = player._compute_target_buffer_bars()

        transition_cap = max(14, player._transition_queue_cap_bars + 6)
        self.assertLessEqual(target, transition_cap)

    def test_transition_crossfade_blends_previous_tail_into_new_bar(self):
        player = self._make_player()
        player._last_generated_audio = np.ones((8, 2), dtype=np.float32)
        player._crossfade_pending = True
        incoming = np.zeros((8, 2), dtype=np.float32)

        blended = player._apply_transition_crossfade(incoming)

        self.assertFalse(player._crossfade_pending)
        self.assertTrue(np.all(blended[0] > 0.0))
        self.assertTrue(np.allclose(blended[-1], 0.0))

    def test_transition_crossfade_uses_longer_dynamic_fade_for_real_bar_lengths(self):
        player = self._make_player()
        player._transition_crossfade_samples = 8
        player._transition_overlap_ratio = 0.25
        player._last_generated_audio = np.ones((80, 2), dtype=np.float32)
        player._crossfade_pending = True

        blended = player._apply_transition_crossfade(np.zeros((80, 2), dtype=np.float32))

        self.assertTrue(np.all(blended[8] > 0.0))
        self.assertTrue(np.all(blended[18] > 0.0))
        self.assertTrue(np.allclose(blended[-1], 0.0))

    def test_underflow_auto_buffer_boost_increases_target_after_trigger(self):
        player = self._make_player()
        status = FakeStatus(output_underflow=True, priming_output=False)
        # trigger_count=2 in test config
        player._log_stream_status(status)
        self.assertEqual(int(player._target_buffer_bars), 8)
        player._log_stream_status(status)
        self.assertEqual(int(player._target_buffer_bars), 10)

    def test_prepare_next_bar_after_section_end_swap_uses_bar_zero_not_stale_end_flag(self):
        """Regression: section_end_reached was computed pre-activate; first bar after swap must be index 0."""
        player = self._make_player()
        player.load_emotion(0, 60)
        sch = player.section_scheduler
        sch.current_section_bars = 8
        sch.next_bar_index = 8
        sch.next_section_ready = True
        sch.next_section_bars = 32
        sch.next_section_events = list(sch.current_section_events)
        sch.pending_emotion = EMOTIONS[1]
        sch.pending_root = 64
        sch.next_section_emotion = EMOTIONS[1]
        sch.next_section_root = 64

        data = sch.prepare_next_bar()

        self.assertEqual(data["bar_index"], 0)
        self.assertTrue(data["switched_section"])
        self.assertTrue(data.get("emotion_handoff"))
        self.assertEqual(sch.next_bar_index, 1)

    def test_prepare_next_bar_arranged_loop_end_sets_arranged_loop_handoff_not_emotion(self):
        player = self._make_player()
        player.config.composition.arranged_songs_default = True
        player.load_emotion(0, 60)
        sch = player.section_scheduler
        sch.current_section_bars = 4
        sch.next_bar_index = 4
        sch.next_section_ready = True
        sch.next_section_events = list(sch.current_section_events)
        sch.next_section_bars = 4
        sch.next_section_emotion = EMOTIONS[0]
        sch.next_section_root = 60
        sch.pending_emotion = None

        data = sch.prepare_next_bar()

        self.assertTrue(data.get("arranged_loop_handoff"))
        self.assertFalse(data.get("emotion_handoff"))

    def test_prepare_next_bar_failed_activate_does_not_advance_as_if_swap_succeeded(self):
        """If activate aborts (ready flag set but empty buffer), do not use post-activate bar-0 path."""
        player = self._make_player()
        player.load_emotion(0, 60)
        sch = player.section_scheduler
        sch.current_section_bars = 8
        sch.next_bar_index = 8
        sch.next_section_ready = True
        sch.next_section_events = []
        sch.next_section_bars = 4
        sch.pending_emotion = EMOTIONS[1]
        sch.pending_root = 64

        data = sch.prepare_next_bar()

        self.assertFalse(data["switched_section"])
        self.assertFalse(data.get("emotion_handoff"))
        self.assertEqual(data["bar_index"], 7)
        self.assertEqual(sch.next_bar_index, 8)

    def test_pending_emotion_phrase_boundary_waits_for_heard_bars_not_generation_depth(self):
        player = self._make_player()
        player.load_emotion(0, 60)
        sch = player.section_scheduler
        sch.current_section_bars = 8
        sch.next_bar_index = 4
        sch.bars_played_this_section = 0
        sch.pending_emotion = EMOTIONS[1]
        sch.pending_root = 64
        sch.next_section_ready = True
        sch.next_section_events = list(sch.current_section_events)
        sch.next_section_bars = 4
        sch.next_section_emotion = EMOTIONS[1]
        sch.next_section_root = 64

        data = sch.prepare_next_bar()

        self.assertFalse(data["switched_section"])
        self.assertEqual(player.emotion.name, EMOTIONS[0].name)

    def test_generate_next_bar_swaps_queued_emotion_when_next_section_ready(self):
        player = self._make_player()
        player.load_emotion(0, 60)
        player.section_scheduler.current_section_bars = 8
        player.section_scheduler.next_bar_index = 4
        player.section_scheduler.bars_played_this_section = 4
        player.section_scheduler.pending_emotion = EMOTIONS[1]
        player.section_scheduler.pending_root = 64
        player.section_scheduler.next_section_ready = True
        player.section_scheduler.next_section_events = list(player.section_scheduler.current_section_events)
        player.section_scheduler.next_section_bars = 4
        player.section_scheduler.next_section_emotion = EMOTIONS[1]
        player.section_scheduler.next_section_root = 64

        chunk = player._generate_next_bar()

        self.assertEqual(chunk.bar_index, 0)
        self.assertEqual(player.emotion.name, EMOTIONS[1].name)
        self.assertEqual(player.root, 64)
        self.assertIsNone(player.section_scheduler.pending_emotion)

    def test_activate_next_section_drone_reset_respects_keep_playing_flag(self):
        player = self._make_player()
        player.load_emotion(0, 60)

        class DroneResetStub:
            def __init__(self):
                self.calls = []

            def reset_drone(self, *, hard=False):
                self.calls.append(bool(hard))

        stub = DroneResetStub()
        player.composer.gen = stub
        sch = player.section_scheduler
        sch.next_section_ready = True
        sch.next_section_events = list(sch.current_section_events)
        sch.next_section_bars = sch.current_section_bars
        sch.next_section_emotion = EMOTIONS[1]
        sch.next_section_root = 64
        sch.pending_emotion = EMOTIONS[1]
        sch.pending_root = 64

        # Default behavior: keep the drone continuous across emotion/root switches.
        try:
            from audiogen_core.config import CONFIG

            CONFIG.composition.drone_keep_playing_on_switch = True
            CONFIG.composition.drone_always_on = False
        except Exception:
            pass

        ok = sch.activate_next_section()

        self.assertTrue(ok)
        self.assertEqual(stub.calls, [])

        # When explicitly disabled, switching emotion/root triggers a drone reset.
        sch.next_section_ready = True
        sch.next_section_events = list(sch.current_section_events)
        sch.next_section_bars = sch.current_section_bars
        sch.next_section_emotion = EMOTIONS[2]
        sch.next_section_root = 67
        sch.pending_emotion = EMOTIONS[2]
        sch.pending_root = 67
        try:
            from audiogen_core.config import CONFIG

            CONFIG.composition.drone_keep_playing_on_switch = False
            CONFIG.composition.drone_always_on = False
        except Exception:
            pass
        ok2 = sch.activate_next_section()
        self.assertTrue(ok2)
        self.assertEqual(stub.calls, [True])

    def test_sanitize_audio_coerces_invalid_shapes_values_and_length(self):
        player = self._make_player()

        raw = np.array([np.nan, np.inf, -np.inf, 2.5], dtype=np.float32)
        sanitized = player._sanitize_audio(raw, expected_samples=6)

        self.assertEqual(sanitized.shape, (6, 2))
        self.assertEqual(sanitized.dtype, np.float32)
        self.assertTrue(np.all(np.isfinite(sanitized)))
        self.assertLessEqual(float(np.max(np.abs(sanitized))), 1.0)

    def test_dequeue_audio_frames_drains_partial_chunks_and_counts_completed_bars(self):
        player = self._make_player()
        player._running = True
        chunk_a = type("Chunk", (), {"audio": np.full((3, 2), 0.25, dtype=np.float32)})()
        chunk_b = type("Chunk", (), {"audio": np.full((3, 2), 0.5, dtype=np.float32)})()
        player.buffer.write(chunk_a)
        player.buffer.write(chunk_b)

        frames = player._dequeue_audio_frames(5)

        self.assertEqual(frames.shape, (5, 2))
        self.assertTrue(np.allclose(frames[:3], 0.25))
        self.assertTrue(np.allclose(frames[3:], 0.5))
        self.assertEqual(player.total_bars_played, 1)
        self.assertIsNotNone(player.buffer_controller._active_chunk)
        self.assertEqual(player.buffer_controller._active_chunk_offset, 2)

    def test_compute_target_buffer_bars_grows_with_render_cost(self):
        player = self._make_player()
        player.load_emotion(0, 60)
        player.last_bar_render_time = 9.0
        player.max_bar_render_time = 9.0

        target = player._compute_target_buffer_bars()

        self.assertGreaterEqual(target, 7)

    def test_note_underrun_increases_buffer_backoff(self):
        player = self._make_player()
        player.load_emotion(0, 60)
        baseline = player._compute_target_buffer_bars()

        player.buffer_controller.note_underrun()
        boosted = player._compute_target_buffer_bars()

        self.assertGreaterEqual(player.telemetry.buffer_underruns, 1)
        self.assertGreater(player.buffer_controller._underrun_backoff_bars, 0)
        self.assertGreaterEqual(boosted, baseline)

    def test_update_playback_telemetry_tracks_callback_and_buffer_levels(self):
        player = self._make_player()
        player.buffer.write("chunk-a")
        player.buffer.write("chunk-b")

        player._update_playback_telemetry(256)
        stats = player.get_stats()

        self.assertEqual(stats["callback_count"], 1)
        self.assertEqual(stats["callback_frames"], 256)
        self.assertEqual(stats["buffer_fill_avg"], 2.0)
        self.assertEqual(stats["buffer_low_watermark"], 2)
        self.assertEqual(stats["buffer_high_watermark"], 2)
        self.assertIn("gen_culprit", stats)
        self.assertIn("gen_stage_ema_ms", stats)
        self.assertIn("gen_stage_last_ms", stats)

    def test_generation_stage_telemetry_tracks_culprit(self):
        player = self._make_player()
        player.renderer.last_stage_timing_ms = {
            "mono": 2.0,
            "chords": 1.0,
            "mix": 3.0,
            "master": 8.0,
            "total": 14.0,
        }

        player._update_generation_stage_telemetry()

        self.assertEqual(player._dominant_generation_stage(), "master")
        self.assertGreaterEqual(float(player._gen_stage_ema_ms.get("master", 0.0)), 1.0)

    def test_log_stream_status_tracks_output_underflow_in_telemetry(self):
        player = self._make_player()

        player._log_stream_status(FakeStatus(output_underflow=False, priming_output=False))
        self.assertEqual(player.telemetry.callback_underflows, 0)

        player._log_stream_status(FakeStatus(output_underflow=True, priming_output=False))
        self.assertGreaterEqual(player.telemetry.callback_underflows, 1)


if __name__ == "__main__":
    unittest.main()
