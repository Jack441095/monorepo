"""Website read-only ops (Phase 2 -- website visibility without credentials).

Live-reads the website + backend checkouts on disk. No network, no DB
credentials, no writes -- everything here works standalone:

- site_map(): real page list from website/app/*/page.tsx.
- product_pricing(): £ figures from the pricing page + commerce config,
  cited file:line. Never paraphrased into constants.
- pricing_check(): website product prices vs the truth-sheet beta
  (0.2.0 free beta vs £3 planned licence) + scope note that Audio_Too
  SERVICES (£45-180) are a different line from website PRODUCTS.
  Reports drift or scope difference honestly, never invents alignment.
- enquiry_surfaces(): contact/waitlist code paths that exist + honest
  live-DB status (backend is Postgres; without DATABASE_URL in this
  environment the live counts are unavailable, stated plainly).
- traffic_status(): honest analytics-instrumentation check + what to
  instrument when ready.

"Live revenue/enquiries" from the real database is deliberately NOT
implemented here: backend/app uses Postgres (see backend/app/config.py
database_url) and this standalone checkout carries no credentials.
Adding a second reader with hardcoded creds would be a secret-handling
regression; read the DB from the backend process (funding_ops pattern)
once credentials exist.
"""

from __future__ import annotations

import logging
import os
import re
from pathlib import Path

from thursday.redaction import get_logger as _get_redacting_logger
from thursday.repo_root import nite_dsp_root

logger = _get_redacting_logger(__name__)

_POUND_RE = re.compile(r"£\s?\d[\d,]*(?:\.\d+)?")


def _website_root() -> Path | None:
    root = nite_dsp_root() / "website"
    return root if root.is_dir() else None


def _backend_root() -> Path | None:
    root = nite_dsp_root() / "backend" / "app"
    return root if root.is_dir() else None


def site_map() -> dict:
    """Real page list from website/app. Returns {"ok", "pages", "count"}."""
    web = _website_root()
    if web is None:
        return {"ok": False, "pages": [], "count": 0,
                "error": "Evidence missing — website checkout not found."}
    pages = sorted(
        str(p.parent.relative_to(web / "app"))
        for p in (web / "app").rglob("page.tsx")
    )
    return {"ok": True, "pages": pages, "count": len(pages), "error": None}


def product_pricing() -> dict:
    """£ figures from website pricing surfaces, cited file:line."""
    web = _website_root()
    if web is None:
        return {"ok": False, "figures": [],
                "error": "Evidence missing — website checkout not found."}
    targets = [web / "app" / "pricing" / "page.tsx", web / "lib" / "commerce-config.ts"]
    figures = []
    for path in targets:
        if not path.is_file():
            continue
        try:
            lines = path.read_text(encoding="utf-8").splitlines()
        except OSError as exc:
            logger.warning("website_ops: could not read %s: %s", path, exc)
            continue
        for i, line in enumerate(lines, start=1):
            for m in _POUND_RE.finditer(line):
                figures.append({"figure": m.group(0).replace(" ", ""),
                                "source": f"{path.relative_to(web)}:{i}",
                                "context": line.strip()[:160]})
    if not figures:
        return {"ok": False, "figures": [],
                "error": "Evidence missing — no £ figures found on website pricing surfaces."}
    return {"ok": True, "figures": figures, "error": None}


def pricing_check() -> str:
    """Website product prices vs truth-sheet beta + services scope note."""
    from thursday.ops import beta_invite_ops as bio
    from thursday.ops import finance_ops as fo

    lines = ["WEBSITE PRICING CHECK", ""]
    site = product_pricing()
    if site["ok"]:
        shown = ", ".join(sorted({f["figure"] for f in site["figures"]}))
        lines.append(f"  Website shows: {shown}")
        for f in site["figures"][:6]:
            lines.append(f"    {f['figure']} — {f['source']}: {f['context']}")
    else:
        lines.append(f"  {site['error']}")
    version = bio._read_truth_sheet_field("Version")
    lines.append(f"  Truth-sheet beta: {version or 'not found live'}")
    offerings = fo.get_offerings()
    if offerings:
        lines.append(f"  Audio_Too services (business_knowledge.json, NOT website products): "
                     f"{len(offerings)} offerings from £{min(o.get('price_from_gbp', 0) for o in offerings)}")
        lines.append("  Scope note: website sells PRODUCTS (Submit £3 planned, SLO/KENN at-launch); "
                     "business_knowledge sells SERVICES (£45-180). No drift check applies across lines -- "
                     "drift matters only if the same item appears in both with different prices.")
    else:
        lines.append("  Evidence missing — could not read service price list.")
    return "\n".join(lines)


