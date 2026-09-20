#!/usr/bin/env python3
"""
Audit every emotion × N seeds: composition metrics, seed divergence, optional WAV/MIDI.

  .venv/bin/python tools/emotion_seed_audit.py
  .venv/bin/python tools/emotion_seed_audit.py --seeds 7,42 --preview-bars 8 --render-audio
  .venv/bin/python tools/emotion_seed_audit.py --emotions admiration,neutral,sadness --verify-repeat
"""
from __future__ import annotations

import argparse
import hashlib
import json
import sys
import time
from pathlib import Path
from typing import Any, Dict, List, Sequence, Tuple

_REPO = Path(__file__).resolve().parents[1]
if str(_REPO) not in sys.path:
    sys.path.insert(0, str(_REPO))

from tools.system_full_audit import summarize_events  # noqa: E402


def _events_fingerprint(events: Sequence[Any]) -> str:
    parts: List[str] = []
    for ev in sorted(events or [], key=lambda e: (int(e[0]), float(e[3]), int(e[1]))):
        if not ev or len(ev) < 5:
            continue
        parts.append(f"{int(ev[0])}:{int(ev[1])}:{int(ev[2])}:{float(ev[3]):.4f}:{float(ev[4]):.4f}")
    blob = "\n".join(parts).encode("utf-8")
    return hashlib.sha256(blob).hexdigest()[:16]


def _truncate_events_to_bars(events: Sequence[Any], bars: int, *, beats_per_bar: float = 4.0) -> List[Tuple]:
    end = float(bars) * float(beats_per_bar)
    out: List[Tuple] = []
    for ev in events or []:
        if not ev or len(ev) < 5:
            continue
        ch, midi, vel, st, dur = ev[0], ev[1], ev[2], float(ev[3]), float(ev[4])
        if st >= end:
            continue
        st2 = max(0.0, st)
        dur2 = min(dur, end - st2)
        if dur2 <= 1e-9:
            continue
        notes = list(ev[5]) if len(ev) > 5 else [int(midi)]
        out.append((int(ch), midi, int(vel), st2, dur2, notes))
    return out


def _prepare_config_for_seeded_compose() -> None:
    from audiogen_core.config import CONFIG

    CONFIG.composition.section_pick_use_wall_clock = False
    CONFIG.composition.joint_generation_use_wall_clock = False


def generate_emotion_song(
    *,
    emotion_name: str,
    seed: int,
    root: int,
    target_seconds: float,
    max_bars: int,
) -> Dict[str, Any]:
    from composition.engine import CompositionGenerator
    from composition.song_generator import SongGenerator
    from data.music_data import EMOTION_BY_NAME

    _prepare_config_for_seeded_compose()
    em = EMOTION_BY_NAME.get(emotion_name.strip().lower())
    if em is None:
        raise ValueError(f"Unknown emotion: {emotion_name}")

    gen = CompositionGenerator(enable_perf_monitoring=False)
    sg = SongGenerator(composer=gen)
    specs = SongGenerator.ambient_form(
        getattr(em, "name", emotion_name),
        root_note=int(root),
        base_tempo_bpm=70.0,
        target_seconds=float(target_seconds),
        max_bars=int(max_bars),
    )
    t0 = time.perf_counter()
    song = sg.generate_song(specs, base_tempo_bpm=70.0, arrangement_form="ambient", seed=int(seed))
    wall_ms = (time.perf_counter() - t0) * 1000.0
    events = list(song.events or [])
    total_bars = int(sum(int(s.bars) for s in specs)) if specs else 0
    metrics = (song.metadata or {}).get("metrics") if song.metadata else {}
    return {
        "emotion": getattr(em, "name", emotion_name),
        "seed": int(seed),
        "root_midi": int(root),
        "wall_ms": round(wall_ms, 2),
        "total_bars": total_bars,
        "event_count": len(events),
        "summary": summarize_events(events),
        "fingerprint": _events_fingerprint(events),
        "metrics": metrics,
        "song": song,
        "events": events,
    }


