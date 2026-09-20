"""QA / Beta Readiness (Thursday Ops upgrade, phase 5).

Reads `docs/NITE_DSP_SUBMIT_BETA_LAUNCH_CHECKLIST_V1.md` LIVE from disk on
every call and parses its real `- [ ]` / `- [x]` checkboxes, grouped by
section -- it never paraphrases or snapshots that content into code, so
this module cannot drift stale against the checklist the way a hardcoded
summary would. The checklist's own header says exactly this discipline
applies to humans reading it too: "if a gate turns out to already be
satisfied, verify against current staging state before checking it off
rather than trusting a prior doc's claim." This module holds the same
line — it reports whatever is *currently* checked, nothing more, and
never infers or guesses at an item's real-world status beyond what the
checkbox says.

That checklist lives at the NITE_DSP monorepo root, not inside Audio_Too
(where this Thursday process actually runs) -- resolved via NITE_DSP_ROOT
env var with a computed fallback, the same convention established
tonight in autonomous-systems/thursday's shadow_adapters.py/lease_policy.py
for the same kind of cross-repo path.

Scoped to this one checklist deliberately, not every checkbox-shaped doc
in the repo (several exist, for SLO/website/other tracks) -- the Submit
beta checklist is the one that matches "QA / beta readiness" and is
explicitly the founder's own current single bottleneck (see
funding_ops.py's recommended next actions). Aggregating unrelated
checklists of different products/freshness would conflate things that
shouldn't be conflated.

Only ever reads this file. Never writes to it, never checks a box on the
founder's behalf -- that's a real-world decision this module has no
authority to make.
"""

from __future__ import annotations

import os
import re
from pathlib import Path

CHECKLIST_RELATIVE_PATH = "docs/NITE_DSP_SUBMIT_BETA_LAUNCH_CHECKLIST_V1.md"

_CHECKBOX_RE = re.compile(r"^- \[([ xX])\]\s*(.+)$")
_HEADING_RE = re.compile(r"^##\s+(.+)$")

# Section heading substring that identifies the checklist's own declared
# "nothing below moves without these" gate -- read from the doc's own
# section title, not a separately-maintained list of item texts, so a
# reworded item still gets classified correctly as long as the section
# heading itself still says "Gate 0".
_BLOCKING_GATE_MARKER = "gate 0"


def nite_dsp_root() -> Path:
    """NITE_DSP_ROOT env var wins if set. Otherwise search upward from
    this file for a directory that actually contains the checklist --
    this module lives at a different depth inside Audio_Too/thursday/ops/
    (3 parents up) versus the autonomous-systems/thursday extraction
    (4 parents up), so a fixed parents[N] index is wrong in one of the
    two copies. Bounded to 6 levels so a misconfigured environment fails
    with a clear "not found" rather than walking to filesystem root.
    """
    configured = os.environ.get("NITE_DSP_ROOT", "").strip()
    if configured:
        return Path(configured).expanduser()

    here = Path(__file__).resolve()
    for candidate in list(here.parents)[:6]:
        if (candidate / CHECKLIST_RELATIVE_PATH).exists():
            return candidate

    # Nothing found -- fall back to the depth that's correct for this
    # module's own location today (thursday/ops/qa_ops.py -> parents[3]).
    # beta_readiness_check() will still report "Evidence missing" rather
    # than silently using a wrong path, since this fallback almost
    # certainly won't contain the checklist either if the search above
    # found nothing.
    return here.parents[3]


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
            "Can't assess beta readiness without it."
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
        "BETA READINESS CHECK",
        f"Source (read live): {path}",
        "",
        f"Overall: {checked_items}/{total_items} items checked "
        f"({checked_items / total_items:.0%}).",
        "",
    ]

    if gate_section and gate_unchecked:
        lines.append(
            f"BLOCKED on \"{gate_section['heading']}\" — the checklist's own "
            "declared prerequisite gate. Nothing else on this checklist "
            "is meaningful progress until these clear:"
        )
        for item in gate_unchecked:
            lines.append(f"  - [ ] {item}")
        lines.append("")
    elif gate_section:
        lines.append(f"\"{gate_section['heading']}\" is fully checked off — not blocking.")
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
