#!/usr/bin/env python3
"""
Full system audit with composition output (offline engine + RT runtime) printed to stdout.

  .venv/bin/python tools/system_full_audit.py
  .venv/bin/python tools/system_full_audit.py --rt-seconds 15 --include-tests
"""
from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
import time
from collections import Counter, defaultdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional, Sequence, Tuple

_REPO = Path(__file__).resolve().parents[1]
if str(_REPO) not in sys.path:
    sys.path.insert(0, str(_REPO))

from audiogen_core.config_utils import resolve_project_path

CHANNEL_NAMES = {0: "bass", 1: "chords", 2: "melody", 3: "arp", 4: "drone", 5: "counter_melody", 6: "kick"}


def _event_tuple(ev: Any) -> Optional[Tuple]:
    if isinstance(ev, (list, tuple)) and len(ev) >= 5:
        return tuple(ev)
    return None


def summarize_events(events: Sequence[Any], *, beats_per_bar: float = 4.0) -> Dict[str, Any]:
    rows: List[Tuple] = []
    for ev in events or []:
        t = _event_tuple(ev)
        if t is not None:
            rows.append(t)
    by_ch: Dict[int, int] = Counter()
    starts: List[float] = []
    ends: List[float] = []
    max_dur_for_span = 64.0 * beats_per_bar  # ignore bar-long drone holds in span estimate
    for ch, midi, vel, start, dur, *_ in rows:
        by_ch[int(ch)] += 1
        s = float(start)
        d = float(dur)
        if d <= max_dur_for_span:
            starts.append(s)
            ends.append(s + d)
    span_beats = (max(ends) - min(starts)) if starts and ends else 0.0
    bars_est = span_beats / max(1e-9, float(beats_per_bar)) if span_beats > 0 else 0.0
    return {
        "event_count": len(rows),
        "channels": {CHANNEL_NAMES.get(k, str(k)): int(v) for k, v in sorted(by_ch.items())},
        "timeline_beats": {
            "start_min": round(min(starts), 3) if starts else None,
            "end_max": round(max(ends), 3) if ends else None,
            "span": round(span_beats, 3) if span_beats else 0.0,
            "bars_est": round(bars_est, 2),
        },
    }


def sample_events(events: Sequence[Any], *, max_total: int = 24) -> List[Dict[str, Any]]:
    rows: List[Tuple] = []
    for ev in events or []:
        t = _event_tuple(ev)
        if t is not None:
            rows.append(t)
    rows.sort(key=lambda e: (float(e[3]), int(e[0]), int(e[1])))
    out: List[Dict[str, Any]] = []
    per_ch: Dict[int, int] = defaultdict(int)
    for ev in rows:
        ch = int(ev[0])
        if per_ch[ch] >= 4:
            continue
        per_ch[ch] += 1
        out.append(
            {
                "channel": CHANNEL_NAMES.get(ch, str(ch)),
                "midi": int(ev[1]),
                "velocity": int(ev[2]),
                "start_beats": round(float(ev[3]), 3),
                "duration_beats": round(float(ev[4]), 3),
            }
        )
        if len(out) >= max_total:
            break
    return out


def audit_config_snapshot() -> Dict[str, Any]:
    from audiogen_core.config import CONFIG

    comp = CONFIG.composition
    audio = CONFIG.audio
    return {
        "performance_mode": getattr(CONFIG, "_performance_mode", None),
        "active_sample_pack": str(getattr(CONFIG, "active_sample_pack", "")),
        "active_style_profile": str(getattr(CONFIG, "active_style_profile", "")),
        "active_conversation_preset": str(getattr(CONFIG, "active_conversation_preset", "")),
        "composition": {
            "default_tempo": float(getattr(comp, "default_tempo", 0.0) or 0.0),
            "arranged_songs_default": bool(getattr(comp, "arranged_songs_default", False)),
            "arranged_song_mode": str(getattr(comp, "arranged_song_mode", "")),
            "section_k_samples": int(getattr(comp, "section_k_samples", 0) or 0),
            "section_pick_use_wall_clock": bool(getattr(comp, "section_pick_use_wall_clock", False)),
            "compose_runtime_mode": str(getattr(comp, "compose_runtime_mode", "")),
        },
        "audio": {
            "sample_rate": int(getattr(audio, "sample_rate", 0) or 0),
            "target_buffer_bars": int(getattr(audio, "target_buffer_bars", 0) or 0),
            "rt_reverb_default_tier": str(getattr(audio, "rt_reverb_default_tier", "")),
            "rt_bypass_master_multiband": bool(getattr(audio, "rt_bypass_master_multiband", False)),
            "reverb_wet": float(getattr(audio, "reverb_wet", 0.0) or 0.0),
        },
        "samplers": {
            str(getattr(s, "name", i)): str(getattr(s, "file_path", "") or "")
            for i, s in enumerate(getattr(CONFIG, "samplers", None) or [])
        },
    }


