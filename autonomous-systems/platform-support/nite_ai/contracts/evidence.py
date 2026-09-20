"""Typed, provenance-preserving evidence contracts.

Generalised from KENN's EvidencePacket (studio/kenn/kenn/core/evidence.py).
Measured facts and inferred/reasoned claims must never collapse into one
string; confidence is always labelled by kind so LLM-invented confidence can
never masquerade as measurement confidence.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from enum import Enum

from nite_ai._serialization import dataclass_to_dict
from nite_ai.errors import ValidationError
from nite_ai.versioning import CONTRACT_SCHEMA_VERSION

_ID_RE = re.compile(r"^[a-z0-9][a-z0-9_.-]{2,128}$")


def _validate_id(value: str, label: str) -> None:
    if not isinstance(value, str) or not _ID_RE.match(value):
        raise ValidationError(f"{label} must match {_ID_RE.pattern!r}, got {value!r}")


class ConfidenceKind(str, Enum):
    MEASURED = "measured"          # deterministic DSP/analyser output
    CLASSIFIER = "classifier"      # ML model output score
    DERIVED = "derived"            # computed from other evidence
    REASONING = "reasoning"        # LLM/rule-based judgement — never a measurement


@dataclass(frozen=True)
class EvidenceItem:
    """A single provenance-preserving fact."""

    name: str
    value: float | int | str | bool
    unit: str = ""
    source: str = ""                       # source component, e.g. "kenn.mix_review"
    confidence_kind: ConfidenceKind | None = None
    confidence: float | None = None        # only meaningful with a confidence_kind
    captured_at_epoch: float | None = None
    analysis_version: str | None = None
    artifact_ref: str | None = None        # reference to an ArtifactRef.artifact_id

    def __post_init__(self) -> None:
        if not self.name:
            raise ValidationError("EvidenceItem.name must not be empty")
        if self.confidence is not None:
            if not 0.0 <= self.confidence <= 1.0:
                raise ValidationError("EvidenceItem.confidence must be within [0, 1]")
            if self.confidence_kind is None:
                raise ValidationError(
                    "EvidenceItem.confidence requires confidence_kind "
                    "(measurement vs classifier vs reasoning confidence)"
                )
        if self.analysis_version is not None and not self.analysis_version:
            raise ValidationError("EvidenceItem.analysis_version must not be empty string")


@dataclass(frozen=True)
class EvidencePacket:
    """A bounded bundle of evidence facts from one source."""

    packet_id: str
    source: str
    facts: tuple[EvidenceItem, ...] = ()
    limitations: tuple[str, ...] = ()
    created_at_epoch: float | None = None
    schema_version: str = CONTRACT_SCHEMA_VERSION

    def __post_init__(self) -> None:
        _validate_id(self.packet_id, "EvidencePacket.packet_id")
        if not self.source:
            raise ValidationError("EvidencePacket.source must not be empty")

    def payload(self) -> dict:
        return dataclass_to_dict(self)


__all__ = ["ConfidenceKind", "EvidenceItem", "EvidencePacket"]
