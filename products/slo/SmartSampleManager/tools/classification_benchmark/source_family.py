"""Explicit, repeatable source-family boundaries for classification research."""

from pathlib import Path


LEGACY_PREFIX_TOKENS = 3
CANDIDATE_PREFIX_TOKENS = 5


def legacy_source_family(filename: str) -> str:
    """Return the historical filename-only grouping key."""
    parts = Path(filename).stem.split("_")
    return "_".join(parts[:LEGACY_PREFIX_TOKENS]) if len(parts) >= LEGACY_PREFIX_TOKENS else Path(filename).stem


def candidate_source_family(vendor: str, relative_folder: str, filename: str) -> str:
    """Return the proposed provenance-aware grouping key.

    The mapped source folder separates labels assigned by different mapping
    rules, while the filename prefix keeps obvious exports/variants together.
    This is a candidate research boundary and still requires provenance and
    owner review before it can support a product claim.
    """
    parts = Path(filename).stem.split("_")
    prefix = "_".join(parts[:CANDIDATE_PREFIX_TOKENS]) if parts else Path(filename).stem
    return f"{Path(vendor, relative_folder).as_posix()}/{prefix}"
