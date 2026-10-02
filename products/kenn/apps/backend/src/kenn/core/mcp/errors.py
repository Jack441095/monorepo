"""Errors the MCP companion can raise to the caller.

Lives apart from ``mcp_facade`` so the handler modules can catch it without
importing the facade that imports them.
"""

from __future__ import annotations


class KennTransportError(RuntimeError):
    """A companion request did not complete; a mutation may be ambiguous."""
