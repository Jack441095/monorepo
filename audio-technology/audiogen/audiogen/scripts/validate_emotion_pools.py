#!/usr/bin/env python3
"""
CI / pre-commit: validate curated emotion harmony data.

Runs the same checks as tests/test_emotion_harmony_audit.py plus a Markov-corpus
smoke test (chord token sequences from data/training_corpus.py).

  python3 scripts/validate_emotion_pools.py
  python3 scripts/validate_emotion_pools.py --verbose
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path
from typing import List


def _root() -> Path:
    return Path(__file__).resolve().parents[1]


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument(
        "-v",
        "--verbose",
        action="store_true",
        help="Print per-issue lines (default: count only on failure).",
    )
    args = ap.parse_args()
    root = _root()
    if str(root) not in sys.path:
        sys.path.insert(0, str(root))

    from data.audit import AuditIssue, audit_all_emotions
    from data.music_data import EMOTIONS
    from data.training_corpus import get_chord_sequences

    issues: List[AuditIssue] = audit_all_emotions(EMOTIONS)

    get_chord_sequences.cache_clear()
    names = tuple(str(getattr(e, "name", "") or "").strip().lower() for e in EMOTIONS)
    nseq_bucket = 0
    for mode in ("bucket", "degree"):
        seqs, weights = get_chord_sequences(names, token_mode=mode, include_cadences=True)
        if not seqs:
            print(
                f"validate_emotion_pools: FAIL  get_chord_sequences({mode!r}) returned 0 sequences",
                file=sys.stderr,
            )
            return 1
        for i, s in enumerate(seqs):
            if len(s) < 2:
                print(
                    f"validate_emotion_pools: FAIL  sequence {i} len={len(s)} mode={mode!r} seq={s!r}",
                    file=sys.stderr,
                )
                return 1
        if len(weights) != len(seqs):
            print("validate_emotion_pools: FAIL  weights/seqs length mismatch", file=sys.stderr)
            return 1
        if mode == "bucket":
            nseq_bucket = len(seqs)

    if issues:
        if bool(args.verbose):
            for it in issues:
                sev = str(getattr(it, "severity", "warn") or "warn")
                print(f"[{sev}] {it.kind} @ {it.where}: {it.message}", file=sys.stderr)
        else:
            err = [i for i in issues if str(getattr(i, "severity", "warn") or "warn") == "error"]
            warn = [i for i in issues if str(getattr(i, "severity", "warn") or "warn") != "error"]
            print(
                f"validate_emotion_pools: FAIL  emotions={len(EMOTIONS)}  "
                f"issues={len(issues)}  (error={len(err)}, other={len(warn)})  (use -v for lines)",
                file=sys.stderr,
            )
        return 1

    print(
        f"validate_emotion_pools: OK  emotions={len(EMOTIONS)}  chord_markov_sequences={nseq_bucket}"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
