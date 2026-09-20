#!/usr/bin/env python3
"""Generate and score arranged songs for musical quality regression audits."""

from __future__ import annotations

import argparse
import json
import math
import sys
import time
from collections import Counter, defaultdict
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional, Sequence, Tuple

_REPO = Path(__file__).resolve().parents[1]
if str(_REPO) not in sys.path:
    sys.path.insert(0, str(_REPO))

from audiogen_core.config_utils import resolve_project_path

CHANNEL_NAMES = {
    0: "bass",
    1: "chords",
    2: "melody",
    3: "arp",
    4: "drone",
    5: "counter_melody",
    6: "kick",
}
CORE_CHANNELS = {0: "bass", 1: "chords", 2: "melody"}
DEFAULT_EMOTIONS = ("neutral", "sadness", "joy", "anger", "relief")
DEFAULT_SEEDS = (101, 202)
DEFAULT_FORMS = ("default", "ambient")


def _parse_csv(value: str) -> List[str]:
    return [x.strip() for x in str(value or "").split(",") if x.strip()]


def _parse_int_csv(value: str) -> List[int]:
    out = []
    for raw in _parse_csv(value):
        out.append(int(raw))
    return out


def _event_rows(events: Sequence[Any]) -> List[Tuple[int, int, int, float, float, Tuple[int, ...]]]:
    rows: List[Tuple[int, int, int, float, float, Tuple[int, ...]]] = []
    for ev in events or []:
        if not isinstance(ev, (list, tuple)) or len(ev) != 6:
            continue
        try:
            ch = int(ev[0])
            midi = int(ev[1])
            vel = int(ev[2])
            start = float(ev[3])
            dur = float(ev[4])
            notes_raw = ev[5]
            if isinstance(notes_raw, (list, tuple)):
                notes = tuple(int(n) for n in notes_raw)
            else:
                notes = (midi,)
        except Exception:
            continue
        rows.append((ch, midi, vel, start, dur, notes))
    rows.sort(key=lambda row: (row[3], row[0], row[1]))
    return rows


