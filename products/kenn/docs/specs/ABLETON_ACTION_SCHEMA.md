# KENN Ableton Action Schema

Intent schema: `kenn.ableton_intent.v1`.

The parser returns `mode`, `action`, `track`, `device`, `parameter`, `desired_value`, `relative`, `unit`, `confidence`, `missing_fields`, `ambiguity`, and `confirmation_required`. It is non-executable.

Proposal schema: `kenn.action_proposal.v1` or `kenn.batch_action_proposal.v1`. A proposal must include exact indices and names read from Live, current value, proposed value, valid range, unit, reason, evidence, confidence, risk, operation, timestamp/session context supplied by the caller, and a session fingerprint. Device parameter proposals require confirmation.

Execution receipt schema: `kenn.execution_receipt.v1` or `kenn.batch_execution_receipt.v1`. A successful receipt includes before/requested/readback values, verified=true, timestamp, exact target, and an undo payload. A sent-but-unverified write is a failure and is not reported as successful. Tokens are HMAC-bound to session, service, exact request, expiry, and nonce, then consumed once.
