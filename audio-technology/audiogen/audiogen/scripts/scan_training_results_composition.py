#!/usr/bin/env python3
"""
Scan generated training/eval artifacts and summarize composition quality vs emotion + preset/style.

What it reads (best-effort; missing files are skipped):
- artifacts/datasets/live_melody/<tag>/live_melody_training.jsonl
- artifacts/datasets/live_melody/<tag>/emotion_diagnostics.json
- artifacts/datasets/live_melody/<tag>/run_meta.txt
- artifacts/reports/**/melody_jsonl_eval.json  (optional; usually produced by melody_eval_gate.py --report)

What it computes:
- Joint composition diagnostics per emotion (melody↔harmony fit proxies)
- Chord/harmony diagnostics per emotion (diversity + repetition)
- Merges in melody emotion diagnostics (lyrical/accept/etc) when available
- Extracts STYLE / META_PRESET / composition knobs from run_meta.txt when present

Outputs:
- Prints "worst" emotions per tag for quick triage
- Optionally writes a consolidated JSON report
"""

from __future__ import annotations

import argparse
import heapq
import json
import re
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from scripts.chord_emotion_diagnostics_fast import analyze_fast as chord_analyze_fast
from scripts.joint_composition_diagnostics_fast import analyze_fast as joint_analyze_fast


@dataclass(frozen=True)
class RunMeta:
    tag: str = ""
    style: str = ""
    meta_preset: str = ""
    knobs: Dict[str, str] = None  # type: ignore[assignment]


_KV_RE = re.compile(r"^\s*([A-Za-z0-9_./-]+)\s*=\s*(.*)\s*$")


def _safe_load_json(path: Path) -> Optional[Dict[str, Any]]:
    try:
        if not path.is_file():
            return None
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return None


def _parse_run_meta(path: Path) -> Optional[RunMeta]:
    if not path.is_file():
        return None
    tag = ""
    style = ""
    meta_preset = ""
    knobs: Dict[str, str] = {}
    try:
        for raw in path.read_text(encoding="utf-8").splitlines():
            m = _KV_RE.match(raw)
            if not m:
                continue
            k, v = m.groups()
            k = str(k).strip()
            v = str(v).strip()
            if k == "tag":
                tag = v
            elif k == "STYLE":
                style = "" if v == "(default)" else v
            elif k == "META_PRESET":
                meta_preset = "" if v.startswith("(unset") else v.split()[0]
            elif k in {
                "melody_strongbeat_chord_tone_mult",
                "harmony_antistuck_enabled",
                "harmony_repeat_penalty_mult",
                "melody_phrase_rerank_cadence_land_bonus",
                "melody_rerank_cadence_target_bonus",
                "section_k_samples",
                "chord_k_samples",
                "use_voice_leading",
            }:
                knobs[k] = v
    except Exception:
        return None
    return RunMeta(tag=tag, style=style, meta_preset=meta_preset, knobs=knobs)


def _composition_score_from_joint(m: Dict[str, Any]) -> float:
    """
    Heuristic 0..1-ish score from joint diagnostics emotion metrics.
    Higher is better.
    """
    fit = float(m.get("strong_beat_chord_tone_rate", 0.0) or 0.0)
    cad = float(m.get("cadence_agreement_rate", 0.0) or 0.0)
    rep = float(m.get("chord_repeat_rate", 0.0) or 0.0)
    # Root leap is unbounded; just softly penalize large averages.
    root_mean = float(m.get("root_leap_mean", 0.0) or 0.0)
    root_pen = min(1.0, max(0.0, root_mean / 8.0))
    # We want low repetition and moderate root motion.
    return (0.45 * fit) + (0.35 * cad) + (0.15 * (1.0 - rep)) + (0.05 * (1.0 - root_pen))


_ROMAN_RE = re.compile(r"^([#b]*)([ivIV]+)")
_ROMAN_TO_DEG = {
    "I": 0,
    "II": 1,
    "III": 2,
    "IV": 3,
    "V": 4,
    "VI": 5,
    "VII": 6,
}


def _roman_root_degree(chord_symbol: str) -> Optional[int]:
    s = str(chord_symbol or "").strip()
    if not s:
        return None
    m = _ROMAN_RE.match(s)
    if not m:
        return None
    _acc, roman = m.groups()
    key = str(roman).upper()
    return _ROMAN_TO_DEG.get(key)


def _chord_tone_degrees(chord_symbol: str) -> Optional[set[int]]:
    """
    Approximate chord tones in diatonic degree space.
    Triad approximation: {root, root+2, root+4} mod 7.
    """
    root = _roman_root_degree(chord_symbol)
    if root is None:
        return None
    return {int(root) % 7, int(root + 2) % 7, int(root + 4) % 7}


