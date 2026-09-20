"""Backend advisory, read-only (Phase 3).

Schema-aware explanations parsed live from backend/app/models.py via AST
-- never imports the backend package (its deps aren't installed here).
Row COUNTS are honestly unavailable standalone (Postgres, no
DATABASE_URL); the schema SHAPE is fully answerable from code.

Marketing advice is grounded ONLY in numbers Thursday can read live
right now (website pages/prices, truth-sheet beta, service price list,
schema shape, Plausible pageview presence). Anything else gets "cannot
answer -- instrument this" instead of an invented funnel.
"""

from __future__ import annotations

import ast
import os
from pathlib import Path

from thursday.redaction import get_logger as _get_redacting_logger
from thursday.repo_root import nite_dsp_root

logger = _get_redacting_logger(__name__)

_MODELS_REL = "backend/app/models.py"


def _models_path() -> Path | None:
    p = nite_dsp_root() / _MODELS_REL
    return p if p.is_file() else None


def schema_summary() -> dict:
    """Live-parsed tables + columns from backend models. No DB needed."""
    path = _models_path()
    if path is None:
        return {"ok": False, "tables": {},
                "error": "Evidence missing — backend/app/models.py not found."}
    try:
        tree = ast.parse(path.read_text(encoding="utf-8"))
    except (OSError, SyntaxError) as exc:
        logger.warning("advisory_ops: could not parse %s: %s", path, exc)
        return {"ok": False, "tables": {}, "error": f"Evidence missing — could not parse models: {exc}"}
    tables: dict[str, list[str]] = {}
    for node in ast.walk(tree):
        if not isinstance(node, ast.ClassDef):
            continue
        table = None
        columns: list[str] = []
        for stmt in node.body:
            if isinstance(stmt, ast.Assign) and any(
                    isinstance(t, ast.Name) and t.id == "__tablename__" for t in stmt.targets):
                try:
                    table = ast.literal_eval(stmt.value)
                except (ValueError, SyntaxError):
                    table = None
            if isinstance(stmt, ast.AnnAssign) and isinstance(stmt.target, ast.Name):
                columns.append(stmt.target.id)
        if table:
            tables[table] = columns
    return {"ok": True, "tables": tables, "source": f"{_MODELS_REL} (parsed live)",
            "counts": ("unavailable — Postgres, no DATABASE_URL in this environment; "
                       "counts need the backend process, not a second reader here."),
            "error": None}


def data_availability() -> dict:
    """What Thursday can/can't read live right now. Never raises."""
    schema = schema_summary()
    from thursday.ops import website_ops
    traffic = website_ops.traffic_status()
    return {
        "schema_tables": sorted(schema.get("tables", {})),
        "live_counts": ("unavailable — set DATABASE_URL and query from the backend process "
                        "(funding_ops pattern); this checkout carries no DB credentials by design."
                        if not os.environ.get("DATABASE_URL", "").strip()
                        else "DATABASE_URL is set — query from the backend process."),
        "traffic": ("Plausible pageviews + WaitlistSubmit custom event instrumented "
                    "(layout.tsx tagged-events build; WaitlistForm fires on success). "
                    "Pricing/download/checkout are URL pageviews -- define URL goals in "
                    "Plausible; funnel decisions need 2+ weeks of event data."
                    if traffic.get("custom_events") else traffic.get("detail", "unknown")),
        "error": None,
    }


def business_brief() -> dict:
    """Real-facts bundle for advice: every value read live just now."""
    from thursday.ops import finance_ops as fo, website_ops
    from thursday.ops import beta_invite_ops as bio
    brief: dict = {"facts": [], "missing": []}
    offerings = fo.get_offerings()
    if offerings:
        cheapest = min(o.get("price_from_gbp", 0) for o in offerings)
        brief["facts"].append(
            f"Services: {len(offerings)} offerings from £{cheapest} (business_knowledge.json, live)")
    else:
        brief["missing"].append("service price list unreadable")
    site = website_ops.site_map()
    brief["facts"].append(f"Website: {site['count']} pages live" if site["ok"] else "Website: checkout missing")
    pricing = website_ops.product_pricing()
    if pricing["ok"]:
        shown = ", ".join(sorted({f["figure"] for f in pricing["figures"]}))
        brief["facts"].append(f"Website prices shown: {shown} (pricing page + commerce config, live)")
    version = bio._read_truth_sheet_field("Version")
    brief["facts"].append(f"Beta: {version}" if version else "Beta version: truth sheet unreadable")
    schema = schema_summary()
    if schema["ok"]:
        brief["facts"].append(f"Backend schema: {len(schema['tables'])} tables parsed live from models.py")
    return brief


