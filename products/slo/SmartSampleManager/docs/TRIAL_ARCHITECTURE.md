# NITE DSP Trial Architecture (Design Only)

Phase 3, Sections 33-34. **Design document — no trial system is implemented.**

## Model: 14-day full-featured trial

Matches the master prompt's own recommendation and the existing licensing architecture's
established "grace period" pattern (`docs/PRODUCTION_LICENSING_ARCHITECTURE.md`'s 14-day offline
grace already uses the same duration, giving the client a single, consistent time-window concept
rather than two different magic numbers).

## Mechanics

```text
1. Customer downloads SmartSampleManager without an account (or with one, either
   works -- see "Anonymous trials" below)
2. First launch: client requests a trial token from the licensing service,
   scoped to this machine's ID
3. Server issues a trial-type LicenseToken (LicenseToken::tier = "trial",
   expiresAt = now + 14 days) -- reuses the EXISTING LicenseToken struct and
   Ed25519 verification path (Source/Licensing/LicenseTypes.h), no new
   client-side format
4. trials table (docs/NITE_DSP_DATABASE_SCHEMA.md) records this machine_id +
   product_id combination
5. Client behaves identically to a licensed copy for 14 days -- "full-featured"
   is not a marketing claim, it's the literal mechanism: the same LicenseToken
   verification path the client already has just sees a token with an expiry
   date instead of a perpetual one
6. On day 15, LicenseManager's existing expiry handling (already built --
   docs/LICENSING_PRODUCTION_GAP.md confirms the client already handles
   expiresAt correctly) surfaces the trial-ended state
```

**No new client-side licensing code is required.** The existing `LicenseToken`/`LicenseManager`
architecture already supports an expiring token — a trial is simply a token with `expiresAt` set
14 days out and `tier = "trial"`, issued without a `purchases` row. This is exactly why Phase
3/Section 17 insists on not rewriting the crypto: the existing design already generalizes to this
use case for free.

## What trial expiry must NEVER touch (Section 33)

The indexed sample library, SQLite cache database, user tags/taxonomy edits, application
settings, project state, and — obviously — the customer's own source audio files. **This is
already guaranteed by construction**: `docs/PLUGIN_STATE_ARCHITECTURE.md` and the SQLite cache
(`docs/DATABASE_HARDENING.md`) are entirely independent of licensing state — nothing in
`SampleManagerEngine`'s scan/cache/database code path reads or depends on `LicenseState` at all.
A trial ending changes what `LicenseManager::getState()` reports; it does not and cannot cascade
into deleting anything, because no code path connects the two. Purchasing later simply issues a
new (perpetual) token to the same installation — same database, same indexed library, same
everything, just a different `LicenseToken`.

## Anonymous trials

The `trials` table's `user_id` column is nullable specifically to support starting a trial
without requiring an account first — lower friction (Section 35's "optimise for low friction"
principle extends to the trial funnel, not just login). If the trial later converts to a
purchase, the checkout flow's email collection naturally creates/links the `users` row at that
point (`docs/NITE_DSP_ACCOUNT_ARCHITECTURE.md`'s "first login = signup" pattern).

## Trial abuse (Section 34)

**Reasonable resistance, not invasive fingerprinting** — the master prompt's own explicit
instruction. Mechanism: `trials` table's `UNIQUE (product_id, machine_id)` constraint
(`docs/NITE_DSP_DATABASE_SCHEMA.md`) — one trial per machine per product, using the same
`machine_id` the licensing client already generates for activation binding (no new
device-fingerprinting code needed, reuses existing infrastructure). This is trivially
circumventable by a determined user (wipe the machine ID file, reinstall) — accepted as a known,
reasonable limitation rather than building anything more invasive (hardware fingerprinting,
kernel-level checks) to close a gap that mostly matters for a minority of bad-faith users, not
the overwhelming majority of legitimate trial-then-purchase customers this system is actually
for.

## Status

**Design only.** No trial-issuance endpoint exists on the (also not-yet-deployed) licensing
service.
