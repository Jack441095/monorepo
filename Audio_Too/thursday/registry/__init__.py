"""Service Registry v2 — declarative service definitions.

Each service knows:
  - What intents and keywords trigger it
  - What session context it requires
  - How to execute (via the unified client)
  - How to update context after execution

This module used to be one 1,263-line file; it's now a thin composition shim over
registry_core (ServiceDef/permissions/scoring), registry_handlers (the _handle_*
functions), and registry_business/registry_studio/registry_system (the 50 service
definitions, grouped by domain). See docs/BACKLOG.md for the decomposition record.
"""

from __future__ import annotations

from typing import Any

from thursday.registry.core import (  # noqa: F401
    _ANALYSIS_SERVICES,
    ActionRisk,
    ServiceDef,
    _permission_scopes,
    _service_risk,
    request_risk,
    score_by_triggers,
)
from thursday.registry.handlers import (  # noqa: F401
    _handle_agent_workflow_chain,
    _handle_audio_storage,
)
from thursday.registry.business import _register_business_services
from thursday.registry.studio import _register_studio_services
from thursday.registry.system import _register_system_services
from thursday.registry.codebase import _register_codebase_services


def build_services(api: Any) -> dict[str, ServiceDef]:
    """Build the complete service registry.

    Args:
        api: The unified API client instance (Thursday.client module).
              Used for action callbacks.

    Returns:
        Dict of service_id -> ServiceDef
    """
    services: dict[str, ServiceDef] = {}
    _register_business_services(services, api)
    _register_studio_services(services, api)
    _register_system_services(services, api)
    _register_codebase_services(services, api)

    for service_id, service in services.items():
        service.permissions = _permission_scopes(service_id)
        service.risk = _service_risk(service_id)
        if service_id in {"audiogen", "audiogen_render"}:
            service.resource_needs = {"audiogen_runtime": True}
        elif service_id in _ANALYSIS_SERVICES:
            service.resource_needs = {"local_models": service_id.startswith("kenn")}
    return services


# Declarative registry snapshot for discovery and tooling. Runtime callers use
# build_services(api) so actions receive the selected client implementation.
SERVICES = build_services(None)