def audit_offline_composition(*, emotion_name: str, root: int, seed: int) -> Dict[str, Any]:
    from composition.engine import CompositionGenerator
    from composition.song_generator import SongGenerator
    from data.music_data import EMOTION_BY_NAME

    em = EMOTION_BY_NAME.get(emotion_name.strip().lower()) or EMOTION_BY_NAME.get("neutral")
    gen = CompositionGenerator(enable_perf_monitoring=False)

    t0 = time.perf_counter()
    section_events = gen.generate_section(
        em,
        root_note=int(root),
        bars=8,
        section_index=1,
        target_notes_per_bar=6.0,
    )
    section_ms = (time.perf_counter() - t0) * 1000.0

    sg = SongGenerator(composer=gen)
    specs = SongGenerator.ambient_form(
        getattr(em, "name", emotion_name),
        root_note=int(root),
        base_tempo_bpm=70.0,
        target_seconds=24.0,
        max_bars=24,
    )
    t1 = time.perf_counter()
    song = sg.generate_song(specs, base_tempo_bpm=70.0, arrangement_form="ambient", seed=int(seed))
    song_ms = (time.perf_counter() - t1) * 1000.0

    return {
        "emotion": getattr(em, "name", emotion_name),
        "root_midi": int(root),
        "seed": int(seed),
        "section_8bar": {
            "wall_ms": round(section_ms, 2),
            "summary": summarize_events(section_events),
            "samples": sample_events(section_events),
        },
        "arranged_song_ambient": {
            "wall_ms": round(song_ms, 2),
            "sections": [
                {"emotion": s.emotion_name, "bars": int(s.bars), "root": int(s.root_note)}
                for s in (specs or [])
            ],
            "summary": summarize_events(song.events or []),
            "samples": sample_events(song.events or [], max_total=32),
            "metadata_keys": sorted((song.metadata or {}).keys()) if song.metadata else [],
            "metrics": (song.metadata or {}).get("metrics") if song.metadata else None,
        },
    }


