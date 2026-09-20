#!/usr/bin/env python3
"""
Realtime playback health check: cold-start timings + buffer / generation telemetry.

Run from repo root (records JSON line to stdout for dashboards / diff over time):

  AUDIOGEN_STARTUP_PROFILE=1 python tools/rt_playback_health_check.py
  AUDIOGEN_RT_PROFILE=1 python tools/rt_playback_health_check.py   # also enables per-bar render profiling logs

Environment:
  AUDIOGEN_STARTUP_PROFILE=1  — stage timings printed via StartupProfiler
  AUDIOGEN_RT_PROFILE=1       — bar render breakdown (see AudioRenderer)
  AUDIOGEN_RT_BAR_LOG=1       — per-bar prepare vs render wall splits (see utils/rt_bar_profiler.py)
  AUDIOGEN_RT_CPROFILE=1      — slow-bar cProfile top-N dump (ratio via AUDIOGEN_RT_PROFILE_SLOW_RATIO)
  LOGLEVEL=DEBUG              — PortAudio / underrun diagnostics (verbose)
"""
from __future__ import annotations

import json
import os
import sys
import time
from typing import Any

# Repo root on path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))


def _truthy(name: str) -> bool:
    v = (os.environ.get(name) or "").strip().lower()
    return v not in ("", "0", "false", "no", "off")


def main() -> int:
    from audio.audio_container import AudioContainer
    from audio.RT_player import PolyphonicPlayer
    from composition.engine import CompositionGenerator
    from composition.song_generator import SongGenerator
    from audiogen_core.config import CONFIG
    from data.music_data import EMOTIONS
    from utils.startup_profiler import StartupProfiler
    from utils.numba_warmup import warmup_numba_kernels

    prof = StartupProfiler(emit=lambda s: print(s, file=sys.stderr), enabled=_truthy("AUDIOGEN_STARTUP_PROFILE"))
    if _truthy("AUDIOGEN_RT_PROFILE"):
        try:
            CONFIG.audio.rt_render_profile_enabled = True
        except Exception:
            pass

    prof.mark("healthcheck_start")
    # Precompile Numba kernels so the first slow bar doesn't include JIT compile time.
    try:
        warmup_numba_kernels()
    except Exception:
        pass
    # Use low CPU profile for stable headless CI-style runs unless overridden.
    # Legacy name "balanced" is still accepted, but prefer the 2-mode interface.
    perf_mode = (os.environ.get("AUDIOGEN_PERF_MODE") or "low").strip() or "low"
    CONFIG.set_performance_mode(perf_mode)
    # Slightly higher runway than the unit smoke test so headless runs less often
    # hit emergency tier before the gen thread refills (still logs honest timings).
    # Headless baseline: slightly tighter than full ``quality`` defaults but above minimum runway.
    CONFIG.audio.target_buffer_bars = 8
    CONFIG.audio.startup_preroll_bars = 2
    CONFIG.audio.gen_burst_max_bars = 6
    try:
        CONFIG.composition.arranged_songs_default = True
        CONFIG.composition.arranged_song_mode = "ambient"
        CONFIG.composition.arranged_song_seconds = 18.0
        CONFIG.composition.arranged_song_max_bars = 20
        CONFIG.composition.arranged_song_k = 1
        CONFIG.composition.arranged_song_pick_time_budget_s = 0.35
    except Exception:
        pass
    try:
        CONFIG.rebuild_samplers()
    except Exception:
        pass
    prof.mark("healthcheck_config_ready")

    gen = CompositionGenerator(enable_perf_monitoring=False)

    class _Adapter:
        def __init__(self, g, cfg):
            self.gen = g
            self.config = cfg
            self._song_gen = None

        def generate_section_events(
            self, emotion, root, bars, target_notes_per_bar=6.0, runtime_mode="normal", section_index=0, transition_handoff_context=None
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

    t0 = time.perf_counter()
    container = AudioContainer.create_from_config(CONFIG)
    prof.mark("healthcheck_audio_container")
    adapter = _Adapter(gen, CONFIG)
    player = PolyphonicPlayer(adapter, CONFIG, container=container)
    prof.mark("healthcheck_player_constructed")
    player.start()
    prof.mark("healthcheck_player_started")
    wall_init_ms = (time.perf_counter() - t0) * 1000.0

    report: dict[str, Any] = {"wall_init_ms": round(wall_init_ms, 2)}
    try:
        t_load = time.perf_counter()
        player.load_emotion(0 if EMOTIONS else 0, 60)
        report["load_emotion_ms"] = round((time.perf_counter() - t_load) * 1000.0, 2)
        prof.mark("healthcheck_load_emotion")

        # Let the generation thread and headless clock advance a few bars.
        time.sleep(1.2)
        prof.mark("healthcheck_after_warmup_sleep")

        stats = player.get_stats()
        report["playback_stats"] = stats
        report["portaudio_stream_active"] = bool(getattr(player, "stream", None) is not None)
        report["headless_no_callbacks"] = int(stats.get("callback_count", 0) or 0) <= 0
        report["buffer_underruns"] = int(stats.get("buffer_underruns", 0) or 0)
        report["callback_underflows"] = int(stats.get("callback_underflows", 0) or 0)
        report["last_gen_time_ms"] = float(stats.get("last_gen_time_ms", 0.0) or 0.0)
        report["max_gen_time_ms"] = float(stats.get("max_gen_time_ms", 0.0) or 0.0)
        report["quality_tier"] = str(stats.get("quality_tier", ""))
    finally:
        t_stop = time.perf_counter()
        player.stop()
        report["shutdown_ms"] = round((time.perf_counter() - t_stop) * 1000.0, 2)
        prof.mark("healthcheck_player_stopped")

    prof.report(title="rt_playback_health_check stages")
    print(json.dumps(report, indent=2, default=str))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
