"""
Regression tests for realtime robustness metrics (schema + smoke bounds).

Use `tools/rt_playback_health_check.py` locally or in CI for human-readable timings.
"""

import time
import unittest


class TestPlaybackStatsSchema(unittest.TestCase):
    def test_get_stats_includes_latency_and_underrun_fields(self):
        import logging

        from audio.RT_player.buffer_controller import PlaybackBufferController
        from audio.RT_player.telemetry import PlaybackTelemetry

        tel = PlaybackTelemetry(buffer_capacity=64, logger=logging.getLogger("test"))
        bc = PlaybackBufferController(capacity=64, telemetry=tel)

        snap = tel.snapshot(buffer_fill=2, target_buffer_bars=8)
        for key in (
            "buffer_underruns",
            "callback_underflows",
            "callback_count",
            "callback_frames",
            "buffer_fill_avg",
            "target_buffer_bars",
        ):
            self.assertIn(key, snap)

        bc.note_underrun()
        self.assertGreaterEqual(tel.buffer_underruns, 1)


class TestRtSmokeHealthBounds(unittest.TestCase):
    def test_smoke_run_reports_stable_stats_schema(self):
        """Reuses smoke-style boot; bounds are generous to avoid flaky CI."""
        from audio.audio_container import AudioContainer
        from audio.RT_player import PolyphonicPlayer
        from composition.engine import CompositionGenerator
        from composition.song_generator import SongGenerator
        from audiogen_core.config import CONFIG
        from data.music_data import EMOTIONS

        CONFIG.set_performance_mode("balanced")
        CONFIG.audio.target_buffer_bars = 2
        CONFIG.audio.startup_preroll_bars = 1
        CONFIG.audio.gen_burst_max_bars = 2
        try:
            CONFIG.composition.arranged_songs_default = True
            CONFIG.composition.arranged_song_mode = "ambient"
            CONFIG.composition.arranged_song_seconds = 18.0
            CONFIG.composition.arranged_song_max_bars = 20
            CONFIG.composition.arranged_song_k = 1
            CONFIG.composition.arranged_song_pick_time_budget_s = 0.25
        except Exception:
            pass
        try:
            CONFIG.rebuild_samplers()
        except Exception:
            pass

        gen = CompositionGenerator(enable_perf_monitoring=False)

        class _Adapter:
            def __init__(self, g, cfg):
                self.gen = g
                self.config = cfg
                self._song_gen = None

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

            def generate_arranged_song_events(self, emotion, root, runtime_mode="normal"):
                self.gen.runtime_generation_mode = runtime_mode
                comp = getattr(self.config, "composition", None)
                mode = str(getattr(comp, "arranged_song_mode", "default") or "default") if comp is not None else "default"
                seconds = float(getattr(comp, "arranged_song_seconds", 18.0) or 18.0) if comp is not None else 18.0
                max_bars = int(getattr(comp, "arranged_song_max_bars", 20) or 20) if comp is not None else 20
                base_tempo_bpm = 70.0
                if self._song_gen is None:
                    self._song_gen = SongGenerator(composer=self.gen)
                base = getattr(emotion, "name", "neutral")
                if str(mode).strip().lower() == "ambient":
                    specs = SongGenerator.ambient_form(
                        str(base),
                        root_note=int(root),
                        base_tempo_bpm=float(base_tempo_bpm),
                        target_seconds=float(seconds),
                        max_bars=int(max_bars),
                    )
                else:
                    specs = SongGenerator.default_form(str(base), bars_per_section=8, root_note=int(root))
                song = self._song_gen.generate_song(
                    specs, base_tempo_bpm=float(base_tempo_bpm), arrangement_form=str(mode), seed=0
                )
                total_bars = int(sum(int(s.bars) for s in (specs or []))) if specs else 0
                return list(song.events or []), int(total_bars)

            def generate_arranged_preview_events(self, emotion, root, *, runtime_mode="normal", preview_sections: int = 2):
                self.gen.runtime_generation_mode = runtime_mode
                comp = getattr(self.config, "composition", None)
                mode = str(getattr(comp, "arranged_song_mode", "default") or "default") if comp is not None else "default"
                seconds = float(getattr(comp, "arranged_song_seconds", 18.0) or 18.0) if comp is not None else 18.0
                max_bars = int(getattr(comp, "arranged_song_max_bars", 20) or 20) if comp is not None else 20
                base_tempo_bpm = 70.0
                if self._song_gen is None:
                    self._song_gen = SongGenerator(composer=self.gen)
                base = getattr(emotion, "name", "neutral")
                if str(mode).strip().lower() == "ambient":
                    specs = SongGenerator.ambient_form(
                        str(base),
                        root_note=int(root),
                        base_tempo_bpm=float(base_tempo_bpm),
                        target_seconds=float(seconds),
                        max_bars=int(max_bars),
                    )
                else:
                    specs = SongGenerator.default_form(str(base), bars_per_section=8, root_note=int(root))
                n = max(1, int(preview_sections))
                specs = list(specs[:n]) if specs else []
                song = self._song_gen.generate_song(
                    specs, base_tempo_bpm=float(base_tempo_bpm), arrangement_form=str(mode), seed=0
                )
                total_bars = int(sum(int(s.bars) for s in (specs or []))) if specs else 0
                return list(song.events or []), int(total_bars)

        container = AudioContainer.create_from_config(CONFIG)
        player = PolyphonicPlayer(_Adapter(gen, CONFIG), CONFIG, container=container)
        player.start()
        try:
            player.load_emotion(0 if EMOTIONS else 0, 60)
            time.sleep(0.8)
            stats = player.get_stats()
            self.assertIsInstance(stats, dict)
            self.assertIn("buffer_underruns", stats)
            self.assertIn("last_gen_time_ms", stats)
            self.assertIn("max_gen_time_ms", stats)
            self.assertIn("quality_tier", stats)
            # Generous ceiling: smoke config is tiny; underruns should stay rare.
            self.assertLessEqual(int(stats.get("buffer_underruns", 0)), 12)
            self.assertLessEqual(int(stats.get("callback_underflows", 0)), 12)
            self.assertGreaterEqual(float(stats.get("last_gen_time_ms", 0.0)), 0.0)
        finally:
            player.stop()


class TestDequeueIntoUnderrun(unittest.TestCase):
    def test_empty_queue_increments_underruns_once_per_starved_callback(self):
        import logging

        import numpy as np

        from audio.RT_player.buffer_controller import PlaybackBufferController
        from audio.RT_player.telemetry import PlaybackTelemetry

        tel = PlaybackTelemetry(buffer_capacity=32, logger=logging.getLogger("test"))
        bc = PlaybackBufferController(capacity=32, telemetry=tel)
        out = np.zeros((64, 2), dtype=np.float32)
        n0 = tel.buffer_underruns
        bc.dequeue_audio_frames_into(out, 64, running=True, paused=False, on_bar_complete=lambda: None)
        self.assertEqual(tel.buffer_underruns, n0 + 1)
