# SHIP BLOCKERS — NITE Submit 1.0.0

**Date:** 2026-09-30
**Status:** 3 open, 0 code blocks. Two are owner accounts, one is a key the owner holds offline.

---

## Open — owner action required

### P0-1: Not signed with a Developer ID certificate, not notarized

**Evidence:** `tools/check_distribution_readiness.sh` → `developer_id_identity_count: 0`, `current_app_developer_id_signed: false`, `current_app_notarised: false`, `ready_for_public_distribution: false`. The current build is ad-hoc signed, which Gatekeeper rejects on any Mac but this one.

**Fix steps:**
1. Install a Developer ID Application certificate in the login keychain (`security find-identity -v -p codesigning` must list one).
2. Configure the `NITE_SUBMIT` notarytool profile (`xcrun notarytool store-credentials NITE_SUBMIT`).
3. `tools/package_app.sh` then `tools/sign_and_notarize.sh`.
4. `xcrun stapler validate` and `spctl -a -vv` must report `accepted` with `source=Notarized Developer ID`. `spctl` in that script now fails closed, so a rejected build stops the run instead of warning.
5. `tools/check_distribution_readiness.sh --require-ready` must pass.

**Owner:** Jack. Nothing in the codebase blocks this.

### P0-3: No payment processor or key fulfilment

**Evidence:** no checkout integration in `web/index.html`; `LicenseEngine` validates keys but nothing mints one for a customer. The "£3 lifetime licence" claim on the sales page has no fulfilment path.

**Fix steps:**
1. Choose a processor (LemonSqueezy or Paddle both handle EU VAT and key delivery).
2. Mint keys with `nitesubmit-keygen` (now reading the signing key from `$XDG_CONFIG_HOME/nite-submit/license-private-key.base64`).
3. Wire the webhook so a paid order receives a key by email.
4. Test: purchase → key arrives → activates → refund.

**Owner:** Jack. The key tooling is ready and tested.

### P1-6: Update feed ships an empty signature

**Evidence:** `web/appcast.xml` carries `length="0"` and `sparkle:edSignature=""`. `UpdateEngine.checkStatus` refuses an enclosure with no signature while `requireSignature` is true, so the live feed shows "no update available" rather than offering a download.

**Fix steps:** `tools/update_appcast.sh <version> <built-zip> <release-private-key>`. It writes both attributes and refuses a key that does not verify against `UpdateEngine.updatePublicKeyBase64`. The release key is offline and is a different key from the licence key in `tools/`.

**Owner:** Jack.

---

## Closed — 2026-09-30

All fixed with regression tests; 475/475 checks pass. Full detail in `docs/NITE_SUBMIT_REVIEW_V1.md`.

| ID | Was | Fix |
|----|-----|-----|
| P0-2 | No licensing or activation system | `LicenseEngine.swift` Ed25519 `NTSUB1-` gate on first launch; little-endian timestamp, 24 h skew refused, failed writes surfaced. Was implemented before this pass but the docs still called it absent — corrected in `SHIP_READINESS_REPORT.md` and `ARCHITECTURE.md`. |
| B1 | Archive shipped every queued file after one approval | Approved rows only; skip count named in the message |
| B2 | Update signature parsed and never verified; download URL unvalidated | Ed25519 verification, `https` + host allowlist, XML entities off, fail closed |
| B3 | Organize executor hardcoded `.replace` | Refused unless `--force` |
| B4 | CLI `--policy replace` silent; `copy` defaulted to CWD | `--force` required, `--to` defaults to source folder |
| B5 | `try!` traps in batch and validation | `do`/`catch`, stderr, exit 2 |
| B6 | Duplicate basenames aborted an archive | `report.pdf`, `report 2.pdf`, … |
| B7 | Password in argv; ZipCrypto ZIPs | stdin, 7zAES-256, refusal rather than a weak substitute |
| B8 | `Filename:` matched the `name` label | Word-boundary anchored match; corpus `student_id` 215→219 at precision 1.0 |
| B9 | Template traversal out of the target folder | Confined path, reported as a collision |
| B10 | `1.2-beta` compared equal to `1.2.0` | Prerelease refused |
| M1 | Latin-1-only person names | `\p{L}` with conditional casing |
| M2 | Cross-volume staging, TOCTOU, symlink following | Sibling temp, `replaceItemAt`, `O_EXCL` claim, symlinks refused |
| M3 | Case-sensitive collision check | Lowercased comparison key for APFS |
| M4 | Unreadable folder read as empty; nondeterministic order | `FolderScanError`, sorted `relativePath`, `realpath` fix |
| M5 | Native-endian licence timestamp; swallowed store failure | Explicit little-endian, throwing store, future-dated refused |
| M6 | PDF text unbounded; scans behind a typed page never OCR'd | Truncate first, per-page OCR, OCR fields drop a confidence notch |
| M7 | Optimizer deleted the destination before running | Temp sibling, atomic replace, stat failures throw |
| M8 | Media kind by extension; camera dates read as student IDs | 16-byte header sniff, filename-only matches `.low` |
| M9 | Media drops could never load; main-thread blocking; reset resurrected state | `loadFile`, work queue with staleness token, queue cleared, receipts per item |
| M10 | Batch manifest fail-open; partial confidence gate; `--out` inside `--input` | Exit 2, every templated field gated, containment enforced |
| M11 | Runner crashed on regression; missing fixtures skipped; corpora drifted 239 vs 209 | Soft-failure runner, missing fixture fails, one generator + parity gate |
| M12 | Unpinned third-party blobs; `--deep` signing; key in `tools/` | `SHA256SUMS`, inside-out signing, key outside the tree with a bundle guard |
| P1-1 | `CHANGELOG` said `[Unreleased]` | `[1.0.0] - 2026-09-18` |
| P1-2 | Artifact built from a stale commit | Rebuilt from HEAD, `verify_app_bundle.sh` passes |
| P1-3 | Sales page mockup showed the old console UI | Updated to the current drop → review → preview flow |
| P1-4 | Apple Silicon not disclosed | Added to the system requirements line |
| P1-5 | No rollback plan | Documented in `RELEASE.md` |

---

## Still open, not blocking v1.0.0

- `ARCHITECTURE.md` notes a CJK name with no `Student Name:` label is still missed, because the title-page path requires letter casing. Needs a script-aware heuristic.
- Archive checksums are not reproducible across machines: mtimes, uids, and traversal order land in the bytes.
- Undo covers one interactive rename. Batch, organize, archive, and copy have no undo.
- `TemplateEngine` drops a user's `caseStyle` preference unless the caller re-applies it.
- `Settings.load()` rewrites the file to repair permissions on every launch; `save()` swallows write errors.
- `Presets.swift` reuses `id: "custom"` in both lists and its Harvard/Chicago labels read as institutional endorsement.
- Entitlements have no expiry or revocation. Deliberate for a one-shot student purchase.
