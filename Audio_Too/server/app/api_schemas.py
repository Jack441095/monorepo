"""Typed request schemas for stable Audio_Too API operations."""

from __future__ import annotations

import json
import re
from dataclasses import dataclass

import path_safety

MAX_GENRE_CHARS = 80
MAX_STYLE_PREFS_BYTES = 16 * 1024
MAX_REVISION_FEEDBACK_CHARS = 2_000
MAX_ADVISOR_FEEDBACK_REASON_CHARS = 1_000
MAX_CORRELATION_ID_CHARS = 200
EMAIL_RE = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")


class SchemaValidationError(ValueError):
    """A safe validation failure with machine-readable field details."""

    def __init__(self, field: str, message: str) -> None:
        super().__init__(message)
        self.field = field
        self.message = message

    @property
    def details(self) -> dict:
        return {"field": self.field, "reason": self.message}


def _project_id(payload: dict) -> str:
    try:
        return path_safety.validate_identifier(payload.get("project_id"), label="project ID")
    except ValueError as exc:
        raise SchemaValidationError("project_id", str(exc)) from exc


def _enquiry_id(payload: dict) -> str:
    try:
        return path_safety.validate_identifier(payload.get("id"), label="enquiry ID")
    except ValueError as exc:
        raise SchemaValidationError("id", str(exc)) from exc


def _draft_id(payload: dict) -> str:
    try:
        return path_safety.validate_identifier(payload.get("id"), label="draft ID")
    except ValueError as exc:
        raise SchemaValidationError("id", str(exc)) from exc


def _lead_id(payload: dict) -> str:
    try:
        return path_safety.validate_identifier(payload.get("id"), label="lead ID")
    except ValueError as exc:
        raise SchemaValidationError("id", str(exc)) from exc


def _reject_unknown(payload: dict, allowed: set[str]) -> None:
    unknown = sorted(set(payload) - allowed)
    if unknown:
        raise SchemaValidationError(
            unknown[0], f"Unknown request field: {unknown[0]}."
        )


@dataclass(frozen=True)
class AutomixStartRequest:
    project_id: str
    genre: str
    style_prefs: dict
    target_lufs: float | None = None
    correlation_id: str = ""

    @classmethod
    def from_payload(cls, payload: dict) -> AutomixStartRequest:
        _reject_unknown(
            payload, {"project_id", "genre", "style_prefs", "target_lufs", "correlation_id"}
        )
        project_id = _project_id(payload)
        genre = str(payload.get("genre", "pop")).strip() or "pop"
        if len(genre) > MAX_GENRE_CHARS:
            raise SchemaValidationError(
                "genre", f"genre must be {MAX_GENRE_CHARS} characters or fewer."
            )
        style_prefs = payload.get("style_prefs", {})
        if not isinstance(style_prefs, dict):
            raise SchemaValidationError("style_prefs", "style_prefs must be a JSON object.")
        encoded = json.dumps(style_prefs, ensure_ascii=True, separators=(",", ":")).encode()
        if len(encoded) > MAX_STYLE_PREFS_BYTES:
            raise SchemaValidationError(
                "style_prefs", "style_prefs exceeds the 16 KB encoded limit."
            )
        raw_lufs = payload.get("target_lufs")
        try:
            target_lufs = float(raw_lufs) if raw_lufs is not None else None
            if target_lufs is not None and not (-40.0 <= target_lufs <= 0.0):
                raise SchemaValidationError("target_lufs", "target_lufs must be between -40 and 0 LUFS.")
        except (TypeError, ValueError):
            target_lufs = None
        correlation_id = str(payload.get("correlation_id", "") or "").strip()
        if len(correlation_id) > MAX_CORRELATION_ID_CHARS:
            raise SchemaValidationError(
                "correlation_id",
                f"correlation_id must be {MAX_CORRELATION_ID_CHARS} characters or fewer.",
            )
        return cls(
            project_id=project_id,
            genre=genre,
            style_prefs=style_prefs,
            target_lufs=target_lufs,
            correlation_id=correlation_id,
        )


@dataclass(frozen=True)
class AutomixRevisionRequest:
    project_id: str
    feedback: str

    @classmethod
    def from_payload(cls, payload: dict) -> AutomixRevisionRequest:
        _reject_unknown(payload, {"project_id", "feedback"})
        project_id = _project_id(payload)
        feedback = str(payload.get("feedback", "")).strip()
        if not feedback:
            raise SchemaValidationError("feedback", "feedback is required.")
        if len(feedback) > MAX_REVISION_FEEDBACK_CHARS:
            raise SchemaValidationError(
                "feedback",
                f"feedback must be {MAX_REVISION_FEEDBACK_CHARS:,} characters or fewer.",
            )
        return cls(project_id=project_id, feedback=feedback)