def audit_rt_runtime(*, rt_seconds: float, emotion_index: int, root: int) -> Dict[str, Any]:
    from audio.audio_container import AudioContainer
    from audio.RT_player import PolyphonicPlayer
    from composition.engine import CompositionGenerator
    from composition.song_generator import SongGenerator
    from audiogen_core.config import CONFIG
    from utils.numba_warmup import warmup_numba_kernels

    os.environ.setdefault("AUDIOGEN_PERF_MODE", "high")
    CONFIG.set_performance_mode("high")
    try:
        CONFIG.audio.rt_render_profile_enabled = True
    except Exception:
        pass
    try:
        warmup_numba_kernels()
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
            self._song_gen: Optional[SongGenerator] = None
            self.last_compose_path = ""
            self.last_compose_event_count = 0

        def generate_section_events(self, emotion, root_note, bars, **kwargs):
            self.gen.runtime_generation_mode = kwargs.get("runtime_mode", "normal")
            self.last_compose_path = "section"
            ev = self.gen.generate_section(
                emotion,
                root_note,
                bars,
                target_notes_per_bar=kwargs.get("target_notes_per_bar", 6.0),
                section_index=int(kwargs.get("section_index", 0) or 0),
                transition_handoff_context=kwargs.get("transition_handoff_context"),
            )
            self.last_compose_event_count = len(ev or [])
            return ev

        def generate_arranged_song_events(self, emotion, root_note, runtime_mode="normal"):
            self.gen.runtime_generation_mode = runtime_mode
            self.last_compose_path = "arranged_song"
            comp = getattr(self.config, "composition", None)
            mode = str(getattr(comp, "arranged_song_mode", "ambient") or "ambient")
            seconds = float(getattr(comp, "arranged_song_seconds", 24.0) or 24.0)
            max_bars = int(getattr(comp, "arranged_song_max_bars", 24) or 24)
            if self._song_gen is None:
                self._song_gen = SongGenerator(composer=self.gen)
            base = getattr(emotion, "name", "neutral")
            specs = SongGenerator.ambient_form(
                str(base),
                root_note=int(root_note),
                base_tempo_bpm=70.0,
                target_seconds=seconds,
                max_bars=max_bars,
            )
            song = self._song_gen.generate_song(
                specs, base_tempo_bpm=70.0, arrangement_form=mode, seed=0
            )
            ev = list(song.events or [])
            self.last_compose_event_count = len(ev)
            total_bars = int(sum(int(s.bars) for s in specs)) if specs else 0
            return ev, total_bars

    container = AudioContainer.create_from_config(CONFIG)
    adapter = _Adapter(gen, CONFIG)
    player = PolyphonicPlayer(adapter, CONFIG, container=container)
    sched = player.section_scheduler

    bar_log: List[Dict[str, Any]] = []
    t0 = time.perf_counter()
    try:
        player.start()
        t_load = time.perf_counter()
        player.load_emotion(int(emotion_index), int(root))
        load_ms = (time.perf_counter() - t_load) * 1000.0

        deadline = time.perf_counter() + max(2.0, float(rt_seconds))
        last_seen = -1
        while time.perf_counter() < deadline:
            time.sleep(0.12)
            stats = player.get_stats()
            bar_n = int(stats.get("chunks_generated", 0) or 0)
            if bar_n <= last_seen:
                continue
            last_seen = bar_n
            bar_events = list(getattr(player, "_debug_last_bar_events", []) or [])
            stages = dict(getattr(player.renderer, "last_stage_timing_ms", {}) or {})
            bar_log.append(
                {
                    "bar": bar_n,
                    "events_in_bar": len(bar_events),
                    "bar_summary": summarize_events(bar_events),
                    "bar_samples": sample_events(bar_events, max_total=12),
                    "render_stages_ms": {k: round(float(v), 1) for k, v in stages.items() if k != "events_total"},
                    "quality_tier": str(stats.get("quality_tier", "")),
                    "last_gen_ms": round(float(stats.get("last_gen_time_ms", 0.0) or 0.0), 1),
                }
            )
            if len(bar_log) >= 12:
                break
    finally:
        player.stop()

    section_events = list(sched.current_section_events or [])
    next_section = list(sched.next_section_events or []) if sched.next_section_events else None

    return {
        "wall_seconds": round(time.perf_counter() - t0, 2),
        "load_emotion_ms": round(load_ms, 2),
        "adapter_last_compose": {
            "path": getattr(adapter, "last_compose_path", ""),
            "event_count": int(getattr(adapter, "last_compose_event_count", 0) or 0),
        },
        "scheduler": {
            "section_index": int(getattr(sched, "section_index", 0) or 0),
            "current_section_bars": int(getattr(sched, "current_section_bars", 0) or 0),
            "next_bar_index": int(getattr(sched, "next_bar_index", 0) or 0),
            "bars_played_this_section": int(getattr(sched, "bars_played_this_section", 0) or 0),
            "arranged_song_iteration": int(getattr(sched, "_arranged_song_iteration", 0) or 0),
            "current_section_summary": summarize_events(section_events),
            "current_section_samples": sample_events(section_events, max_total=20),
            "next_section_ready": bool(getattr(sched, "next_section_ready", False)),
            "next_section_event_count": len(next_section or []),
            "arrangement_segments": list(getattr(sched, "current_arrangement_segments", None) or [])[:8],
        },
        "playback_stats": player.get_stats(),
        "bars_observed": bar_log,
    }


def _run_subprocess_step(py: str, cmd: List[str], env: Dict[str, str]) -> Dict[str, Any]:
    proc = subprocess.run(cmd, cwd=str(_REPO), env=env, capture_output=True, text=True)
    return {
        "cmd": cmd,
        "returncode": int(proc.returncode),
        "stdout_tail": "\n".join((proc.stdout or "").splitlines()[-15:]),
        "stderr_tail": "\n".join((proc.stderr or "").splitlines()[-15:]),
    }


