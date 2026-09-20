#!/usr/bin/env python3
"""Versioned, decision-neutral evidence record for SLO audio analysis.

This module deliberately does not classify audio or authorize a rename.  It
provides the contract between feature extraction, independent prediction
heads, review tooling, and the later policy/naming layer.
"""
from __future__ import annotations

from dataclasses import asdict, dataclass, field
from typing import Any


SCHEMA_VERSION = "1.0.0"
CLAIM_STATES = {"observed", "predicted", "user", "unknown", "rejected"}
FORMS = {"one-shot", "loop", "phrase", "fill", "sustained", "unknown"}


@dataclass(frozen=True)
class EvidenceClaim:
    value: str = ""
    confidence: float = 0.0
    source: str = "unknown"
    state: str = "unknown"
    alternatives: tuple[tuple[str, float], ...] = ()

    def validate(self) -> None:
        if self.state not in CLAIM_STATES:
            raise ValueError(f"unsupported claim state: {self.state}")
        if not 0.0 <= self.confidence <= 1.0:
            raise ValueError("claim confidence must be in [0, 1]")
        if self.state in {"observed", "predicted", "user"} and not self.value:
            raise ValueError(f"{self.state} claim requires a value")
        for value, confidence in self.alternatives:
            if not value or not 0.0 <= confidence <= 1.0:
                raise ValueError("invalid alternative claim")


@dataclass(frozen=True)
class PhysicalMeasurement:
    value: float
    unit: str
    method: str
    valid: bool = True


@dataclass
class AudioEvidenceRecord:
    content_id: str
    source_path: str
    schema_version: str = SCHEMA_VERSION
    identity: EvidenceClaim = field(default_factory=EvidenceClaim)
    family: EvidenceClaim = field(default_factory=EvidenceClaim)
    form: EvidenceClaim = field(default_factory=EvidenceClaim)
    attributes: dict[str, EvidenceClaim] = field(default_factory=dict)
    measurements: dict[str, PhysicalMeasurement] = field(default_factory=dict)
    metadata: dict[str, Any] = field(default_factory=dict)
    duplicate_group: str = ""
    model_versions: dict[str, str] = field(default_factory=dict)
    legacy: dict[str, Any] = field(default_factory=dict)

    def validate(self) -> None:
        if self.schema_version != SCHEMA_VERSION:
            raise ValueError(f"unsupported evidence schema: {self.schema_version}")
        if not self.content_id:
            raise ValueError("content_id is required")
        if not self.source_path:
            raise ValueError("source_path is required")
        for claim in (self.identity, self.family, self.form, *self.attributes.values()):
            claim.validate()
        if self.form.value and self.form.value not in FORMS:
            raise ValueError(f"unsupported form: {self.form.value}")
        for name, measurement in self.measurements.items():
            if not name or not measurement.method or not measurement.unit:
                raise ValueError("measurements require name, method, and unit")

    def as_dict(self) -> dict[str, Any]:
        self.validate()
        payload = asdict(self)
        # JSON has no tuples; normalize alternatives for a stable wire format.
        for key in ("identity", "family", "form"):
            payload[key]["alternatives"] = [list(item) for item in payload[key]["alternatives"]]
        for claim in payload["attributes"].values():
            claim["alternatives"] = [list(item) for item in claim["alternatives"]]
        return payload


def _legacy_identity_and_form(subcategory: str, secondary_tags: list[str]) -> tuple[str, str]:
    """Expose legacy semantics without inventing information.

    This is a compatibility view only.  A learned factorised head may replace
    either claim later, while the untouched legacy fields remain available for
    parity checks.
    """
    label = (subcategory or "").strip()
    tags = {str(tag).strip().lower() for tag in secondary_tags}
    form = "unknown"
    if "loop" in tags or label.endswith(" Loop") or label == "Music Loop":
        form = "loop"
    elif "one-shot" in tags or label.endswith(" One-Shot"):
        form = "one-shot"
    elif "phrase" in label.lower():
        form = "phrase"
    elif "fill" in label.lower():
        form = "fill"

    identity = label
    suffixes = (" Loop", " One-Shot", " Phrase")
    for suffix in suffixes:
        if identity.endswith(suffix):
            identity = identity[: -len(suffix)]
            break
    if identity == "Music":
        identity = ""
    return identity, form


def from_legacy_taxonomy(*, content_id: str, source_path: str, category: str,
                         subcategory: str, secondary_tags: list[str],
                         confidence: float, winning_evidence: str,
                         taxonomy_version: int, classification_model_version: int,
                         measurements: dict[str, PhysicalMeasurement] | None = None,
                         metadata: dict[str, Any] | None = None) -> AudioEvidenceRecord:
    """Adapt the current flat product result into schema v1 without mutation."""
    identity, form = _legacy_identity_and_form(subcategory, secondary_tags)
    state = "predicted" if subcategory else "unknown"
    source = (winning_evidence or "unknown").lower()
    record = AudioEvidenceRecord(
        content_id=content_id,
        source_path=source_path,
        identity=EvidenceClaim(identity, confidence if identity else 0.0, source,
                               state if identity else "unknown"),
        family=EvidenceClaim(category, confidence if category else 0.0, source,
                             state if category else "unknown"),
        form=EvidenceClaim(form, confidence if form != "unknown" else 0.0,
                           source, state if form != "unknown" else "unknown"),
        attributes={
            tag: EvidenceClaim(tag, confidence, "legacy_secondary_tag", state)
            for tag in secondary_tags
            if tag.lower() not in {"loop", "one-shot"}
        },
        measurements=measurements or {},
        metadata=metadata or {},
        model_versions={
            "taxonomy": str(taxonomy_version),
            "classification": str(classification_model_version),
        },
        legacy={
            "category": category,
            "subcategory": subcategory,
            "secondary_tags": list(secondary_tags),
            "confidence": confidence,
            "winning_evidence": winning_evidence,
        },
    )
    record.validate()
    return record