@dataclass(frozen=True)
class AutomixAdvisorFeedbackRequest:
    job_id: str
    shadow_artifact_id: str
    operation_index: int
    decision: str
    usefulness_rating: int
    explanation_quality_rating: int
    audible_improvement_rating: int | None
    preview_artifact_id: str
    reason: str

    @classmethod
    def from_payload(cls, payload: dict) -> AutomixAdvisorFeedbackRequest:
        if not isinstance(payload, dict):
            raise SchemaValidationError("body", "Request body must be an object.")
        _reject_unknown(
            payload,
            {
                "job_id",
                "shadow_artifact_id",
                "operation_index",
                "decision",
                "usefulness_rating",
                "explanation_quality_rating",
                "audible_improvement_rating",
                "preview_artifact_id",
                "reason",
            },
        )
        try:
            job_id = path_safety.validate_identifier(payload.get("job_id"), label="job ID")
            shadow_artifact_id = path_safety.validate_identifier(
                payload.get("shadow_artifact_id"), label="shadow artifact ID"
            )
        except ValueError as exc:
            raise SchemaValidationError("lineage", str(exc)) from exc
        operation_index = payload.get("operation_index")
        if (
            isinstance(operation_index, bool)
            or not isinstance(operation_index, int)
            or operation_index < 0
        ):
            raise SchemaValidationError(
                "operation_index", "operation_index must be a non-negative integer."
            )
        decision = str(payload.get("decision", "")).strip().lower()
        if decision not in {"accepted", "rejected", "needs_work"}:
            raise SchemaValidationError(
                "decision", "decision must be accepted, rejected, or needs_work."
            )
        ratings = {}
        for field in ("usefulness_rating", "explanation_quality_rating"):
            value = payload.get(field)
            if isinstance(value, bool) or not isinstance(value, int) or not 1 <= value <= 5:
                raise SchemaValidationError(field, f"{field} must be an integer from 1 to 5.")
            ratings[field] = value
        audible = payload.get("audible_improvement_rating")
        if audible is not None and (
            isinstance(audible, bool)
            or not isinstance(audible, int)
            or not 1 <= audible <= 5
        ):
            raise SchemaValidationError(
                "audible_improvement_rating",
                "audible_improvement_rating must be null or an integer from 1 to 5.",
            )
        preview_id = str(payload.get("preview_artifact_id", "")).strip()
        if preview_id:
            try:
                preview_id = path_safety.validate_identifier(
                    preview_id, label="preview artifact ID"
                )
            except ValueError as exc:
                raise SchemaValidationError("preview_artifact_id", str(exc)) from exc
        reason = str(payload.get("reason", "")).strip()
        if len(reason) > MAX_ADVISOR_FEEDBACK_REASON_CHARS:
            raise SchemaValidationError(
                "reason",
                f"reason must be {MAX_ADVISOR_FEEDBACK_REASON_CHARS} characters or fewer.",
            )
        return cls(
            job_id=job_id,
            shadow_artifact_id=shadow_artifact_id,
            operation_index=operation_index,
            decision=decision,
            usefulness_rating=ratings["usefulness_rating"],
            explanation_quality_rating=ratings["explanation_quality_rating"],
            audible_improvement_rating=audible,
            preview_artifact_id=preview_id,
            reason=reason,
        )


@dataclass(frozen=True)
class EnquiryConversionRequest:
    enquiry_id: str

    @classmethod
    def from_payload(cls, payload: dict) -> EnquiryConversionRequest:
        _reject_unknown(payload, {"id"})
        return cls(enquiry_id=_enquiry_id(payload))


@dataclass(frozen=True)
class DraftSendRequest:
    draft_id: str

    @classmethod
    def from_payload(cls, payload: dict) -> DraftSendRequest:
        _reject_unknown(payload, {"id"})
        return cls(draft_id=_draft_id(payload))


@dataclass(frozen=True)
class DraftDeliveryRequest:
    draft_id: str
    recipient_email: str

    @classmethod
    def from_payload(cls, payload: dict) -> DraftDeliveryRequest:
        _reject_unknown(payload, {"id", "recipient_email"})
        draft_id = _draft_id(payload)
        recipient_email = str(payload.get("recipient_email", "")).strip().lower()
        if len(recipient_email) > 254 or not EMAIL_RE.fullmatch(recipient_email):
            raise SchemaValidationError(
                "recipient_email", "A valid recipient_email is required."
            )
        return cls(draft_id=draft_id, recipient_email=recipient_email)


MAX_DRAFT_SUBJECT_CHARS = 300
MAX_DRAFT_BODY_CHARS = 20_000
MAX_DRAFT_FIELD_CHARS = 254


@dataclass(frozen=True)
class DraftCreateRequest:
    type: str
    recipient: str
    subject: str
    body: str
    source: str

    @classmethod
    def from_payload(cls, payload: dict) -> DraftCreateRequest:
        _reject_unknown(payload, {"type", "recipient", "subject", "body", "source"})
        type_ = str(payload.get("type", "message")).strip() or "message"
        recipient = str(payload.get("recipient", "")).strip()
        subject = str(payload.get("subject", "")).strip()
        body = str(payload.get("body", ""))
        source = str(payload.get("source", "admin")).strip() or "admin"
        if len(type_) > MAX_DRAFT_FIELD_CHARS or len(source) > MAX_DRAFT_FIELD_CHARS:
            raise SchemaValidationError("type", "type/source is too long.")
        if len(recipient) > MAX_DRAFT_FIELD_CHARS:
            raise SchemaValidationError("recipient", "recipient is too long.")
        if len(subject) > MAX_DRAFT_SUBJECT_CHARS:
            raise SchemaValidationError(
                "subject", f"subject must be {MAX_DRAFT_SUBJECT_CHARS} characters or fewer."
            )
        if len(body) > MAX_DRAFT_BODY_CHARS:
            raise SchemaValidationError(
                "body", f"body must be {MAX_DRAFT_BODY_CHARS} characters or fewer."
            )
        return cls(type=type_, recipient=recipient, subject=subject, body=body, source=source)


@dataclass(frozen=True)
class LeadConversionRequest:
    lead_id: str

    @classmethod
    def from_payload(cls, payload: dict) -> LeadConversionRequest:
        _reject_unknown(payload, {"id"})
        return cls(lead_id=_lead_id(payload))
