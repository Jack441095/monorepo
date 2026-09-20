#!/usr/bin/env python3
"""Merge curated emotion-reference melody rows into a generated training JSONL."""

from __future__ import annotations

import argparse
import json
import time
from pathlib import Path
from typing import Any, Dict, Iterable, List, Tuple


DEFAULT_SCALE = [0, 2, 4, 5, 7, 9, 11]
DEFAULT_CHORDS_BY_EMOTION = {
    "anger": ["i", "bII", "V", "i"],
    "annoyance": ["i", "bII", "v", "i"],
    "disapproval": ["i", "iv", "bII", "V"],
    "disgust": ["i", "bII", "iv", "V"],
    "fear": ["i", "bII", "V", "i"],
    "nervousness": ["i", "vii°", "i", "V"],
    "confusion": ["i", "bII", "bVII", "V"],
    "grief": ["i", "bVI", "iv", "V"],
    "sadness": ["i", "bVI", "III", "v"],
    "remorse": ["i", "iv", "bVI", "V"],
    "disappointment": ["i", "bVI", "iv", "i"],
    "joy": ["I", "V", "vi", "IV"],
    "excitement": ["I", "V", "IV", "V"],
    "optimism": ["I", "IV", "V", "I"],
    "amusement": ["I", "vi", "IV", "V"],
    "pride": ["I", "V", "I", "IV"],
    "love": ["Imaj7", "vi7", "IVmaj7", "V"],
    "caring": ["I", "vi", "IV", "I"],
    "gratitude": ["IV", "V", "I", "I"],
    "relief": ["iv", "V", "I", "I"],
    "approval": ["I", "IV", "V", "I"],
    "admiration": ["Imaj7", "IVmaj7", "V", "I"],
    "curiosity": ["I", "iii", "IV", "V"],
    "realization": ["ii", "V", "I", "I"],
    "surprise": ["I", "bVII", "IV", "I"],
    "desire": ["vi", "IV", "I", "V"],
    "embarrassment": ["vi", "ii", "V", "I"],
    "neutral": ["I", "IV", "V", "I"],
}


def _iter_jsonl_paths(paths: Iterable[str]) -> List[Path]:
    out: List[Path] = []
    for raw in paths:
        p = Path(str(raw)).expanduser()
        if p.is_dir():
            out.extend(sorted(x for x in p.rglob("*.jsonl") if x.is_file()))
        elif p.is_file():
            out.append(p)
    seen = set()
    uniq: List[Path] = []
    for p in out:
        k = str(p.resolve())
        if k in seen:
            continue
        seen.add(k)
        uniq.append(p)
    return uniq


def _melody(row: Dict[str, Any]) -> List[Tuple[int, float]]:
    raw = row.get("melody") or row.get("events") or []
    out: List[Tuple[int, float]] = []
    if isinstance(raw, list):
        for item in raw:
            if isinstance(item, (list, tuple)) and len(item) >= 2:
                try:
                    out.append((int(item[0]), float(item[1])))
                except Exception:
                    continue
    return out


def _string_list(value: Any) -> List[str]:
    if not isinstance(value, list):
        return []
    return [str(v or "").strip() for v in value if str(v or "").strip()]


def _default_contour(melody: List[Tuple[int, float]]) -> str:
    voiced = [int(d) for d, _ in melody if int(d) >= 0]
    if len(voiced) < 2:
        return "static"
    delta = int(voiced[-1]) - int(voiced[0])
    if delta >= 2:
        return "asc"
    if delta <= -2:
        return "desc"
    if max(voiced) - min(voiced) >= 3:
        return "arch"
    return "static"


