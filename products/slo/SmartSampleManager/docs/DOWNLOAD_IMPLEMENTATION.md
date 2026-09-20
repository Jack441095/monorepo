# Download Implementation

Phase 4 Milestone F. Implementation: `nitedsp/backend/app/downloads.py`.

## Design

- `GET /downloads/latest?product_id&platform&architecture&channel` -- requires an authenticated
  session AND an active entitlement for the requested product (Section 52's "no download without
  entitlement"). Returns a short-lived (15 min) signed download token
  (`itsdangerous.URLSafeTimedSerializer`, separate salt from the session cookie), not a permanent
  public URL.
- `GET /downloads/fetch?token=...` -- decodes and time-checks the token, streams the file from
  `mock_storage/` (stands in for real object storage during staging -- `config.py`'s
  `mock_storage_dir`), and records a `downloads` row.

`mock_storage/` never contains real SmartSampleManager build artifacts under the NITE DSP name --
the identity has not been approved (`docs/NITE_DSP_PRODUCT_IDENTITY.md`), so the one release row
seeded for testing points at a placeholder text file, explicitly labeled as such, created solely
to exercise the download mechanics (entitlement gating, signed-URL expiry, checksum field,
download logging).

## Verified this session

Confirmed via live HTTP requests: a user with an active entitlement can request and successfully
fetch the placeholder release; a user without one gets 403 at `/downloads/latest`; a tampered
token is rejected at `/downloads/fetch`; a `downloads` row was recorded with the correct
`release_id`/`user_id`, confirmed via `psql`. A missing-release case (`platform=windows`, which
has no seeded row) correctly returns 404. All of the above is also automated in
`tests/test_e2e.py`.