def _bar_signatures(
    rows: Sequence[Tuple[int, int, int, float, float, Tuple[int, ...]]],
    *,
    bars: int,
    beats_per_bar: float,
) -> List[Tuple[Tuple[int, float, Tuple[int, ...]], ...]]:
    buckets: List[List[Tuple[int, float, Tuple[int, ...]]]] = [[] for _ in range(max(0, int(bars)))]
    for ch, midi, _vel, start, _dur, notes in rows:
        if ch == 4 or start < 0.0:
            continue
        bar = int(start // beats_per_bar)
        if not (0 <= bar < len(buckets)):
            continue
        rel = round((float(start) - (float(bar) * beats_per_bar)) * 4.0) / 4.0
        pitch_classes = tuple((int(n) % 12) for n in (notes[:4] if notes else (midi,)))
        buckets[bar].append((int(ch), float(rel), pitch_classes))
    return [tuple(sorted(bucket)) for bucket in buckets]


def _max_adjacent_repeat_run(signatures: Sequence[Tuple[Any, ...]]) -> int:
    best = 0
    run = 0
    prev: Optional[Tuple[Any, ...]] = None
    for sig in signatures:
        if not sig:
            prev = None
            run = 0
            continue
        if sig == prev:
            run += 1
        else:
            run = 1
            prev = sig
        best = max(best, run)
    return int(best)


def _dominant_bar_share(signatures: Sequence[Tuple[Any, ...]]) -> float:
    nonempty = [sig for sig in signatures if sig]
    if not nonempty:
        return 0.0
    counts = Counter(nonempty)
    return float(max(counts.values()) / max(1, len(nonempty)))


def _max_velocity_jump_ratio(
    rows: Sequence[Tuple[int, int, int, float, float, Tuple[int, ...]]],
    *,
    bars: int,
    beats_per_bar: float,
) -> float:
    by_ch_bar: Dict[int, Dict[int, List[int]]] = defaultdict(lambda: defaultdict(list))
    for ch, _midi, vel, start, _dur, _notes in rows:
        if ch not in {1, 2, 3, 5} or start < 0.0:
            continue
        bar = int(start // beats_per_bar)
        if 0 <= bar < int(bars):
            by_ch_bar[int(ch)][int(bar)].append(int(vel))

    worst = 1.0
    for bar_map in by_ch_bar.values():
        last: Optional[float] = None
        last_bar: Optional[int] = None
        for bar in range(int(bars)):
            vals = bar_map.get(bar) or []
            if not vals:
                continue
            cur = float(sum(vals) / max(1, len(vals)))
            if last is not None and last_bar is not None and int(bar) == int(last_bar) + 1 and min(last, cur) > 1e-6:
                worst = max(worst, float(max(last, cur) / max(1e-6, min(last, cur))))
            last = cur
            last_bar = int(bar)
    return float(worst)


def _melody_boundary_crowding_count(
    rows: Sequence[Tuple[int, int, int, float, float, Tuple[int, ...]]],
    *,
    bars: int,
    beats_per_bar: float,
    phrase_bars: int = 4,
    breath_beats: float = 0.18,
) -> int:
    if bars <= phrase_bars:
        return 0
    boundaries = [
        float(bar) * beats_per_bar
        for bar in range(int(phrase_bars), int(bars), int(max(1, phrase_bars)))
    ]
    count = 0
    for ch, _midi, _vel, start, dur, _notes in rows:
        if ch != 2 or dur <= 0.0:
            continue
        end = float(start) + float(dur)
        for boundary in boundaries:
            if float(start) < boundary and end > boundary - float(breath_beats):
                count += 1
                break
    return int(count)


def analyze_song_events(
    events: Sequence[Any],
    *,
    bars: int,
    beats_per_bar: float = 4.0,
    section_roles: Optional[Sequence[str]] = None,
) -> Dict[str, Any]:
    rows = _event_rows(events)
    bars = max(1, int(bars))
    bpb = float(beats_per_bar) if beats_per_bar else 4.0
    by_ch = Counter(int(row[0]) for row in rows)
    events_by_bar = Counter(int(row[3] // bpb) for row in rows if 0.0 <= row[3] < bars * bpb)
    empty_bars = [bar for bar in range(bars) if int(events_by_bar.get(bar, 0)) == 0]
    melody_events = int(by_ch.get(2, 0))
    signatures = _bar_signatures(rows, bars=bars, beats_per_bar=bpb)
    roles = [str(role or "") for role in list(section_roles or [])]

    return {
        "event_count": int(len(rows)),
        "bars": int(bars),
        "beats_per_bar": float(bpb),
        "channels": {CHANNEL_NAMES.get(ch, str(ch)): int(count) for ch, count in sorted(by_ch.items())},
        "events_per_bar": float(len(rows) / max(1, bars)),
        "melody_events_per_bar": float(melody_events / max(1, bars)),
        "missing_core_channels": [
            name for ch, name in CORE_CHANNELS.items() if int(by_ch.get(int(ch), 0)) <= 0
        ],
        "empty_bar_count": int(len(empty_bars)),
        "empty_bar_share": float(len(empty_bars) / max(1, bars)),
        "max_adjacent_repeat_run": _max_adjacent_repeat_run(signatures),
        "dominant_bar_share": _dominant_bar_share(signatures),
        "max_velocity_jump_ratio": _max_velocity_jump_ratio(rows, bars=bars, beats_per_bar=bpb),
        "melody_boundary_crowding_count": _melody_boundary_crowding_count(
            rows,
            bars=bars,
            beats_per_bar=bpb,
        ),
        "section_role_count": int(len(roles)),
        "section_role_variety": int(len({role for role in roles if role})),
    }


def quality_score_from_metrics(
    metrics: Dict[str, Any],
    quality_report: Optional[Dict[str, Any]] = None,
) -> Tuple[float, List[str]]:
    score = 100.0
    issues: List[str] = []

    missing = list(metrics.get("missing_core_channels") or [])
    if missing:
        score -= 25.0 * len(missing)
        issues.append(f"missing core channels: {', '.join(str(x) for x in missing)}")

    bars = max(1, int(metrics.get("bars", 1) or 1))
    event_count = int(metrics.get("event_count", 0) or 0)
    if event_count < bars * 3:
        score -= 15.0
        issues.append("overall event density is very low")

    empty_share = float(metrics.get("empty_bar_share", 0.0) or 0.0)
    if empty_share > 0.15:
        penalty = min(20.0, (empty_share - 0.15) * 60.0)
        score -= penalty
        issues.append(f"many empty bars ({empty_share:.0%})")

    melody_per_bar = float(metrics.get("melody_events_per_bar", 0.0) or 0.0)
    if melody_per_bar < 0.45:
        score -= 15.0
        issues.append("melody density is too sparse")
    elif melody_per_bar > 8.0:
        score -= 8.0
        issues.append("melody density is probably too busy")

    repeat_run = int(metrics.get("max_adjacent_repeat_run", 0) or 0)
    if repeat_run >= 4:
        score -= min(14.0, float(repeat_run - 3) * 4.0 + 6.0)
        issues.append(f"long adjacent bar repetition run ({repeat_run} bars)")

    dominant_share = float(metrics.get("dominant_bar_share", 0.0) or 0.0)
    if dominant_share > 0.45:
        score -= min(12.0, (dominant_share - 0.45) * 30.0)
        issues.append(f"one bar pattern dominates ({dominant_share:.0%})")

    velocity_ratio = float(metrics.get("max_velocity_jump_ratio", 1.0) or 1.0)
    if velocity_ratio > 1.6:
        score -= min(12.0, (velocity_ratio - 1.6) * 12.0)
        issues.append(f"large bar-to-bar velocity jump ratio ({velocity_ratio:.2f})")

    boundary_crowding = int(metrics.get("melody_boundary_crowding_count", 0) or 0)
    if boundary_crowding > 0:
        score -= min(12.0, float(boundary_crowding) * 3.0)
        issues.append(f"melody crowds phrase boundaries ({boundary_crowding} events)")

    role_count = int(metrics.get("section_role_count", 0) or 0)
    role_variety = int(metrics.get("section_role_variety", 0) or 0)
    if role_count >= 3 and role_variety < 2:
        score -= 8.0
        issues.append("arrangement role variety is low")

    qr = dict(quality_report or {})
    checks = dict(qr.get("checks") or {})
    values = dict(qr.get("values") or {})
    if checks and not bool(checks.get("singable_lead_range", True)):
        lead_range = int(values.get("lead_pitch_range", 0) or 0)
        lead_max_leap = int(values.get("lead_max_leap", 0) or 0)
        penalty = min(18.0, max(0, lead_range - 24) * 1.5 + max(0, lead_max_leap - 14) * 2.5 + 8.0)
        score -= float(penalty)
        issues.append(f"lead range/leaps need singability repair (range {lead_range}, max leap {lead_max_leap})")
    if checks and not bool(checks.get("bass_not_static", True)):
        static_sections = list(values.get("bass_static_sections") or [])
        score -= min(10.0, 5.0 + 2.0 * len(static_sections))
        issues.append(f"bass motion is static in core sections ({len(static_sections)} sections)")
    if checks and not bool(checks.get("memorable_hook", True)):
        score -= 10.0
        issues.append("chorus hook motif is not clearly stated")
    if checks and not bool(checks.get("chorus_stronger_than_verse", True)):
        score -= 8.0
        issues.append("chorus does not read stronger than verse")
    if checks and not bool(checks.get("lead_not_too_empty", True)):
        score -= 10.0
        issues.append("lead line is too empty")

    return float(max(0.0, min(100.0, score))), issues


def _build_specs(
    form: str,
    emotion: str,
    *,
    root: int,
    tempo: float,
    bars_per_section: int,
    target_seconds: float,
    max_bars: int,
) -> Tuple[str, List[Any]]:
    from composition.song_generator import SongGenerator

    form_lc = str(form or "default").strip().lower()
    if form_lc == "ambient":
        return "default", SongGenerator.ambient_form(
            emotion,
            root_note=int(root),
            base_tempo_bpm=float(tempo),
            target_seconds=float(target_seconds),
            max_bars=int(max_bars),
        )
    if form_lc == "pop":
        return "pop", SongGenerator.pop_form(emotion, bars_per_section=int(bars_per_section), root_note=int(root))
    if form_lc == "pop_ext":
        return "pop_ext", SongGenerator.pop_ext_form(emotion, bars_per_section=int(bars_per_section), root_note=int(root))
    if form_lc == "wave":
        return "wave", SongGenerator.wave_form(emotion, bars_per_section=int(bars_per_section), root_note=int(root))
    if form_lc == "ballad":
        return "ballad", SongGenerator.ballad_form(emotion, bars_per_section=int(bars_per_section), root_note=int(root))
    if form_lc == "anthem":
        return "anthem", SongGenerator.anthem_form(emotion, bars_per_section=int(bars_per_section), root_note=int(root))
    if form_lc == "rondo":
        return "rondo", SongGenerator.rondo_form(emotion, bars_per_section=int(bars_per_section), root_note=int(root))
    return "default", SongGenerator.default_form(emotion, bars_per_section=int(bars_per_section), root_note=int(root))


def _case_slug(emotion: str, form: str, seed: int) -> str:
    return f"{emotion.strip().lower()}__{form.strip().lower()}__seed_{int(seed)}".replace(" ", "_")


def _safe_export(song: Any, *, case_dir: Path, slug: str, export_midi: bool) -> Dict[str, str]:
    from composition.song_generator import SongGenerator

    out: Dict[str, str] = {}
    base = case_dir / slug
    try:
        out["report_json"] = SongGenerator.export_report(song, out_path=str(base))
    except Exception as exc:
        out["report_error"] = str(exc)
    if export_midi:
        try:
            out["midi"] = SongGenerator.export_to_midi(song, out_path=str(base.with_suffix(".mid")))
        except Exception as exc:
            out["midi_error"] = str(exc)
    return out


def run_case(
    *,
    emotion: str,
    seed: int,
    form: str,
    root: int,
    tempo: float,
    bars_per_section: int,
    target_seconds: float,
    max_bars: int,
    case_dir: Path,
    export_midi: bool,
) -> Dict[str, Any]:
    from composition.engine import CompositionGenerator
    from composition.evaluation import evaluate_song, quality_report, score_song
    from composition.song_generator import SongGenerator

    t0 = time.perf_counter()
    arrangement_form, specs = _build_specs(
        form,
        emotion,
        root=int(root),
        tempo=float(tempo),
        bars_per_section=int(bars_per_section),
        target_seconds=float(target_seconds),
        max_bars=int(max_bars),
    )
    composer = CompositionGenerator(enable_perf_monitoring=False)
    composer.reseed(int(seed))
    song_gen = SongGenerator(composer=composer)
    song = song_gen.generate_song(specs, base_tempo_bpm=float(tempo), arrangement_form=arrangement_form, seed=int(seed))
    elapsed_ms = (time.perf_counter() - t0) * 1000.0

    events = list(song.events or [])
    total_bars = int(sum(int(s.bars) for s in list(song.sections or specs)))
    section_roles = list((song.metadata or {}).get("section_roles", []) or [])
    qa_report = quality_report(
        events,
        section_roles=section_roles,
        section_bars=[int(s.bars) for s in list(song.sections or specs)],
        metadata=dict(song.metadata or {}),
        beats_per_bar=4.0,
        bars=total_bars,
    )
    metrics = analyze_song_events(events, bars=total_bars, section_roles=section_roles)
    quality_score, issues = quality_score_from_metrics(metrics, qa_report)
    eval_metrics = evaluate_song(events, beats_per_bar=4.0, bars=total_bars).to_dict()
    eval_score, eval_details = score_song(events, beats_per_bar=4.0, bars=total_bars)

    slug = _case_slug(emotion, form, seed)
    case_dir.mkdir(parents=True, exist_ok=True)
    exports = _safe_export(song, case_dir=case_dir, slug=slug, export_midi=bool(export_midi))

    payload = {
        "emotion": str(emotion),
        "seed": int(seed),
        "requested_form": str(form),
        "arrangement_form": str(arrangement_form),
        "root": int(root),
        "tempo": float(tempo),
        "bars": int(total_bars),
        "section_count": int(len(song.sections or specs)),
        "wall_ms": round(float(elapsed_ms), 2),
        "quality_score": round(float(quality_score), 2),
        "issues": list(issues),
        "event_quality_metrics": metrics,
        "evaluation_score": float(eval_score),
        "evaluation_metrics": eval_metrics,
        "evaluation_details": eval_details,
        "quality_report": qa_report,
        "exports": exports,
        "metadata_keys": sorted((song.metadata or {}).keys()),
    }
    with open(case_dir / f"{slug}.quality.json", "w", encoding="utf-8") as handle:
        json.dump(payload, handle, indent=2, sort_keys=True)
    return payload


def _mean(values: Iterable[float]) -> float:
    vals = [float(v) for v in values]
    return float(sum(vals) / max(1, len(vals))) if vals else 0.0


def _write_summary(run_dir: Path, rows: Sequence[Dict[str, Any]]) -> Path:
    path = run_dir / "quality_audit_summary.txt"
    worst = sorted(rows, key=lambda row: float(row.get("quality_score", 0.0)))[:8]
    lines = [
        "Song Quality Audit",
        f"Cases: {len(rows)}",
        f"Mean quality score: {_mean(float(row.get('quality_score', 0.0)) for row in rows):.2f}",
        "",
        "Worst cases:",
    ]
    for row in worst:
        issues = "; ".join(str(x) for x in list(row.get("issues") or [])[:3]) or "no major issues"
        lines.append(
            f"- {row.get('emotion')} / {row.get('requested_form')} / seed {row.get('seed')}: "
            f"{float(row.get('quality_score', 0.0)):.2f} ({issues})"
        )
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    return path


def build_arg_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Generate songs and audit musical quality signals.")
    parser.add_argument("--output-dir", default="artifacts/quality_audits")
    parser.add_argument("--emotions", default=",".join(DEFAULT_EMOTIONS))
    parser.add_argument("--seeds", default=",".join(str(x) for x in DEFAULT_SEEDS))
    parser.add_argument("--forms", default=",".join(DEFAULT_FORMS))
    parser.add_argument("--root", type=int, default=60)
    parser.add_argument("--tempo", type=float, default=70.0)
    parser.add_argument("--bars-per-section", type=int, default=8)
    parser.add_argument("--target-seconds", type=float, default=32.0)
    parser.add_argument("--max-bars", type=int, default=32)
    parser.add_argument("--performance", choices=("low", "high", "balanced"), default="low")
    parser.add_argument("--export-midi", action="store_true")
    parser.add_argument("--fail-under-score", type=float, default=0.0)
    return parser


def main(argv: Optional[Sequence[str]] = None) -> int:
    args = build_arg_parser().parse_args(argv)
    from audiogen_core.config import CONFIG

    CONFIG.set_performance_mode(str(args.performance))
    emotions = _parse_csv(args.emotions)
    seeds = _parse_int_csv(args.seeds)
    forms = _parse_csv(args.forms)
    if not emotions or not seeds or not forms:
        raise SystemExit("Provide at least one emotion, seed, and form.")

    timestamp = time.strftime("%Y%m%d_%H%M%S")
    run_dir = resolve_project_path(str(args.output_dir)) / f"song_quality_audit_{timestamp}"
    cases_dir = run_dir / "cases"
    cases_dir.mkdir(parents=True, exist_ok=True)

    rows: List[Dict[str, Any]] = []
    failures: List[Dict[str, Any]] = []
    for emotion in emotions:
        for form in forms:
            for seed in seeds:
                row = run_case(
                    emotion=emotion,
                    seed=int(seed),
                    form=form,
                    root=int(args.root),
                    tempo=float(args.tempo),
                    bars_per_section=max(4, int(args.bars_per_section)),
                    target_seconds=float(args.target_seconds),
                    max_bars=max(16, int(args.max_bars)),
                    case_dir=cases_dir,
                    export_midi=bool(args.export_midi),
                )
                rows.append(row)
                if float(args.fail_under_score) > 0.0 and float(row.get("quality_score", 0.0)) < float(
                    args.fail_under_score
                ):
                    failures.append(row)

    report = {
        "ok": not failures,
        "case_count": int(len(rows)),
        "mean_quality_score": round(_mean(float(row.get("quality_score", 0.0)) for row in rows), 2),
        "min_quality_score": round(min((float(row.get("quality_score", 0.0)) for row in rows), default=math.nan), 2),
        "fail_under_score": float(args.fail_under_score),
        "failed_cases": [
            {
                "emotion": row.get("emotion"),
                "form": row.get("requested_form"),
                "seed": row.get("seed"),
                "quality_score": row.get("quality_score"),
                "issues": row.get("issues"),
            }
            for row in failures
        ],
        "rows": rows,
    }
    report_path = run_dir / "quality_audit_report.json"
    with open(report_path, "w", encoding="utf-8") as handle:
        json.dump(report, handle, indent=2, sort_keys=True)
    summary_path = _write_summary(run_dir, rows)

    print(
        json.dumps(
            {
                "ok": bool(report["ok"]),
                "case_count": int(report["case_count"]),
                "mean_quality_score": report["mean_quality_score"],
                "min_quality_score": report["min_quality_score"],
                "report": str(report_path),
                "summary": str(summary_path),
            },
            indent=2,
            sort_keys=True,
        )
    )
    return 0 if not failures else 1


if __name__ == "__main__":
    raise SystemExit(main())
