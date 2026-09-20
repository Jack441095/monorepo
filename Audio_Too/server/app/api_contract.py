"""Versioned API compatibility map and OpenAPI document."""

from __future__ import annotations

from urllib.parse import urlsplit, urlunsplit

API_VERSION = "1.3.0"
LEGACY_API_SUNSET = "Thu, 01 Jan 2027 00:00:00 GMT"

VERSIONED_ALIASES = {
    ("GET", "/api/v1/automix/jobs"): "/api/automix/status",
    ("GET", "/api/v1/automix/queue-health"): "/api/automix/queue-health",
    ("GET", "/api/v1/business/draft-deliveries"): "/api/admin/draft-deliveries/status",
    ("POST", "/api/v1/automix/jobs"): "/api/automix/start",
    ("POST", "/api/v1/automix/revisions"): "/api/automix/revise",
    ("POST", "/api/v1/automix/uploads"): "/api/automix/upload",
    ("POST", "/api/v1/automix/advisor-feedback"): "/api/automix/advisor-feedback",
    ("POST", "/api/v1/automix/advisor-feedback/deletions"): "/api/automix/advisor-feedback/delete",
    ("POST", "/api/v1/automix/musical-role-corrections/deletions"): "/api/automix/musical-role-corrections/delete",
    ("POST", "/api/v1/business/enquiries/conversions"): "/api/admin/enquiries/convert",
    ("POST", "/api/v1/business/leads/conversions"): "/api/admin/leads/convert",
    ("POST", "/api/v1/business/drafts/sends"): "/api/admin/drafts/send",
    ("POST", "/api/v1/business/draft-deliveries"): "/api/admin/draft-deliveries",
}
LEGACY_SUCCESSORS = {
    ("GET", "/api/automix/status"): "/api/v1/automix/jobs",
    ("GET", "/api/automix/queue-health"): "/api/v1/automix/queue-health",
    ("GET", "/api/admin/draft-deliveries/status"): "/api/v1/business/draft-deliveries",
    ("POST", "/api/automix/start"): "/api/v1/automix/jobs",
    ("POST", "/api/automix/revise"): "/api/v1/automix/revisions",
    ("POST", "/api/automix/upload"): "/api/v1/automix/uploads",
    ("POST", "/api/automix/advisor-feedback"): "/api/v1/automix/advisor-feedback",
    ("POST", "/api/automix/advisor-feedback/delete"): "/api/v1/automix/advisor-feedback/deletions",
    ("POST", "/api/automix/musical-role-corrections/delete"): "/api/v1/automix/musical-role-corrections/deletions",
    ("POST", "/api/admin/enquiries/convert"): "/api/v1/business/enquiries/conversions",
    ("POST", "/api/admin/leads/convert"): "/api/v1/business/leads/conversions",
    ("POST", "/api/admin/drafts/send"): "/api/v1/business/drafts/sends",
    ("POST", "/api/admin/draft-deliveries"): "/api/v1/business/draft-deliveries",
}


def dispatch_path(method: str, full_path: str) -> str:
    """Map a versioned path to its tested legacy implementation, preserving query data."""
    parsed = urlsplit(full_path)
    target = VERSIONED_ALIASES.get((method.upper(), parsed.path))
    if not target:
        return full_path
    return urlunsplit((parsed.scheme, parsed.netloc, target, parsed.query, parsed.fragment))


def legacy_successor(method: str, path: str) -> str:
    return LEGACY_SUCCESSORS.get((method.upper(), path), "")


