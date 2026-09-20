# Auth Implementation

Phase 4 Milestone B. Passwordless magic-link auth, per `docs/NITE_DSP_ACCOUNT_ARCHITECTURE.md`.
Implementation: `nitedsp/backend/app/auth.py`, `security.py`, `email.py`.

## Flow

1. `POST /auth/request-link {email}` -- generates a random token (`secrets.token_urlsafe(32)`),
   stores only its SHA-256 hash in `magic_link_tokens` (never the raw token), "sends" a link
   containing the raw token via `email.send_email` (console-logged locally, since no
   transactional email account exists yet).
2. `POST /auth/verify {token}` -- looks up by hash, checks `used_at IS NULL` and `expires_at`
   (15 min TTL), marks used, creates the `users` row if new, sets a signed session cookie
   (`itsdangerous.URLSafeTimedSerializer`, 30-day max age, `HttpOnly`, `SameSite=Lax`, `Secure`
   only in production).
3. `GET /auth/me` / `GET /auth/entitlements` -- session-cookie-gated.
4. `POST /auth/logout` -- clears the cookie.

## Verified this session

Live HTTP requests confirmed: link request → real DB row with hashed token → verify creates a
real user + sets a real signed cookie → `/auth/me` succeeds with the cookie, returns 401 without
it → replaying the same token returns "Token already used" (400). Automated in
`tests/test_e2e.py`.

## Correction found and fixed during implementation

`get_current_user`'s FastAPI dependency initially declared `session_cookie` as a plain function
parameter, which FastAPI would have bound as a query parameter rather than reading the actual
cookie. Fixed to use `fastapi.Cookie(alias=SESSION_COOKIE_NAME)` before this was ever exercised
against a real request -- caught by re-reading the dependency signature against FastAPI's cookie
docs, not by a failed test.
