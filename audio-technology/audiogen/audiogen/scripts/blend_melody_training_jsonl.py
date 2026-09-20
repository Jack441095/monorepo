#!/usr/bin/env python3
"""Blend generated and reference melody-training JSONL files."""

from __future__ import annotations

import argparse
from pathlib import Path


def _append(src: Path, dst, copies: int) -> int:
    rows = [line for line in src.read_text(encoding="utf-8").splitlines() if line.strip()]
    for _ in range(max(1, int(copies))):
        for line in rows:
            dst.write(line + "\n")
    return len(rows) * max(1, int(copies))


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--generated", required=True)
    ap.add_argument("--reference", required=True)
    ap.add_argument("--reference-copies", type=int, default=8)
    ap.add_argument("--out", required=True)
    args = ap.parse_args()

    out = Path(args.out).expanduser()
    out.parent.mkdir(parents=True, exist_ok=True)
    with out.open("w", encoding="utf-8") as fh:
        generated_n = _append(Path(args.generated).expanduser(), fh, 1)
        reference_n = _append(Path(args.reference).expanduser(), fh, int(args.reference_copies))
    print(f"wrote {out} generated_rows={generated_n} reference_rows={reference_n}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
