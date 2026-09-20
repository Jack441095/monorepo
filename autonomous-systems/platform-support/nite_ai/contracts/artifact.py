"""Generic artifact references. Metadata only — never embedded blobs."""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum

from nite_ai._serialization import dataclass_to_dict, json_schema_for
from nite_ai.contracts.evidence import _validate_id
from nite_ai.errors import ValidationError


class ArtifactKind(str, Enum):
    FILE = "file"
    REPORT = "report"
    AUDIO_ANALYSIS = "audio_analysis"
    IMAGE = "image"
    JSON_RESULT = "json_result"
    MODEL_OUTPUT = "model_output"


@dataclass(frozen=True)
class ArtifactRef:
    """A reference to an artifact stored out-of-band (file/object store/etc.)."""

    artifact_id: str
    kind: ArtifactKind
    uri: str                      # file path, object-store key, or other URI — not a blob
    media_type: str = ""          # e.g. "application/json", "audio/wav"
    byte_size: int | None = None
    sha256: str | None = None
    metadata: dict = field(default_factory=dict)

    def __post_init__(self) -> None:
        _validate_id(self.artifact_id, "ArtifactRef.artifact_id")
        if not self.uri:
            raise ValidationError("ArtifactRef.uri must not be empty")
        if self.byte_size is not None and self.byte_size < 0:
            raise ValidationError("ArtifactRef.byte_size must be non-negative")
        if len(self.metadata) > 64:
            raise ValidationError("ArtifactRef.metadata is limited to 64 keys")

    def to_dict(self) -> dict:
        return dataclass_to_dict(self)


def artifact_ref_json_schema() -> dict:
    return json_schema_for(ArtifactRef)


__all__ = ["ArtifactKind", "ArtifactRef"]
