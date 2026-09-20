#!/usr/bin/env python3
"""
Realtime audio benchmark + output quality snapshot.

Example:
  python tools/benchmark_realtime_audio.py --seconds 10 --output .cache/rt_benchmark.json
"""
from __future__ import annotations

import argparse
import json
import logging
import os
import sys
import time
from collections import Counter
from typing import Any, Dict, List

import numpy as np

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from audiogen_core.config_utils import resolve_project_path

logger = logging.getLogger(__name__)


class _LogCaptureHandler(logging.Handler):
    """Capture selected log lines for benchmark reports."""

    def __init__(self) -> None:
        super().__init__(level=logging.WARNING)
        self.rows: List[Dict[str, Any]] = []

    def emit(self, record: logging.LogRecord) -> None:  # pragma: no cover
        try:
            msg = str(record.getMessage() or "")
        except Exception:
            return
        if "rt_cprofile slow bar" not in msg:
            return
        self.rows.append(
            {
                "logger": str(record.name),
                "level": str(record.levelname),
                "message": msg,
            }
        )


def _audio_metrics(audio: np.ndarray, sample_rate: int) -> Dict[str, float]:
    x = np.asarray(audio, dtype=np.float32)
    if x.ndim == 2 and x.shape[1] >= 2:
        mono = 0.5 * (x[:, 0] + x[:, 1])
    elif x.ndim == 2:
        mono = x[:, 0]
    else:
        mono = x.reshape(-1)
    mono = np.nan_to_num(np.asarray(mono, dtype=np.float32), nan=0.0, posinf=0.0, neginf=0.0)
    if mono.size == 0:
        return {
            "peak": 0.0,
            "rms": 0.0,
            "crest_db": 0.0,
            "true_peak_est": 0.0,
            "spectral_tilt_db_per_oct": 0.0,
        }
    peak = float(np.max(np.abs(mono))) if mono.size else 0.0
    rms = float(np.sqrt(np.mean(mono * mono) + 1e-12)) if mono.size else 0.0
    crest = float(20.0 * np.log10(max(1e-9, peak / max(1e-9, rms))))

    # Quick true-peak estimate via 2x linear interpolation.
    n = int(mono.shape[0])
    if n > 1:
        src = np.arange(n, dtype=np.float32)
        dst = np.linspace(0.0, float(n - 1), n * 2, dtype=np.float32)
        up = np.interp(dst, src, mono).astype(np.float32)
        true_peak = float(np.max(np.abs(up)))
    else:
        true_peak = peak

    # Spectral tilt: slope of log-mag (dB) vs log2(freq), excluding sub/nyquist edges.
    tilt = 0.0
    try:
        win = np.hanning(len(mono)).astype(np.float32)
        spec = np.fft.rfft((mono * win).astype(np.float32))
        mag = np.maximum(1e-9, np.abs(spec))
        freqs = np.fft.rfftfreq(len(mono), d=1.0 / max(1.0, float(sample_rate)))
        mask = (freqs >= 40.0) & (freqs <= min(18000.0, sample_rate * 0.45))
        if np.any(mask):
            x_log2 = np.log2(freqs[mask])
            y_db = 20.0 * np.log10(mag[mask])
            p = np.polyfit(x_log2, y_db, deg=1)
            tilt = float(p[0])
    except Exception:
        tilt = 0.0

    return {
        "peak": peak,
        "rms": rms,
        "crest_db": crest,
        "true_peak_est": true_peak,
        "spectral_tilt_db_per_oct": tilt,
    }



def _percentile(xs: List[float], q: float) -> float:
    if not xs:
        return 0.0
    ys = sorted(float(x) for x in xs)
    n = len(ys)
    if n == 1:
        return float(ys[0])
    q = min(1.0, max(0.0, float(q)))
    pos = q * (n - 1)
    lo = int(pos)
    hi = min(n - 1, lo + 1)
    frac = pos - lo
    return float(ys[lo] * (1.0 - frac) + ys[hi] * frac)