def _iter_melody_events(row: Dict[str, Any]) -> List[Tuple[int, float]]:
    out: List[Tuple[int, float]] = []
    melody = row.get("melody")
    if isinstance(melody, list):
        for item in melody:
            if isinstance(item, (list, tuple)) and len(item) >= 2:
                try:
                    out.append((int(item[0]), float(item[1])))
                except (TypeError, ValueError):
                    continue
    if out:
        return out
    phrases = row.get("phrases")
    if isinstance(phrases, list):
        for phrase in phrases:
            if not isinstance(phrase, list):
                continue
            for item in phrase:
                if isinstance(item, (list, tuple)) and len(item) >= 2:
                    try:
                        out.append((int(item[0]), float(item[1])))
                    except (TypeError, ValueError):
                        continue
    return out


def _sanitize_filename(s: str) -> str:
    s = str(s or "").strip().lower().replace(" ", "_")
    s = re.sub(r"[^a-z0-9_.-]+", "_", s)
    s = re.sub(r"_+", "_", s)
    return s.strip("._") or "unknown"


def _row_joint_metrics(row: Dict[str, Any]) -> Dict[str, Any]:
    melody = _iter_melody_events(row)
    chords = row.get("chord_sequence")
    beats_per_bar = float(row.get("beats_per_bar", 4.0) or 4.0)
    if not melody or not isinstance(chords, list) or not chords:
        return {"ok": False}

    strong_hits = 0
    strong_den = 0
    t = 0.0
    for deg, dur in melody:
        d = int(deg)
        if d < 0:
            t += float(dur)
            continue
        bar = int(t // beats_per_bar) if beats_per_bar > 1e-9 else 0
        if bar < 0:
            bar = 0
        if bar >= len(chords):
            bar = len(chords) - 1
        beat_in_bar = float(t) - float(bar) * float(beats_per_bar)
        strong = (abs(beat_in_bar - 0.0) < 1e-6) or (abs(beat_in_bar - (beats_per_bar / 2.0)) < 1e-6)
        if strong:
            strong_den += 1
            tones = _chord_tone_degrees(str(chords[bar] or ""))
            if tones is not None and (int(d) % 7) in tones:
                strong_hits += 1
        t += float(dur)
    fit = float(strong_hits) / float(max(1, strong_den))

    voiced = [int(d) % 7 for d, _dur in melody if int(d) >= 0]
    cadence_target = None
    cadence_ok = None
    cadence_targets = row.get("cadence_targets")
    if voiced and isinstance(cadence_targets, list) and cadence_targets:
        last = cadence_targets[-1] if isinstance(cadence_targets[-1], dict) else {}
        cad = last.get("cadence_degree")
        if cad is not None:
            cadence_target = int(cad) % 7
            cadence_ok = bool(int(voiced[-1]) == cadence_target)

    toks = row.get("chord_markov_tokens")
    tok_list = [str(t or "") for t in toks] if isinstance(toks, list) and toks else [str(c or "") for c in chords]
    rep_hits = 0
    rep_den = 0
    if len(tok_list) >= 2:
        for a, b in zip(tok_list, tok_list[1:]):
            rep_den += 1
            if str(a) == str(b):
                rep_hits += 1
    rep = float(rep_hits) / float(max(1, rep_den))

    roots = row.get("roots")
    root_mean = 0.0
    root_max = 0.0
    if isinstance(roots, list) and len(roots) >= 2:
        try:
            rr = [int(x) for x in roots if x is not None]
            if len(rr) >= 2:
                leaps = [abs(int(b) - int(a)) for a, b in zip(rr, rr[1:])]
                if leaps:
                    root_mean = float(sum(leaps)) / float(len(leaps))
                    root_max = float(max(leaps))
        except Exception:
            pass

    cad_rate = 1.0 if cadence_ok is True else 0.0
    root_pen = min(1.0, max(0.0, float(root_mean) / 8.0))
    score = (0.45 * float(fit)) + (0.35 * float(cad_rate)) + (0.15 * (1.0 - float(rep))) + (0.05 * (1.0 - float(root_pen)))

    return {
        "ok": True,
        "joint_score": float(score),
        "strong_beat_chord_tone_rate": float(fit),
        "strong_beat_den": int(strong_den),
        "cadence_ok": cadence_ok,
        "cadence_target_degree": cadence_target,
        "chord_repeat_rate": float(rep),
        "root_leap_mean": float(root_mean),
        "root_leap_max": float(root_max),
    }


def dump_worst_rows(
    jsonl_path: Path,
    *,
    out_dir: Path,
    per_emotion: int,
    emotions_allow: Optional[set[str]] = None,
) -> Dict[str, Any]:
    """
    Stream jsonl and write bottom-N rows per emotion by per-row joint_score.
    """
    from data.emotion_aliases import canonical_emotion_name

    out_dir.mkdir(parents=True, exist_ok=True)
    heaps: Dict[str, list[tuple[float, int, Dict[str, Any]]]] = {}
    seen = 0
    candidates = 0

    def _push(emo: str, score: float, idx: int, payload: Dict[str, Any]) -> None:
        nonlocal candidates
        h = heaps.get(emo)
        if h is None:
            h = []
            heaps[emo] = h
        item = (-float(score), int(idx), payload)  # max-heap via negative score
        if len(h) < int(per_emotion):
            heapq.heappush(h, item)
            candidates += 1
            return
        if item[0] > h[0][0]:
            heapq.heapreplace(h, item)

    with jsonl_path.open("r", encoding="utf-8") as f:
        for idx, line in enumerate(f):
            s = (line or "").strip()
            if not s:
                continue
            try:
                row = json.loads(s)
            except json.JSONDecodeError:
                continue
            if not isinstance(row, dict):
                continue
            seen += 1
            emo = canonical_emotion_name(str(row.get("emotion") or "neutral")) or "neutral"
            if emotions_allow is not None and emo not in emotions_allow:
                continue
            m = _row_joint_metrics(row)
            if not bool(m.get("ok")):
                continue
            payload = dict(row)
            payload["_triage"] = m
            _push(emo, float(m["joint_score"]), int(idx), payload)

    wrote = 0
    emotions_written: Dict[str, int] = {}
    for emo, h in sorted(heaps.items()):
        rows = [(-neg, idx, payload) for (neg, idx, payload) in h]
        rows.sort(key=lambda t: (t[0], t[1]))  # worst first (lowest score)
        out_path = out_dir / f"worst_rows_{_sanitize_filename(emo)}.jsonl"
        with out_path.open("w", encoding="utf-8") as wf:
            for score, _idx, payload in rows:
                try:
                    payload["_triage"]["joint_score"] = float(score)
                except Exception:
                    pass
                wf.write(json.dumps(payload, ensure_ascii=False) + "\n")
                wrote += 1
        emotions_written[emo] = int(len(rows))

    return {
        "jsonl": str(jsonl_path),
        "out_dir": str(out_dir),
        "seen_rows": int(seen),
        "kept_candidates": int(candidates),
        "wrote_rows": int(wrote),
        "per_emotion": int(per_emotion),
        "emotions_written": dict(sorted(emotions_written.items())),
    }


def _maybe_load_melody_eval_reports() -> Dict[str, Dict[str, Any]]:
    """
    Returns map jsonl_path -> melody_jsonl_eval payload.
    """
    reports_dir = ROOT / "artifacts" / "reports"
    out: Dict[str, Dict[str, Any]] = {}
    if not reports_dir.is_dir():
        return out
    for p in sorted(reports_dir.glob("**/melody_jsonl_eval.json")):
        payload = _safe_load_json(p)
        if not isinstance(payload, dict):
            continue
        jsonl_path = str(payload.get("path") or "").strip()
        if jsonl_path:
            out[jsonl_path] = payload
    return out


def scan_tag(tag_dir: Path, *, max_rows_per_emotion: int = 80) -> Dict[str, Any]:
    tag = tag_dir.name
    jsonl = tag_dir / "live_melody_training.jsonl"
    run_meta_path = tag_dir / "run_meta.txt"
    emo_diag_path = tag_dir / "emotion_diagnostics.json"
    run_meta = _parse_run_meta(run_meta_path)
    emo_diag = _safe_load_json(emo_diag_path)

    joint = joint_analyze_fast(jsonl, max_rows_per_emotion=int(max_rows_per_emotion))
    chord = chord_analyze_fast(jsonl, max_rows_per_emotion=int(max_rows_per_emotion))

    # Rank "worst" emotions by joint composition score, but require a minimum number of rows.
    rows = []
    for emo, m in dict(joint.get("emotions") or {}).items():
        if not isinstance(m, dict):
            continue
        r = int(m.get("rows", 0) or 0)
        if r <= 0:
            continue
        rows.append((emo, _composition_score_from_joint(m), r))
    rows.sort(key=lambda t: (t[1], -t[2]))
    worst = [{"emotion": e, "score": float(s), "rows": int(r)} for e, s, r in rows[:12]]

    return {
        "tag": tag,
        "paths": {
            "jsonl": str(jsonl),
            "run_meta": str(run_meta_path) if run_meta_path.is_file() else "",
            "emotion_diagnostics": str(emo_diag_path) if emo_diag_path.is_file() else "",
        },
        "run_meta": {
            "tag": getattr(run_meta, "tag", "") if run_meta else "",
            "style": getattr(run_meta, "style", "") if run_meta else "",
            "meta_preset": getattr(run_meta, "meta_preset", "") if run_meta else "",
            "knobs": getattr(run_meta, "knobs", {}) if run_meta else {},
        },
        "worst_emotions_by_joint_score": worst,
        "joint": joint,
        "chord": chord,
        "melody_emotion_diagnostics": emo_diag if isinstance(emo_diag, dict) else {},
    }


def _fmt_float(x: Any, *, default: float = 0.0) -> float:
    try:
        return float(x)
    except Exception:
        return float(default)


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument(
        "--max-rows-per-emotion",
        type=int,
        default=80,
        help="Cap rows per emotion when computing fast diagnostics (0 = no cap).",
    )
    ap.add_argument(
        "--json-out",
        default="",
        help="Optional path to write the consolidated JSON report.",
    )
    ap.add_argument(
        "--dump-worst-rows-per-emotion",
        type=int,
        default=0,
        help="If > 0, dump bottom-N rows per emotion under artifacts/reports/<tag>/worst_rows_<emotion>.jsonl",
    )
    args = ap.parse_args()

    base = ROOT / "artifacts" / "datasets" / "live_melody"
    if not base.is_dir():
        print(f"missing: {base}", file=sys.stderr)
        return 2

    melody_eval = _maybe_load_melody_eval_reports()

    tags = sorted([p for p in base.iterdir() if p.is_dir()])
    results = []
    for tag_dir in tags:
        jsonl = tag_dir / "live_melody_training.jsonl"
        if not jsonl.is_file():
            continue
        report = scan_tag(tag_dir, max_rows_per_emotion=int(args.max_rows_per_emotion))
        # Attach a matching melody_jsonl_eval.json if we have one.
        # The eval report path is stored as an absolute path in some runs; match by suffix too.
        jsonl_str = str(jsonl)
        eval_payload = melody_eval.get(jsonl_str)
        if eval_payload is None:
            # Fallback: match by suffix for portability.
            for k, v in melody_eval.items():
                try:
                    if str(k).endswith(str(tag_dir / "live_melody_training.jsonl")):
                        eval_payload = v
                        break
                except Exception:
                    continue
        report["melody_jsonl_eval"] = eval_payload if isinstance(eval_payload, dict) else {}

        if int(args.dump_worst_rows_per_emotion) > 0:
            out_dir = ROOT / "artifacts" / "reports" / str(tag_dir.name)
            report["worst_rows_dump"] = dump_worst_rows(
                jsonl,
                out_dir=out_dir,
                per_emotion=int(args.dump_worst_rows_per_emotion),
            )

        results.append(report)

        worst = report.get("worst_emotions_by_joint_score") or []
        joint_emotions = ((report.get("joint") or {}).get("emotions")) or {}
        style = (report.get("run_meta") or {}).get("style") or ""
        preset = (report.get("run_meta") or {}).get("meta_preset") or ""
        print("")
        print(f"== tag={tag_dir.name} style={style or '(none)'} preset={preset or '(none)'} ==")
        for item in list(worst)[:8]:
            emo = str(item.get("emotion") or "")
            jm = joint_emotions.get(emo) if isinstance(joint_emotions, dict) else None
            if not isinstance(jm, dict):
                jm = {}
            fit = _fmt_float(jm.get("strong_beat_chord_tone_rate"))
            cad = _fmt_float(jm.get("cadence_agreement_rate"))
            rep = _fmt_float(jm.get("chord_repeat_rate"))
            root_mean = _fmt_float(jm.get("root_leap_mean"))
            print(
                f"- {emo:15s} "
                f"jointScore={float(item.get('score', 0.0)):.3f} rows={int(item.get('rows', 0))} "
                f"fit={fit:.3f} cad={cad:.3f} rep={rep:.3f} rootMean={root_mean:.2f}"
            )

    payload = {
        "schema_version": 1,
        "root": str(ROOT),
        "tag_count": int(len(results)),
        "tags": results,
    }
    if str(args.json_out or "").strip():
        out = Path(str(args.json_out)).expanduser()
        if not out.is_absolute():
            out = ROOT / out
        out.parent.mkdir(parents=True, exist_ok=True)
        out.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")
        print("")
        print(f"json_out: {out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

