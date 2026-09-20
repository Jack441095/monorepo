#!/usr/bin/env python3
"""
One command: render a track's stems baseline + matched-to-a-genre-reference, and
write the before/after evidence report. The whole P1 loop in a single line.

    python scripts/eval/match_track.py <stems_dir> \
        --reference reference_tracks/hiphop_rnb \
        --genre hip_hop \
        --output out/<track>

Produces under --output:
    baseline/  matched/  match_report.html   (+ prints the score movement)

`--reference` is a genre FOLDER (robust median target) or a single file.
`--genre` is the AutoMix decision-engine genre (pop / hip_hop / rock / …);
defaults to a guess from the reference folder name.
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
for p in (ROOT, ROOT / "scripts", ROOT / "studio" / "audio_analysis",
          ROOT / "studio" / "audio_analysis" / "audio_analysis"):
    if str(p) not in sys.path:
        sys.path.insert(0, str(p))

# Map reference-folder names -> a sensible decision-engine genre.
_FOLDER_GENRE = {
    "hiphop_rnb": "hip_hop", "pop": "pop", "electronic": "electronic",
    "cinematic": "pop", "acoustic": "acoustic", "rock": "rock",
}


def _find_mix(out_dir: Path) -> Path | None:
    hits = sorted(out_dir.rglob("mixdown_v1.wav"))
    return hits[0] if hits else None


def _find_decisions(out_dir: Path) -> Path | None:
    hits = sorted(out_dir.rglob("mix_decisions_v1.json"))
    return hits[0] if hits else None


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("stems_dir", help="Folder of stem WAVs (or a track folder containing them).")
    ap.add_argument("--reference", required=True,
                    help="Genre reference FOLDER (median target) or a single reference file.")
    ap.add_argument("--genre", default=None,
                    help="AutoMix decision-engine genre (default: guessed from the reference folder).")
    ap.add_argument("--output", default=None, help="Output dir (default: out/<stems folder name>).")
    ap.add_argument("--label", default=None, help="Track label for the report.")
    args = ap.parse_args(argv)

    from automix_local import run_local_automix
    from audio_analysis.mix_review.match_report import build_match_evidence, render_match_report_html

    stems = Path(args.stems_dir).expanduser().resolve()
    ref = Path(args.reference).expanduser().resolve()
    if not stems.is_dir():
        print(f"FAILED: {stems} is not a directory.")
        return 1
    if not ref.exists():
        print(f"FAILED: reference {ref} not found.")
        return 1
    genre = args.genre or _FOLDER_GENRE.get(ref.name.lower(), "pop")
    label = args.label or stems.parent.name if stems.name.lower() in ("wavs", "wav's", "stems") else stems.name
    out = Path(args.output).expanduser().resolve() if args.output else (ROOT / "out" / label)
    ref_label = ref.name if ref.is_dir() else ref.stem

    print(f"Track: {label}  |  genre: {genre}  |  reference: {ref_label}\n")

    print("[1/3] Rendering BASELINE (no match) ...", flush=True)
    run_local_automix(stems, genre=genre, output_dir=out / "baseline", project_id="baseline")

    print("[2/3] Rendering MATCHED (two-pass reference match) ...", flush=True)
    run_local_automix(stems, genre=genre, output_dir=out / "matched", project_id="matched",
                      reference_track=ref, match_reference=True)

    base_mix = _find_mix(out / "baseline")
    match_mix = _find_mix(out / "matched")
    if not base_mix or not match_mix:
        print("FAILED: a render did not produce a mixdown.")
        return 1

    print("[3/3] Building evidence report ...", flush=True)
    applied = []
    dj = _find_decisions(out / "matched")
    if dj:
        import json
        try:
            data = json.loads(dj.read_text())
            applied = [b for b in (data.get("bus", {}).get("bus_eq_bands") or [])
                       if "ref match" in str(b.get("reason", "")).lower()]
        except Exception:
            pass

    evidence = build_match_evidence(base_mix.read_bytes(), match_mix.read_bytes(), ref,
                                    applied_bands=applied, genre=genre)
    html = render_match_report_html(evidence, mix_label=label, ref_label=ref_label)
    report = out / "match_report.html"
    report.write_text(html, encoding="utf-8")

    s = evidence.get("safety") or {}
    print(f"\n  match score:  {evidence['score_before']} -> {evidence['score_after']} "
          f"({evidence['score_delta']:+})")
    print(f"  final master: LUFS {s.get('integrated_lufs')}, true-peak {s.get('true_peak_dbfs')} dBFS, "
          f"clipped {s.get('clipped_frames')}")
    print(f"\n  baseline mix: {base_mix}")
    print(f"  matched mix:  {match_mix}")
    print(f"  REPORT ->     {report}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