def summarize_stage_samples(samples: List[Dict[str, Any]]) -> Dict[str, Any]:
    """Aggregate per-bar realtime stage timings into a compact bottleneck report."""
    rows = list(samples or [])
    stage_keys = ("mono", "chords", "mix", "master")
    stage_values: Dict[str, List[float]] = {k: [] for k in stage_keys}
    total_values: List[float] = []
    ratios: List[float] = []
    culprit_counts: Counter[str] = Counter()

    for row in rows:
        stages = dict(row.get("stages_ms") or {})
        for key in stage_keys:
            try:
                stage_values[key].append(float(stages.get(key, 0.0) or 0.0))
            except Exception:
                stage_values[key].append(0.0)
        try:
            total_values.append(float(stages.get("total", row.get("total_ms", 0.0)) or 0.0))
        except Exception:
            total_values.append(0.0)
        try:
            ratios.append(float(row.get("render_ratio", 0.0) or 0.0))
        except Exception:
            ratios.append(0.0)
        culprit = str(row.get("culprit", "") or "").strip().lower()
        if culprit:
            culprit_counts[culprit] += 1

    def _mean(xs: List[float]) -> float:
        return float(sum(xs) / max(1, len(xs)))

    def _max(xs: List[float]) -> float:
        return float(max(xs)) if xs else 0.0

    means = {k: round(_mean(v), 3) for k, v in stage_values.items()}
    maxes = {k: round(_max(v), 3) for k, v in stage_values.items()}
    dominant_stage = max(means.items(), key=lambda kv: float(kv[1]))[0] if means else "unknown"
    culprit = culprit_counts.most_common(1)[0][0] if culprit_counts else dominant_stage
    p95 = {k: round(_percentile(v, 0.95), 3) for k, v in stage_values.items()}
    p99 = {k: round(_percentile(v, 0.99), 3) for k, v in stage_values.items()}

    cache_deltas: List[int] = []
    spike_bars = 0
    for row in rows:
        try:
            ratio = float(row.get("render_ratio", 0.0) or 0.0)
        except Exception:
            ratio = 0.0
        if ratio > 1.0:
            spike_bars += 1
        delta = dict(row.get("sampler_cache_delta") or {})
        try:
            cache_deltas.append(int(delta.get("chord_cache_entries", 0) or 0))
        except Exception:
            cache_deltas.append(0)

    return {
        "bars_profiled": int(len(rows)),
        "dominant_stage": str(dominant_stage),
        "dominant_culprit": str(culprit),
        "stage_mean_ms": means,
        "stage_max_ms": maxes,
        "stage_p95_ms": p95,
        "stage_p99_ms": p99,
        "total_mean_ms": round(_mean(total_values), 3),
        "total_max_ms": round(_max(total_values), 3),
        "total_p95_ms": round(_percentile(total_values, 0.95), 3),
        "total_p99_ms": round(_percentile(total_values, 0.99), 3),
        "render_ratio_mean": round(_mean(ratios), 4),
        "render_ratio_max": round(_max(ratios), 4),
        "render_ratio_p95": round(_percentile(ratios, 0.95), 4),
        "render_ratio_p99": round(_percentile(ratios, 0.99), 4),
        "over_budget_bars": int(sum(1 for r in ratios if float(r) > 1.0)),
        "near_budget_bars": int(sum(1 for r in ratios if float(r) >= 0.85)),
        "spike_bars": int(spike_bars),
        "chord_cache_delta_max": int(max(cache_deltas)) if cache_deltas else 0,
        "culprit_counts": {str(k): int(v) for k, v in culprit_counts.items()},
    }


