#!/usr/bin/env python3
"""Prepare an unapproved specialist packet from locally reviewed source-family drafts."""

from __future__ import annotations

import argparse
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "tooling"))

from seal_experiment.preparation import emit
from seal_experiment.records import read


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--spec", type=Path, required=True)
    parser.add_argument("--out", type=Path, required=True)
    args = parser.parse_args()
    output = args.out.resolve()
    # Source rights may still be unresolved. Follow the experiment CLI's runtime
    # boundary so a preparation command cannot publish licensed or private text.
    if output.is_relative_to(ROOT.parents[1]) and not output.is_relative_to(ROOT / ".runtime"):
        parser.error("output must be outside the Git checkout or under ignored products/kenn/.runtime/")
    try:
        receipt = emit(read(args.spec), output)
    except ValueError as exc:
        # Invalid or reused drafts produce no training-ready artifact; the owner fixes the input.
        parser.error(str(exc))
    print(f"Prepared {receipt['counts']}; owner review pending, training disabled")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
