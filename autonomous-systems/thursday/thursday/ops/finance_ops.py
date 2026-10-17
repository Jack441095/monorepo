"""Finance / Admin (Thursday Ops upgrade, phase 9).

Scoped to exactly one real, live data source:
`data/business_knowledge.json`'s `offerings` list — the real,
current studio-services price list, read fresh every call so a price
change there is reflected immediately, never stale.

**Deliberately does not add invoice listing.** Checked first (per the
standing discipline all night: verify existing capability before
building) and found `"invoices"` is already a registered service
(`thursday/registry/business.py`), backed by `client.invoices_list()`,
which shells out to the real, more mature Admin business agent
(`_cli_cmd("admin", "invoices")`). A second "invoice status" reader over
the same `app.db` table would have been a straight duplicate of existing,
already-shipped functionality — the exact anti-pattern this whole Ops
upgrade has been careful to avoid (see the task_ledger vs. taskgraph.py
discussion in Phase 1). Pricing was the one genuinely missing piece: no
existing command surfaces the live service price list.

"Subscription tracking" from the original spec is also NOT implemented:
no data source for recurring costs/subscriptions exists anywhere in this
codebase (unlike pricing, which is real, live-readable data). Says so
plainly rather than guessing at subscription costs.
"""

from __future__ import annotations

import json
from pathlib import Path

from thursday.redaction import get_logger as _get_redacting_logger

logger = _get_redacting_logger(__name__)

# Thursday's own copy, moved out of Audio_Too/server/app/ on 18 Oct 2026
# when Audio_Too was retired (earlier history under archive/audio-too-final).
# A fixed path is right here, unlike the upward searches elsewhere, because
# the file now lives inside this project: ops/ -> thursday/ -> project root.
_BUSINESS_KNOWLEDGE_FILE = Path(__file__).resolve().parents[2] / "data" / "business_knowledge.json"


def _business_knowledge_path() -> Path | None:
    # THURSDAY_BUSINESS_KNOWLEDGE_FILE wins when set (server deploys that
    # ship the corpus somewhere else -- see deploy notes). A missing file
    # returns None so callers print "Evidence missing" rather than prices
    # they cannot back up.
    import os

    configured = os.environ.get("THURSDAY_BUSINESS_KNOWLEDGE_FILE", "").strip()
    candidate = Path(configured).expanduser() if configured else _BUSINESS_KNOWLEDGE_FILE
    return candidate if candidate.is_file() else None


def get_offerings() -> list[dict]:
    """Live-read the real service price list. Returns [] (not a
    fabricated default list) if the file can't be found or parsed.
    """
    path = _business_knowledge_path()
    if path is None:
        return []
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
        return list(data.get("offerings", []))
    except (json.JSONDecodeError, OSError) as exc:
        logger.warning("finance_ops: could not read business_knowledge.json: %s", exc)
        return []


def pricing_summary() -> str:
    offerings = get_offerings()
    if not offerings:
        return (
            "PRICING SUMMARY\n\n"
            "Evidence missing — could not read the real service price "
            "list (data/business_knowledge.json)."
        )

    lines = ["PRICING SUMMARY", ""]
    for o in offerings:
        name = o.get("name", o.get("id", "unknown"))
        price = o.get("price_from_gbp")
        price_str = f"from £{price}" if price is not None else "price not recorded"
        turnaround = o.get("turnaround", "turnaround not recorded")
        lines.append(f"  {name}: {price_str} — {turnaround}")
    lines.append("")
    lines.append(
        "SUBSCRIPTION/RECURRING COSTS: not tracked — no data source exists "
        "for this in the codebase. Provide directly if needed."
    )
    lines.append(f"Source (read live): {_business_knowledge_path()}")
    return "\n".join(lines)


_CHASE_KEYWORDS = ("payment", "await", "quote", "invoice", "deposit", "paid", "chase")


def chase_list() -> list[dict]:
    """Open finance_admin ledger tasks that look like money waiting.

    Derived read-only view over task_ledger (no new state): matches open
    finance_admin tasks whose objective/next_action mentions payment flow
    words. Thursday drafts the chase (draft_ops.reminder_draft); the
    founder sends it. Empty list is a legitimate "nothing to chase".
    """
    from thursday.ops import task_ledger

    items = []
    for t in task_ledger.list_tasks(workstream="finance_admin"):
        if t.status not in task_ledger.OPEN_STATUSES:
            continue
        haystack = f"{t.objective}\n{t.next_action}".lower()
        if any(k in haystack for k in _CHASE_KEYWORDS):
            items.append({"task_id": t.task_id, "objective": t.objective,
                          "status": t.status, "next_action": t.next_action,
                          "created_at": t.created_at})
    items.sort(key=lambda i: i["created_at"])
    return items


def render_chase_list(items: list[dict] | None = None) -> str:
    items = chase_list() if items is None else items
    if not items:
        return "MONEY CHASE\n\nNothing to chase — no open payment-flow tasks in the ledger."
    lines = ["MONEY CHASE", ""]
    for i in items:
        lines.append(f"  - {i['objective']} ({i['task_id']}) — {i['status']}")
        lines.append(f"    Next: {i['next_action'] or 'draft a polite reminder (draft_ops.reminder_draft)'}")
    lines.append("")
    lines.append("Draft the chase with draft_ops.reminder_draft; founder sends manually.")
    return "\n".join(lines)
