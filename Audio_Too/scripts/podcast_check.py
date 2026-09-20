#!/usr/bin/env python3
"""Run the podcast/spoken-word analysis on a real audio file.

Decodes an audio file (wav/mp3/flac/... via the mix-review decoders), computes
the standard analysis metrics, runs ``analyze_podcast``, and prints a readable
report — optionally writing the shareable HTML.

Usage:
    python scripts/podcast_check.py data/podcast_test_corpus/<file>.mp3
    python scripts/podcast_check.py episode.wav --target spotify --html out.html
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
for _p in (
    REPO_ROOT / "studio" / "audio_analysis",
    REPO_ROOT / "studio" / "audio_analysis" / "audio_analysis",
    REPO_ROOT / "business",
    REPO_ROOT / "business" / "app",
    REPO_ROOT,
):
    if str(_p) not in sys.path:
        sys.path.insert(0, str(_p))

_STATUS_MARK = {"ok": "OK  ", "warn": "WARN", "fail": "FAIL"}


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("audio", help="Path to an audio file (wav/mp3/flac/...).")
    parser.add_argument("--target", default="apple",
                        help="Delivery target: apple | spotify | mono | youtube (default apple).")
    parser.add_argument("--html", help="Also write the shareable HTML report to this path.")
    args = parser.parse_args(argv)

    audio_path = Path(args.audio)
    if not audio_path.is_file():
        print(f"File not found: {audio_path}")
        return 2

    from audio_analysis.mix_review import mix_review
    from audio_analysis.podcast import analyze_podcast, render_podcast_report_html

    file_bytes = audio_path.read_bytes()
    try:
        result = mix_review.analyze_wav(file_bytes, audio_path.name)
    except Exception as exc:  # noqa: BLE001 - surface decode/analysis errors plainly
        print(f"Analysis failed for {audio_path.name}: {exc}")
        return 1

    # analyze_wav returns the measurements dict; accept a {'metrics': {...}} wrap too.
    metrics = result.get("metrics") if isinstance(result.get("metrics"), dict) else result
    # explain=True: this is the report-generation CLI (the one that gets
    # --publish'd or read by a person), so it's the one caller that should
    # opt into KENN's grounded explanations -- analyze_podcast defaults
    # explain to False for every other, more lightweight caller.
    report = analyze_podcast(metrics, target=args.target, explain=True)

    print(f"\nPodcast check — {audio_path.name}")
    print(f"Target: {report['target_label']}    Readiness: {report['score']}/100")
    print(f"{report['summary']}\n")
    for c in sorted(report["checks"], key=lambda c: {"fail": 0, "warn": 1, "ok": 2}.get(c["status"], 3)):
        mark = _STATUS_MARK.get(c["status"], "?")
        meta = f"[{c['measured']} vs {c['target']}]" if c.get("measured") else ""
        print(f"  {mark}  {c['label']:<26} {meta}")
        if c["status"] != "ok":
            print(f"        -> {c['fix']}")
    if not report["checks"]:
        print("  (no measurable issues — very short or silent clip?)")
    if not report["calibrated"]:
        print("\nNote: thresholds are heuristics pending calibration on a real dialogue corpus.")

    if args.html:
        out = Path(args.html)
        out.parent.mkdir(parents=True, exist_ok=True)
        out.write_text(render_podcast_report_html(report, title=audio_path.stem), encoding="utf-8")
        print(f"\nHTML report: {out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