def evaluate_stage_profile(
    summary: Dict[str, Any],
    *,
    max_render_ratio: float = 0.0,
    max_over_budget_bars: int = -1,
    min_profiled_bars: int = 0,
) -> Dict[str, Any]:
    """Return pass/fail details for optional realtime performance gates."""
    failures: List[str] = []
    try:
        bars = int(summary.get("bars_profiled", 0) or 0)
    except Exception:
        bars = 0
    if int(min_profiled_bars) > 0 and bars < int(min_profiled_bars):
        failures.append(f"profiled bars {bars} < required {int(min_profiled_bars)}")
    try:
        ratio_max = float(summary.get("render_ratio_max", 0.0) or 0.0)
    except Exception:
        ratio_max = 0.0
    if float(max_render_ratio) > 0.0 and ratio_max > float(max_render_ratio):
        failures.append(f"max render ratio {ratio_max:.3f} > {float(max_render_ratio):.3f}")
    try:
        over = int(summary.get("over_budget_bars", 0) or 0)
    except Exception:
        over = 0
    if int(max_over_budget_bars) >= 0 and over > int(max_over_budget_bars):
        failures.append(f"over-budget bars {over} > allowed {int(max_over_budget_bars)}")
    return {"ok": not failures, "failures": failures}


def summarize_cold_start(
    *,
    stats: Dict[str, Any],
    stage_samples: List[Dict[str, Any]],
    init_ms: float,
    elapsed_ms: float,
) -> Dict[str, Any]:
    """Summarize cold-start and first-profiled-bar timing separately from steady-state."""
    first = dict(stage_samples[0]) if stage_samples else {}
    first_stages = dict(first.get("stages_ms") or {})

    def _float(value: Any, default: float = 0.0) -> float:
        try:
            return float(value)
        except Exception:
            return float(default)

    return {
        "init_ms": round(_float(init_ms), 2),
        "elapsed_ms": round(_float(elapsed_ms), 2),
        "emotion_switch_latency_ms": round(_float(stats.get("last_emotion_switch_latency_ms", 0.0)), 2),
        "emotion_switch_stage": str(stats.get("last_emotion_switch_stage", "") or ""),
        "section_compose_ms": round(_float(stats.get("last_section_compose_time_ms", 0.0)), 2),
        "first_profiled_chunk": int(first.get("chunk", 0) or 0),
        "first_profiled_elapsed_ms": round(_float(first.get("elapsed_ms", 0.0)), 2),
        "first_profiled_render_ratio": round(_float(first.get("render_ratio", 0.0)), 4),
        "first_profiled_total_ms": round(_float(first_stages.get("total", 0.0)), 3),
        "first_profiled_dominant_stage": str(first.get("culprit", "") or ""),
        "chunks_generated": int(stats.get("chunks_generated", 0) or 0),
    }


def evaluate_cold_start(summary: Dict[str, Any], *, max_cold_start_ms: float = 0.0) -> Dict[str, Any]:
    """Return pass/fail details for optional cold-start gates."""
    failures: List[str] = []
    try:
        max_ms = float(max_cold_start_ms)
    except Exception:
        max_ms = 0.0
    if max_ms > 0.0:
        try:
            first_ms = float(summary.get("first_profiled_elapsed_ms", 0.0) or 0.0)
        except Exception:
            first_ms = 0.0
        if first_ms <= 0.0:
            failures.append("no profiled first bar for cold-start gate")
        elif first_ms > max_ms:
            failures.append(f"first profiled bar {first_ms:.1f}ms > allowed {max_ms:.1f}ms")
    return {"ok": not failures, "failures": failures}


