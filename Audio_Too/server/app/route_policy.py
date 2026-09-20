"""Central route trust-boundary classification."""

from __future__ import annotations

from nite_core import EndpointAccess, endpoint_policy

PUBLIC_GET_ROUTES = {
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
AUTHENTICATED_GET_ROUTES = {"/api/activity", "/api/summary", "/api/records", "/api/invoices"}
AUTHENTICATED_GET_PREFIXES = ("/api/admin/", "/api/ableton/", "/api/automix/", "/api/v1/", "/kenn/api/")
PUBLIC_POST_ROUTES = {
    "/api/auth/login",
    "/api/public/stem-upload",
    "/api/public/stem-separate",
    "/api/public/automix-start",
    "/api/public/tips/ask",
    "/api/public/ask",
    "/api/enquiry",
}


def route_access(method: str, path: str) -> str:
    """Classify the HTTP trust boundary before route-specific handling."""
    method = method.upper()
    policy = endpoint_policy("business", method, path)
    if policy.access == EndpointAccess.DEMO:
        return "demo"
    if policy.access == EndpointAccess.SIGNED_TOKEN:
        return "signed-token"
    if policy.access == EndpointAccess.AUTHENTICATED:
        return "authenticated-read" if method == "GET" else "authenticated-write"
    if policy.access == EndpointAccess.PUBLIC:
        return "public" if path.startswith("/api/") else "public-static"
    return "unknown"
