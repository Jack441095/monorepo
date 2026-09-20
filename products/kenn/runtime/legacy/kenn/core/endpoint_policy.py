"""Shared access, effect, and permission classification for HTTP endpoints.

Ported into this standalone repository (not a live dependency on the old
NITE DSP platform): pure classification logic over strings, with no
external calls. Depends only on ``PermissionScope`` from
``kenn.core.platform_contracts`` (also ported, also stdlib-only).
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum

from kenn.core.platform_contracts import PermissionScope


class EndpointAccess(str, Enum):
    PUBLIC = "public"
    SIGNED_TOKEN = "signed_token"
    AUTHENTICATED = "authenticated"
    SERVICE_TOKEN = "service_token"
    LOOPBACK = "loopback"
    DEMO = "demo"


class EndpointEffect(str, Enum):
    READ_ONLY = "read_only"
    ANALYSIS = "analysis"
    LOCAL_MUTATION = "local_mutation"
    EXTERNAL_COMMUNICATION = "external_communication"
    DESTRUCTIVE = "destructive"
    ORCHESTRATED = "orchestrated"


@dataclass(frozen=True)
class EndpointPolicy:
    surface: str
    method: str
    path: str
    access: EndpointAccess
    effect: EndpointEffect
    permissions: tuple[PermissionScope, ...]
    origin_required: bool
    csrf_required: bool
    rate_limit_required: bool
    body_limit_required: bool
    idempotency_required: bool
    confirmation_required: bool

    @property
    def mutates(self) -> bool:
        return self.effect in {
            EndpointEffect.LOCAL_MUTATION,
            EndpointEffect.EXTERNAL_COMMUNICATION,
            EndpointEffect.DESTRUCTIVE,
            EndpointEffect.ORCHESTRATED,
        }


_BUSINESS_PUBLIC_GET = {
    "/api/auth/session",
    "/api/public/business",
    "/api/hub/status",
    "/api/audiogen/status",
    "/api/portfolio",
    "/api/public/tips",
    "/api/public/tips/suggest",
    "/api/public/stem-upload/info",
    "/api/public/stem-separate/status",
    "/api/public/stem-separate/download",
    "/api/public/automix-start/status",
}
_BUSINESS_PUBLIC_POST = {
    "/api/auth/login",
    "/api/public/stem-upload",
    "/api/public/podcast-check",
    "/api/public/mix-doctor",
    "/api/public/delivery-check",
    "/api/public/stem-separate",
    "/api/public/automix-start",
    "/api/public/tips/ask",
    "/api/public/ask",
    "/api/enquiry",
}
_ANALYSIS_POST_SUFFIXES = {
    "/ask",
    "/suggest",
    "/transcribe",
    "/speak",
    "/detect_scale",
    "/groove",
    "/bassline",
    "/doctor/audit",
    "/doctor/remediate",
}
_EXTERNAL_PATH_PARTS = (
    "/drafts/send",
    "/draft-deliveries",
    "/portfolio/publish",
    "/admin/agent",
)
_EXTERNAL_EXACT_PATHS = {"/api/enquiry"}
_DESTRUCTIVE_PATH_PARTS = (
    "/session/clear",
    "/render-job/cancel",
    "/dismiss",
)


def _effect(surface: str, method: str, path: str) -> EndpointEffect:
    if method in {"GET", "HEAD", "OPTIONS"}:
        if path.endswith("/reload-index"):
            return EndpointEffect.LOCAL_MUTATION
        return EndpointEffect.READ_ONLY
    if method == "DELETE":
        return EndpointEffect.DESTRUCTIVE
    if path.endswith("/ask") or path == "/ask":
        return (
            EndpointEffect.ORCHESTRATED
            if surface == "thursday"
            else EndpointEffect.ANALYSIS
        )
    if path == "/command":
        return EndpointEffect.ORCHESTRATED
    if any(path.endswith(suffix) for suffix in _ANALYSIS_POST_SUFFIXES):
        return EndpointEffect.ANALYSIS
    if path in _EXTERNAL_EXACT_PATHS or any(part in path for part in _EXTERNAL_PATH_PARTS):
        return EndpointEffect.EXTERNAL_COMMUNICATION
    if any(part in path for part in _DESTRUCTIVE_PATH_PARTS):
        return EndpointEffect.DESTRUCTIVE
    return EndpointEffect.LOCAL_MUTATION


def _permissions(effect: EndpointEffect) -> tuple[PermissionScope, ...]:
    scopes = [PermissionScope.READ]
    if effect == EndpointEffect.ANALYSIS:
        scopes.append(PermissionScope.ANALYZE)
    elif effect in {
        EndpointEffect.LOCAL_MUTATION,
        EndpointEffect.DESTRUCTIVE,
        EndpointEffect.ORCHESTRATED,
    }:
        scopes.append(PermissionScope.MUTATE_LOCAL)
    elif effect == EndpointEffect.EXTERNAL_COMMUNICATION:
        scopes.extend(
            (PermissionScope.MUTATE_LOCAL, PermissionScope.COMMUNICATE_EXTERNAL)
        )
    return tuple(scopes)


def endpoint_policy(surface: str, method: str, path: str) -> EndpointPolicy:
    """Classify a concrete endpoint, with fail-closed family defaults."""
    surface = surface.strip().lower()
    method = method.upper()
    path = "/" + path.lstrip("/")
    effect = _effect(surface, method, path)

    if surface == "business":
        if path.startswith("/api/demo/"):
            access = EndpointAccess.DEMO
        elif method == "GET" and path.startswith(("/invoice/", "/mix-report/", "/podcast-report/")):
            access = EndpointAccess.SIGNED_TOKEN
        elif (method == "GET" and path in _BUSINESS_PUBLIC_GET) or (
            method == "POST" and path in _BUSINESS_PUBLIC_POST
        ):
            access = EndpointAccess.PUBLIC
        elif path.startswith(("/api/", "/kenn/api/")):
            access = EndpointAccess.AUTHENTICATED
        else:
            access = EndpointAccess.PUBLIC
        csrf_required = method in {"POST", "PUT", "PATCH", "DELETE"} and access == EndpointAccess.AUTHENTICATED
        origin_required = method in {"POST", "PUT", "PATCH", "DELETE"}
    elif surface == "thursday":
        access = EndpointAccess.PUBLIC if path == "/health" else EndpointAccess.SERVICE_TOKEN
        csrf_required = False
        origin_required = method == "OPTIONS"
    elif surface == "kenn":
        access = EndpointAccess.LOOPBACK
        csrf_required = False
        origin_required = path.startswith("/api/")
    else:
        raise ValueError(f"Unknown endpoint surface: {surface}")

    return EndpointPolicy(
        surface=surface,
        method=method,
        path=path,
        access=access,
        effect=effect,
        permissions=_permissions(effect),
        origin_required=origin_required,
        csrf_required=csrf_required,
        rate_limit_required=(
            (surface == "thursday" and path != "/health")
            or (
                surface == "business"
                and method == "POST"
                and path.startswith(("/api/", "/kenn/api/"))
            )
            or (surface == "kenn" and effect != EndpointEffect.READ_ONLY)
        ),
        body_limit_required=method in {"POST", "PUT", "PATCH"},
        idempotency_required=effect in {
            EndpointEffect.EXTERNAL_COMMUNICATION,
            EndpointEffect.DESTRUCTIVE,
        },
        confirmation_required=effect in {
            EndpointEffect.EXTERNAL_COMMUNICATION,
            EndpointEffect.DESTRUCTIVE,
        },
    )
