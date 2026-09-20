"""Draft composers + confirmation-gated outbox (Phase 4 -- scoped writes).

Drafts are pure text from live data (prices, turnarounds, FAQ policies,
truth-sheet beta): composing invents nothing and sends nothing. Getting a
draft OUT of Thursday (into the founder-visible outbox queue) is the one
gated write here, and it requires a confirmation token (confirmation.py:
session+service+text bound, expiring) claimed exactly once
(action_receipts.py: single-use, replay returns the cached receipt,
cross-session replay raises ReceiptConflict).

Sending itself stays manual -- the founder sends from the outbox. This
module never touches network, email, or payment APIs.
"""

from __future__ import annotations

import json
import time

from thursday import action_receipts, confirmation
from thursday.redaction import get_logger as _get_redacting_logger
from thursday.runtime_paths import DATA_DIR

logger = _get_redacting_logger(__name__)

OUTBOX_SERVICE_ID = "outbox"
OUTBOX_FILE = DATA_DIR / "outbox.jsonl"


def _offerings() -> list[dict]:
    from thursday.ops import finance_ops
    return finance_ops.get_offerings()


def list_draft_kinds() -> list[str]:
    return ["quote", "review-request", "reminder"]


def quote_draft(service_query: str, client_name: str = "") -> str:
    """Fixed-price quote text for one live offering. Never sends."""
    offerings = _offerings()
    if not offerings:
        return ("QUOTE DRAFT — NOT SENT\n\nEvidence missing — could not read the real "
                "service price list (business/app/business_knowledge.json).")
    q = service_query.strip().lower()
    match = next((o for o in offerings
                  if q in str(o.get("id", "")).lower() or q in str(o.get("name", "")).lower()
                  or any(q in k.lower() for k in o.get("keywords", []))), None)
    if match is None:
        valid = ", ".join(o.get("id", "?") for o in offerings)
        return (f"QUOTE DRAFT — NOT SENT\n\nNo live offering matches {service_query!r}. "
                f"Valid services: {valid}. Nothing quoted, nothing sent.")
    from thursday.ops import finance_ops
    name = match.get("name", match.get("id", "service"))
    price = match.get("price_from_gbp")
    price_str = f"from £{price}" if price is not None else "price on application"
    greeting = f"Hi {client_name}," if client_name else "Hi,"
    return "\n".join([
        "QUOTE DRAFT — NOT SENT. Review and send manually.",
        "",
        f"{greeting}",
        "",
        f"Service: {name} — {price_str}.",
        f"Turnaround: {match.get('turnaround', 'to be confirmed')}.",
        *(f"- {item}" for item in match.get("includes", [])),
        "",
        "Payment: deposit or full payment agreed before final delivery files are released.",
        "Indicative guidance only — final quotes depend on track count, length, and deadline.",
        "",
        f"Source (read live): {finance_ops._business_knowledge_path()}",
    ])


def review_request_draft(service_name: str, client_name: str = "") -> str:
    """Review + referral ask per thursday-sops policy. Never sends."""
    greeting = f"Hi {client_name}," if client_name else "Hi,"
    return "\n".join([
        "REVIEW REQUEST DRAFT — NOT SENT. Review and send manually.",
        "",
        f"{greeting}",
        "",
        f"Thanks for choosing NITE DSP for {service_name}. Two quick favours:",
        "1. A one-line review I can quote (reply here is fine).",
        "2. One person who might need the same -- an intro beats any advert.",
        "",
        "Per sop policy: review + referral requested on every completed job.",
    ])


def reminder_draft(kind: str, ref: str = "") -> str:
    """Polite chase text (payment / stems / feedback). Never sends."""
    from thursday.ops import support_ops
    kind_low = kind.strip().lower()
    if kind_low not in ("payment", "stems", "feedback"):
        return ("REMINDER DRAFT — NOT SENT\n\nUnknown reminder kind "
                f"{kind!r}. Valid: payment, stems, feedback. Nothing drafted, nothing sent.")
    policy = ""
    if kind_low == "payment":
        policy = support_ops.faq_lookup("payment")
    elif kind_low == "stems":
        policy = support_ops.faq_lookup("stems")
    lines = [
        "REMINDER DRAFT — NOT SENT. Review and send manually.",
        "",
        f"Kind: {kind_low}" + (f" (ref: {ref})" if ref else ""),
        "Tone: polite, one nudge, assume good intent. No second chase without founder approval.",
        "",
        policy,
    ]
    return "\n".join(lines)


def parse_draft_command(text: str) -> tuple[str, str] | None:
    """Parse 'draft quote <service>' / 'draft review request [for <job>]' /
    'draft reminder <kind>'. Returns (kind, tail) or None if no match."""
    stripped = text.strip()
    lower = stripped.lower()
    for prefix in ("draft quote", "draft review request", "draft reminder"):
        if lower.startswith(prefix):
            tail = stripped[len(prefix):].strip(" :")
            kind = {"draft quote": "quote", "draft review request": "review-request",
                    "draft reminder": "reminder"}[prefix]
            return kind, tail
    return None


def queue_draft(kind: str, text: str, *, session_id: str, confirmation_token: str) -> dict:
    """Queue an approved draft to the outbox. Gated: needs a valid
    confirmation token for THIS session + exact text. Replay-safe: the
    second confirm of the same token returns the cached receipt without
    queueing twice; another session's token raises ReceiptConflict.
    Raises ValueError on bad/expired token (nothing queued)."""
    if kind not in list_draft_kinds():
        raise ValueError(f"unknown draft kind: {kind!r}")
    if not confirmation.verify_confirmation(
            confirmation_token, session_id=session_id,
            service_id=OUTBOX_SERVICE_ID, text=text):
        raise ValueError("Invalid or expired confirmation token — nothing queued.")
    receipt_id = action_receipts.receipt_id_for_token(confirmation_token)
    try:
        claim = action_receipts.claim_action(
            receipt_id, session_id=session_id, service_id=OUTBOX_SERVICE_ID, text=text)
    except action_receipts.ReceiptConflict as exc:
        raise ValueError(f"Token already used by a different session/request — refused: {exc}") from exc
    if not claim.claimed:
        existing = claim.receipt
        return {"ok": True, "replayed": True, "receipt_id": existing.receipt_id,
                "response": existing.response_text}
    try:
        OUTBOX_FILE.parent.mkdir(parents=True, exist_ok=True)
        with OUTBOX_FILE.open("a", encoding="utf-8") as f:
            f.write(json.dumps({"kind": kind, "text": text, "session_id": session_id,
                                "receipt_id": receipt_id, "queued_at": time.time()}) + "\n")
    except OSError as exc:
        logger.warning("draft_ops: outbox write failed: %s", exc)
        raise ValueError(f"Outbox write failed — nothing queued: {exc}") from exc
    response = f"Queued {kind} draft to outbox ({receipt_id}). Send manually -- Thursday never sends."
    action_receipts.complete_action(receipt_id, response_text=response)
    return {"ok": True, "replayed": False, "receipt_id": receipt_id, "response": response}


def read_outbox() -> list[dict]:
    """Founder-visible queued drafts. Read-only."""
    if not OUTBOX_FILE.exists():
        return []
    try:
        return [json.loads(line) for line in OUTBOX_FILE.read_text(encoding="utf-8").splitlines()
                if line.strip()]
    except (OSError, ValueError) as exc:
        logger.warning("draft_ops: could not read outbox: %s", exc)
        return []
