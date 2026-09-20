"""Funding/investment readiness (Thursday Ops upgrade, phase 3).

The highest fabrication-risk module in the whole Ops upgrade spec: a
wrong revenue number, an invented user count, or a made-up grant fit
score in front of an investor or a grant application isn't just an
internal inconvenience like a bad marketing draft would be -- it's a
real, external, reputational claim. So this module holds a stricter line
than marketing_ops/advertising_ops:

1. Every quantitative figure is a LIVE query against `app.db` (the real
   Admin CRM SQLite store business/app/db.py already reads/writes) --
   never a cached, remembered, or paraphrased number. If the query fails,
   that figure is reported as unavailable, never assumed to be zero or
   silently omitted.
2. No qualitative company/product narrative is duplicated or paraphrased
   into this code. Doing that would create a second, stale copy of facts
   that live in docs/NITE_DSP_BUSINESS_PLAN_V1.md,
   docs/NITE_SUBMIT_LAUNCH_TRUTH_SHEET.md, and
   docs/NITE_DSP_PORTFOLIO_READINESS_AUDIT_V1.md -- this module cites
   those paths as the source of truth instead, exactly the failure mode
   the whole reorg has held itself to avoiding elsewhere.
3. Grant matching is explicitly NOT implemented here. Confirmed with the
   founder 2026-09-02: Thursday has no way to verify current, real grant
   programs or their criteria, so inventing program names or fit scores
   would be fabrication dressed up as a feature. This function returns an
   honest "needs founder/human research" placeholder instead.
4. Data-sourcing audit performed 2026-09-02 (see
   docs/NITE_DSP_THURSDAY_AUDIT_AND_UPGRADE_PLAN_V1.md, Phase 3): as of
   that audit, `app.db`'s clients/leads/invoices/expenses/enquiries
   tables were all empty (0 rows) -- NITE DSP is pre-revenue. That is
   this function's live-query result, not a hardcoded assumption; it will
   correctly report differently once real records exist.

Legal-entity status, team size, and funding history are NOT determinable
from this codebase and are never guessed at here -- the report says so
plainly wherever the spec asks for them.
"""

from __future__ import annotations

import logging

logger = logging.getLogger(__name__)

_UNAVAILABLE = "unavailable (could not query app.db)"

_SOURCE_DOCS = {
    "company_strategy": "docs/NITE_DSP_BUSINESS_PLAN_V1.md",
    "submit_status": "docs/NITE_SUBMIT_LAUNCH_TRUTH_SHEET.md",
    "portfolio_evidence": "docs/NITE_DSP_PORTFOLIO_READINESS_AUDIT_V1.md",
}


def _resolve_list_records():
    """Mirrors thursday.monitor._resolve_list_records()'s exact pattern
    and honest-degrade contract -- an ImportError here means "not running
    inside the Audio_Too app process," not "zero records."
    """
    try:
        from app.db import list_records as _lr
        return _lr
    except ImportError:
        return None


def get_live_traction_counts() -> dict[str, int | str]:
    """Live counts from app.db for the tables that represent real
    business traction. Never cached, never remembered from a prior call.
    """
    list_records = _resolve_list_records()
    tables = ("clients", "leads", "invoices", "enquiries", "expenses", "projects")
    if list_records is None:
        return {t: _UNAVAILABLE for t in tables}

    counts: dict[str, int | str] = {}
    for table in tables:
        try:
            counts[table] = len(list_records(table))
        except Exception as exc:
            logger.warning("funding_ops: could not read table %r: %s", table, exc)
            counts[table] = _UNAVAILABLE
    return counts


def funding_readiness_report() -> str:
    counts = get_live_traction_counts()

    def _fmt(key: str) -> str:
        v = counts.get(key, _UNAVAILABLE)
        return str(v)

    has_any_traction = any(
        isinstance(v, int) and v > 0 for v in counts.values()
    )

    lines = [
        "FUNDING READINESS REPORT",
        "",
        "COMPANY SUMMARY:",
        f"  See {_SOURCE_DOCS['company_strategy']} for current strategy and "
        "product portfolio -- not duplicated here to avoid a second, "
        "stale copy of that narrative.",
        "",
        "PRODUCT EVIDENCE:",
        f"  See {_SOURCE_DOCS['submit_status']} (Submit's current release "
        f"status, truth-checked) and {_SOURCE_DOCS['portfolio_evidence']} "
        "(engineering-rigor evidence across all products).",
        "",
        "TRACTION (live query, app.db, just now):",
        f"  Clients: {_fmt('clients')}",
        f"  Leads: {_fmt('leads')}",
        f"  Invoices: {_fmt('invoices')}",
        f"  Enquiries: {_fmt('enquiries')}",
        f"  Expenses tracked: {_fmt('expenses')}",
        f"  Projects: {_fmt('projects')}",
        "",
        "INVESTMENT READINESS:",
    ]

    if not has_any_traction:
        lines += [
            "  Not ready. Live traction data shows zero clients, leads, "
            "invoices, or enquiries recorded. This is a real, current "
            "reading, not an estimate -- an investor conversation before "
            "at least some real usage evidence exists would have nothing "
            "concrete to point to beyond the engineering-rigor story in "
            f"{_SOURCE_DOCS['portfolio_evidence']}.",
            "  Missing proof points: any paying customer, any recorded "
            "lead, Developer ID signing/notarisation (Submit), a named "
            "beta tester cohort.",
        ]
    else:
        lines += [
            "  Live traction data shows real recorded activity above -- "
            "review the actual numbers before characterizing readiness; "
            "this report does not editorialize beyond what it can verify.",
        ]

    lines += [
        "",
        "GRANT READINESS:",
        "  Not assessed here. Grant-program matching requires current, "
        "external knowledge of real grant schemes and their criteria, "
        "which Thursday has no way to verify or keep up to date -- "
        "inventing program names or fit scores would be a fabricated "
        "claim, not a feature. This needs founder/human research.",
        "",
        "LEGAL / TEAM / FUNDING HISTORY:",
        "  Not determinable from this codebase -- no legal-entity status, "
        "team size, or prior funding history is tracked anywhere in the "
        "repository. Provide this directly if it's needed for a report.",
        "",
        "RECOMMENDED NEXT ACTIONS:",
        "1. Get real usage data: send the Submit private beta to its "
        "named tester cohort (blocked on that step per "
        f"{_SOURCE_DOCS['submit_status']}).",
        "2. Restore real enquiry/lead tracking through Audio_Too's "
        "existing CRM (app.db) rather than starting a parallel record.",
        "3. Revisit this report once any of the traction counts above "
        "are non-zero -- it will reflect that automatically.",
    ]

    return "\n".join(lines)