def openapi_document() -> dict:
    error_schema = {
        "type": "object",
        "required": ["error", "code", "message", "details", "request_id"],
        "properties": {
            "error": {"type": "string", "deprecated": True},
            "code": {"type": "string"},
            "message": {"type": "string"},
            "details": {"type": "object", "additionalProperties": True},
            "request_id": {"type": "string"},
        },
    }
    job_response = {
        "type": "object",
        "required": ["ok", "job_id", "status"],
        "properties": {
            "ok": {"type": "boolean"},
            "job_id": {"type": "string"},
            "status": {"type": "string"},
            "source_readiness": {
                "type": "object",
                "properties": {
                    "file_count": {"type": "integer", "minimum": 1},
                    "total_bytes": {"type": "integer", "minimum": 1},
                },
            },
        },
    }
    enquiry_record = {
        "type": "object",
        "additionalProperties": True,
        "properties": {"id": {"type": "string"}},
    }
    enquiry_conversion_response = {
        "type": "object",
        "required": [
            "ok",
            "enquiry",
            "client",
            "project",
            "lead",
            "already_converted",
        ],
        "properties": {
            "ok": {"type": "boolean", "const": True},
            "enquiry": enquiry_record,
            "client": {"oneOf": [enquiry_record, {"type": "null"}]},
            "project": {"oneOf": [enquiry_record, {"type": "null"}]},
            "lead": {"oneOf": [enquiry_record, {"type": "null"}]},
            "already_converted": {"type": "boolean"},
        },
    }
    lead_conversion_response = {
        "type": "object",
        "required": ["ok", "lead", "client", "project", "already_converted"],
        "properties": {
            "ok": {"type": "boolean", "const": True},
            "lead": enquiry_record,
            "client": {"oneOf": [enquiry_record, {"type": "null"}]},
            "project": {"oneOf": [enquiry_record, {"type": "null"}]},
            "already_converted": {"type": "boolean"},
        },
    }
    draft_send_response = {
        "type": "object",
        "required": ["ok", "draft", "followup", "already_sent"],
        "properties": {
            "ok": {"type": "boolean", "const": True},
            "draft": enquiry_record,
            "followup": {"oneOf": [enquiry_record, {"type": "null"}]},
            "already_sent": {"type": "boolean"},
        },
    }
    delivery_record = {
        "type": "object",
        "required": ["id", "recipient", "subject", "status", "attempts"],
        "additionalProperties": True,
        "properties": {
            "id": {"type": "string"},
            "recipient": {"type": "string", "format": "email"},
            "subject": {"type": "string"},
            "status": {
                "type": "string",
                "enum": ["queued", "claimed", "sending", "sent", "uncertain"],
            },
            "attempts": {"type": "integer", "minimum": 0},
            "provider_receipt": {"oneOf": [{"type": "string"}, {"type": "null"}]},
        },
    }
    return {
        "openapi": "3.1.0",
        "info": {
            "title": "Audio_Too Local API",
            "version": API_VERSION,
            "description": "Authenticated local API contract. Legacy routes remain additive aliases until the documented sunset date.",
        },
        "paths": {
            "/api/v1/automix/advisor-previews/{artifact_id}": {
                "get": {
                    "summary": "Stream an integrity-checked advisor A/B preview WAV",
                    "parameters": [
                        {
                            "name": "artifact_id",
                            "in": "path",
                            "required": True,
                            "schema": {"type": "string", "minLength": 1},
                        }
                    ],
                    "responses": {
                        "200": {
                            "description": "Baseline or candidate preview WAV",
                            "content": {"audio/wav": {}},
                        },
                        "404": {"description": "Preview not found"},
                        "409": {"description": "Artifact integrity failure"},
                    },
                }
            },
            "/api/v1/automix/advisor-feedback": {
                "post": {
                    "summary": "Review one lineaged AutoMix advisor shadow operation",
                    "security": [{"dashboardSession": [], "csrfToken": []}],
                    "requestBody": {
                        "required": True,
                        "content": {
                            "application/json": {
                                "schema": {
                                    "$ref": "#/components/schemas/AutomixAdvisorFeedbackRequest"
                                }
                            }
                        },
                    },
                    "responses": {
                        "201": {"description": "Feedback recorded"},
                        "4XX": {
                            "description": "Validation or lineage error",
                            "content": {
                                "application/json": {
                                    "schema": {"$ref": "#/components/schemas/ApiError"}
                                }
                            },
                        },
                    },
                }
            },
            "/api/v1/automix/advisor-feedback/deletions": {
                "post": {
                    "summary": "Delete one AutoMix advisor feedback record",
                    "security": [{"dashboardSession": [], "csrfToken": []}],
                    "requestBody": {
                        "required": True,
                        "content": {
                            "application/json": {
                                "schema": {
                                    "type": "object",
                                    "required": ["feedback_id"],
                                    "additionalProperties": False,
                                    "properties": {"feedback_id": {"type": "string"}},
                                }
                            }
                        },
                    },
                    "responses": {
                        "200": {"description": "Feedback deleted"},
                        "404": {"description": "Feedback not found"},
                    },
                }
            },
            "/api/v1/automix/musical-role-corrections/deletions": {
                "post": {
                    "summary": "Delete a project's reviewed musical-role corrections",
                    "security": [{"dashboardSession": [], "csrfToken": []}],
                    "requestBody": {
                        "required": True,
                        "content": {
                            "application/json": {
                                "schema": {
                                    "type": "object",
                                    "required": ["project_id"],
                                    "additionalProperties": False,
                                    "properties": {"project_id": {"type": "string"}},
                                }
                            }
                        },
                    },
                    "responses": {"200": {"description": "Correction evidence deleted"}},
                }
            },
            "/api/v1/automix/jobs": {
                "get": {
                    "summary": "Get an Automix job",
                    "parameters": [
                        {
                            "name": "id",
                            "in": "query",
                            "required": True,
                            "schema": {"type": "string", "pattern": "^[A-Za-z0-9][A-Za-z0-9_-]{0,63}$"},
                        }
                    ],
                    "responses": {
                        "200": {"description": "Job and immutable status history"},
                        "4XX": {"description": "Request error", "content": {"application/json": {"schema": {"$ref": "#/components/schemas/ApiError"}}}},
                    },
                },
                "post": {
                    "summary": "Queue an Automix job",
                    "security": [{"dashboardSession": [], "csrfToken": []}],
                    "parameters": [
                        {
                            "name": "Idempotency-Key",
                            "in": "header",
                            "required": False,
                            "schema": {"type": "string", "maxLength": 128},
                        }
                    ],
                    "requestBody": {
                        "required": True,
                        "content": {"application/json": {"schema": {"$ref": "#/components/schemas/AutomixStartRequest"}}},
                    },
                    "responses": {
                        "200": {"description": "Job queued", "content": {"application/json": {"schema": job_response}}},
                        "4XX": {"description": "Request error", "content": {"application/json": {"schema": {"$ref": "#/components/schemas/ApiError"}}}},
                    },
                },
            },
            "/api/v1/automix/queue-health": {
                "get": {
                    "summary": "Audit active Automix jobs and source readiness",
                    "responses": {
                        "200": {
                            "description": "Read-only queue health report",
                            "content": {
                                "application/json": {
                                    "schema": {
                                        "type": "object",
                                        "required": ["active_jobs", "ready_jobs", "blocked_jobs", "jobs"],
                                        "properties": {
                                            "active_jobs": {"type": "integer", "minimum": 0},
                                            "ready_jobs": {"type": "integer", "minimum": 0},
                                            "blocked_jobs": {"type": "integer", "minimum": 0},
                                            "jobs": {"type": "array", "items": {"type": "object"}},
                                        },
                                    }
                                }
                            },
                        }
                    },
                }
            },
            "/api/v1/automix/revisions": {
                "post": {
                    "summary": "Queue a revision of the latest completed mix",
                    "security": [{"dashboardSession": [], "csrfToken": []}],
                    "parameters": [
                        {
                            "name": "Idempotency-Key",
                            "in": "header",
                            "required": False,
                            "schema": {"type": "string", "maxLength": 128},
                        }
                    ],
                    "requestBody": {
                        "required": True,
                        "content": {"application/json": {"schema": {"$ref": "#/components/schemas/AutomixRevisionRequest"}}},
                    },
                    "responses": {
                        "200": {"description": "Revision queued", "content": {"application/json": {"schema": job_response}}},
                        "4XX": {"description": "Request error", "content": {"application/json": {"schema": {"$ref": "#/components/schemas/ApiError"}}}},
                    },
                }
            },
            "/api/v1/automix/uploads": {
                "post": {
                    "summary": "Store one validated Automix stem or archive",
                    "security": [{"dashboardSession": [], "csrfToken": []}],
                    "parameters": [
                        {
                            "name": "Idempotency-Key",
                            "in": "header",
                            "required": False,
                            "schema": {"type": "string", "maxLength": 128},
                        }
                    ],
                    "requestBody": {
                        "required": True,
                        "content": {
                            "multipart/form-data": {
                                "schema": {
                                    "type": "object",
                                    "required": ["project_id", "file"],
                                    "properties": {
                                        "project_id": {
                                            "type": "string",
                                            "pattern": "^[A-Za-z0-9][A-Za-z0-9_-]{0,63}$",
                                        },
                                        "file": {"type": "string", "format": "binary"},
                                        "email": {
                                            "type": "string",
                                            "format": "email",
                                            "maxLength": 254,
                                        },
                                    },
                                }
                            }
                        },
                    },
                    "responses": {
                        "200": {
                            "description": "Upload finalized or keyed retry replayed"
                        },
                        "4XX": {
                            "description": "Request error",
                            "content": {
                                "application/json": {
                                    "schema": {"$ref": "#/components/schemas/ApiError"}
                                }
                            },
                        },
                    },
                }
            },
            "/api/v1/business/enquiries/conversions": {
                "post": {
                    "summary": "Convert an enquiry into CRM records",
                    "security": [{"dashboardSession": [], "csrfToken": []}],
                    "parameters": [
                        {
                            "name": "Idempotency-Key",
                            "in": "header",
                            "required": False,
                            "schema": {"type": "string", "maxLength": 128},
                        }
                    ],
                    "requestBody": {
                        "required": True,
                        "content": {
                            "application/json": {
                                "schema": {
                                    "$ref": "#/components/schemas/EnquiryConversionRequest"
                                }
                            }
                        },
                    },
                    "responses": {
                        "200": {
                            "description": "Enquiry converted or previously converted",
                            "content": {
                                "application/json": {
                                    "schema": enquiry_conversion_response
                                }
                            },
                        },
                        "4XX": {
                            "description": "Request error",
                            "content": {
                                "application/json": {
                                    "schema": {"$ref": "#/components/schemas/ApiError"}
                                }
                            },
                        },
                    },
                }
            },
            "/api/v1/business/leads/conversions": {
                "post": {
                    "summary": "Convert a qualified lead into client and project records",
                    "security": [{"dashboardSession": [], "csrfToken": []}],
                    "parameters": [
                        {
                            "name": "Idempotency-Key",
                            "in": "header",
                            "required": False,
                            "schema": {"type": "string", "maxLength": 128},
                        }
                    ],
                    "requestBody": {
                        "required": True,
                        "content": {
                            "application/json": {
                                "schema": {
                                    "$ref": "#/components/schemas/LeadConversionRequest"
                                }
                            }
                        },
                    },
                    "responses": {
                        "200": {
                            "description": "Lead converted or previously converted",
                            "content": {
                                "application/json": {
                                    "schema": lead_conversion_response
                                }
                            },
                        },
                        "4XX": {
                            "description": "Request error",
                            "content": {
                                "application/json": {
                                    "schema": {"$ref": "#/components/schemas/ApiError"}
                                }
                            },
                        },
                    },
                }
            },
            "/api/v1/business/drafts/sends": {
                "post": {
                    "summary": "Mark a draft sent and schedule its follow-up",
                    "security": [{"dashboardSession": [], "csrfToken": []}],
                    "parameters": [
                        {
                            "name": "Idempotency-Key",
                            "in": "header",
                            "required": False,
                            "schema": {"type": "string", "maxLength": 128},
                        }
                    ],
                    "requestBody": {
                        "required": True,
                        "content": {
                            "application/json": {
                                "schema": {"$ref": "#/components/schemas/DraftSendRequest"}
                            }
                        },
                    },
                    "responses": {
                        "200": {
                            "description": "Draft sent or previously sent",
                            "content": {
                                "application/json": {"schema": draft_send_response}
                            },
                        },
                        "4XX": {
                            "description": "Request error",
                            "content": {
                                "application/json": {
                                    "schema": {"$ref": "#/components/schemas/ApiError"}
                                }
                            },
                        },
                    },
                }
            },
            "/api/v1/business/draft-deliveries": {
                "get": {
                    "summary": "Read external draft-delivery state and receipt",
                    "parameters": [
                        {
                            "name": "id",
                            "in": "query",
                            "required": True,
                            "schema": {
                                "type": "string",
                                "pattern": "^[A-Za-z0-9][A-Za-z0-9_-]{0,63}$",
                            },
                        }
                    ],
                    "responses": {
                        "200": {
                            "description": "Delivery state",
                            "content": {
                                "application/json": {
                                    "schema": {
                                        "type": "object",
                                        "required": ["ok", "delivery"],
                                        "properties": {
                                            "ok": {"type": "boolean", "const": True},
                                            "delivery": delivery_record,
                                        },
                                    }
                                }
                            },
                        },
                        "4XX": {
                            "description": "Request error",
                            "content": {
                                "application/json": {
                                    "schema": {"$ref": "#/components/schemas/ApiError"}
                                }
                            },
                        },
                    },
                },
                "post": {
                    "summary": "Queue an approved draft for external email delivery",
                    "security": [{"dashboardSession": [], "csrfToken": []}],
                    "parameters": [
                        {
                            "name": "Idempotency-Key",
                            "in": "header",
                            "required": False,
                            "schema": {"type": "string", "maxLength": 128},
                        }
                    ],
                    "requestBody": {
                        "required": True,
                        "content": {
                            "application/json": {
                                "schema": {
                                    "$ref": "#/components/schemas/DraftDeliveryRequest"
                                }
                            }
                        },
                    },
                    "responses": {
                        "202": {
                            "description": "Delivery queued",
                            "content": {
                                "application/json": {
                                    "schema": {
                                        "type": "object",
                                        "required": ["ok", "delivery", "already_queued"],
                                        "properties": {
                                            "ok": {"type": "boolean", "const": True},
                                            "delivery": delivery_record,
                                            "already_queued": {"type": "boolean"},
                                        },
                                    }
                                }
                            },
                        },
                        "4XX": {
                            "description": "Request error",
                            "content": {
                                "application/json": {
                                    "schema": {"$ref": "#/components/schemas/ApiError"}
                                }
                            },
                        },
                    },
                },
            },
        },
        "components": {
            "securitySchemes": {
                "dashboardSession": {"type": "apiKey", "in": "cookie", "name": "audio_too_session"},
                "csrfToken": {"type": "apiKey", "in": "header", "name": "X-CSRF-Token"},
            },
            "schemas": {
                "ApiError": error_schema,
                "AutomixStartRequest": {
                    "type": "object",
                    "required": ["project_id"],
                    "additionalProperties": False,
                    "properties": {
                        "project_id": {"type": "string", "pattern": "^[A-Za-z0-9][A-Za-z0-9_-]{0,63}$"},
                        "genre": {"type": "string", "maxLength": 80, "default": "pop"},
                        "style_prefs": {"type": "object", "additionalProperties": True},
                    },
                },
                "AutomixRevisionRequest": {
                    "type": "object",
                    "required": ["project_id", "feedback"],
                    "additionalProperties": False,
                    "properties": {
                        "project_id": {"type": "string", "pattern": "^[A-Za-z0-9][A-Za-z0-9_-]{0,63}$"},
                        "feedback": {"type": "string", "minLength": 1, "maxLength": 2000},
                    },
                },
                "AutomixAdvisorFeedbackRequest": {
                    "type": "object",
                    "required": [
                        "job_id",
                        "shadow_artifact_id",
                        "operation_index",
                        "decision",
                        "usefulness_rating",
                        "explanation_quality_rating"
                    ],
                    "additionalProperties": False,
                    "properties": {
                        "job_id": {"type": "string", "minLength": 1},
                        "shadow_artifact_id": {"type": "string", "minLength": 1},
                        "operation_index": {"type": "integer", "minimum": 0},
                        "decision": {
                            "type": "string",
                            "enum": ["accepted", "rejected", "needs_work"]
                        },
                        "usefulness_rating": {"type": "integer", "minimum": 1, "maximum": 5},
                        "explanation_quality_rating": {
                            "type": "integer",
                            "minimum": 1,
                            "maximum": 5
                        },
                        "audible_improvement_rating": {
                            "oneOf": [
                                {"type": "integer", "minimum": 1, "maximum": 5},
                                {"type": "null"}
                            ]
                        },
                        "preview_artifact_id": {"type": "string"},
                        "reason": {"type": "string", "maxLength": 1000}
                    }
                },
                "EnquiryConversionRequest": {
                    "type": "object",
                    "required": ["id"],
                    "additionalProperties": False,
                    "properties": {
                        "id": {
                            "type": "string",
                            "pattern": "^[A-Za-z0-9][A-Za-z0-9_-]{0,63}$",
                        }
                    },
                },
                "LeadConversionRequest": {
                    "type": "object",
                    "required": ["id"],
                    "additionalProperties": False,
                    "properties": {
                        "id": {
                            "type": "string",
                            "pattern": "^[A-Za-z0-9][A-Za-z0-9_-]{0,63}$",
                        }
                    },
                },
                "DraftSendRequest": {
                    "type": "object",
                    "required": ["id"],
                    "additionalProperties": False,
                    "properties": {
                        "id": {
                            "type": "string",
                            "pattern": "^[A-Za-z0-9][A-Za-z0-9_-]{0,63}$",
                        }
                    },
                },
                "DraftDeliveryRequest": {
                    "type": "object",
                    "required": ["id", "recipient_email"],
                    "additionalProperties": False,
                    "properties": {
                        "id": {
                            "type": "string",
                            "pattern": "^[A-Za-z0-9][A-Za-z0-9_-]{0,63}$",
                        },
                        "recipient_email": {
                            "type": "string",
                            "format": "email",
                            "maxLength": 254,
                        },
                    },
                },
            },
        },
        "security": [{"dashboardSession": []}],
    }
