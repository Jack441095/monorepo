"""Web research / prospecting (founder request, 2026-09-02).

Real web search via the Tavily API (https://tavily.com), read from
`TAVILY_API_KEY` in `Audio_Too/.env` — chosen for a generous free tier
(1,000 searches/month), a clean JSON result shape suited to an AI agent
(no HTML scraping), and a privacy-first stance consistent with the rest
of this project (see `docs/NITE_DSP_NEXT_STEPS_AND_AGENTIC_OPPORTUNITIES.md`'s
"no-telemetry, privacy-first" framing for support triage).

**What this deliberately does NOT do:** invent leads, names, emails, or
companies. Every result returned is a real search hit (title, URL,
snippet) from Tavily, never fabricated. If `TAVILY_API_KEY` is unset, this
says so plainly ("Evidence missing — web search not configured") rather
than returning empty/fake results silently — same discipline as
`finance_ops.py`'s business-knowledge lookup.

**What "find potential customers" honestly means here:** there is no
internal lead-generation database this can search (checked first: the
`leads`/`enquiries`/`clients` tables in `Audio_Too/data/audio_too.db` are
real and already wired to the existing `pipeline`/`enquiries` services in
`registry/business.py` — but all currently hold zero rows, per the beta
checklist's own "zero clients, zero enquiries" note). So this module does
two genuinely different, both-real things:
  1. `web_search()` — raw search results for any query, useful for market/
     competitor research as much as prospecting.
  2. `find_potential_customers()` — the same real search, pre-seeded with
     NITE Submit's actual documented target audience
     (`docs/NITE_SUBMIT_LAUNCH_TRUTH_SHEET.md`: "students who need to
     prepare university assignment files") when no specific query is
     given, so a bare "find customers" produces a real, on-topic search
     rather than a generic one or a refusal.

This surfaces real communities/forums/channels where the target audience
gathers -- not personal contact details of named individuals. Thursday
has no outreach/contact capability here (matches the beta_invite_ops.py
precedent: draft-only, founder sends manually) -- turning a search result
into an actual approach is a human judgment call, not something to
automate.
"""

from __future__ import annotations

import json
import logging
import os
import urllib.error
import urllib.request

logger = logging.getLogger(__name__)

TAVILY_SEARCH_URL = "https://api.tavily.com/search"
_DEFAULT_TARGET_AUDIENCE_QUERY = (
    "online communities and forums for students preparing university "
    "assignment submissions and file naming"
)

_FIND_CUSTOMERS_PREFIXES = [
    "find customers:", "find customers", "find potential customers:",
    "find potential customers", "look for customers:", "look for customers",
    "look for potential customers:", "look for potential customers",
    "search for customers:", "search for customers",
]
_WEB_SEARCH_PREFIXES = [
    "web search:", "search the web:", "search the web for", "search online for",
    "look up:", "look up",
]


def parse_find_customers_command(text: str) -> str | None:
    """Returns the (possibly empty) query tail if ``text`` is a
    find-customers command, else None. An empty tail is valid -- it falls
    back to NITE Submit's documented target audience (see
    find_potential_customers()) -- so this never raises, unlike the
    pipe-delimited commands in ops_intake.py.
    """
    stripped = text.strip()
    lower = stripped.lower()
    for prefix in sorted(_FIND_CUSTOMERS_PREFIXES, key=len, reverse=True):
        if lower.startswith(prefix.lower()):
            return stripped[len(prefix):].strip()
    return None


def parse_web_search_command(text: str) -> str | None:
    """Returns the query tail if ``text`` is a web-search command, else
    None. Unlike find-customers, an empty query here is not a valid
    "use a sensible default" case -- there's no default topic for a
    generic search -- so the handler treats an empty return the same as
    a parse miss.
    """
    stripped = text.strip()
    lower = stripped.lower()
    for prefix in sorted(_WEB_SEARCH_PREFIXES, key=len, reverse=True):
        if lower.startswith(prefix.lower()):
            return stripped[len(prefix):].strip()
    return None


def _api_key() -> str | None:
    key = os.environ.get("TAVILY_API_KEY", "").strip()
    return key or None


def web_search(query: str, max_results: int = 5) -> dict:
    """Real Tavily search. Returns {"ok": bool, "results": [...], "error":
    str | None}. Never raises -- network/API failures are returned as a
    structured error, matching this codebase's client.py convention.
    """
    query = query.strip()
    if not query:
        return {"ok": False, "results": [], "error": "Empty search query."}

    api_key = _api_key()
    if api_key is None:
        return {
            "ok": False,
            "results": [],
            "error": (
                "Evidence missing — web search not configured. Add "
                "TAVILY_API_KEY to Audio_Too/.env (sign up at tavily.com, "
                "free tier: 1,000 searches/month)."
            ),
        }

    payload = json.dumps({
        "api_key": api_key,
        "query": query,
        "max_results": max(1, min(max_results, 10)),
        "search_depth": "basic",
    }).encode("utf-8")

    request = urllib.request.Request(
        TAVILY_SEARCH_URL,
        data=payload,
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    try:
        with urllib.request.urlopen(request, timeout=15) as response:
            data = json.loads(response.read().decode("utf-8"))
    except urllib.error.HTTPError as exc:
        return {"ok": False, "results": [], "error": f"Tavily API error ({exc.code}): {exc.reason}"}
    except (urllib.error.URLError, TimeoutError, json.JSONDecodeError) as exc:
        return {"ok": False, "results": [], "error": f"Web search failed: {exc}"}

    results = [
        {
            "title": r.get("title", ""),
            "url": r.get("url", ""),
            "snippet": r.get("content", ""),
        }
        for r in data.get("results", [])
    ]
    return {"ok": True, "results": results, "error": None}


def render_search_results(query: str, result: dict) -> str:
    if not result["ok"]:
        return f"WEB SEARCH: \"{query}\"\n\n{result['error']}"

    if not result["results"]:
        return f"WEB SEARCH: \"{query}\"\n\nNo results found."

    lines = [f"WEB SEARCH: \"{query}\"", ""]
    for i, r in enumerate(result["results"], 1):
        lines.append(f"{i}. {r['title']}")
        lines.append(f"   {r['url']}")
        if r["snippet"]:
            snippet = r["snippet"].strip().replace("\n", " ")
            if len(snippet) > 200:
                snippet = snippet[:197] + "..."
            lines.append(f"   {snippet}")
        lines.append("")
    lines.append(
        "Real search results, not verified leads — review before acting on "
        "any of them. Thursday does not contact anyone automatically."
    )
    return "\n".join(lines)


def find_potential_customers(query: str = "") -> str:
    """Prospecting wrapper: pre-seeds the search with NITE Submit's real
    documented target audience when no specific query is given.
    """
    search_query = query.strip() or _DEFAULT_TARGET_AUDIENCE_QUERY
    result = web_search(search_query)
    rendered = render_search_results(search_query, result)
    if not query.strip() and result["ok"]:
        rendered += (
            "\n\nDefault query used NITE Submit's documented target audience "
            "(docs/NITE_SUBMIT_LAUNCH_TRUTH_SHEET.md) — give a more specific "
            "query (e.g. 'find customers: music production forums UK') to "
            "narrow this."
        )
    return rendered
