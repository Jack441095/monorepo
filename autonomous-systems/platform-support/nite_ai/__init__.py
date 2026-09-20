"""nite_ai — NITE DSP AI Platform core (Phase 1).

Dependency-free typed contracts, registries, and telemetry/evaluation schemas.
Importing this package has no side effects: no network, no models, no files,
no database. See README.md for scope and boundaries.
"""

from nite_ai import capabilities, contracts
from nite_ai.adapters import ProductAdapter
from nite_ai.capabilities import CapabilityRegistry, ToolRegistry
from nite_ai.contracts import (
    AgentRequest,
    AgentResult,
    CapabilityDefinition,
    ConfidenceKind,
    EvidenceItem,
    EvidencePacket,
    LatencyClass,
    RequestPriority,
    ResultStatus,
)
from nite_ai.errors import AgentError, ErrorCategory, RetryPolicy, ValidationError
from nite_ai.permissions import ActionRisk, Permission, PrivacyClass
from nite_ai.telemetry import TaskEvent, TraceContext
from nite_ai.versioning import CONTRACT_SCHEMA_VERSION

__version__ = "0.3.0"

__all__ = [
    "CONTRACT_SCHEMA_VERSION",
    "ActionRisk",
    "AgentError",
    "AgentRequest",
    "AgentResult",
    "CapabilityDefinition",
    "CapabilityRegistry",
    "ConfidenceKind",
    "ErrorCategory",
    "EvidenceItem",
    "EvidencePacket",
    "LatencyClass",
    "Permission",
    "PrivacyClass",
    "ProductAdapter",
    "RequestPriority",
    "ResultStatus",
    "RetryPolicy",
    "TaskEvent",
    "ToolRegistry",
    "TraceContext",
    "ValidationError",
    "__version__",
    "capabilities",
    "contracts",
]