def sampler_cache_snapshot(player: Any) -> Dict[str, Any]:
    """Best-effort cache counters for interpreting chord-stage timings."""
    out: Dict[str, Any] = {}
    engine = getattr(player, "synthesis_engine", None)
    if engine is None:
        return out

    try:
        chord_renderer = engine._get_chord_renderer()
    except Exception:
        chord_renderer = getattr(engine, "chord_renderer", None)
    if chord_renderer is not None:
        try:
            out["chord_cache_entries"] = int(len(getattr(chord_renderer, "cache", {}) or {}))
        except Exception:
            pass
        try:
            out["chord_cache_bytes"] = int(getattr(chord_renderer, "_cache_bytes", 0) or 0)
        except Exception:
            pass

    sampler = None
    try:
        samplers = getattr(engine, "samplers", {}) or {}
        sampler = samplers.get("chords")
    except Exception:
        sampler = None
    if sampler is None:
        try:
            registry = getattr(engine, "registry", None)
            samplers = getattr(registry, "samplers", {}) if registry is not None else {}
            sampler = (samplers or {}).get("chords")
        except Exception:
            sampler = None
    if sampler is not None:
        cfg = getattr(sampler, "config", None)
        try:
            out["chord_sampler_note_cache_entries"] = int(len(getattr(sampler, "_note_cache", {}) or {}))
        except Exception:
            pass
        try:
            out["chord_sampler_random_start"] = bool(getattr(cfg, "random_start_within_loop", False))
        except Exception:
            pass
        try:
            out["chord_sampler_shimmer"] = bool(getattr(cfg, "shimmer_enabled", False))
        except Exception:
            pass
        try:
            out["chord_sampler_note_cache_maxsize"] = int(getattr(sampler, "NOTE_CACHE_MAXSIZE", 0) or 0)
        except Exception:
            pass
    return out


def scheduler_snapshot(player: Any) -> Dict[str, Any]:
    """Best-effort scheduler fields for correlating spikes with transitions."""
    out: Dict[str, Any] = {}
    try:
        sched = getattr(player, "section_scheduler", None)
    except Exception:
        sched = None
    if sched is None:
        return out

    def _int(name: str) -> int:
        try:
            return int(getattr(sched, name, 0) or 0)
        except Exception:
            return 0

    def _bool(name: str) -> bool:
        try:
            return bool(getattr(sched, name, False))
        except Exception:
            return False

    def _str(name: str) -> str:
        try:
            return str(getattr(sched, name, "") or "")
        except Exception:
            return ""

    out["section_index"] = _int("section_index")
    out["current_section_bars"] = _int("current_section_bars")
    out["next_bar_index"] = _int("next_bar_index")
    out["bars_played_this_section"] = _int("bars_played_this_section")
    out["arranged_song_iteration"] = _int("_arranged_song_iteration")
    out["next_section_ready"] = _bool("next_section_ready")
    out["pending_emotion_set"] = _bool("pending_emotion")
    out["pending_root_set"] = _bool("pending_root")
    # Optional debug hint if present.
    out["arrangement_role_hint"] = _str("_arrangement_role_hint")
    return out



