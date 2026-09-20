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
import logging
from pathlib import Path

logger = logging.getLogger(__name__)

_BUSINESS_KNOWLEDGE_RELATIVE_PATHS = (
    "server/app/business_knowledge.json",
)


def _business_knowledge_path() -> Path | None:
    # Bounded to 6 levels (not tied to this module's own depth) -- same
    # reasoning as qa_ops.nite_dsp_root(): a fixed parents[N] index breaks
    # the moment the module moves (as it did, thursday/finance_ops.py ->
    # thursday/ops/finance_ops.py, 2026-09-02), while an upward search for
    # the actual target finds it correctly regardless of nesting depth.
    here = Path(__file__).resolve()
    for candidate in list(here.parents)[:6]:
        for rel in _BUSINESS_KNOWLEDGE_RELATIVE_PATHS:
            p = candidate / rel
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
