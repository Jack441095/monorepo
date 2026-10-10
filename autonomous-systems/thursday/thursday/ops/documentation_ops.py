"""Report the current paid-launch blockers from the operations audit.

The audit is the source of truth for launch blockers. This helper reads only
its named paid-sales section and reports the checkbox state as written; it
does not independently verify completed work or approve a release.
"""

from __future__ import annotations

import re
from pathlib import Path

OPERATIONS_AUDIT_RELATIVE_PATH = "docs/OPERATIONS_AUDIT_2026-10-08.md"

_CHECKBOX_RE = re.compile(r"^- \[([ xX])\]\s*(.+)$")
_HEADING_RE = re.compile(r"^##\s+(.+)$")
_LABEL_RE = re.compile(r"^\*\*(.+?)\*\*")
_LAUNCH_BLOCKERS_HEADING = "launch blockers — complete before paid sales"


def parse_launch_blockers(text: str) -> list[dict]:
    """Read checkbox labels only from the paid-sales section of the audit."""
    items: list[dict] = []
    in_launch_section = False
    for line in text.splitlines():
        heading = _HEADING_RE.match(line)
        if heading:
            if in_launch_section:
                break
            in_launch_section = (
                heading.group(1).strip().casefold() == _LAUNCH_BLOCKERS_HEADING
            )
            continue
        if not in_launch_section:
            continue
        checkbox = _CHECKBOX_RE.match(line)
        if not checkbox:
            continue
        raw_label = checkbox.group(2).strip()
        bold_label = _LABEL_RE.match(raw_label)
        items.append({
            "label": bold_label.group(1) if bold_label else raw_label,
            "checked": checkbox.group(1).lower() == "x",
        })
    return items


def _nite_dsp_root() -> Path:
    """Same upward-search pattern as qa_ops.nite_dsp_root() and
    shadow_adapters._nite_dsp_root() -- search loop delegated to
    thursday.repo_root.search_upward (2026-09-18 audit fix); only the
    target + per-copy fallback live here.
    """
    from thursday.repo_root import search_upward

    here = Path(__file__).resolve()
    found = search_upward(here, (OPERATIONS_AUDIT_RELATIVE_PATH,), depth=6)
    if found is not None:
        return found
    # Fallback depth for this copy's location: autonomous-systems/thursday/
    # thursday/ops/documentation_ops.py -> parents[4] is NITE_DSP root
    # (one deeper than Audio_Too/thursday/ops/'s parents[3]).
    return here.parents[4]


def operations_audit_path() -> Path:
    return _nite_dsp_root() / OPERATIONS_AUDIT_RELATIVE_PATH




def launch_tracker_status() -> str:
    path = operations_audit_path()
    if not path.exists():
        return f"PAID LAUNCH BLOCKERS\n\nEvidence missing — operations audit not found at {path}."

    try:
        text = path.read_text(encoding="utf-8")
    except OSError as exc:
        return f"PAID LAUNCH BLOCKERS\n\nEvidence missing — could not read {path}: {exc}"

    items = parse_launch_blockers(text)
    if not items:
        return (
            f"PAID LAUNCH BLOCKERS\n\nEvidence missing — {path} has no checkbox items "
            "in its paid-sales section."
        )

    completed = sum(item["checked"] for item in items)
    open_items = [item["label"] for item in items if not item["checked"]]
    lines = [
        "PAID LAUNCH BLOCKERS",
        f"Source (read live): {path}",
        "",
        f"{len(items)} blockers tracked: {completed} checked, {len(open_items)} open.",
        "",
    ]
    if open_items:
        lines.append(f"OPEN ({len(open_items)}):")
        lines.extend(f"  - {label}" for label in open_items)
    else:
        lines.append("No unchecked items remain in the paid-sales section.")
    lines.extend(
        [
            "",
            "This reports the audit's checkbox state; it is not an independent "
            "verification of checked work or a release approval.",
        ]
    )
    return "\n".join(lines)
