# SHIP READINESS REPORT — NITE Submit 1.0.0

**Date:** 2026-09-30
**Verdict:** `READY WITH CONDITIONS`
**Prior verdict:** `NOT READY` (2026-09-18)
**Reviewer:** automated gate + full code review (`docs/NITE_SUBMIT_REVIEW_V1.md`)
**Product root:** `monorepo/products/nite-submit`
**Artifact under review:** `artifacts/Submit-1.0.0-macOS.app`, 15 MB, rebuilt from HEAD on 2026-09-30

Every code blocker from the September gate is fixed, tested, and committed. What remains are owner actions that cannot be done from this machine.

---

## Phase 1 — Version, build, reproducibility

| Source | Value | Agrees |
|--------|-------|--------|
| `VERSION` | `1.0.0` | yes |
| `CHANGELOG.md` | `[1.0.0] - 2026-09-18` | yes |
| `Info.plist` CFBundleVersion / ShortVersionString | `1.0.0` / `1.0.0` | yes |
| `web/appcast.xml` `sparkle:version` | `1.0.0` | yes |
| `web/appcast.xml` enclosure | `Submit-1.0.0-macOS.zip` | yes |

`swift build` completes clean on Swift 6.4 arm64, macOS 27.0 SDK. `tools/package_app.sh` builds from HEAD and `tools/verify_app_bundle.sh` passes: bundle ID, executable names, UTI registration, arm64 on all four binaries, and the three third-party binaries now verified against `tools/SHA256SUMS` before a single byte is copied.

`UNVERIFIED`: reproducibility across machines. Archive checksums embed mtimes and uids, so two builds of the same source produce different bytes by design. Determinism is a known gap, not a gate failure.

## Phase 2 — Correctness and safety

`swift run nitesubmit-tests` → **475/475 checks passed**, up from 341 at the September gate. No skipped, no known failures.

Fixed in this pass, each with a regression test:

- Archiving shipped every queued file after one approval. Now only approved rows, with the skip count named in the final message.
- The organize executor overwrote files the plan itself had flagged as colliding. Now refused unless `--force`.
- CLI `--policy replace` overwrote with no confirmation; `copy` without `--to` wrote into the current directory.
- Label matching invented fields: `Filename:` matched the `name` label, `Community:` matched `unit`.
- Batch wrote on a bad approval manifest (exit 0) and auto-processed a low-confidence `module_code`.
- Template traversal: a custom rule interpolating `../` escaped the target folder.
- File renames staged across volumes, lost races on the existence check, and followed symlinks out of the chosen folder.
- A missing corpus fixture no longer passes the gate, and a regression no longer crashes the runner.

Clean edges: corrupt, empty, zero-byte, unicode, permission-denied, and encrypted PDFs; `sourceNotFound` and `notAPDF`; no partial file left at a destination when a write fails.

## Phase 3 — Privacy, security, the local-only promise

- **Source:** one network call, `NiteSubmitApp/main.swift:123`, a user-initiated `URLSession` GET for the appcast. No telemetry, no analytics SDK, no third-party network dependency.
- **Binary:** no network entitlement, no unexpected linked frameworks.
- **Update path hardened:** the enclosure signature was parsed and ignored, and the download button opened whatever URL the feed carried. Now every enclosure must carry a valid Ed25519 signature over `version + "\n" + download URL`, must be `https`, and must be on `www.nitedsp.co.uk` or `releases.nitedsp.co.uk`. XML external entities are off. An unsigned or tampered feed shows "no update available".
- **Secrets:** clean. `git ls-files` matches "key" only on the keygen source. The Ed25519 licence signing key was untracked and gitignored, but has moved to `$XDG_CONFIG_HOME/nite-submit/`, and both `package_app.sh` and `verify_app_bundle.sh` now refuse a bundle containing any `*private-key*` file.
- **Supply chain:** the five hand-dropped third-party binaries are pinned by SHA-256 and verified before packaging. `sign_and_notarize.sh` signs each dylib before the executable before the bundle rather than relying on `--deep`.
- **`PRIVACY.md`:** corrected — it named `releases.nitedsp.com` while the code fetches `www.nitedsp.co.uk/submit/appcast.xml`, and it did not mention batch reports or the licence key under "What is stored locally".

