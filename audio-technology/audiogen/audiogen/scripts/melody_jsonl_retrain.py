#!/usr/bin/env python3
"""Batch-retrain Markov melody models from live JSONL export (Phase 2e)."""

from __future__ import annotations

import argparse
import hashlib
import json
import math
import pickle
import random
import sys
from collections import Counter
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

# Allow running as a standalone script (tests invoke it via subprocess).
_ROOT = Path(__file__).resolve().parents[1]
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))

from audiogen_core.markov_serving_contract import MARKOV_BUNDLE_FORMAT_VERSION_KEY


def _iter_degree_duration_pairs(seq: Any) -> List[Tuple[int, float]]:
    out: List[Tuple[int, float]] = []
    if not isinstance(seq, list):
        return out
    for item in seq:
        if isinstance(item, (list, tuple)) and len(item) >= 2:
            try:
                out.append((int(item[0]), float(item[1])))
            except (TypeError, ValueError):
                continue
    return out


def _iter_melody_events(row: Dict[str, Any]) -> List[Tuple[int, float]]:
    out = _iter_degree_duration_pairs(row.get("melody"))
    if out:
        return out
    phrases = row.get("phrases")
    if isinstance(phrases, list):
        for ph in phrases:
            if not isinstance(ph, list):
                continue
            out.extend(_iter_degree_duration_pairs(ph))
    if out:
        return out
    # Arranged joint export (live_joint_training.v1): lead lane holds scale-degree sequences.
    lead = row.get("lead")
    if isinstance(lead, dict):
        for key in ("degrees", "midi", "pcs"):
            lane = _iter_degree_duration_pairs(lead.get(key))
            if lane:
                return lane
    return out


def _melody_key(mel: List[Tuple[int, float]]) -> str:
    try:
        raw = json.dumps([[int(d), float(t)] for d, t in mel], separators=(",", ":"))
        return hashlib.sha256(raw.encode("utf-8")).hexdigest()
    except Exception:
        return str(hash(tuple(mel)))


def _string_list(value: Any) -> List[str]:
    if not isinstance(value, list):
        return []
    return [str(v or "").strip() for v in value if str(v or "").strip()]


