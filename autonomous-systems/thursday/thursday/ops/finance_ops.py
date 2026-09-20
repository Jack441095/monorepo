"""Finance / Admin (Thursday Ops upgrade, phase 9).

Scoped to exactly one real, live data source:
`business/app/business_knowledge.json`'s `offerings` list — the real,
current Audio_Too service price list, read fresh every call so a price
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

_BUSINESS_KNOWLEDGE_RELATIVE_PATHS = (
    # In Audio_Too/thursday/ops/, 2 parents up *is* Audio_Too, so the bare
    # "business/..." path happens to resolve there directly. This
    # extraction copy is a sibling of Audio_Too, not nested under it, so
    # "Audio_Too/business/..." is added to still reach the same real,
    # live file from any NITE_DSP-root-or-above candidate -- deliberately
    # not vendoring a copy of Audio_Too's business data, same reasoning
    # as the DEFAULT_LLM coupling in registry/handlers.py (see
    # docs/EXTRACTION_COUPLING.md).
    # NOTE 2026-09-18: Audio_Too renamed business/ -> server/ (see
    # Audio_Too/server/app/business_knowledge.json). Both layouts are
    # listed so old and new checkouts resolve.
    "business/app/business_knowledge.json",
    "server/app/business_knowledge.json",
    "Audio_Too/business/app/business_knowledge.json",
    "Audio_Too/server/app/business_knowledge.json",
)


def _business_knowledge_path() -> Path | None:
    # Content-aware upward search delegated to
    # thursday.repo_root.search_upward (2026-09-18 audit fix) -- same
    # reasoning as qa_ops.nite_dsp_root(): a fixed parents[N] index breaks
    # the moment the module moves (as it did, thursday/finance_ops.py ->
    # thursday/ops/finance_ops.py, 2026-09-02), while an upward search for
    # the actual target finds it correctly regardless of nesting depth.
    # THURSDAY_BUSINESS_KNOWLEDGE_FILE wins when set (server deploys where
    # the monorepo layout doesn't exist -- see deploy notes).
    import os

    configured = os.environ.get("THURSDAY_BUSINESS_KNOWLEDGE_FILE", "").strip()
    if configured:
        candidate = Path(configured).expanduser()
        return candidate if candidate.is_file() else None
    from thursday.repo_root import search_upward

    here = Path(__file__).resolve()
    found = search_upward(here, _BUSINESS_KNOWLEDGE_RELATIVE_PATHS, depth=7)
    if found is None:
        return None
    for rel in _BUSINESS_KNOWLEDGE_RELATIVE_PATHS:
        p = found / rel
        if p.exists():
            return p
    return None


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
            "list (business/app/business_knowledge.json)."
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
