"""Shared platform primitives for NITE DSP.

Domain implementations remain in ``products/kenn``, ``audio-technology``,
and ``autonomous-systems/thursday``.
Only dependency-free, versioned boundary contracts belong in this package.
"""

from .contracts import (
    AssistantConfidence,
    AssistantResponse,
    AudioFeatureSet,
    ArtifactRef,
    Capability,
    CommandEnvelope,
    ContractError,
    ContractValidationError,
    DomainEvent,
    JobSnapshot,
    JobStatus,
    PermissionScope,
    ProjectContext,
    ResultEnvelope,
    ResultStatus,
)
from .errors import (
    PublicError,
    PublicErrorCode,
    PublicErrorDetails,
    public_error_details,
    public_error_payload,
)
from .endpoint_policy import (
    EndpointAccess,
    EndpointEffect,
    EndpointPolicy,
    endpoint_policy,
)
from .confirmation import (
    issue_confirmation,
    verify_confirmation,
)

__all__ = [
    "AssistantConfidence",
    "AssistantResponse",
    "AudioFeatureSet",
    "ArtifactRef",
    "Capability",
    "CommandEnvelope",
    "ContractError",
    "ContractValidationError",
    "DomainEvent",
    "EndpointAccess",
    "EndpointEffect",
    "EndpointPolicy",
    "JobSnapshot",
    "JobStatus",
    "PermissionScope",
    "ProjectContext",
    "PublicError",
    "PublicErrorCode",
    "PublicErrorDetails",
    "ResultEnvelope",
    "ResultStatus",
    "issue_confirmation",
    "verify_confirmation",
    "public_error_details",
    "public_error_payload",
    "endpoint_policy",
]
