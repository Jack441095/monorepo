"""Validation for the product-owned Mix Review local receipt contract."""

from __future__ import annotations

from typing import Any


SCHEMA = "kenn.mix_review.local_receipt.v2"
STATUSES = {"rejected", "failed", "completed"}


def receipt_errors(receipt: dict[str, Any]) -> list[str]:
    errors: list[str] = []
    if receipt.get("schema") != SCHEMA:
        errors.append("schema must be kenn.mix_review.local_receipt.v2")
    if receipt.get("status") not in STATUSES:
        errors.append("status must be rejected, failed, or completed")
    source = receipt.get("source")
    if not isinstance(source, dict) or not source.get("filename") or not source.get("sha256"):
        errors.append("source filename and sha256 are required")
    if receipt.get("audio_uploaded") is not False:
        errors.append("audio_uploaded must remain false")
    if receipt.get("external_network") is not False:
        errors.append("external_network must remain false")
    if receipt.get("storage") != "memory_only":
        errors.append("storage must remain memory_only")
    if not receipt.get("runtime_dir"):
        errors.append("runtime_dir is required")
    if receipt.get("status") == "completed" and not isinstance(receipt.get("analysis"), dict):
        errors.append("completed receipts require an analysis object")
    return errors
