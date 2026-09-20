# Beta Entitlement Flow

Phase 5, Sections 20-23. Real, implemented, verified this phase.

## Private beta ≠ purchase (Section 20)

Beta testers get a `beta` entitlement, never a fake `purchases` row. The schema already
separates the two (`docs/NITE_DSP_DATABASE_SCHEMA.md`); `admin.py`'s `issue_entitlement` creates
an `entitlements` row with `purchase_id = NULL` and `license_type = "beta"` -- no synthetic
purchase record is ever created for a beta grant.

## Workflow (Section 21)

```text
ADMIN (X-Admin-Key, fail-closed -- docs/SECURITY_MODEL.md)
  -> POST /admin/entitlements/issue {email, product_id, license_type: "beta", max_activations}
  -> user created if new
  -> beta entitlement created (90-day default expiry -- see below)
  -> invite email sent (license key + sign-in link + expiry date)
TESTER
  -> signs in via magic link at /account
  -> sees the entitlement, downloads via /downloads/latest (entitlement-gated)
  -> activates via /v1/activate with the license key
```

No payment step anywhere in this path.

## Entitlement metadata (Section 22)

Stored: `product_id`, `license_type` ("beta"), `created_at` (issued date), `expires_at`
(optional), `max_activations`. The admin audit log (`admin_audit_log`) records who issued it and
why (`reason` field, e.g. "beta for jack@example.com") -- deliberately just enough to trace the
grant, never free-text notes that could accumulate sensitive personal information beyond the
email address already required to create the account.

## Expiration (Section 23)

Default: **90 days** if the admin doesn't specify `expires_in_days` explicitly
(`admin.py`'s `DEFAULT_BETA_EXPIRY_DAYS`). Chosen to comfortably span a private-beta cycle
(feedback rounds, a couple of point releases) without needing manual renewal, while still being
a bounded grant rather than silently perpetual. An admin can always override with an explicit
value. The invite email states the expiry date plainly so a tester is never surprised by losing
access mid-cycle.

## Verified this phase

Live request: issuing a beta entitlement for a new email created the user, the entitlement (with
a real 90-day-out `expires_at`), and fired a real invite email via the console provider
containing the license key, sign-in link, and expiry date -- confirmed via direct log
inspection. The underlying activate/validate/revoke mechanics were already verified in Phase 4
(`docs/LICENSING_IMPLEMENTATION.md`) and are unchanged.
