"""Contract tests for every registered Thursday service.

Thursday routes ~50 services; if one is half-registered (missing a name, a bad
permission, an uncallable action, or no way to reach it) it fails at runtime, not
at import. These assert the minimum contract for all of them at test time.
"""

from __future__ import annotations

import re
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from nite_core import Capability  # noqa: E402
from thursday import client as api  # noqa: E402
from thursday.registry import build_services  # noqa: E402


@pytest.fixture(scope="module")
def services():
    return build_services(api)


def test_registry_registers_the_expected_service_count(services):
    assert len(services) >= 40  # ~50 registered; guards against a broken registry


def test_every_service_has_name_description_and_callable_action(services):
    for service_id, svc in services.items():
        assert isinstance(service_id, str) and service_id, "service id must be a non-empty string"
        assert svc.name and svc.name.strip(), f"{service_id}: missing name"
        assert svc.description and svc.description.strip(), f"{service_id}: missing description"
        assert callable(svc.action), f"{service_id}: action must be callable"


def test_every_service_produces_a_valid_capability(services):
    # to_capability() constructs a Capability, which validates permissions/version/
    # description/resource_needs on construction — so a malformed service raises here.
    for service_id, svc in services.items():
        capability = svc.to_capability(service_id)
        assert isinstance(capability, Capability)
        assert capability.name == f"thursday.{service_id}"
        assert capability.permissions, f"{service_id}: capability declares no permissions"


def test_service_ids_are_capability_safe(services):
    for service_id in services:
        assert re.fullmatch(r"[A-Za-z0-9_.:-]+", service_id), f"invalid service id: {service_id}"


def test_every_service_is_reachable(services):
    # A service with neither triggers nor intents can never be routed to.
    unreachable = [
        service_id
        for service_id, svc in services.items()
        if not svc.triggers and not svc.intents
    ]
    assert not unreachable, f"services with no triggers or intents (unreachable): {unreachable}"
