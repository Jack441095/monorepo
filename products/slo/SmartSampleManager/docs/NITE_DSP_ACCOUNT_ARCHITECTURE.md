# NITE DSP Account Architecture (Design Only)

Phase 3, Sections 13, 35-37. **Design document — no account system is deployed.** A universal
NITE DSP Account, not a SmartSampleManager-specific one — see `docs/NITE_DSP_DATABASE_SCHEMA.md`
for the underlying `users`/`entitlements` tables this sits on top of.

## Authentication method

**Recommendation: passwordless magic link as the primary method, with email/password as a
fallback if customer feedback during beta shows real demand for it.**

Rationale (Section 35's "optimise for low friction, low support burden, secure account
recovery"):
- No password to forget → no "forgot password" support burden, which is disproportionately high
  for a small team's support load relative to a SaaS product with heavier daily usage.
- No password database to secure/hash — removes an entire class of security obligation for a
  small, low-traffic commercial site.
- A magic link email doubles as email-address verification for free.

The `users.password_hash` column in the database schema is nullable specifically so this can
launch passwordless-only without a later schema migration if password auth is added.

## Flow

```text
1. Customer enters email at /login
2. NITE DSP backend generates a short-lived, single-use signed token
3. Magic link emailed (see docs/PAYMENT_FLOW.md's transactional email provider)
4. Customer clicks link within the expiry window (recommend 15 minutes)
5. Backend verifies token, issues a session (secure HTTP-only cookie)
6. If no `users` row exists for that email yet, one is created at this point
   (first login = signup, no separate "create account" flow needed)
```

## Account security (Section 36)

- **Secure HTTP-only cookies** for session tokens — never accessible to client-side JS (XSS
  mitigation).
- **Session expiration** — reasonable default (e.g. 30 days sliding, common for low-friction
  consumer products), configurable server-side without a client update.
- **CSRF protection** — standard double-submit-cookie or same-site-cookie approach; framework-
  provided (Next.js/whatever server framework is chosen has this built in — not hand-rolled).
- **Rate limiting** on the magic-link-request endpoint — prevents email-bombing a victim's inbox
  and brute-force token guessing.
- **Email enumeration protection** — the "request a magic link" endpoint returns the same
  response whether or not the email exists (`"If an account exists, we've sent a link"`), so an
  attacker can't use it to discover which emails have NITE DSP accounts.
- **No password hashing needed for the passwordless-primary path** — if email/password is added
  later as a fallback, use a modern hash (argon2id or bcrypt), never anything weaker.

## Account UI (Section 37)

Deliberately minimal — Phase 3's own instruction: "do not build a giant SaaS dashboard."

```text
My Products
    Smart Sample Manager — Licensed (Perpetual)
        [Download]  [Manage Activations]

Downloads
    Smart Sample Manager v1.0.0 (macOS)

License
    License type: Perpetual
    Activations: 1 / 3 used

Activations
    MacBook Pro (activated 2026-08-12)  [Deactivate]

Purchases
    Smart Sample Manager — £59.00 — 2026-08-12  [Receipt]

Account
    Email: jack@example.com
    [Change email] [Delete account]
```

Every section here maps directly to a table in `docs/NITE_DSP_DATABASE_SCHEMA.md` — no UI
surface exists without a corresponding, already-designed data source.

## Multi-product readiness

Adding a second NITE DSP product later means "My Products" shows a second entry — no auth
change, no session change, no new account-system code. This is the entire point of the
`entitlements`/`products` schema design: the account layer only ever queries "what does this
user have entitlements for," never anything product-specific.

## What this document does NOT decide

- The specific session/JWT library or framework — an implementation detail for whichever web
  framework `docs/NITE_DSP_WEBSITE_ARCHITECTURE.md` settles on, not an architecture question.
- Social login (Google/Apple sign-in) — not requested by the master prompt, adds real complexity
  (OAuth provider registration, additional attack surface) for uncertain benefit at this scale;
  revisit if beta feedback asks for it.

## Status

**Design only.** No authentication service, no session store, no deployed account UI exists.
