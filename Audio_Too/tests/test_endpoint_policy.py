"""Completeness and invariant checks for every HTTP endpoint family."""

from __future__ import annotations

import ast
from pathlib import Path

from app import api_contract

from nite_core import (
    EndpointAccess,
    EndpointEffect,
    PermissionScope,
    endpoint_policy,
)

ROOT = Path(__file__).resolve().parent.parent


def _route_literals(path: Path, function_methods: dict[str, str]) -> set[tuple[str, str]]:
    tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
    routes = set()
    for function in (node for node in ast.walk(tree) if isinstance(node, ast.FunctionDef)):
        method = function_methods.get(function.name)
        if method is None:
            if function.name.endswith("_get") or function.name == "handle_get":
                method = "GET"
            elif function.name.endswith("_post") or function.name == "handle_post":
                method = "POST"
        if method is None:
            continue
        for node in ast.walk(function):
            if isinstance(node, ast.Constant) and isinstance(node.value, str):
                value = node.value
                if value.startswith(
                    ("/api/", "/invoice/", "/kenn/api/", "/portfolio/", "/session/")
                ):
                    routes.add((method, value))
    return routes


def _inventory() -> dict[str, set[tuple[str, str]]]:
    business = set()
    for path in (ROOT / "server" / "app" / "routes").glob("*.py"):
        business |= _route_literals(path, {})
    for path in (ROOT / "server" / "app").glob("*routes.py"):
        business |= _route_literals(path, {})
    business |= _route_literals(
        ROOT / "server" / "app" / "server.py",
        {"do_GET": "GET", "do_POST": "POST"},
    )
    business |= set(api_contract.VERSIONED_ALIASES)
    kenn = _route_literals(
        ROOT / "studio" / "kenn" / "kenn" / "server.py",
        {"do_GET": "GET", "do_POST": "POST"},
    )
    thursday = _route_literals(
        ROOT / "thursday" / "server.py",
        {"do_GET": "GET", "do_POST": "POST", "do_DELETE": "DELETE"},
    )
    thursday |= {("GET", "/health"), ("POST", "/ask"), ("POST", "/command")}
    return {"business": business, "kenn": kenn, "thursday": thursday}


def test_every_discovered_endpoint_has_a_complete_policy() -> None:
    inventory = _inventory()
    assert len(inventory["business"]) >= 120
    assert len(inventory["kenn"]) >= 25
    assert len(inventory["thursday"]) >= 5
    for surface, routes in inventory.items():
        for method, path in routes:
            policy = endpoint_policy(surface, method, path)
            assert policy.access
            assert policy.effect
            assert policy.permissions
            if policy.mutates:
                assert PermissionScope.MUTATE_LOCAL in policy.permissions
            if policy.effect == EndpointEffect.EXTERNAL_COMMUNICATION:
                assert PermissionScope.COMMUNICATE_EXTERNAL in policy.permissions
            if policy.effect in {
                EndpointEffect.EXTERNAL_COMMUNICATION,
                EndpointEffect.DESTRUCTIVE,
            }:
                assert policy.confirmation_required
                assert policy.idempotency_required


def test_business_private_writes_require_session_origin_and_csrf() -> None:
    for path in (
        "/api/admin/drafts/send",
        "/api/admin/portfolio/publish-audio",
        "/api/ableton/build",
        "/api/automix/start",
        "/kenn/api/session/clear",
    ):
        policy = endpoint_policy("business", "POST", path)
        assert policy.access == EndpointAccess.AUTHENTICATED
        assert policy.origin_required
        assert policy.csrf_required
        assert policy.rate_limit_required
        assert policy.body_limit_required


def test_public_business_writes_are_explicit_and_rate_limited() -> None:
    for path in (
        "/api/auth/login",
        "/api/public/stem-upload",
        "/api/public/podcast-check",
        "/api/public/mix-doctor",
        "/api/public/delivery-check",
        "/api/public/tips/ask",
        "/api/public/ask",
        "/api/enquiry",
    ):
        policy = endpoint_policy("business", "POST", path)
        assert policy.access == EndpointAccess.PUBLIC
        assert policy.origin_required
        assert policy.rate_limit_required


def test_kenn_and_thursday_fail_closed_at_their_service_boundaries() -> None:
    kenn_mutation = endpoint_policy("kenn", "POST", "/api/session/clear")
    assert kenn_mutation.access == EndpointAccess.LOOPBACK
    assert kenn_mutation.origin_required
    assert kenn_mutation.rate_limit_required
    assert kenn_mutation.effect == EndpointEffect.DESTRUCTIVE

    ask = endpoint_policy("thursday", "POST", "/ask")
    assert ask.access == EndpointAccess.SERVICE_TOKEN
    assert ask.effect == EndpointEffect.ORCHESTRATED
    assert ask.rate_limit_required
    assert ask.body_limit_required

    health = endpoint_policy("thursday", "GET", "/health")
    assert health.access == EndpointAccess.PUBLIC
    assert health.effect == EndpointEffect.READ_ONLY
