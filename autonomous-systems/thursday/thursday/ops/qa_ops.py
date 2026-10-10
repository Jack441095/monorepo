"""Read the current Submit private-preview handoff checklist on demand.

The checklist records local artifact handoff evidence only. Its owner-send
gate and the separate operations audit control tester distribution and paid
launch; checked handoff boxes do not approve either. This module reports the
written checkbox state and never edits the owner's checklist.
"""

from __future__ import annotations

import os
import re
from pathlib import Path

CHECKLIST_RELATIVE_PATH = "products/nite-submit/docs/NITE_SUBMIT_PRIVATE_TECHNICAL_PREVIEW_CHECKLIST_V1.md"

_CHECKBOX_RE = re.compile(r"^- \[([ xX])\]\s*(.+)$")
_HEADING_RE = re.compile(r"^##\s+(.+)$")

# Read the section title so reworded checklist items remain correctly scoped.
_BLOCKING_GATE_MARKER = "handoff gate"


def nite_dsp_root() -> Path:
    """NITE_DSP_ROOT env var wins if set. Otherwise search upward from
    this file for a directory that actually contains the checklist --
    this module lives at a different depth inside Audio_Too/thursday/ops/
    (3 parents up) versus the autonomous-systems/thursday extraction
    (4 parents up), so a fixed parents[N] index is wrong in one of the
    two copies. Bounded to 6 levels so a misconfigured environment fails
    with a clear "not found" rather than walking to filesystem root.

    Search loop delegated to thursday.repo_root.search_upward (2026-09-18
    audit fix); only the target + per-copy fallback live here.
    """
    from thursday.repo_root import search_upward

    here = Path(__file__).resolve()
    found = search_upward(here, (CHECKLIST_RELATIVE_PATH,), depth=6)
    if found is not None:
        return found

    # Nothing found -- fall back to the depth that's correct for this
    # copy's own location (autonomous-systems/thursday/thursday/ops/qa_ops.py
    # -> parents[4]; one deeper than Audio_Too/thursday/ops/qa_ops.py's
    # parents[3], per the docstring above). beta_readiness_check() will
    # still report "Evidence missing" rather than silently using a wrong
    # path, since this fallback almost certainly won't contain the
    # checklist either if the search above found nothing.
    return here.parents[4]


def checklist_path() -> Path:
    return nite_dsp_root() / CHECKLIST_RELATIVE_PATH


def parse_checklist(text: str) -> list[dict]:
    """Parse markdown into [{"heading": str, "items": [{"text": str, "checked": bool}]}].

    Lines before the first "## " heading are grouped under heading
    "(preamble)". A line's checkbox state is exactly what's written --
    no normalization beyond case-insensitive "x".
    """
    sections: list[dict] = []
    current: dict | None = None
    for line in text.splitlines():
        heading_match = _HEADING_RE.match(line)
        if heading_match:
            current = {"heading": heading_match.group(1).strip(), "items": []}
            sections.append(current)
            continue
        box_match = _CHECKBOX_RE.match(line)
        if box_match:
            if current is None:
                current = {"heading": "(preamble)", "items": []}
                sections.append(current)
            current["items"].append({
                "text": box_match.group(2).strip(),
                "checked": box_match.group(1).lower() == "x",
            })
    return sections


def beta_readiness_check() -> str:
    path = checklist_path()
    if not path.exists():
        return (
            f"Evidence missing — checklist not found at {path}. "
            "Can't assess the private-preview handoff without it."
        )

    try:
        text = path.read_text(encoding="utf-8")
    except OSError as exc:
        return f"Evidence missing — could not read {path}: {exc}"

    sections = parse_checklist(text)
    total_items = sum(len(s["items"]) for s in sections)
    checked_items = sum(1 for s in sections for i in s["items"] if i["checked"])

    if total_items == 0:
        return (
            f"Evidence missing — {path} exists but has no checkbox items "
            "to parse. Check the file hasn't changed format."
        )

    gate_section = next(
        (s for s in sections if _BLOCKING_GATE_MARKER in s["heading"].lower()), None,
    )
    gate_unchecked = (
        [i["text"] for i in gate_section["items"] if not i["checked"]]
        if gate_section else []
    )

    lines = [
        "SUBMIT PRIVATE PREVIEW HANDOFF CHECK",
        f"Source (read live): {path}",
        "",
        f"Overall: {checked_items}/{total_items} items checked "
        f"({checked_items / total_items:.0%}).",
        "",
    ]

    if gate_section and gate_unchecked:
        lines.append(
            f"BLOCKED on \"{gate_section['heading']}\" — unchecked private-preview "
            "handoff items remain:"
        )
        for item in gate_unchecked:
            lines.append(f"  - [ ] {item}")
        lines.append("")
    elif gate_section:
        lines.append(
            f"\"{gate_section['heading']}\" is fully checked off. "
            "The owner-send gate and commercial release remain separate."
        )
        lines.append("")

    lines.append("BY SECTION:")
    for section in sections:
        if not section["items"]:
            continue
        done = sum(1 for i in section["items"] if i["checked"])
        total = len(section["items"])
        lines.append(f"  {section['heading']}: {done}/{total}")
    lines.append("")

    lines.append(
        "This reflects exactly what's checked in the file above, read "
        "just now — not an independent verification of real-world state. "
        "The checklist's own instruction applies: verify against current "
        "staging state before trusting a checked box, don't just trust "
        "the file."
    )

    return "\n".join(lines)
