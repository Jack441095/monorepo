"""Lightweight schema versioning.

Philosophy (see docs/VERSIONING.md): additive evolution. New fields must be
optional with defaults; removing or renaming a field is a breaking change that
bumps the major contract schema version.
"""

CONTRACT_SCHEMA_VERSION = "1.0.0"

__all__ = ["CONTRACT_SCHEMA_VERSION"]
