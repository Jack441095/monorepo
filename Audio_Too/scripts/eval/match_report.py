#!/usr/bin/env python3
"""
Before/after evidence report for reference spectral matching.

Takes the baseline render, the matched render, and the reference (a single track
OR a genre folder) and writes a self-contained HTML page: match score before ->
after, tonal balance chart (before / after / target), per-band numbers, the EQ
moves applied, and the final master's delivery-safety figures.

Both the QA artifact (did matching help, and is it safe to ship?) and the page
you can send a client.

    python scripts/eval/match_report.py \
        --before  out/baseline/mixdown_v1.wav \
        --after   out/matched/mixdown_v1.wav \
        --reference reference_tracks/pop \
        --output  match_report.html
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
for p in (ROOT, ROOT / "studio" / "audio_analysis"):
    if str(p) not in sys.path:
        sys.path.insert(0, str(p))

from audio_analysis.mix_review.match_report import (  # noqa: E402
    build_match_evidence, render_match_report_html,
)


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--before", required=True, help="Baseline (unmatched) render WAV.")
    ap.add_argument("--after", required=True, help="Matched render WAV.")
    ap.add_argument("--reference", required=True,
                    help="Reference audio file OR a genre folder (median target).")
    ap.add_argument("--output", default="match_report.html", help="Output HTML path.")
    ap.add_argument("--decisions", default=None,
                    help="Optional mix_decisions_v1.json from the matched render; its "
                         "match EQ moves are listed in the report.")
    ap.add_argument("--mix-label", default=None, help="Name for the mix (default: after filename).")
    ap.add_argument("--ref-label", default=None, help="Name for the reference (default: its name).")
    ap.add_argument("--genre", default=None,
                    help="AutoMix decision-engine genre, threaded into KENN's grounded "
                         "explanations of the applied moves and the reference profile.")
    args = ap.parse_args(argv)

    before, after, ref = Path(args.before), Path(args.after), Path(args.reference)
    for p in (before, after):
        if not p.is_file():
            print(f"FAILED: {p} is not a file.")
            return 1
    if not ref.exists():
        print(f"FAILED: reference {ref} not found.")
        return 1

    # The match EQ moves aren't recoverable from a WAV; read them from the
    # matched render's decisions if supplied (bus_eq_bands tagged "Ref match").
    applied: list[dict] = []
    if args.decisions:
        try:
            import json
            data = json.loads(Path(args.decisions).read_text())
            applied = [b for b in (data.get("bus", {}).get("bus_eq_bands") or [])
                       if "ref match" in str(b.get("reason", "")).lower()]
        except Exception as exc:
            print(f"  (could not read decisions: {exc.__class__.__name__}; skipping moves)")

    print(f"Measuring before/after against {ref.name} ...")
    evidence = build_match_evidence(before.read_bytes(), after.read_bytes(), ref,
                                    applied_bands=applied, genre=args.genre)

    html = render_match_report_html(
        evidence,
        mix_label=args.mix_label or after.parent.name or after.stem,
        ref_label=args.ref_label or ref.name,
    )
    out = Path(args.output)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(html, encoding="utf-8")

    print(f"  score {evidence['score_before']} -> {evidence['score_after']} "
          f"({evidence['score_delta']:+})")
    s = evidence.get("safety") or {}
    if s:
        print(f"  final: LUFS {s.get('integrated_lufs')}, true-peak {s.get('true_peak_dbfs')} dBFS, "
              f"clipped {s.get('clipped_frames')}")
    print(f"Report -> {out}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
