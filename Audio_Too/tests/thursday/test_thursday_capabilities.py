"""Thursday capability declaration and permission conformance tests."""

from __future__ import annotations

import json

from nite_core import Capability, PermissionScope
from thursday.registry import build_services


def test_every_service_exposes_a_versioned_json_capability() -> None:
    services = build_services(None)
    assert len(services) >= 50
    names = set()
    for service_id, service in services.items():
        capability = service.to_capability(service_id)
        decoded = json.loads(json.dumps(capability.to_dict()))
        assert Capability.from_dict(decoded) == capability
        assert capability.name == f"thursday.{service_id}"
        assert capability.version == "1.0.0"
        assert capability.permissions
        assert capability.name not in names
        names.add(capability.name)


def test_consequential_services_declare_mutation_scope() -> None:
    services = build_services(None)
    for service_id in {
        "audiogen_render",
        "audiogen_job",
        "daily_maintenance",
        "weekly_maintenance",
        "mix_review_correction_rack",
        "reminder_set",
        "kenn_save_note",
        "user_profile_prefs",
    }:
        assert PermissionScope.MUTATE_LOCAL in services[service_id].permissions


def test_analysis_and_proposal_scopes_are_not_implicitly_mutating() -> None:
    services = build_services(None)
    assert services["kenn"].permissions == (
        PermissionScope.READ,
        PermissionScope.ANALYZE,
    )
    assert services["business_insights"].permissions == (
        PermissionScope.READ,
        PermissionScope.PROPOSE,
    )
    assert PermissionScope.MUTATE_LOCAL not in services["mix_review"].permissions


def test_discovery_payload_contains_contract_not_action_callable() -> None:
    service = build_services(None)["audiogen_render"]
    payload = service.to_dict("audiogen_render")
    assert payload["capability"]["name"] == "thursday.audiogen_render"
    assert payload["capability"]["permissions"] == ["read", "mutate_local"]
    assert "action" not in payload
