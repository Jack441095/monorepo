"""Regression guard for the KENN frontend CSRF bug.

Bug: studio/kenn/kenn/static/app.js is served two ways — directly from the
KENN server (port 8090, origin-checked, no CSRF concept) and proxied through
the business app at /kenn (business/app/server.py's do_POST calls
handle_kenn_post AFTER require_private_post(), so proxied POSTs share the
dashboard's CSRF boundary). app.js never sent an X-CSRF-Token header, so
every mutating request — including every single "ask KENN a question" —
failed with 403 "Invalid CSRF token." whenever reached via the /kenn proxy
(the normal path from the hub). Fixed by routing all mutating fetches
through kennFetch(), which attaches a token fetched from /api/auth/session
when API_ORIGIN indicates the proxied path.

There's no JS test runner in this suite, so this is a content-based tripwire:
it fails loudly if a new mutating fetch call is added without going through
kennFetch(), or if the CSRF plumbing itself is removed.
"""

from __future__ import annotations

import re
from pathlib import Path

APP_JS = Path(__file__).resolve().parent.parent.parent / "studio" / "kenn" / "kenn" / "static" / "app.js"

MUTATING_ENDPOINTS = [
    "/api/ask",
    "/api/feedback",
    "/api/session/feedback",
    "/api/mix-review-step",
    "/api/mix-review",
    "/api/audiogen/generate",
    "/api/audiogen/render-song",
    "/api/session/clear",
]


def _source() -> str:
    return APP_JS.read_text(encoding="utf-8")


def test_kenn_fetch_helper_exists_and_attaches_csrf_header() -> None:
    source = _source()
    assert "async function kennFetch(" in source
    assert "async function ensureKennCsrf(" in source
    assert "X-CSRF-Token" in source
    assert "/api/auth/session" in source


def test_no_mutating_endpoint_bypasses_kenn_fetch() -> None:
    """Every known mutating endpoint must be called via kennFetch(...),
    never a bare fetch(apiUrl(...)) that would skip the CSRF header."""
    source = _source()
    for endpoint in MUTATING_ENDPOINTS:
        bare_call = re.search(
            rf'fetch\(apiUrl\(\s*[`"\']{re.escape(endpoint)}[`"\']', source
        )
        assert bare_call is None, (
            f"{endpoint} is called via a bare fetch(apiUrl(...)) — "
            "this bypasses the CSRF header and will 403 when proxied through /kenn."
        )
        assert f'kennFetch("{endpoint}"' in source or f"kennFetch(\"{endpoint}\"" in source, (
            f"{endpoint} should be called through kennFetch(...)"
        )


def test_kenn_fetch_skips_csrf_lookup_for_get_requests() -> None:
    """GET/HEAD requests shouldn't trigger the CSRF session round-trip."""
    source = _source()
    match = re.search(r"async function kennFetch\(.*?\n\}", source, re.DOTALL)
    assert match, "kennFetch function body not found"
    body = match.group(0)
    assert 'method !== "GET"' in body
    assert 'method !== "HEAD"' in body
