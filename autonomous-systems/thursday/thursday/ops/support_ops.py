"""Support (Thursday Ops upgrade, phase 10).

Two real, live sources, neither paraphrased into code:
- `business/app/business_knowledge.json`'s `faqs` list — the real,
  current FAQ content already shown to real enquirers, read fresh every
  call (shares finance_ops.py's `_business_knowledge_path()` resolution).
- `qa_ops.beta_readiness_check()`'s live-parsed checklist state — Gate 0's
  unchecked items reframed as "known issues" for support triage, not a
  separately maintained list. Reuses the existing parse rather than
  re-reading the checklist file a second, differently-scoped way.

Checked first (per the standing discipline): no existing command surfaces
either of these, so both are genuinely new here, not duplicates.

"Tester support drafts" and "support triage workflow" from the original
spec are NOT implemented -- there are zero live testers or support
tickets yet (confirmed by tonight's funding-readiness audit: zero
clients, zero enquiries in app.db), so there is nothing real to draft a
response to or triage. Building either now would mean inventing a
plausible-looking support interaction that never happened.
"""

from __future__ import annotations

from thursday.ops.finance_ops import _business_knowledge_path
from thursday.redaction import get_logger as _get_redacting_logger
import json

logger = _get_redacting_logger(__name__)


def get_faqs() -> list[dict]:
    path = _business_knowledge_path()
    if path is None:
        return []
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
        return list(data.get("faqs", []))
    except (json.JSONDecodeError, OSError) as exc:
        logger.warning("support_ops: could not read business_knowledge.json: %s", exc)
        return []


_FAQ_PREFIXES = ["faq about", "faq on", "faq for", "faq", "faqs"]


def parse_faq_command(text: str) -> str | None:
    """Returns the query string (possibly empty) if ``text`` is an FAQ
    command, else None. Never raises -- a bare "faq" with no query is a
    legitimate "show me everything" request, same reasoning as
    agent_briefing.parse_brief_agent_command's empty-topic case. Routed
    through structured_commands.py, not plain trigger scoring, because
    the query tail can contain words ("faq about pricing") that collide
    with other services' own triggers -- the same failure mode found
    live with "create task marketing: ...".
    """
    stripped = text.strip()
    lower = stripped.lower()
    for prefix in sorted(_FAQ_PREFIXES, key=len, reverse=True):
        if lower.startswith(prefix.lower()):
            return stripped[len(prefix):].strip()
    return None


def faq_lookup(query: str = "") -> str:
    faqs = get_faqs()
    if not faqs:
        return "FAQ\n\nEvidence missing — could not read the real FAQ content (business_knowledge.json)."

    query_lower = query.strip().lower()
    if query_lower:
        matched = [
            f for f in faqs
            if query_lower in f.get("question", "").lower()
            or any(query_lower in kw.lower() for kw in f.get("keywords", []))
        ]
    else:
        matched = faqs

    if query and not matched:
        return f"FAQ\n\nNo FAQ entry matches '{query}'. {len(faqs)} entries exist — try a broader term."

    lines = ["FAQ", ""]
    for f in matched:
        lines.append(f"  Q: {f.get('question', '(no question recorded)')}")
        lines.append(f"  A: {f.get('answer', '(no answer recorded)')}")
        lines.append("")
    lines.append(f"Source (read live): {_business_knowledge_path()}")
    return "\n".join(lines)


def known_issues() -> str:
    from thursday.ops import qa_ops

    sections = None
    path = qa_ops.checklist_path()
    if not path.exists():
        return "KNOWN ISSUES\n\nEvidence missing — beta checklist not found; nothing to report."

    try:
        text = path.read_text(encoding="utf-8")
    except OSError as exc:
        return f"KNOWN ISSUES\n\nEvidence missing — could not read checklist: {exc}"

    sections = qa_ops.parse_checklist(text)
    gate = next((s for s in sections if qa_ops._BLOCKING_GATE_MARKER in s["heading"].lower()), None)
    open_items = [i["text"] for i in gate["items"] if not i["checked"]] if gate else []

    lines = ["KNOWN ISSUES", ""]
    if not open_items:
        lines.append("  None — the beta launch checklist's Gate 0 is fully cleared.")
    else:
        lines.append(f"  {len(open_items)} open item(s) blocking beta launch (from {path}):")
        for item in open_items:
            lines.append(f"  - {item}")
    lines.append("")
    lines.append(
        "These are the real, currently-unchecked Gate 0 items from the "
        "beta launch checklist, not a separately maintained issue list — "
        "see 'beta readiness' for the full checklist state."
    )
    return "\n".join(lines)