def enquiry_surfaces() -> dict:
    """Contact/waitlist code paths + honest live-DB status."""
    web = _website_root()
    backend = _backend_root()
    routes = []
    if web is not None:
        api = web / "app" / "api"
        if api.is_dir():
            routes = sorted(str(p.relative_to(api)) for p in api.iterdir())
    modules = []
    if backend is not None:
        for name in ("contact.py", "waitlist.py", "commerce.py", "stripe_commerce.py"):
            if (backend / name).is_file():
                modules.append(name)
    db_url = os.environ.get("DATABASE_URL", "").strip()
    if db_url:
        db_status = "DATABASE_URL is set — live counts require the backend process (funding_ops pattern)."
    else:
        db_status = ("Evidence missing — no DATABASE_URL in this environment (backend is Postgres per "
                     "backend/app/config.py); live enquiry/order counts are unavailable, not zero.")
    return {"ok": True, "website_api_routes": routes, "backend_modules": modules,
            "live_db": db_status, "error": None}


def traffic_status() -> dict:
    """Honest analytics-instrumentation check: pageviews, custom funnel
    events (WaitlistSubmit et al.), and what's still unmeasured."""
    web = _website_root()
    if web is None:
        return {"ok": False, "instrumented": False,
                "error": "Evidence missing — website checkout not found."}
    markers = ("plausible", "umami", "posthog", "analytics", "gtag", "vercel/analytics")
    hits = []
    searched = 0
    for path in list((web / "app").rglob("*.tsx"))[:500] + list((web / "lib").glob("*.ts")) \
            + list((web / "components").glob("*.tsx")):
        searched += 1
        try:
            text = path.read_text(encoding="utf-8").lower()
        except OSError:
            continue
        found = [m for m in markers if m in text]
        if found:
            hits.append({"file": str(path.relative_to(web)), "markers": sorted(set(found))})
    if not hits:
        return {"ok": True, "instrumented": False,
                "detail": ("No analytics instrumentation found in website/app + lib "
                           "(checked plausible/umami/posthog/gtag/vercel). Traffic is unmeasured, not zero. "
                           "To instrument: privacy-friendly counter (Plausible/Umami) + events for "
                           "pricing-view, waitlist-submit, download, checkout-start."),
                "error": None}
    event_hits = [h["file"] for h in hits]
    events: list[str] = []
    for rel in event_hits:
        try:
            text = (web / rel).read_text(encoding="utf-8")
        except OSError:
            continue
        events.extend(sorted(set(re.findall(r'plausible\??\.\(\s*["\']([A-Za-z]+)["\']', text))))
        if "tagged-events" in text.lower():
            events.append("tagged-events-build")
    events = sorted(set(events))
    if events:
        return {"ok": True, "instrumented": True, "hits": hits[:10],
                "custom_events": events,
                "detail": (f"Pageviews + custom events instrumented: {', '.join(events)}. "
                           f"Pricing/download/checkout are URL pageviews -- define them as URL goals "
                           f"in Plausible; backend counts (waitlist_entries, purchases) still need "
                           f"DATABASE_URL in the backend process."),
                "error": None}
    return {"ok": True, "instrumented": True, "hits": hits[:10],
            "detail": ("Pageview analytics present but no custom funnel events found -- "
                       "launch conversion is still blind. Next: WaitlistSubmit-style event calls "
                       "on waitlist/pricing/download/checkout actions."),
            "error": None}


def weekly_website_lines() -> list[str]:
    """3-5 honest lines for the weekly report. Never raises."""
    try:
        lines = []
        site = site_map()
        lines.append(f"Pages live: {site['count']}" if site["ok"] else site["error"])
        pricing = product_pricing()
        if pricing["ok"]:
            shown = ", ".join(sorted({f["figure"] for f in pricing["figures"]}))
            lines.append(f"Website prices shown: {shown}")
        else:
            lines.append(pricing["error"])
        lines.append(enquiry_surfaces()["live_db"])
        traffic = traffic_status()
        lines.append(traffic.get("detail", f"Analytics: {traffic.get('hits', [])}"))
        return lines[:5]
    except Exception as exc:  # weekly report must never break on website reads
        logger.warning("website_ops: weekly lines failed: %s", exc)
        return ["Website section unavailable (read failed; see logs)."]
