"""Fast server composition-root smoke gate.

Importing `app.server` exercises the full route-module import graph wired into
`do_GET`/`do_POST`. A 2026-07-20 route rewrite dropped a constant that a sibling
route imported at module top, which broke this import (hence `main.py start`)
while every *subsystem* test still passed. This test is the cheap gate for that
whole class: if the server can't be composed, it fails here, in the CI subset,
regardless of which route module is at fault.

It also asserts the trust-boundary classification of the token-gated public
routes, so a future policy edit can't silently expose them.
"""

from __future__ import annotations


def test_server_module_imports():
    import app.server as server

    for handler in ("do_GET", "do_POST"):
        assert hasattr(server.Handler, handler), f"server missing {handler}"


def test_public_token_routes_are_wired():
    import app.server as server

    # The shareable Mix Doctor report route must be dispatched from the server.
    assert hasattr(server, "handle_mix_report_public_get")
    assert hasattr(server, "handle_invoice_get")


def test_token_gated_routes_bypass_auth_but_stay_signed():
    from nite_core.endpoint_policy import EndpointAccess, endpoint_policy

    for path in ("/mix-report/rev-1", "/invoice/INV-1"):
        policy = endpoint_policy("business", "GET", path)
        assert policy.access == EndpointAccess.SIGNED_TOKEN, path
