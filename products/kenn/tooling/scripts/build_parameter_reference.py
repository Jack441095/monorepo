#!/usr/bin/env python3
"""Turn measure_device_parameters.py evidence into parameter-reference notes (numbers from Live, no prose invented).

    build_parameter_reference.py --out NOTES_DIR [--evidence-dir DIR] [--approve]

Reads every device JSON in tooling/data/measured_devices/ (or --evidence-dir) and writes ``measured-<device>-<n>.md``,
twelve parameters to a note so retrieval gets small chunks. Every line is a range, a mapping or a list of options that
Live itself displayed. What a parameter *does* comes from the manual notes; these say what it can be set to.

New notes are written as ``Status: Draft`` (the index skips drafts) until you run with --approve, so a person looks at
the first batch before it reaches an answer. A rerun without --approve keeps the status each existing note already has, and
removes parts a device no longer needs. The ``measured-`` name and the ``Measured at:`` line are what let the
index label them as measured Live data (see retrieval/build_index.py).
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path
from typing import Any

KENN_ROOT = Path(__file__).resolve().parents[2]
DEFAULT_EVIDENCE = KENN_ROOT / "tooling" / "data" / "measured_devices"
PER_NOTE = 12
_UNIT_TEXT = {"db": "dB", "hz": "Hz", "ms": "ms", "%": "%", "ratio": "(ratio)", "value": ""}


def _number(value: float, unit: str) -> str:
    if unit == "hz" and abs(value) >= 1000:
        return f"{value / 1000:g} kHz"
    if unit == "ms" and abs(value) >= 1000:
        return f"{value / 1000:g} s"
    text = f"{value:+g}" if unit == "db" and value > 0 else f"{value:g}"
    unit_text = _UNIT_TEXT.get(unit, unit)
    return f"{text} {unit_text}".strip() if unit != "ratio" else f"{text}:1"


def _options(entry: dict[str, Any]) -> list[str]:
    options = entry.get("options")
    if not isinstance(options, list):
        return []
    labels = []
    for item in options:
        label = item[1] if isinstance(item, (list, tuple)) and len(item) > 1 else item
        if str(label).strip() and str(label) not in labels:
            labels.append(str(label).strip())
    return labels


def describe(entry: dict[str, Any]) -> str | None:
    """One line for one parameter, or None when Live gave us nothing usable."""
    name = str(entry.get("name") or "").strip()
    if not name or entry.get("error"):
        return None
    if entry.get("quantized"):
        labels = _options(entry)
        return f"- {name}: choose one of {', '.join(labels)}." if labels else None
    mapping, unit = entry.get("mapping"), str(entry.get("unit") or "")
    if mapping in {"linear", "log", "table", "table_descending"} and "display_min" in entry:
        low, high = float(entry["display_min"]), float(entry["display_max"])
        shape = {"linear": "moves in even steps", "log": "moves in a logarithmic curve (equal knob steps are equal ratios)",
                 "table": "does not follow a straight line; Live uses its own table",
                 "table_descending": "does not follow a straight line and runs from high to low; Live uses its own table"}[mapping]
        return f"- {name}: {_number(low, unit)} to {_number(high, unit)}; the control {shape}."
    examples = [str(text) for text in entry.get("examples") or []]
    return f"- {name}: Live shows values such as {', '.join(examples)}." if examples else None


def build_notes(evidence: dict[str, Any], *, status: str) -> dict[str, str]:
    device = str(evidence.get("device") or "").strip()
    measured_at = str(evidence.get("measured_at") or "").strip()
    if not device or not measured_at:
        raise ValueError("evidence needs a device name and a measured_at date")
    lines = [line for entry in evidence.get("parameters", []) if (line := describe(entry))]
    slug = re.sub(r"[^a-z0-9]+", "-", device.casefold()).strip("-")
    tags = ", ".join(sorted({device.casefold(), "parameters", "ranges", "measured", "ableton live"}))
    groups = [lines[i:i + PER_NOTE] for i in range(0, len(lines), PER_NOTE)] or [[]]
    notes = {}
    for number, group in enumerate(groups, start=1):
        part = f" (part {number} of {len(groups)})" if len(groups) > 1 else ""
        body = "\n".join(group) if group else f"- Live reported no readable parameters for {device}."
        notes[f"measured-{slug}-{number}.md"] = (
            f"# {device} parameter ranges, measured in Live{part}\n"
            f"Status: {status}\n"
            f"Tags: {tags}\n"
            f"Measured at: {measured_at}\n"
            f"Source: read from Ableton Live's own display strings by tooling/scripts/measure_device_parameters.py.\n\n"
            f"Short answer:\n"
            f"These are the ranges and options Live displays for the {device} device's parameters. "
            f"They were read from Live, not written from the manual.\n{body}\n"
        )
    return notes


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--out", type=Path, required=True, help="notes folder to write into")
    parser.add_argument("--evidence-dir", type=Path, default=DEFAULT_EVIDENCE)
    parser.add_argument("--approve", action="store_true", help="write Status: Approved for everything written (default: Draft for new notes, existing status kept)")
    args = parser.parse_args()

    files = sorted(args.evidence_dir.glob("*.json")) if args.evidence_dir.is_dir() else []
    if not files:
        print(f"No evidence files in {args.evidence_dir}. Measure a device first: "
              f"measure_device_parameters.py --index N --out {args.evidence_dir}/<device>.json", file=sys.stderr)
        return 1
    args.out.mkdir(parents=True, exist_ok=True)
    written = 0
    for path in files:
        try:
            notes = build_notes(json.loads(path.read_text(encoding="utf-8")), status="Approved" if args.approve else "Draft")
        except (OSError, ValueError) as error:
            print(f"skipped {path.name}: {error}", file=sys.stderr)
            continue
        for name, text in notes.items():
            target = args.out / name
            if target.exists() and not args.approve:
                # Re-running must not undo a review: an approved note stays approved, a draft stays a draft.
                kept = re.search(r"^Status:\s*(\S+)", target.read_text(encoding="utf-8"), re.M)
                if kept:
                    text = re.sub(r"^Status:.*$", f"Status: {kept.group(1)}", text, count=1, flags=re.M)
            target.write_text(text, encoding="utf-8")
            written += 1
        # A device that now needs fewer parts must not leave its old last part indexed.
        stem = next(iter(notes)).rsplit("-", 1)[0]
        for old in args.out.glob(f"{stem}-*.md"):
            if old.name not in notes and re.fullmatch(rf"{re.escape(stem)}-\d+\.md", old.name):
                old.unlink()
    print(f"wrote {written} note(s) from {len(files)} device file(s) into {args.out} "
          f"({'Approved' if args.approve else 'Draft: review, then rerun with --approve'})")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