def render_preview_wav(
    *,
    row: Dict[str, Any],
    preview_bars: int,
    export_dir: Path,
    write_midi: bool,
) -> Dict[str, str]:
    from audiogen_core.config import CONFIG
    from tools.full_song_render import write_full_song_outputs

    events = _truncate_events_to_bars(row["events"], int(preview_bars))
    stem = f"{row['emotion']}_seed{row['seed']}"
    paths = write_full_song_outputs(
        config=CONFIG,
        song_events=events,
        total_bars=int(preview_bars),
        song_render=row["song"],
        export_dir=export_dir,
        name_prefix=stem,
        stem=stem,
        write_wav=True,
        write_midi=bool(write_midi),
        write_report=True,
    )
    row.pop("song", None)
    row.pop("events", None)
    return paths


def _metric_delta(a: Dict[str, Any], b: Dict[str, Any]) -> Dict[str, float]:
    keys = set(a.keys()) | set(b.keys())
    out: Dict[str, float] = {}
    for k in sorted(keys):
        try:
            va = float(a.get(k, 0.0) or 0.0)
            vb = float(b.get(k, 0.0) or 0.0)
            out[k] = round(vb - va, 4)
        except Exception:
            pass
    return out


def print_summary(report: Dict[str, Any]) -> None:
    sep = "=" * 88
    print(sep)
    print("EMOTION × SEED AUDIT")
    print(f"seeds={report.get('seeds')} emotions={report.get('emotion_count')} preview_bars={report.get('preview_bars')}")
    print(f"ok={report.get('ok')} repeatability_failures={len(report.get('repeatability_failures') or [])}")
    print(sep)
    print(f"{'emotion':<16} {'seed':>5} {'events':>7} {'bars':>5} {'ms':>8}  channels (b/c/m/a)")
    print("-" * 88)
    for emo_block in report.get("emotions") or []:
        name = emo_block.get("emotion", "")
        for run in emo_block.get("runs") or []:
            ch = (run.get("summary") or {}).get("channels") or {}
            chs = f"{ch.get('bass',0)}/{ch.get('chords',0)}/{ch.get('melody',0)}/{ch.get('arp',0)}"
            wav = run.get("wav_path") or ""
            print(
                f"{name:<16} {run.get('seed', ''):>5} {run.get('event_count', 0):>7} "
                f"{run.get('total_bars', 0):>5} {run.get('wall_ms', 0):>8.0f}  {chs}"
                + (f"  -> {Path(wav).name}" if wav else "")
            )
        cmp_ = emo_block.get("seed_compare") or {}
        if cmp_:
            print(
                f"  {'':16} diff: fp_match={cmp_.get('fingerprint_match')} "
                f"Δevents={cmp_.get('event_count_delta')} "
                f"lead_act Δ={((cmp_.get('metrics_delta') or {}).get('lead_activity'))}"
            )
        print()
    if report.get("repeatability_failures"):
        print("REPEATABILITY FAILURES:")
        for line in report["repeatability_failures"]:
            print(f"  - {line}")
    if report.get("errors"):
        print("ERRORS:")
        for line in report["errors"]:
            print(f"  - {line}")
    print(sep)
    print(f"JSON: {report.get('report_path')}")
    if report.get("audio_dir"):
        print(f"WAV/MIDI: {report.get('audio_dir')}")
    print(sep)


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--output-dir", default=".cache/emotion_seed_audit")
    ap.add_argument("--seeds", default="7,42", help="Comma-separated integer seeds")
    ap.add_argument("--root", type=int, default=60)
    ap.add_argument("--target-seconds", type=float, default=22.0)
    ap.add_argument("--max-bars", type=int, default=24)
    ap.add_argument("--preview-bars", type=int, default=8, help="Bars rendered to WAV per run")
    ap.add_argument("--render-audio", action="store_true", help="Write preview WAV (+ MIDI/report)")
    ap.add_argument("--midi", action="store_true", help="Also write MIDI when --render-audio")
    ap.add_argument("--emotions", default="", help="Subset comma-list; default = all EMOTIONS")
    ap.add_argument("--verify-repeat", action="store_true", help="Re-run each (emotion,seed) and require identical fingerprint")
    args = ap.parse_args()

    from data.music_data import EMOTIONS

    seeds = [int(s.strip()) for s in str(args.seeds).split(",") if s.strip()]
    if len(seeds) < 1:
        print("Need at least one seed", file=sys.stderr)
        return 1

    if str(args.emotions).strip():
        names = [e.strip().lower() for e in str(args.emotions).split(",") if e.strip()]
    else:
        names = [getattr(e, "name", str(e)).lower() for e in EMOTIONS]

    out_dir = Path(args.output_dir).expanduser()
    out_dir.mkdir(parents=True, exist_ok=True)
    audio_dir = out_dir / "audio"
    if args.render_audio:
        audio_dir.mkdir(parents=True, exist_ok=True)

    report: Dict[str, Any] = {
        "seeds": seeds,
        "emotion_count": len(names),
        "preview_bars": int(args.preview_bars),
        "render_audio": bool(args.render_audio),
        "emotions": [],
        "errors": [],
        "repeatability_failures": [],
        "ok": True,
    }

    t_all = time.perf_counter()
    for idx, emo_name in enumerate(names):
        emo_block: Dict[str, Any] = {"emotion": emo_name, "runs": []}
        runs_by_seed: Dict[int, Dict[str, Any]] = {}
        print(f"[{idx + 1}/{len(names)}] {emo_name}", file=sys.stderr, flush=True)
        for seed in seeds:
            try:
                row = generate_emotion_song(
                    emotion_name=emo_name,
                    seed=int(seed),
                    root=int(args.root),
                    target_seconds=float(args.target_seconds),
                    max_bars=int(args.max_bars),
                )
                if args.verify_repeat:
                    row2 = generate_emotion_song(
                        emotion_name=emo_name,
                        seed=int(seed),
                        root=int(args.root),
                        target_seconds=float(args.target_seconds),
                        max_bars=int(args.max_bars),
                    )
                    if row2["fingerprint"] != row["fingerprint"]:
                        report["repeatability_failures"].append(
                            f"{emo_name} seed={seed}: fp {row['fingerprint']} != {row2['fingerprint']}"
                        )
                        report["ok"] = False

                paths: Dict[str, str] = {}
                if args.render_audio:
                    t_r = time.perf_counter()
                    paths = render_preview_wav(
                        row=row,
                        preview_bars=int(args.preview_bars),
                        export_dir=audio_dir,
                        write_midi=bool(args.midi),
                    )
                    row["render_ms"] = round((time.perf_counter() - t_r) * 1000.0, 2)
                    row["wav_path"] = paths.get("wav", "")
                    row["midi_path"] = paths.get("midi", "")
                    row["report_json"] = paths.get("report_json", "")
                else:
                    row.pop("song", None)
                    row.pop("events", None)

                runs_by_seed[int(seed)] = row
                emo_block["runs"].append(row)
            except Exception as exc:
                report["errors"].append(f"{emo_name} seed={seed}: {exc}")
                report["ok"] = False

        if len(runs_by_seed) >= 2:
            s0, s1 = seeds[0], seeds[1]
            if s0 in runs_by_seed and s1 in runs_by_seed:
                a, b = runs_by_seed[s0], runs_by_seed[s1]
                emo_block["seed_compare"] = {
                    "seeds": [s0, s1],
                    "fingerprint_match": a["fingerprint"] == b["fingerprint"],
                    "event_count_delta": int(b["event_count"]) - int(a["event_count"]),
                    "metrics_delta": _metric_delta(
                        dict(a.get("metrics") or {}),
                        dict(b.get("metrics") or {}),
                    ),
                }
                if a["fingerprint"] == b["fingerprint"]:
                    report["errors"].append(f"{emo_name}: seeds {s0} and {s1} produced identical events")
                    report["ok"] = False

        report["emotions"].append(emo_block)

    report["wall_seconds"] = round(time.perf_counter() - t_all, 2)
    report["audio_dir"] = str(audio_dir) if args.render_audio else ""
    out_path = out_dir / "emotion_seed_audit.json"
    report["report_path"] = str(out_path)
    # JSON-safe (no song objects left)
    out_path.write_text(json.dumps(report, indent=2, default=str))
    print_summary(report)
    return 0 if report.get("ok") else 1


if __name__ == "__main__":
    raise SystemExit(main())
