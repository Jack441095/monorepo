"""Documentation / launch tracker (Thursday Ops upgrade, phase 11).

Live-parses `docs/NITE_SUBMIT_LAUNCH_TRACKER.md`'s real markdown tables
off disk on every call -- same discipline as qa_ops.py, never cached or
paraphrased. Genuinely distinct from qa_ops.beta_readiness_check(): that
module tracks the tactical, checkbox-shaped beta-launch checklist (Gate 0
onward, day-by-day send steps); this tracks the strategic, table-shaped
launch-gate tracker (a different real document, a different status
vocabulary: DONE / IN PROGRESS / OWNER ACTION / BLOCKED / NOT STARTED /
DEFERRED, not checkboxes). Neither replaces the other.

Most of the spec's Documentation Agent bullets are deliberately NOT
implemented here because something else already covers them, and
building a second version would duplicate real, working functionality:
- "risk registers" -- thursday.ops.weekly_report.py already aggregates real
  risks from task_ledger/funding_ops.
- "handoffs" -- thursday.ops.agent_briefing.py already composes a real
  evidence-cited handoff document.
- "internal reports" -- thursday.ops.weekly_report.py's weekly company report
  and this module's launch-tracker status together cover this.
- "product docs" -- no live-generatable scope here; writing product
  documentation is an authoring task, not a data-aggregation one, and
  isn't something Thursday can safely originate without fabricating
  content the same way marketing_ops.py's docstring already argues
  against for marketing copy.

"launch trackers" was the one genuinely unclaimed piece.
"""

from __future__ import annotations

import logging
import re
from pathlib import Path

logger = logging.getLogger(__name__)

LAUNCH_TRACKER_RELATIVE_PATH = "docs/NITE_SUBMIT_LAUNCH_TRACKER.md"

_TABLE_ROW_RE = re.compile(r"^\|(.+)\|\s*$")
_SEPARATOR_ROW_RE = re.compile(r"^\|[\s:|-]+\|\s*$")


def _nite_dsp_root() -> Path:
    """Same upward-search pattern as qa_ops.nite_dsp_root() and
    shadow_adapters._nite_dsp_root() -- see either for why a fixed
    parent-index assumption is the wrong shape here.
    """
    import os

    configured = os.environ.get("NITE_DSP_ROOT", "").strip()
    if configured:
        return Path(configured).expanduser()

    here = Path(__file__).resolve()
    for candidate in list(here.parents)[:6]:
        if (candidate / LAUNCH_TRACKER_RELATIVE_PATH).exists():
            return candidate
    # Fallback depth for this module's location today: thursday/ops/
    # documentation_ops.py -> parents[3] is NITE_DSP root.
    return here.parents[3]


def launch_tracker_path() -> Path:
    return _nite_dsp_root() / LAUNCH_TRACKER_RELATIVE_PATH


def _split_row(line: str) -> list[str]:
    inner = line.strip()[1:-1] if line.strip().startswith("|") else line.strip()
    return [cell.strip() for cell in inner.split("|")]


def parse_gate_statuses(text: str) -> list[dict]:
    """Parse every markdown table row that has a "Status" column into
    [{"label": <first column>, "status": <value>}]. Tables with no
    "Status" column are skipped entirely -- this only extracts what it
    can verify the meaning of, never guesses which column holds status
    from position alone.
    """
    lines = text.splitlines()
    rows: list[dict] = []
    i = 0
    while i < len(lines):
        line = lines[i]
        header_match = _TABLE_ROW_RE.match(line)
        if header_match and i + 1 < len(lines) and _SEPARATOR_ROW_RE.match(lines[i + 1]):
            headers = _split_row(line)
            try:
                status_idx = next(j for j, h in enumerate(headers) if h.strip().lower() == "status")
            except StopIteration:
                i += 2
                continue

            i += 2
            while i < len(lines) and _TABLE_ROW_RE.match(lines[i]):
                cells = _split_row(lines[i])
                if len(cells) > status_idx and cells[0] and cells[0] not in ("---",):
                    rows.append({"label": cells[0], "status": cells[status_idx]})
                i += 1
            continue
        i += 1
    return rows


_BLOCKING_STATUSES = {"blocked", "not started", "owner action"}


def launch_tracker_status() -> str:
    path = launch_tracker_path()
    if not path.exists():
        return f"LAUNCH TRACKER STATUS\n\nEvidence missing — tracker not found at {path}."

    try:
        text = path.read_text(encoding="utf-8")
    except OSError as exc:
        return f"LAUNCH TRACKER STATUS\n\nEvidence missing — could not read {path}: {exc}"

    rows = parse_gate_statuses(text)
    if not rows:
        return f"LAUNCH TRACKER STATUS\n\nEvidence missing — {path} has no parseable Status-column tables."

    tally: dict[str, int] = {}
    for r in rows:
        key = r["status"].strip().lower()
        # Handle compound statuses like "DONE for reviewed fields; policy
        # IN PROGRESS" honestly: tally under the first plain status word
        # this recognizes, else "other" -- never silently drop a row.
        matched = next(
            (s for s in ("done", "in progress", "owner action", "blocked", "not started", "deferred") if s in key),
            "other",
        )
        tally[matched] = tally.get(matched, 0) + 1

    blocking = [r for r in rows if r["status"].strip().lower() in _BLOCKING_STATUSES]

    lines = ["LAUNCH TRACKER STATUS", f"Source (read live): {path}", ""]
    lines.append(f"{len(rows)} gates tracked.")
    for status, count in sorted(tally.items(), key=lambda kv: -kv[1]):
        lines.append(f"  {status}: {count}")
    lines.append("")

    if blocking:
        lines.append(f"BLOCKING ({len(blocking)}):")
        for r in blocking:
            lines.append(f"  - {r['label']}: {r['status']}")
    else:
        lines.append("No gates currently in a blocking status (BLOCKED / NOT STARTED / OWNER ACTION).")

    lines.append("")
    lines.append(
        "This reflects exactly what's in the tracker table, read just "
        "now -- a compound status (e.g. \"DONE for X; Y IN PROGRESS\") is "
        "tallied under its first recognized keyword, not resolved to a "
        "single verdict. Read the full row text for nuance."
    )
    return "\n".join(lines)