def _normalize_reference_row(row: Dict[str, Any], *, source_path: Path, row_index: int) -> Dict[str, Any] | None:
    melody = _melody(row)
    if len(melody) < 3:
        return None
    emotion = str(row.get("emotion") or row.get("label") or "neutral").strip().lower() or "neutral"
    section_role = str(row.get("section_role") or "a").strip().lower() or "a"
    beats_per_bar = float(row.get("beats_per_bar", 4.0) or 4.0)
    contours = _string_list(row.get("phrase_contours"))
    if not contours:
        contours = [str(row.get("contour") or _default_contour(melody))]
    phrase_roles = _string_list(row.get("phrase_roles"))
    if not phrase_roles:
        phrase_roles = [str(row.get("phrase_role") or "reference")]
    chords = _string_list(row.get("chord_sequence"))
    if not chords:
        chords = list(DEFAULT_CHORDS_BY_EMOTION.get(emotion, DEFAULT_CHORDS_BY_EMOTION["neutral"]))
    roots = row.get("roots") if isinstance(row.get("roots"), list) else [int(row.get("root_note", 60) or 60)] * len(chords)
    try:
        lyrical_score = float(row.get("lyrical_score", row.get("emotion_match_score", 1.0)) or 1.0)
    except Exception:
        lyrical_score = 1.0
    try:
        accept_score = float(row.get("accept_score", lyrical_score) or lyrical_score)
    except Exception:
        accept_score = lyrical_score
    out = {
        "ts": float(row.get("ts", time.time()) or time.time()),
        "source": "curated_emotion_reference",
        "reference_source_path": str(source_path),
        "reference_row_index": int(row_index),
        "emotion": emotion,
        "section_role": section_role,
        "phrase_contours": contours,
        "phrase_roles": phrase_roles,
        "phrases": row.get("phrases") if isinstance(row.get("phrases"), list) else [melody],
        "melody": [[int(d), float(dur)] for d, dur in melody],
        "chord_sequence": chords,
        "roots": roots,
        "beats_per_bar": float(beats_per_bar),
        "accept_score": max(0.0, min(1.0, float(accept_score))),
        "lyrical_score": max(0.0, min(1.0, float(lyrical_score))),
        "emotion_match_score": max(0.0, min(1.0, float(row.get("emotion_match_score", lyrical_score) or lyrical_score))),
        "emotion_features": row.get("emotion_features") if isinstance(row.get("emotion_features"), dict) else {},
        "scale_intervals": row.get("scale_intervals") if isinstance(row.get("scale_intervals"), list) else list(DEFAULT_SCALE),
    }
    return out


def _read_reference_rows(paths: List[Path]) -> List[Dict[str, Any]]:
    rows: List[Dict[str, Any]] = []
    for p in paths:
        with p.open("r", encoding="utf-8") as f:
            for idx, line in enumerate(f, start=1):
                s = line.strip()
                if not s or s.startswith("#"):
                    continue
                try:
                    row = json.loads(s)
                except json.JSONDecodeError:
                    continue
                if not isinstance(row, dict):
                    continue
                norm = _normalize_reference_row(row, source_path=p, row_index=idx)
                if norm is not None:
                    rows.append(norm)
    return rows


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--base", required=True, help="Generated training JSONL.")
    ap.add_argument("--references", nargs="+", required=True, help="Reference JSONL file(s) or directories.")
    ap.add_argument("--out", required=True, help="Merged output JSONL.")
    ap.add_argument("--reference-weight", type=int, default=3, help="Repeat curated rows this many times (default: 3).")
    args = ap.parse_args()

    base = Path(str(args.base)).expanduser()
    out = Path(str(args.out)).expanduser()
    refs = _iter_jsonl_paths(list(args.references or []))
    if not base.is_file():
        print(f"base JSONL not found: {base}")
        return 2
    if not refs:
        print("no reference JSONL files found")
        return 2

    ref_rows = _read_reference_rows(refs)
    weight = max(1, int(args.reference_weight))
    out.parent.mkdir(parents=True, exist_ok=True)
    base_lines = 0
    with base.open("r", encoding="utf-8") as f_in, out.open("w", encoding="utf-8") as f_out:
        for line in f_in:
            if line.strip():
                f_out.write(line.rstrip("\n") + "\n")
                base_lines += 1
        for _ in range(weight):
            for row in ref_rows:
                f_out.write(json.dumps(row, ensure_ascii=False, sort_keys=True) + "\n")

    print(
        f"merged base_rows={base_lines} reference_rows={len(ref_rows)} "
        f"reference_weight={weight} total_added={len(ref_rows) * weight} -> {out}"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
