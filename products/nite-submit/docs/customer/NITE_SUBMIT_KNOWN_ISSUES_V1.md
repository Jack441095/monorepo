# NITE Submit — Known Issues (0.2.0 Private Beta RC1)

**Product version:** 0.2.0 (Private Beta RC1)
**Audience:** Customers, beta testers, support staff
**Last reviewed:** 2026-08-25
**Update rule:** Re-issued with every release. Items move to "Fixed" only with a dated receipt. This page is public-safe; internal severity detail stays in product docs.

---

## Status labels

**Accepted** — known, not yet fixed · **Mitigated** — workaround available · **By design** — documented scope limit · **Fixed in this build** — resolved with receipt.

## By design (scope limits — read before reporting)

| # | Item | Guidance |
|---|---|---|
| D-1 | macOS 13+, Apple Silicon only | No Windows/Linux/Intel builds in this release |
| D-2 | Handwriting not recognised | Type fields manually |
| D-3 | OCR is bounded to the first few pages of scanned PDFs and capped at review-level confidence | Treat OCR output as a draft to check |
| D-4 | Presets are generic editable starting points; no official university rule database | Enter your department's rule as a template |
| D-5 | No batch workflow inside the app window | Use `nitesubmit-cli batch` with dry-run + approval manifest |
| D-6 | App never submits work or transmits documents | Preparation only, local only |

## Accepted / mitigated

| # | Item | Status | Workaround |
|---|---|---|---|
| K-1 | Beta build is ad-hoc signed; Gatekeeper requires right-click → Open on first launch | Mitigated | See Troubleshooting §Installation; Developer ID signing + notarisation planned before public launch (tracker S-05/S-06) |
| K-2 | Real-document validation still in progress for some field types (student-ID/module-code formats) | Accepted | Approval gate keeps every finding subject to your check; report wrong findings to improve detectors |
| K-3 | Complex multi-column or poster-style covers may produce ? Check fields needing manual picks | Accepted | Use… menu alternatives; edit directly |
| K-4 | Password-protected PDFs unreadable until decrypted locally | Mitigated | Export unencrypted copy via Preview first |
| K-5 | Session undo limited to current window lifetime | Accepted | Rename Original carefully; Create Renamed Copy default avoids the need |

## Regression protection note

Confirmed layout patterns that previously produced unsafe filenames (group cover pages, licence-text wrappers, split titles, supervisor lines) are protected by regression tests and remain capped at medium confidence requiring approval — see `products/nite-submit/docs/NITE_SUBMIT_CONFIRMED_REGRESSIONS_V1.md`.

## Fixed in this build

- Required missing fields now expose an editable entry prompt, refresh their
  confidence state after manual input, and re-open the approval path only when
  the completed template is valid. Verified in the packaged runtime QA and the
  deterministic manual-name regression checks.
- Rename-original operations now keep the active document path and preserve
  undo after a collision is resolved with a numbered filename. Covered by the
  deterministic file-operation regression checks.
- Rename verification now attempts to restore the original path if destination
  hashing fails before the operation is reported as unsuccessful.
- Failed verification of a newly installed copy now removes that unverified
  output rather than leaving it in the destination folder.
- Same-path operations are rejected before moving anything, and explicit
  replacement mode restores the existing target if installation fails.

## Reporting a new issue

Use the privacy-safe route in Troubleshooting §Escalating to support. Safety-classified reports (`SAFETY` subject) jump the queue: acknowledged same business day, worked before feature work resumes.