def run_realtime_benchmark(
    *,
    seconds: float = 10.0,
    emotion: str = "neutral",
    root: int = 60,
    performance: str = "low",
    max_render_ratio: float = 0.0,
    max_over_budget_bars: int = -1,
    min_profiled_bars: int = 0,
    gate_warmup_bars: int = 0,
    max_cold_start_ms: float = 0.0,
) -> Dict[str, Any]:
    """
    Run the realtime benchmark and return a JSON-serializable report.

    The returned report shape is intentionally aligned with the original CLI output
    (stage samples, stage summary, optional gate summaries, cold-start summary, etc.).
    """
    from audio.audio_container import AudioContainer
    from audio.RT_player import PolyphonicPlayer
    from composition.engine import CompositionGenerator
    from audiogen_core.config import CONFIG
    from data.music_data import EMOTION_BY_NAME, EMOTIONS

    CONFIG.set_performance_mode(str(performance))
    CONFIG.audio.target_buffer_bars = max(6, int(getattr(CONFIG.audio, "target_buffer_bars", 8) or 8))
    CONFIG.audio.startup_preroll_bars = max(2, int(getattr(CONFIG.audio, "startup_preroll_bars", 2) or 2))
    try:
        CONFIG.rebuild_samplers()
    except Exception:
        pass

    em_name = str(emotion).strip().lower()
    em = EMOTION_BY_NAME.get(em_name)
    if em is None:
        em = EMOTION_BY_NAME.get("neutral")
    em_index = 0
    try:
        if em is not None:
            em_name_norm = str(getattr(em, "name", "")).strip().lower()
            for i, cand in enumerate(list(EMOTIONS or [])):
                if str(getattr(cand, "name", "")).strip().lower() == em_name_norm:
                    em_index = int(i)
                    break
    except Exception:
        em_index = 0

    gen = CompositionGenerator(enable_perf_monitoring=False)

    class _Adapter:
        def __init__(self, g):
            self.gen = g

        def generate_section_events(
            self,
            emotion,
            root,
            bars,
            target_notes_per_bar=6.0,
            runtime_mode="normal",
            planner_effort=None,
            section_index=0,
            transition_handoff_context=None,
        ):
            prev_effort = getattr(self.gen, "runtime_planner_effort_override", None)
            self.gen.runtime_generation_mode = runtime_mode
            if planner_effort:
                self.gen.runtime_planner_effort_override = str(planner_effort)
            try:
                return self.gen.generate_section(
                    emotion,
                    root,
                    bars,
                    target_notes_per_bar=target_notes_per_bar,
                    section_index=section_index,
                    transition_handoff_context=transition_handoff_context,
                )
            finally:
                try:
                    self.gen.runtime_planner_effort_override = prev_effort
                except Exception:
                    pass

        def generate_arranged_preview_events(self, emotion, root, runtime_mode="normal", preview_sections=2):
            comp = getattr(CONFIG, "composition", None)
            bars_per_section = int(getattr(comp, "bars_per_section", 4) or 4) if comp is not None else 4
            audio_cfg = getattr(CONFIG, "audio", None)
            planner_effort = (
                str(getattr(audio_cfg, "cold_start_preview_planner_effort", "minimal") or "minimal")
                if str(runtime_mode).strip().lower() in {"preview", "cold_preview"}
                else None
            )
            events = []
            n = max(1, int(preview_sections))
            for idx in range(n):
                events.extend(
                    self.generate_section_events(
                        emotion,
                        root,
                        bars_per_section,
                        runtime_mode=runtime_mode,
                        planner_effort=planner_effort,
                        section_index=int(idx),
                    )
                )
            return events, int(n * bars_per_section)

    t0 = time.perf_counter()
    container = AudioContainer.create_from_config(CONFIG)
    player = PolyphonicPlayer(_Adapter(gen), CONFIG, container=container)
    # Prewarm chord cache and mix/master paths to reduce mid-run spikes.
    try:
        tempo_hint = float(getattr(getattr(CONFIG, "composition", None), "default_tempo", 70.0) or 70.0)
    except Exception:
        tempo_hint = 70.0
    try:
        sr = int(getattr(CONFIG.audio, "sample_rate", 44100) or 44100)
    except Exception:
        sr = 44100
    from audio.rt_prewarm import run_rt_prewarm

    prewarm_report = run_rt_prewarm(
        player,
        root_note=int(root),
        tempo_bpm=float(tempo_hint),
        sample_rate=int(sr),
        chord_cache=True,
        mono_cache=bool(getattr(getattr(CONFIG, "audio", None), "rt_mono_cache_prewarm_enabled", False)),
        mix_master=True,
    )
    report_prewarm = prewarm_report.get("chords", {})
    report_mono_prewarm = prewarm_report.get("mono", {})
    report_warmup = prewarm_report.get("mix_master", {})
    # Capture any slow-bar cProfile dumps (logged by player thread when enabled via env).
    cap = _LogCaptureHandler()
    root_logger = logging.getLogger()
    root_logger.addHandler(cap)
    player.start()
    setup_done = time.perf_counter()

    report: Dict[str, Any] = {
        "run_seconds": float(seconds),
        "emotion": getattr(em, "name", "neutral"),
        "performance": str(performance),
        "sample_rate": int(getattr(CONFIG.audio, "sample_rate", 0) or 0),
        "buffer_size": int(getattr(CONFIG.audio, "buffer_size", 0) or 0),
        "reverb_rt60": float(getattr(CONFIG.audio, "reverb_rt60", 0.0) or 0.0),
        "reverb_wet": float(getattr(CONFIG.audio, "reverb_wet", 0.0) or 0.0),
        "delay_bus_enabled": bool(getattr(CONFIG.audio, "delay_bus_enabled", False)),
        "prewarm": {"chords": report_prewarm, "mono": report_mono_prewarm, "mix_master": report_warmup},
    }
    try:
        player.load_emotion(int(em_index), int(root))
        stage_samples: List[Dict[str, Any]] = []
        deadline = time.perf_counter() + max(0.5, float(seconds))
        last_seen = 0
        last_cache: Dict[str, Any] = {}
        while time.perf_counter() < deadline:
            time.sleep(0.10)
            stats_now = player.get_stats()
            try:
                chunks = int(stats_now.get("chunks_generated", 0) or 0)
            except Exception:
                chunks = 0
            if chunks <= 0 or chunks <= last_seen:
                continue
            last_seen = chunks
            stages = dict(stats_now.get("gen_stage_last_ms") or {})
            try:
                bar_seconds = float(player.current_bar_seconds)
            except Exception:
                try:
                    bar_seconds = float(getattr(player, "_rt_profile_bar_seconds", 0.0) or 0.0)
                except Exception:
                    bar_seconds = 0.0
            total_ms = float(stages.get("total", 0.0) or 0.0)
            if bar_seconds > 0.0:
                render_ratio = (total_ms / 1000.0) / max(0.001, float(bar_seconds))
            else:
                render_ratio = 0.0
            cache_now = sampler_cache_snapshot(player)
            # Small derived signals to correlate cache churn with spikes.
            try:
                chord_entries = int(cache_now.get("chord_cache_entries", 0) or 0)
            except Exception:
                chord_entries = 0
            try:
                prev_entries = int(last_cache.get("chord_cache_entries", chord_entries) or chord_entries)
            except Exception:
                prev_entries = chord_entries
            cache_delta = chord_entries - prev_entries
            last_cache = dict(cache_now)
            stage_samples.append(
                {
                    "chunk": int(chunks),
                    "elapsed_ms": round((time.perf_counter() - t0) * 1000.0, 2),
                    "quality_tier": str(stats_now.get("quality_tier", "")),
                    "culprit": str(stats_now.get("gen_culprit", "")),
                    "bar_seconds": round(float(bar_seconds), 4),
                    "render_ratio": round(float(render_ratio), 4),
                    "stages_ms": {str(k): round(float(v), 3) for k, v in stages.items()},
                    "sampler_cache": cache_now,
                    "sampler_cache_delta": {"chord_cache_entries": int(cache_delta)},
                    "scheduler": scheduler_snapshot(player),
                }
            )
        stats = player.get_stats()
        init_ms = round((setup_done - t0) * 1000.0, 2)
        elapsed_ms = round((time.perf_counter() - t0) * 1000.0, 2)
        report["init_ms"] = init_ms
        report["elapsed_ms"] = elapsed_ms
        report["playback_stats"] = stats
        report["stage_samples"] = stage_samples
        report["stage_summary"] = summarize_stage_samples(stage_samples)
        gate_warmup = max(0, int(gate_warmup_bars))
        gate_samples = stage_samples[gate_warmup:] if gate_warmup > 0 else stage_samples
        report["stage_gate_warmup_bars"] = int(gate_warmup)
        report["stage_gate_summary"] = summarize_stage_samples(gate_samples)
        report["stage_gate"] = evaluate_stage_profile(
            report["stage_gate_summary"],
            max_render_ratio=float(max_render_ratio),
            max_over_budget_bars=int(max_over_budget_bars),
            min_profiled_bars=int(min_profiled_bars),
        )
        report["cold_start"] = summarize_cold_start(
            stats=stats,
            stage_samples=stage_samples,
            init_ms=float(init_ms),
            elapsed_ms=float(elapsed_ms),
        )
        report["cold_start_gate"] = evaluate_cold_start(
            report["cold_start"],
            max_cold_start_ms=float(max_cold_start_ms),
        )
        report["sampler_cache"] = sampler_cache_snapshot(player)
        report["rt_cprofile_slow_bars"] = list(cap.rows)
        report["buffer_underruns"] = int(stats.get("buffer_underruns", 0) or 0)
        report["callback_underflows"] = int(stats.get("callback_underflows", 0) or 0)
        report["quality_tier"] = str(stats.get("quality_tier", ""))
        report["render_watchdog_triggers"] = int(stats.get("rt_watchdog_triggered_count", 0) or 0)
        report["audio_metrics"] = _audio_metrics(
            getattr(player, "_last_generated_audio", np.zeros((0, 2), dtype=np.float32)),
            sample_rate=int(getattr(CONFIG.audio, "sample_rate", 44100)),
        )
    finally:
        t_stop = time.perf_counter()
        player.stop()
        report["shutdown_ms"] = round((time.perf_counter() - t_stop) * 1000.0, 2)
        try:
            root_logger.removeHandler(cap)
        except Exception:
            pass

    return report