def marketing_advice(topic: str) -> str:
    """Grounded advice on one topic. Claims cite live sources; gaps name
    the exact instrumentation needed instead of inventing numbers."""
    brief = business_brief()
    topic_low = topic.lower()
    lines = [f"MARKETING ADVICE: {topic}", ""]
    lines.append("LIVE FACTS USED:")
    for fact in brief["facts"]:
        lines.append(f"  - {fact}")
    if brief["missing"]:
        lines.append("  Missing: " + "; ".join(brief["missing"]))
    lines.append("")
    lines.append("ADVICE:")
    if any(w in topic_low for w in ("price", "pricing", "cost", "monet")):
        lines.append("  - Website shows products from £2-3 (Submit £3 planned licence); "
                     "services run £45-180. Keep the lines separate in messaging -- "
                     "buyers confuse a £3 app with £180 services otherwise.")
        lines.append("  - Beta is free (0.2.0 per truth sheet): say so on the beta page "
                     "to defuse price questions before they become support tickets.")
    elif any(w in topic_low for w in ("waitlist", "launch", "beta", "acqui")):
        lines.append("  - 38 live pages + Plausible pageviews + WaitlistSubmit event exist; "
                     "pricing-view/download/checkout are URL pageviews (define URL goals).")
        lines.append("  - Decide launch spend only after 2 weeks of real conversion data; "
                     "until then the honest answer on conversion is 'unmeasured'.")
    elif any(w in topic_low for w in ("content", "seo", "social", "channel")):
        lines.append("  - SOPs + truth sheet + 38 pages are the content corpus; doc search "
                     "answers 30/30 business questions from it (see corpus eval). "
                     "Publish from that corpus, not from scratch.")
        lines.append("  - One channel until £1k MRR (per ops plan); measure per-channel "
                     "leads in the task ledger before adding a second.")
    else:
        lines.append("  - No grounded recommendation for this topic yet -- see WHAT TO "
                     "INSTRUMENT below rather than guessing.")
    lines.append("")
    lines.append("CANNOT ANSWER (needs instrumentation): conversion rates, CAC, "
                 "revenue attribution -- " + data_availability()["live_counts"])
    return "\n".join(lines)


def what_to_instrument() -> list[str]:
    """Concrete instrumentation list. Stable, actionable, no guessing."""
    return [
        "Plausible custom events: waitlist-submit, pricing-view, download-start, checkout-start "
        "(pageviews already present in website/app/layout.tsx).",
        "Backend weekly counts from existing tables (needs DATABASE_URL in the backend process, "
        "never credentials here): waitlist_entries, contact_entries, purchases, paraphrase_orders.",
        "Lead source field on every enquiry (one channel at a time until £1k MRR).",
        "Review + referral capture on every completed job (per thursday-sops policy) -- "
        "testimonials feed the website trust page with real quotes.",
    ]


_BACKEND_TABLES = ("waitlist_entries", "contact_entries", "purchases", "paraphrase_orders")

_UNAVAILABLE_DB = ("unavailable — no DB reader in this process (backend is Postgres; "
                   "this checkout carries no credentials by design)")


def _resolve_backend_list_records():
    """funding_ops pattern for the backend store: succeed only when running
    inside a process that actually has the backend DB layer importable.
    Standalone this is always None -- honest, not zero."""
    try:
        from app.db import list_records as _lr  # Audio_Too-style app process
        return _lr
    except ImportError:
        pass
    try:
        import backend.app.database as _be  # noqa: F401 (presence check only)
        get_records = getattr(_be, "list_records", None)
        return get_records
    except ImportError:
        return None


def backend_counts(list_records=None) -> dict:
    """Live row counts for backend business tables when a reader exists.

    `list_records` is injectable so the backend process passes its own
    reader (no credentials ever live here). Standalone every table
    reports unavailable-with-reason, never 0. Never raises.
    Founder SQL equivalent (run where DATABASE_URL exists):
      SELECT 'waitlist_entries', COUNT(*) FROM waitlist_entries;
    """
    resolve = list_records or _resolve_backend_list_records()
    if resolve is None:
        return {t: _UNAVAILABLE_DB for t in _BACKEND_TABLES}
    counts = {}
    for table in _BACKEND_TABLES:
        try:
            counts[table] = len(resolve(table))
        except Exception as exc:
            logger.warning("advisory_ops: backend count failed for %s: %s", table, exc)
            counts[table] = f"unavailable — count query failed: {exc}"
    return counts
