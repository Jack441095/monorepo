# R-07 STATIC RESULT — Paddle webhook/idempotency code review (2026-09-17)

Tests: `backend/tests/test_webhook_robustness_r07.py` (commit on `exec/r07-webhook-tests`).
Run: 4 passed + 1 xfailed, Postgres `nitedsp_test`, synthetic HMAC payloads, no secrets, no live calls.

## Proven working
- Duplicate delivery: two identical posts → `processed` then `already_processed`; exactly 1 Purchase + 1 Entitlement. The row-claim + FOR UPDATE + processed_at design holds (matches the documented 0/600 concurrency result).
- Missing event_id → 400 before any row claim. Tampered signature → 401/400. Unknown catalog → 200 `rejected_unknown_catalog_item` (no retry storm).
- Replay window (5d), UTF-8 enforcement, persisted processing errors, 200-vs-500 retry semantics: correct by code read (`commerce.py:99-130,342-476`).

## One real finding (P3, proven by the xfail)
- Signed-but-malformed JSON: `json.loads(raw_body)` (`commerce.py:359`) sits OUTSIDE any try → unhandled 500 → Paddle retries to exhaustion → event lost with no row (same bug class as the 2026-08-14 KeyError incident the handler comments describe).
- Likelihood LOW (Paddle always sends well-formed JSON); fix is 3 lines (try/except → 400). Prepared patch:
  ```python
  try:
      payload = json.loads(raw_body)
  except (ValueError, UnicodeDecodeError):
      raise HTTPException(status_code=400, detail="Invalid webhook payload") from None
  ```
  NOT applied: `commerce.py` has in-progress dirty work; apply on a clean tree and the xfail flips to xpass (non-strict, suite stays green either way).

## Remainder for the Claude live-fire session (needs sandbox secrets)
Duplicate/out-of-order/real-replay against sandbox, `transaction.updated` vs `completed` double-fulfil check, refund (`adjustment.*`) → entitlement revocation path (read but untested live), PII handling in stored payloads, unit economics per seat.