def main() -> int:
    ap = argparse.ArgumentParser(add_help=True)
    ap.add_argument("--seconds", type=float, default=10.0, help="Benchmark run duration")
    ap.add_argument("--emotion", default="neutral", help="Emotion name")
    ap.add_argument("--root", type=int, default=60, help="Root MIDI")
    ap.add_argument(
        "--performance",
        default="low",
        choices=("low", "high", "quality", "maximum", "balanced"),
        help="CONFIG performance mode (high=quality FX, low=RT-safe)",
    )
    ap.add_argument("--output", default=".cache/rt_benchmark.json", help="Output JSON path")
    ap.add_argument(
        "--max-render-ratio",
        type=float,
        default=0.0,
        help="Fail if profiled max render/bar ratio exceeds this; 0 disables",
    )
    ap.add_argument(
        "--max-over-budget-bars",
        type=int,
        default=-1,
        help="Fail if profiled over-budget bar count exceeds this; -1 disables",
    )
    ap.add_argument(
        "--min-profiled-bars",
        type=int,
        default=0,
        help="Fail if fewer bars are profiled; 0 disables",
    )
    ap.add_argument(
        "--gate-warmup-bars",
        type=int,
        default=0,
        help="Ignore this many initial profiled bars for stage gate thresholds",
    )
    ap.add_argument(
        "--max-cold-start-ms",
        type=float,
        default=0.0,
        help="Fail if first profiled bar appears after this many ms; 0 disables",
    )
    ap.add_argument(
        "--baseline",
        type=str,
        default="",
        help="Path to a previous benchmark JSON to diff current results against",
    )
    args = ap.parse_args()

    report = run_realtime_benchmark(
        seconds=float(args.seconds),
        emotion=str(args.emotion),
        root=int(args.root),
        performance=str(args.performance),
        max_render_ratio=float(args.max_render_ratio),
        max_over_budget_bars=int(args.max_over_budget_bars),
        min_profiled_bars=int(args.min_profiled_bars),
        gate_warmup_bars=int(args.gate_warmup_bars),
        max_cold_start_ms=float(args.max_cold_start_ms),
    )

    out_path = resolve_project_path(str(args.output))
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(json.dumps(report, indent=2, sort_keys=True))

    # ------------------------------------------------------------------
    # Baseline comparison (if --baseline path is provided).
    # ------------------------------------------------------------------
    baseline_path = str(args.baseline or "").strip()
    if baseline_path:
        bp = resolve_project_path(baseline_path)
        if bp.is_file():
            try:
                baseline = json.loads(bp.read_text())
            except Exception as exc:
                logger.warning("Cannot load baseline %s: %s", baseline_path, exc)
                baseline = None
            if baseline:
                prev_summary = baseline.get("stage_summary") or {}
                cur_summary = report.get("stage_summary") or {}
                diff: Dict[str, Any] = {}
                for key in ("total_mean_ms", "total_max_ms", "total_p95_ms", "total_p99_ms",
                            "render_ratio_mean", "render_ratio_max", "render_ratio_p95", "render_ratio_p99",
                            "over_budget_bars", "near_budget_bars", "spike_bars"):
                    pv = prev_summary.get(key)
                    cv = cur_summary.get(key)
                    if pv is not None and cv is not None:
                        try:
                            delta = round(float(cv) - float(pv), 3)
                        except Exception:
                            delta = None
                        if delta is not None:
                            diff[key] = {"baseline": float(pv), "current": float(cv), "delta": delta}
                # Stage breakdown deltas.
                for kind in ("stage_mean_ms", "stage_max_ms", "stage_p95_ms", "stage_p99_ms"):
                    prev_s = prev_summary.get(kind, {}) or {}
                    cur_s = cur_summary.get(kind, {}) or {}
                    for stage_key in ("mono", "chords", "mix", "master"):
                        pv = prev_s.get(stage_key)
                        cv = cur_s.get(stage_key)
                        if pv is not None and cv is not None:
                            d = round(float(cv) - float(pv), 3)
                            label = f"{kind}.{stage_key}"
                            if label not in diff:
                                diff[label] = {}
                            diff[label].update({"baseline": float(pv), "current": float(cv), "delta": d})
                # Cold-start comparison.
                prev_cs = baseline.get("cold_start") or {}
                cur_cs = report.get("cold_start") or {}
                for key in ("init_ms", "first_profiled_elapsed_ms", "first_profiled_render_ratio",
                            "first_profiled_total_ms", "chunks_generated"):
                    pv = prev_cs.get(key)
                    cv = cur_cs.get(key)
                    if pv is not None and cv is not None:
                        try:
                            d = round(float(cv) - float(pv), 3)
                        except Exception:
                            d = None
                        if d is not None:
                            diff[key] = {"baseline": float(pv), "current": float(cv), "delta": d}
                # Audio quality deltas.
                prev_audio = baseline.get("audio_metrics") or {}
                cur_audio = report.get("audio_metrics") or {}
                for key in ("peak", "rms", "crest_db", "true_peak_est", "spectral_tilt_db_per_oct"):
                    pv = prev_audio.get(key)
                    cv = cur_audio.get(key)
                    if pv is not None and cv is not None:
                        try:
                            d = round(float(cv) - float(pv), 3)
                        except Exception:
                            d = None
                        if d is not None:
                            diff[key] = {"baseline_audio": float(pv), "current_audio": float(cv), "delta": d}
                report["baseline_diff"] = {
                    "baseline_path": str(bp),
                    "baseline_emotion": baseline.get("emotion", "?"),
                    "baseline_performance": baseline.get("performance", "?"),
                    "deltas": diff,
                }
                # Print diff side-by-side if any.
                if diff:
                    print("\n--- Baseline diff ---")
                    print(f"  vs {baseline_path}")
                    for key, dv in sorted(diff.items()):
                        b = dv.get("baseline") if "baseline" in dv else dv.get("baseline_audio", "?")
                        c = dv.get("current") if "current" in dv else dv.get("current_audio", "?")
                        d = dv.get("delta", "?")
                        print(f"  {key:<40s}  baseline={str(b):<10s}  current={str(c):<10s}  delta={d}")
                else:
                    print("\n--- Baseline diff (no comparable keys) ---")
        else:
            print(f"\n--- Baseline not found: {baseline_path} ---")

    out_path.write_text(json.dumps(report, indent=2, sort_keys=True))
    print(json.dumps(report, indent=2, sort_keys=True))
    gates_ok = bool((report.get("stage_gate") or {}).get("ok", True)) and bool(
        (report.get("cold_start_gate") or {}).get("ok", True)
    )
    return 0 if gates_ok else 2


if __name__ == "__main__":
    raise SystemExit(main())