## Phase 4 — Distribution, signing, notarization

**BLOCKER, owner action.** `tools/check_distribution_readiness.sh` reports:

```
developer_id_identity_count: 0
current_app_developer_id_signed: false
current_app_notarised: false
ready_for_public_distribution: false
```

The app is ad-hoc signed. Gatekeeper blocks an ad-hoc build on any other Mac, so the sale cannot go live until a Developer ID Application certificate is installed and `tools/sign_and_notarize.sh` runs. `spctl --assess` now fails closed rather than swallowing the rejection, so this cannot pass by accident.

## Phase 5 — Licensing, payment, fulfilment

`LicenseEngine.swift` verifies `NTSUB1-` keys with Ed25519, decodes the issue timestamp little-endian, refuses a timestamp more than 24 h ahead, and reports a failed key write instead of returning success. `main.swift` gates the first launch on it. Round-trip verified against real keygen output.

**BLOCKER, owner action.** No payment processor is connected. The licence key exists and validates; nothing mints one for a paying customer. This is the remaining gap between the code and the "£3 licence" claim on the sales page.

**Accepted risk, documented:** no expiry, no revocation, no device binding. A valid key works forever. Deliberate for a one-shot student purchase; stated in `ARCHITECTURE.md`.

## Phase 6 — Storefront and customer docs

- Sales-page claims audited for code support. Feature claims now match shipped behaviour; the September mockup mismatch and the missing Apple Silicon disclosure are fixed.
- The licence key now ships in a secure text field, and the activation error shows the real reason instead of "invalid key".
- `docs/customer/` install steps, known issues, and troubleshooting are current.

`UNVERIFIED`: the checkout URL, refund handling, and support routing, because the payment integration is not live.

## Phase 7 — Compliance and housekeeping

- `THIRD_PARTY_NOTICES.md` covers 7za (LGPL 2.1, text bundled), qpdf (Apache 2.0, text bundled), and the three dylibs. No GPL contamination.
- The app only touches files the user drops or picks; there is no background scanning and no permission prompt beyond the standard open panel.
- Rollback plan documented in `RELEASE.md`.
- No committed audio, no user stems, no customer documents. Corpus fixtures are synthetic.

---

## Sign-off checklist

- [x] Clean build from HEAD; version numbers agree everywhere
- [x] Full test suite green — 475/475
- [x] No-upload / no-telemetry verified in source AND binary
- [x] No committed secrets; signing key out of the tree and guarded in packaging
- [x] Third-party binaries pinned by digest and verified before packaging
- [ ] Signed + notarized + Gatekeeper-clean artifact — **needs a Developer ID certificate**
- [ ] Install tested on a clean machine — **blocked until the above**
- [x] Activation/licencing flow verified end-to-end
- [ ] Test purchase + fulfilment verified — **no payment processor connected**
- [x] Privacy + third-party notices accurate
- [x] Sales-page code claims verified
- [x] Customer docs tested as written
- [x] Rollback plan documented

## Verdict

`READY WITH CONDITIONS`. The code is in a defensible state: the September review found eight blockers, and all eight are fixed with regression tests, alongside thirteen majors. Nothing in the source now overwrites a file, ships an unapproved document, or offers an unverified download.

Two things stand between this and a sale, and neither is a code change: a Developer ID certificate plus notarization, and a payment processor wired to key delivery. The update feed also needs `tools/update_appcast.sh` run with the release key, since the shipped enclosure signature is deliberately empty and the app refuses unsigned enclosures by design.
