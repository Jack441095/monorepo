#!/usr/bin/env python3
"""
Retrain chord Markov models from the live melody training JSONL export.

This produces a pickled bundle that `CompositionGenerator` can load at runtime
to replace the startup-fit chord Markovs trained from curated pools.

Inputs:
- live JSONL rows that contain either:
  - `chord_markov_tokens` (preferred), and/or
  - `chord_sequence` (roman symbols), which will be tokenized via `ChordToken`.

Outputs:
- A pickle bundle with:
  - degree-token chord Markov
  - bucket backoff chord Markov
  - optional global variants (same training set, but kept distinct for wiring)
- A JSON manifest with dataset hash + token counts.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import pickle
import sys
from collections import Counter
from pathlib import Path
from typing import Any, Dict, Iterable, List, Sequence, Tuple

# Allow running as a standalone script (tests invoke it via subprocess).
_ROOT = Path(__file__).resolve().parents[1]
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))

from audiogen_core.markov_serving_contract import MARKOV_BUNDLE_FORMAT_VERSION_KEY


def _iter_jsonl(path: Path) -> Iterable[Dict[str, Any]]:
    with path.open("r", encoding="utf-8") as handle:
        for line in handle:
            s = (line or "").strip()
            if not s:
                continue
            try:
                row = json.loads(s)
            except json.JSONDecodeError:
                continue
            if isinstance(row, dict):
                yield row


def _safe_float(x: Any, default: float = 0.0) -> float:
    try:
        return float(x)
    except Exception:
        return float(default)


def _string_list(x: Any) -> List[str]:
    if not isinstance(x, list):
        return []
    out = []
    for v in x:
        s = str(v or "").strip()
        if s:
            out.append(s)
    return out


def _dataset_hash(rows: Sequence[Dict[str, Any]]) -> str:
    h = hashlib.sha256()
    for row in rows:
        payload = {
            "emotion": str(row.get("emotion") or ""),
            "section_role": str(row.get("section_role") or ""),
            "chord_markov_tokens": list(row.get("chord_markov_tokens") or []),
            "chord_sequence": list(row.get("chord_sequence") or []),
        }
        h.update(json.dumps(payload, sort_keys=True, separators=(",", ":")).encode("utf-8"))
        h.update(b"\n")
    return h.hexdigest()


def _tokenize_row(
    row: Dict[str, Any],
    *,
    use_degree_tokens: bool,
) -> List[str]:
    toks = _string_list(row.get("chord_markov_tokens"))
    if toks:
        # Already includes degree token prefix when exported from generator.
        if use_degree_tokens:
            return toks
        # Bucketize: strip degree component.
        try:
            from data.tokens import ChordToken

            return [ChordToken.token_bucket(t) for t in toks if str(t)]
        except Exception:
            return [str(t).split(":", 1)[-1] for t in toks]

    chords = _string_list(row.get("chord_sequence"))
    if not chords:
        return []
    try:
        from data.tokens import ChordToken
    except Exception:
        return []
    out = []
    for ch in chords:
        try:
            bucket = "dom"
            # Minimal default bucket guess if we can't import owner simplifier here.
            s = str(ch)
            if s.startswith("i") and not s.startswith("I"):
                bucket = "min"
            tok = ChordToken.from_symbol(str(ch), bucket=str(bucket))
            out.append(tok.serialize(use_degree=bool(use_degree_tokens)))
        except Exception:
            continue
    if not use_degree_tokens:
        try:
            out = [ChordToken.token_bucket(t) for t in out]
        except Exception:
            out = [str(t).split(":", 1)[-1] for t in out]
    return out


def load_training_sequences(
    path: Path,
    *,
    min_len: int,
    max_rows: int,
) -> Tuple[List[Dict[str, Any]], List[List[str]], List[List[str]], List[float]]:
    """
    Returns:
    - filtered rows (for hashing/manifest)
    - degree-token sequences
    - bucket-token sequences
    - sequence weights (accept_score)
    """
    rows: List[Dict[str, Any]] = []
    degree_seqs: List[List[str]] = []
    bucket_seqs: List[List[str]] = []
    weights: List[float] = []

    for row in _iter_jsonl(path):
        deg = _tokenize_row(row, use_degree_tokens=True)
        buc = _tokenize_row(row, use_degree_tokens=False)
        # Require at least one representation.
        if len(deg) < int(min_len) and len(buc) < int(min_len):
            continue
        # Keep sequences aligned lengthwise; prefer degree tokens if present.
        if len(deg) < int(min_len):
            deg = []
        if len(buc) < int(min_len):
            buc = []
        if not deg and not buc:
            continue
        w = _safe_float(row.get("accept_score"), 1.0)
        w = max(0.0, float(w))

        rows.append(row)
        degree_seqs.append(deg if deg else buc)
        bucket_seqs.append(buc if buc else [str(x).split(":", 1)[-1] for x in (deg or [])])
        weights.append(w if w > 0 else 1.0)
        if int(max_rows) > 0 and len(rows) >= int(max_rows):
            break

    return rows, degree_seqs, bucket_seqs, weights


def build_manifest(
    *,
    input_path: Path,
    output_path: Path,
    rows: List[Dict[str, Any]],
    degree_seqs: List[List[str]],
    bucket_seqs: List[List[str]],
    weights: List[float],
    order: int,
    smoothing: float,
    backoff_decay: float,
) -> Dict[str, Any]:
    emo = Counter()
    roles = Counter()
    deg_tok = Counter()
    buc_tok = Counter()
    for row, ds, bs in zip(rows, degree_seqs, bucket_seqs):
        e = str(row.get("emotion") or "").strip().lower()
        r = str(row.get("section_role") or "").strip().lower()
        if e:
            emo[e] += 1
        if r:
            roles[r] += 1
        deg_tok.update(str(t) for t in (ds or []) if str(t))
        buc_tok.update(str(t) for t in (bs or []) if str(t))
    return {
        "schema_version": 1,
        "source": "scripts/chord_jsonl_retrain.py",
        "input_path": str(input_path),
        "output_path": str(output_path),
        "dataset_sha256": _dataset_hash(rows),
        "rows": int(len(rows)),
        "order": int(order),
        "smoothing": float(smoothing),
        "backoff_decay": float(backoff_decay),
        "emotion_counts": dict(sorted(emo.items())),
        "section_role_counts": dict(sorted(roles.items())),
        "degree_token_vocab": int(len(deg_tok)),
        "bucket_token_vocab": int(len(buc_tok)),
        "top_degree_tokens": dict(deg_tok.most_common(20)),
        "top_bucket_tokens": dict(buc_tok.most_common(12)),
        "mean_accept_weight": float(sum(weights) / max(1, len(weights))) if weights else 0.0,
    }


def main() -> int:
    root = Path(__file__).resolve().parent.parent
    if str(root) not in sys.path:
        sys.path.insert(0, str(root))

    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("jsonl", nargs="?", default=".cache/live_melody_training.jsonl")
    ap.add_argument(
        "-o",
        "--output",
        default="training_data/active_models/chord_markov.pkl",
        help="Output pickle for chord Markov bundle.",
    )
    ap.add_argument("--manifest-output", default=None)
    ap.add_argument("--order", type=int, default=3)
    ap.add_argument("--smoothing", type=float, default=0.01)
    ap.add_argument("--backoff-decay", type=float, default=0.84)
    ap.add_argument("--min-len", type=int, default=4, help="Minimum tokens per sequence to include.")
    ap.add_argument("--max-rows", type=int, default=0, help="Optional cap on training rows (0 = no cap).")
    ap.add_argument("--seed", type=int, default=0)
    args = ap.parse_args()

    p = Path(str(args.jsonl)).expanduser()
    if not p.is_absolute():
        p = root / p
    if not p.is_file():
        print(f"File not found: {p}", file=sys.stderr)
        return 1

    order = max(1, int(args.order))
    smoothing = max(0.0, float(args.smoothing))
    backoff = max(0.05, min(0.99, float(args.backoff_decay)))

    rows, degree_seqs, bucket_seqs, weights = load_training_sequences(
        p,
        min_len=int(args.min_len),
        max_rows=int(args.max_rows),
    )
    if not rows:
        print("No chord rows after filtering (need chord_markov_tokens or chord_sequence).", file=sys.stderr)
        return 2

    try:
        import random

        rng = random.Random(int(args.seed))
    except Exception:
        rng = None

    from ai.markov import ChordMarkov, GlobalChordMarkov

    degree_model = ChordMarkov(order=order, smoothing=smoothing, backoff_decay=backoff, rng=rng)
    bucket_model = ChordMarkov(order=order, smoothing=smoothing, backoff_decay=backoff, rng=rng)
    degree_model.train(degree_seqs, sequence_weights=weights)
    bucket_model.train(bucket_seqs, sequence_weights=weights)

    global_degree = GlobalChordMarkov(order=order, smoothing=smoothing, backoff_decay=backoff, rng=rng)
    global_bucket = GlobalChordMarkov(order=order, smoothing=smoothing, backoff_decay=backoff, rng=rng)
    global_degree.train(degree_seqs, sequence_weights=weights)
    global_bucket.train(bucket_seqs, sequence_weights=weights)

    out = Path(str(args.output)).expanduser()
    if not out.is_absolute():
        out = root / out
    out.parent.mkdir(parents=True, exist_ok=True)

    manifest = build_manifest(
        input_path=p,
        output_path=out,
        rows=rows,
        degree_seqs=degree_seqs,
        bucket_seqs=bucket_seqs,
        weights=weights,
        order=order,
        smoothing=smoothing,
        backoff_decay=backoff,
    )

    bundle = {
        "kind": "chord_markov_bundle",
        "version": 1,
        MARKOV_BUNDLE_FORMAT_VERSION_KEY: 1,
        "degree": degree_model,
        "bucket": bucket_model,
        "global_degree": global_degree,
        "global_bucket": global_bucket,
        "metadata": manifest,
    }
    with out.open("wb") as f:
        pickle.dump(bundle, f, protocol=pickle.HIGHEST_PROTOCOL)

    if args.manifest_output:
        m_out = Path(str(args.manifest_output)).expanduser()
        if not m_out.is_absolute():
            m_out = root / m_out
    else:
        m_out = out.with_suffix(out.suffix + ".manifest.json")
    m_out.parent.mkdir(parents=True, exist_ok=True)
    m_out.write_text(json.dumps(manifest, indent=2, sort_keys=True) + "\n", encoding="utf-8")

    print(f"wrote {out} rows={len(rows)} degree_vocab={manifest['degree_token_vocab']} bucket_vocab={manifest['bucket_token_vocab']}")
    print(f"manifest {m_out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