def print_report(report: Dict[str, Any]) -> None:
    sep = "=" * 72
    print(sep)
    print("SYSTEM FULL AUDIT")
    print(f"timestamp_utc: {report.get('timestamp_utc')}")
    print(f"ok: {report.get('ok')}")
    print(sep)

    cfg = report.get("config") or {}
    print("\n## Config snapshot")
    print(json.dumps(cfg, indent=2))

    offline = report.get("offline_composition") or {}
    print("\n## Offline composition (generative engine)")
    print(f"emotion={offline.get('emotion')} root={offline.get('root_midi')} seed={offline.get('seed')}")
    sec = offline.get("section_8bar") or {}
    print(f"\n--- Section (8 bars, role index 1) — {sec.get('wall_ms')} ms ---")
    print(json.dumps(sec.get("summary"), indent=2))
    print("samples:")
    for row in sec.get("samples") or []:
        print(f"  {row}")

    song = offline.get("arranged_song_ambient") or {}
    print(f"\n--- Arranged song (ambient form) — {song.get('wall_ms')} ms ---")
    print("sections:", json.dumps(song.get("sections"), indent=2))
    print(json.dumps(song.get("summary"), indent=2))
    if song.get("metrics"):
        print("song metrics:", json.dumps(song.get("metrics"), indent=2, default=str)[:2000])
    print("samples (first per channel):")
    for row in song.get("samples") or []:
        print(f"  {row}")

    rt = report.get("rt_runtime") or {}
    print("\n## RT runtime (PolyphonicPlayer + scheduler)")
    print(f"wall={rt.get('wall_seconds')}s load_emotion={rt.get('load_emotion_ms')}ms")
    print("adapter:", json.dumps(rt.get("adapter_last_compose"), indent=2))
    sched = rt.get("scheduler") or {}
    print("\n--- Scheduler / current section buffer ---")
    print(json.dumps(
        {
            k: sched.get(k)
            for k in (
                "section_index",
                "current_section_bars",
                "next_bar_index",
                "bars_played_this_section",
                "arranged_song_iteration",
                "current_section_summary",
                "next_section_ready",
                "next_section_event_count",
                "arrangement_segments",
            )
        },
        indent=2,
        default=str,
    ))
    print("current section samples:")
    for row in sched.get("current_section_samples") or []:
        print(f"  {row}")

    print("\n--- Per-bar RT render log ---")
    for row in rt.get("bars_observed") or []:
        print(
            f"bar {row.get('bar')}: events={row.get('events_in_bar')} "
            f"gen_ms={row.get('last_gen_ms')} tier={row.get('quality_tier')} "
            f"channels={((row.get('bar_summary') or {}).get('channels'))}"
        )
        for s in row.get("bar_samples") or []:
            print(f"    {s}")

    print("\n--- Final playback stats ---")
    print(json.dumps(rt.get("playback_stats"), indent=2, default=str))

    steps = report.get("test_steps") or []
    if steps:
        print("\n## Test / health steps")
        for step in steps:
            print(f"- {step.get('name')}: rc={step.get('returncode')} ({step.get('elapsed_s', '?')}s)")
            if int(step.get("returncode", 0)) != 0:
                tail = step.get("stderr_tail") or step.get("stdout_tail") or ""
                if tail:
                    print(tail)

    print(sep)
    print(f"JSON report: {report.get('report_path')}")
    print(sep)


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--output-dir", default=".cache/system_full_audit")
    ap.add_argument("--emotion", default="neutral")
    ap.add_argument("--root", type=int, default=60)
    ap.add_argument("--seed", type=int, default=0)
    ap.add_argument("--rt-seconds", type=float, default=12.0)
    ap.add_argument("--emotion-index", type=int, default=0)
    ap.add_argument(
        "--include-tests",
        action="store_true",
        help="Run fast pytest + rt_full_audit targeted steps (slower)",
    )
    args = ap.parse_args()

    out_dir = resolve_project_path(args.output_dir)
    out_dir.mkdir(parents=True, exist_ok=True)

    report: Dict[str, Any] = {
        "timestamp_utc": datetime.now(timezone.utc).isoformat(),
        "repo": str(_REPO),
        "ok": True,
    }

    report["config"] = audit_config_snapshot()
    report["offline_composition"] = audit_offline_composition(
        emotion_name=str(args.emotion),
        root=int(args.root),
        seed=int(args.seed),
    )
    report["rt_runtime"] = audit_rt_runtime(
        rt_seconds=float(args.rt_seconds),
        emotion_index=int(args.emotion_index),
        root=int(args.root),
    )

    py = str(_REPO / ".venv" / "bin" / "python")
    if not Path(py).is_file():
        py = sys.executable
    env = os.environ.copy()
    env["AUDIOGEN_TEST_SUBPROCESS"] = "1"

    test_steps: List[Dict[str, Any]] = []
    t0 = time.perf_counter()
    health = _run_subprocess_step(
        py,
        [py, str(_REPO / "tools" / "rt_playback_health_check.py")],
        {**env, "AUDIOGEN_PERF_MODE": "high", "AUDIOGEN_RT_PROFILE": "1"},
    )
    health["elapsed_s"] = round(time.perf_counter() - t0, 2)
    health["name"] = "rt_playback_health"
    test_steps.append(health)
    if int(health.get("returncode", 1)) != 0:
        report["ok"] = False

    if args.include_tests:
        t0 = time.perf_counter()
        fast = _run_subprocess_step(
            py,
            [py, "-m", "pytest", "tests", "-q", "-m", "not slow", "--tb=line"],
            env,
        )
        fast["elapsed_s"] = round(time.perf_counter() - t0, 2)
        fast["name"] = "pytest_not_slow"
        test_steps.append(fast)
        if int(fast.get("returncode", 1)) != 0:
            report["ok"] = False

    report["test_steps"] = test_steps

    out_path = out_dir / "system_full_audit_report.json"
    report["report_path"] = str(out_path)
    out_path.write_text(json.dumps(report, indent=2, default=str))

    print_report(report)
    return 0 if report.get("ok") else 1


if __name__ == "__main__":
    raise SystemExit(main())