def _event_chord_sequence(row: Dict[str, Any], events: List[Tuple[int, float]]) -> Optional[List[str]]:
    chords = _string_list(row.get("chord_sequence"))
    if not chords or not events:
        return None
    if len(chords) == len(events):
        return list(chords)

    try:
        beats_per_bar = float(row.get("beats_per_bar", 4.0) or 4.0)
    except Exception:
        beats_per_bar = 4.0
    beats_per_bar = max(0.25, float(beats_per_bar))

    out: List[str] = []
    beat = 0.0
    for _, dur in events:
        bar = int(max(0.0, float(beat)) // beats_per_bar)
        out.append(str(chords[min(max(0, bar), len(chords) - 1)]))
        try:
            beat += abs(float(dur))
        except Exception:
            beat += 0.5
    return out if len(out) == len(events) else None


def _row_training_payload(row: Dict[str, Any]) -> Optional[Dict[str, Any]]:
    events = _iter_melody_events(row)
    if not events:
        return None
    mel = [(int(d), float(dur)) for d, dur in events]
    emotion = str(row.get("emotion") or "neutral").strip().lower() or "neutral"
    try:
        scale_iv = row.get("scale_intervals")
        if isinstance(scale_iv, list) and scale_iv:
            scale_iv = [int(x) for x in scale_iv]
        else:
            scale_iv = None
    except Exception:
        scale_iv = None
    try:
        roots = row.get("roots")
        root0 = int(roots[0]) if isinstance(roots, list) and roots else None
    except Exception:
        root0 = None
    return {
        "melody": mel,
        "emotion": emotion,
        "section_role": str(row.get("section_role") or "").strip().lower(),
        "accept_score": _safe_float(row.get("accept_score"), 1.0),
        "phrase_contours": _string_list(row.get("phrase_contours")),
        "phrase_roles": _string_list(row.get("phrase_roles")),
        "chord_sequence": _event_chord_sequence(row, mel),
        "root_note": root0,
        "scale_intervals": scale_iv,
        "beats_per_bar": _safe_float(row.get("beats_per_bar"), 4.0),
        "bpm": _safe_float(row.get("bpm", row.get("tempo", row.get("global_tempo"))), 0.0),
    }


def _safe_float(value: Any, default: float = 0.0) -> float:
    try:
        return float(value)
    except Exception:
        return float(default)


def emotion_family_for_name(name: str) -> str:
    n = (name or "").strip().lower()
    if not n:
        return "neutral"
    if any(k in n for k in ("grief", "sad", "remorse", "disappointment", "melanch")):
        return "sad"
    if any(k in n for k in ("calm", "relax", "peace", "serene")):
        return "calm"
    if any(k in n for k in ("fear", "nervous", "anxiety", "tense", "confus")):
        return "tense"
    if any(k in n for k in ("anger", "rage", "furious")):
        return "angry"
    if any(k in n for k in ("joy", "excite", "optim", "amuse", "pride")):
        return "energetic"
    if any(k in n for k in ("love", "caring", "gratitude", "relief", "approval")):
        return "warm"
    if any(k in n for k in ("surprise", "realization", "curiosity")):
        return "curious"
    return "neutral"


def _entropy_from_counter(counts: Counter, total: int) -> float:
    if total <= 0:
        return 0.0
    h = 0.0
    for c in counts.values():
        if c <= 0:
            continue
        p = float(c) / float(total)
        h -= p * math.log(p + 1e-18, 2)
    return float(h)


def _voiced_intervals(events: List[Tuple[int, float]]) -> List[int]:
    voiced = [int(d) for d, _ in events if isinstance(d, int) and int(d) >= 0]
    if len(voiced) < 2:
        return []
    return [int(voiced[i + 1]) - int(voiced[i]) for i in range(len(voiced) - 1)]


def _dataset_hash(rows: List[Dict[str, Any]]) -> str:
    h = hashlib.sha256()
    for row in rows:
        mel = row.get("melody") or []
        payload = {
            "melody": [[int(d), float(dur)] for d, dur in mel],
            "emotion": str(row.get("emotion") or ""),
            "section_role": str(row.get("section_role") or ""),
            "phrase_contours": list(row.get("phrase_contours") or []),
            "phrase_roles": list(row.get("phrase_roles") or []),
            "chord_sequence": list(row.get("chord_sequence") or []),
        }
        raw = json.dumps(payload, sort_keys=True, separators=(",", ":")).encode("utf-8")
        h.update(raw)
        h.update(b"\n")
    return h.hexdigest()


def build_training_manifest(
    *,
    input_path: Path,
    output_path: Path,
    rows: List[Dict[str, Any]],
    min_notes: int,
    min_accept: float,
    dedup: bool,
    max_melodies: int,
    seed: int,
) -> Dict[str, Any]:
    emotion_c: Counter[str] = Counter()
    section_c: Counter[str] = Counter()
    contour_c: Counter[str] = Counter()
    role_c: Counter[str] = Counter()
    duration_c: Counter[str] = Counter()
    interval_c: Counter[str] = Counter()
    events_total = 0
    rests_total = 0
    accept_sum = 0.0
    accept_n = 0
    chord_rows = 0
    contour_rows = 0
    role_rows = 0

    for row in rows:
        mel = list(row.get("melody") or [])
        emotion = str(row.get("emotion") or "neutral")
        if emotion:
            emotion_c[emotion] += 1
        section = str(row.get("section_role") or "")
        if section:
            section_c[section] += 1
        contours = [str(v) for v in (row.get("phrase_contours") or []) if str(v)]
        roles = [str(v) for v in (row.get("phrase_roles") or []) if str(v)]
        if contours:
            contour_rows += 1
            contour_c.update(contours)
        if roles:
            role_rows += 1
            role_c.update(roles)
        if row.get("chord_sequence"):
            chord_rows += 1
        accept_sum += _safe_float(row.get("accept_score"), 1.0)
        accept_n += 1
        for d, dur in mel:
            events_total += 1
            if isinstance(d, int) and int(d) < 0:
                rests_total += 1
            duration_c[f"{float(dur):g}"] += 1
        interval_c.update(str(v) for v in _voiced_intervals(mel))

    rest_rate = float(rests_total) / float(events_total) if events_total else 0.0
    interval_total = int(sum(interval_c.values()))
    return {
        "schema_version": 1,
        "source": "scripts/melody_jsonl_retrain.py",
        "input_path": str(input_path),
        "output_path": str(output_path),
        "dataset_sha256": _dataset_hash(rows),
        "filters": {
            "min_notes": int(min_notes),
            "min_accept": float(min_accept),
            "dedup": bool(dedup),
            "max_melodies": int(max_melodies),
        },
        "seed": int(seed),
        "rows": int(len(rows)),
        "events": int(events_total),
        "rests": int(rests_total),
        "rest_rate": float(rest_rate),
        "mean_accept": float(accept_sum / float(accept_n)) if accept_n else 0.0,
        "rows_with_phrase_contours": int(contour_rows),
        "rows_with_phrase_roles": int(role_rows),
        "rows_with_chord_sequences": int(chord_rows),
        "emotion_counts": dict(sorted(emotion_c.items())),
        "section_role_counts": dict(sorted(section_c.items())),
        "phrase_contour_counts": dict(sorted(contour_c.items())),
        "phrase_role_counts": dict(sorted(role_c.items())),
        "duration_counts": dict(sorted(duration_c.items(), key=lambda kv: (-kv[1], kv[0]))),
        "interval_counts": dict(sorted(interval_c.items(), key=lambda kv: (-kv[1], kv[0]))),
        "interval_entropy_bits": _entropy_from_counter(interval_c, interval_total),
    }


def _train_markov_from_rows(
    rows: List[Dict[str, Any]],
    *,
    seed: int,
    global_fallback: Any = None,
) -> Any:
    from ai.markov.melody.generator import MelodyGenerator

    melodies = [r["melody"] for r in rows]
    phrase_contours = [r["phrase_contours"] for r in rows]
    phrase_roles = [r["phrase_roles"] for r in rows]
    emotion_names = [r["emotion"] for r in rows]
    chord_sequences_raw = [r["chord_sequence"] for r in rows]
    root_notes = [r.get("root_note") for r in rows]
    scale_iv = [r.get("scale_intervals") for r in rows]
    chord_sequences = [
        seq if isinstance(seq, list) and len(seq) == len(mel) else []
        for seq, mel in zip(chord_sequences_raw, melodies)
    ]
    use_chords = any(bool(seq) for seq in chord_sequences)
    beats_per_bar = [r.get("beats_per_bar") for r in rows]
    bpms_raw = [r.get("bpm") for r in rows]
    bpms = [float(v) if v is not None and float(v) > 1e-9 else None for v in bpms_raw]

    rng = random.Random(int(seed))
    g = MelodyGenerator(rng=rng, use_chord_conditioned_markov=bool(use_chords))
    g.train_from_melodies(
        melodies,
        phrase_contours=phrase_contours if any(phrase_contours) else None,
        phrase_roles=phrase_roles if any(phrase_roles) else None,
        emotion_name="neutral",
        emotion_names=emotion_names,
        chord_sequences=chord_sequences if use_chords else None,
        root_notes=list(root_notes),
        scale_intervals_by_melody=list(scale_iv),
        beats_per_bar_by_melody=list(beats_per_bar),
        bpm_by_melody=list(bpms),
    )
    if global_fallback is not None:
        g.markov.global_fallback = global_fallback
    return g.markov


def _group_rows(rows: List[Dict[str, Any]], key: str) -> Dict[str, List[Dict[str, Any]]]:
    grouped: Dict[str, List[Dict[str, Any]]] = {}
    for row in rows:
        if key == "emotion":
            name = str(row.get("emotion") or "neutral").strip().lower() or "neutral"
        elif key == "family":
            name = emotion_family_for_name(str(row.get("emotion") or "neutral"))
        else:
            name = "global"
        grouped.setdefault(name, []).append(row)
    return dict(sorted(grouped.items()))


def load_filtered_melodies(
    path: Path,
    *,
    min_notes: int,
    min_accept: float,
    dedup: bool,
    max_lines: int = 0,
) -> List[List[Tuple[int, float]]]:
    seen: set = set()
    out: List[List[Tuple[int, float]]] = []
    with path.open("r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            try:
                row = json.loads(line)
            except json.JSONDecodeError:
                continue
            try:
                if float(row.get("accept_score", 1.0) or 1.0) < float(min_accept):
                    continue
            except Exception:
                pass
            events = _iter_melody_events(row)
            if len(events) < int(min_notes):
                continue
            mel = [(int(d), float(dur)) for d, dur in events]
            if dedup:
                k = _melody_key(mel)
                if k in seen:
                    continue
                seen.add(k)
            out.append(mel)
            if max_lines > 0 and len(out) >= int(max_lines):
                break
    return out


def load_filtered_training_rows(
    path: Path,
    *,
    min_notes: int,
    min_accept: float,
    dedup: bool,
    max_lines: int = 0,
) -> List[Dict[str, Any]]:
    seen: set = set()
    out: List[Dict[str, Any]] = []
    with path.open("r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            try:
                row = json.loads(line)
            except json.JSONDecodeError:
                continue
            try:
                if float(row.get("accept_score", 1.0) or 1.0) < float(min_accept):
                    continue
            except Exception:
                pass
            payload = _row_training_payload(row)
            if not payload:
                continue
            mel = payload["melody"]
            if len(mel) < int(min_notes):
                continue
            if dedup:
                k = _melody_key(mel)
                if k in seen:
                    continue
                seen.add(k)
            out.append(payload)
            if max_lines > 0 and len(out) >= int(max_lines):
                break
    return out


def main() -> int:
    # Ensure repo root is importable when running as a script.
    try:
        root = Path(__file__).resolve().parent.parent
        if str(root) not in sys.path:
            sys.path.insert(0, str(root))
    except Exception:
        pass

    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument(
        "jsonl",
        nargs="?",
        default=".cache/live_melody_training.jsonl",
        help="Input JSONL path.",
    )
    ap.add_argument(
        "-o",
        "--output",
        default="training_data/active_models/melody_markov.pkl",
        help="Output pickle for MarkovModelSet.",
    )
    ap.add_argument("--min-notes", type=int, default=4)
    ap.add_argument("--min-accept", type=float, default=0.0)
    ap.add_argument("--dedup", action="store_true", help="Drop duplicate melodies (content hash).")
    ap.add_argument("--max-melodies", type=int, default=0, help="Cap training set size (0 = no cap).")
    ap.add_argument(
        "--manifest-output",
        default=None,
        help="Write artifact manifest JSON here (default: <output>.manifest.json).",
    )
    ap.add_argument(
        "--grouped",
        choices=("none", "emotion", "family", "both"),
        default="none",
        help="Train a bundle with global fallback plus per-emotion and/or per-family models.",
    )
    ap.add_argument(
        "--min-group-melodies",
        type=int,
        default=4,
        help="Minimum rows required to train an emotion/family model in grouped mode.",
    )
    ap.add_argument("--seed", type=int, default=0)
    args = ap.parse_args()

    p = Path(args.jsonl)
    if not p.is_file():
        print(f"File not found: {p}", file=sys.stderr)
        return 1

    try:
        from audiogen_core.config import CONFIG

        min_notes = int(getattr(CONFIG.composition, "melody_jsonl_retrain_min_notes", args.min_notes) or args.min_notes)
        min_accept = float(getattr(CONFIG.composition, "melody_jsonl_retrain_min_accept_score", args.min_accept) or args.min_accept)
    except Exception:
        min_notes = int(args.min_notes)
        min_accept = float(args.min_accept)

    cap = int(args.max_melodies) if int(args.max_melodies) > 0 else 0
    rows = load_filtered_training_rows(
        p,
        min_notes=min_notes,
        min_accept=min_accept,
        dedup=bool(args.dedup),
        max_lines=cap,
    )
    if len(rows) < 1:
        print("No melodies after filtering.", file=sys.stderr)
        return 2

    melodies = [r["melody"] for r in rows]
    phrase_contours = [r["phrase_contours"] for r in rows]
    phrase_roles = [r["phrase_roles"] for r in rows]
    emotion_names = [r["emotion"] for r in rows]
    chord_sequences_raw = [r["chord_sequence"] for r in rows]
    chord_sequences = [
        seq if isinstance(seq, list) and len(seq) == len(mel) else []
        for seq, mel in zip(chord_sequences_raw, melodies)
    ]

    out = Path(args.output)
    manifest = build_training_manifest(
        input_path=p,
        output_path=out,
        rows=rows,
        min_notes=int(min_notes),
        min_accept=float(min_accept),
        dedup=bool(args.dedup),
        max_melodies=int(cap),
        seed=int(args.seed),
    )
    grouped_mode = str(args.grouped or "none")
    min_group = max(1, int(args.min_group_melodies))
    if grouped_mode == "none":
        artifact = _train_markov_from_rows(rows, seed=int(args.seed))
        artifact.training_metadata = manifest
    else:
        global_model = _train_markov_from_rows(rows, seed=int(args.seed))
        global_model.training_metadata = dict(manifest)
        emotion_models = {}
        family_models = {}
        if grouped_mode in {"emotion", "both"}:
            for name, group in _group_rows(rows, "emotion").items():
                if len(group) >= min_group:
                    model = _train_markov_from_rows(group, seed=int(args.seed), global_fallback=global_model)
                    model.training_metadata = build_training_manifest(
                        input_path=p,
                        output_path=out,
                        rows=group,
                        min_notes=int(min_notes),
                        min_accept=float(min_accept),
                        dedup=bool(args.dedup),
                        max_melodies=0,
                        seed=int(args.seed),
                    )
                    emotion_models[str(name)] = model
        if grouped_mode in {"family", "both"}:
            for name, group in _group_rows(rows, "family").items():
                if len(group) >= min_group:
                    model = _train_markov_from_rows(group, seed=int(args.seed), global_fallback=global_model)
                    model.training_metadata = build_training_manifest(
                        input_path=p,
                        output_path=out,
                        rows=group,
                        min_notes=int(min_notes),
                        min_accept=float(min_accept),
                        dedup=bool(args.dedup),
                        max_melodies=0,
                        seed=int(args.seed),
                    )
                    family_models[str(name)] = model
        manifest["grouped"] = {
            "mode": grouped_mode,
            "min_group_melodies": int(min_group),
            "emotion_models": sorted(emotion_models.keys()),
            "family_models": sorted(family_models.keys()),
        }
        artifact = {
            "kind": "melody_markov_bundle",
            "version": 1,
            MARKOV_BUNDLE_FORMAT_VERSION_KEY: 1,
            "global": global_model,
            "emotion_models": emotion_models,
            "family_models": family_models,
            "metadata": manifest,
        }

    out.parent.mkdir(parents=True, exist_ok=True)
    with out.open("wb") as f:
        pickle.dump(artifact, f, protocol=pickle.HIGHEST_PROTOCOL)
    if args.manifest_output:
        manifest_out = Path(str(args.manifest_output))
    else:
        manifest_out = out.with_suffix(out.suffix + ".manifest.json")
    manifest_out.parent.mkdir(parents=True, exist_ok=True)
    manifest_out.write_text(json.dumps(manifest, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(
        f"wrote {out}  melodies={len(melodies)}"
        f"  contours={sum(1 for x in phrase_contours if x)}"
        f"  roles={sum(1 for x in phrase_roles if x)}"
        f"  chord_conditioned={sum(1 for x in chord_sequences if x)}"
        f"  emotions={len(set(emotion_names))}"
        f"  grouped={grouped_mode}"
        f"  manifest={manifest_out}"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
