# Thursday Execution Lease Policy V1

This document defines the lease verification rules that govern sandbox write operations.

## 1. Confinement Validation
Lease checks block:
- **Path Traversal Escape**: Any relative directory references (`..`) or paths that evaluate outside the allowed path bounds.
- **SHA Mismatch**: Writes are rejected if the checkout HEAD SHA changes after lease issuance, marking the result `STALE_RESULT`.
- **Expired/Stale Leases**: Attempting write operations after the lease lifetime expires.

## 2. Global Execution Lock
If `EXECUTION_MODE = SHADOW` or if the lease ID does not map to a registered active task, all write requests fail closed immediately.
