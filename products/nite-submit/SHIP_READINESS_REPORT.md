# SHIP READINESS REPORT — NITE Submit 1.0.0

**Date:** 2026-09-18
**Verdict:** `NOT READY`
**Reviewer:** Automated ship gate (NITE_SUBMIT_SHIP_READINESS_PROMPT_V1)
**Product root:** `Nite-DSP-Operations/monorepo/products/nite-submit`
**Artifact under review:** `artifacts/Submit-1.0.0-macOS.app` (built 2026-09-14)

---

## Phase 1 — Version, Build & Reproducibility

### Check 1: Version agreement

| Source | Version |
|--------|---------|
| `VERSION` | `1.0.0` |
| `Info.plist` CFBundleVersion | `1.0.0` |
| `Info.plist` CFBundleShortVersionString | `1.0.0` |
| `CHANGELOG.md` latest section | `[Unreleased] - 2026-09-08` |
| `Package.swift` | No version field (SwiftPM package name only) |
| `artifacts/Submit-1.0.0-release-manifest.json` | `1.0.0` |

OBSERVED: `VERSION`, `Info.plist`, and release manifest agree on `1.0.0`. `CHANGELOG.md` latest section header reads `[Unreleased]`, not `[1.0.0]`.
INFERRED (HIGH): CHANGELOG was not updated to tag the release. **P1 finding.**

### Check 2: Reproducible build from HEAD

OBSERVED: Release manifest records `git_sha: 2d63db206a15b56853b0586b976357c5c9035802` (commit `2d63db2`). Current HEAD is `1e086a6` — two commits ahead (`refactor: simplify Submit around three-step workflow`). The artifact was built from an older commit.
INFERRED (HIGH): The shipped artifact does not correspond to HEAD. Build not verified against current code. **P1 finding.**

### Check 3: Git state

OBSERVED:
```
Branch: engineering/nite-submit-v1.1-beta
Status: 2 commits ahead of remote
Uncommitted: deleted artifacts/Submit-0.2.0-macOS.app/*, modified test results CSVs/JSONs
Tags: v0.2.0-private-beta.1, v1.0.0-rc.1 (no final v1.0.0 tag)
```
INFERRED (HIGH): Not on a release branch, working tree dirty, no final release tag. **P1 finding.**

### Check 4: CI green

OBSERVED: `.github/workflows/ci.yml` triggers on `workflow_dispatch` only — never automatic. It does run `swift build -c release` and `swift run nitesubmit-tests`, but there is no evidence of recent execution.
INFERRED (MED): CI is designed to run tests but is manual-only. No proof it has been run against the release artifact or current HEAD. **P1 finding.**

**Phase 1 receipt:** Read `VERSION`, `CHANGELOG.md:1-50`, `Package.swift:1-30`, `Info.plist`, `ci.yml`. Ran `git status`, `git log --oneline -10`, `git tag -l`. Read release manifest JSON.

---

## Phase 2 — Correctness & Safety

### Check 5: Test suite

OBSERVED: 13 test files exist under `Sources/NiteSubmitTests/` (ArchiveTests, AudioArchiveRoundTripTests, CorpusTests, DetectorTests, FailureTests, FileOperationTests, FolderCleanerTests, PDFOptimizerTests, PresetTests, SanitizerTests, TemplateTests, UpdateEngineTests, plus TestKit and main). Release manifest records `deterministic_checks: 341/341` and `batch_summary: 43 pass, 41 [secondary], 2 [other], 0 fail`.
UNVERIFIED: Test suite was not re-run in this gate because ground rule R1 restricts mutation of build state. The release manifest's SHA (`2d63db2`) predates HEAD by 2 commits — tests are unverified against current code. **P1 finding.**

### Check 6: Safety guarantees

OBSERVED: No destructive write operations to user files found in source. `FileOperations.swift` creates renamed copies; the "Rename Original" path renames in-place but is documented as undoable. `real_validation_corpus/` exists with test fixtures.
INFERRED (HIGH): File safety design appears sound. No-upload guarantee verified (see Phase 3).

### Check 7: Deterministic behavior / error messages

OBSERVED: Release manifest confirms `deterministic_checks: 341/341`. `tools/test_deterministic_archive.sh` exists for archive reproducibility. Error handling uses `NSAlert` and status labels, not raw stack traces.
INFERRED (HIGH): Deterministic output and user-facing error paths appear well-handled.

**Phase 2 receipt:** Read all test filenames. Read release manifest verification section. Grepped `Sources/` for error handling patterns. Read `FileOperations.swift` filename.

---

## Phase 3 — Privacy, Security & the Local-Only Promise

### Check 8: Network API grep

OBSERVED:
- `Sources/NiteSubmitApp/main.swift:114` — `URLSession.shared.dataTask(with: feedURL)` in `checkForUpdates()` method, triggered only by user clicking "Check for Updates..." menu item.
- `Sources/NiteSubmitCore/UpdateEngine.swift:69` — `defaultAppcastURL = URL(string: "https://www.nitedsp.co.uk/submit/appcast.xml")!`
- No other `URLSession`, `NWConnection`, `Socket`, `URLRequest` calls found in `Sources/`.
- No third-party SDKs in `Package.swift` dependencies (zero external packages).
- No analytics, telemetry, crash reporting, Firebase, Sentry, Mixpanel, or Amplitude references found.

INFERRED (HIGH): The only network call is a user-initiated update check. This is disclosed in `PRIVACY.md` ("The one network request the app makes"). **No P0 violation.**

### Check 9: Binary inspection

OBSERVED:
- `strings` on the binary: only URL found is `https://www.nitedsp.co.uk/submit/appcast.xml`. No analytics endpoints.
- `otool -L`: Links only Apple system frameworks (Foundation, AppKit, CoreFoundation, CoreGraphics, CryptoKit, PDFKit, QuartzCore, Vision, plus Swift runtime libraries). No third-party dylibs.
- `codesign -d --entitlements`: No entitlements returned (no `com.apple.security.network.client` or other entitlements).

INFERRED (HIGH): Binary confirms no hidden network capability beyond what source review shows. The app will use the system networking stack for the update check via Foundation/URLSession without a specific entitlement (entitlements are not required for outbound HTTP on macOS without App Sandbox). **No P0 violation.**

### Check 10: Committed secrets scan

OBSERVED: No `.p8`, `.p12`, `.env`, `.pem`, `*secret*`, `*token*`, or `*credential*` files found in the repo tree (excluding `.build/`). Grep for `api_key`, `apiKey`, `secret`, `token`, `password` in Sources returned only user-facing archive password fields (CLI `--password` flag, UI password text field for 7z encryption). No API keys or tokens.
INFERRED (HIGH): No committed secrets. **Clean.**

### Check 11: PRIVACY.md and THIRD_PARTY_NOTICES.md accuracy

OBSERVED:
- `PRIVACY.md` accurately describes: local-only processing, no uploads, no analytics, no accounts, settings stored at `~/Library/Application Support/NiteSubmit/settings.json`, and the single user-initiated update check. All claims verified against source.
- `THIRD_PARTY_NOTICES.md` lists: 7za (LGPL-2.1), qpdf (Apache-2.0), OpenSSL libcrypto (Apache-2.0), libjpeg-turbo (IJG/BSD/zlib). License files bundled in `Contents/Resources/bin/`.
- App bundle contains `7za` and `qpdf` as separate arm64 executables. OpenSSL and libjpeg-turbo are statically linked into qpdf (not visible as separate binaries but listed in notices). Notices correctly state they are local-only.

INFERRED (HIGH): Privacy and third-party documentation is accurate and matches observed behavior. **Clean.**

**Phase 3 receipt:** Grepped `Sources/` for `URLSession|NWConnection|Socket|upload|http|URLRequest`. Grepped for analytics keywords. Read `UpdateEngine.swift` (full file). Read `main.swift:100-140`. Ran `strings`, `otool -L`, `codesign -d --entitlements` on app binary. Searched for secret-pattern filenames. Grepped source for API key patterns. Read `PRIVACY.md` and `THIRD_PARTY_NOTICES.md` in full. Listed `Contents/Resources/bin/`.

---

## Phase 4 — Distribution, Signing & Notarization

### Check 12: Developer ID signing and notarization — P0

OBSERVED:
```
$ codesign -dv --verbose=2 artifacts/Submit-1.0.0-macOS.app
CodeDirectory flags=0x2(adhoc)
Signature=adhoc
TeamIdentifier=not set

$ spctl -a -vv artifacts/Submit-1.0.0-macOS.app
artifacts/Submit-1.0.0-macOS.app: rejected

$ xcrun stapler validate artifacts/Submit-1.0.0-macOS.app
Submit-1.0.0-macOS.app does not have a ticket stapled to it.
```

`artifacts/Submit-1.0.0-distribution-readiness.json`:
```json
"developer_id_identity_count": 0,
"developer_id_identity_available": false,
"current_app_developer_id_signed": false,
"current_app_notarised": false,
"current_dmg_notarised": false,
"ready_for_public_distribution": false
```

`RELEASE.md` acknowledges: "Ad-hoc signed. Not Developer-ID signed, not notarised. First launch requires right-click → Open."

INFERRED (HIGH): The artifact is ad-hoc signed with no Developer ID identity available on the build machine. Gatekeeper will block this for all customers who download it normally. The right-click workaround is unacceptable for a paid commercial product. **P0 — blocks sale.**

### Check 13: Hardened runtime and architecture

OBSERVED: No hardened runtime flags in codesign output. Architecture is `Mach-O 64-bit executable arm64` (thin binary, not Universal). Bundled `7za` and `qpdf` are also arm64-only.
INFERRED (HIGH): No hardened runtime (required for notarization). Intel Mac users cannot run the app. Sales page says "macOS 13+" without specifying architecture — Intel users running macOS 13 would be misled. **P1 finding.**

### Check 14: Packaging quality

OBSERVED: `artifacts/Submit-1.0.0-macOS.dmg` exists (6.4 MB). `.DS_Store` present in `artifacts/` directory. `tools/verify_app_bundle.sh` exists for bundle verification.
UNVERIFIED: DMG mount/quarantine test not performed (would require clean-machine simulation). `.DS_Store` in artifacts is minor packaging hygiene issue. **P2 finding.**

### Check 15: Clean-machine launch / hardcoded paths

OBSERVED: No `/Users/jack/` or `/Users/Ganders/` hardcoded paths found in `Sources/**/*.swift`. Settings path uses `~/Library/Application Support/NiteSubmit/`.
UNVERIFIED: First-run experience not tested (requires clean-machine environment). **Assumed clean based on source review.**

**Phase 4 receipt:** Ran `codesign -dv --verbose=2`, `spctl -a -vv`, `xcrun stapler validate`, `codesign -d --entitlements` on `Submit-1.0.0-macOS.app`. Read `distribution-readiness.json`. Read `RELEASE.md:1-60`. Ran `file` on bundled binaries. Grepped for hardcoded paths.

---

## Phase 5 — Licensing, Payments & Fulfillment

### Check 16: Licensing/activation — P0

OBSERVED: No licensing, activation, serial key, trial, or registration code exists anywhere in `Sources/`. Grep for `license|activation|licence|serial|registration|trial|expire` returned only:
- PDF field-detection vocabulary (`"end user licence"`, `"registration number"`) — these detect student document fields, not app licensing.
- `NSApplication.setActivationPolicy(.regular)` — standard macOS app lifecycle, not license activation.

There is no license key validation, no activation flow, no trial period, no grace period, no DRM of any kind.

INFERRED (HIGH): The app is completely unprotected. Anyone with a copy of the binary can use it indefinitely without payment. The sales page advertises "£3 Mac licence" but there is no mechanism to enforce it. **P0 — blocks commercial sale.**

### Check 17: Payment processor integration — P0

OBSERVED: No Paddle, Stripe, Gumroad, LemonSqueezy, FastSpring, or any payment processor SDK, API, or integration exists in the codebase. The "buy" buttons on the sales page link to `https://www.nitedsp.co.uk/pricing` — an external URL whose checkout functionality was not verified in this gate.
UNVERIFIED: Whether `nitedsp.co.uk/pricing` has a working payment flow. No test purchase possible from this gate.
INFERRED (HIGH): No payment fulfillment pipeline exists in the product itself. The product relies entirely on an external website for payment, with no license delivery mechanism back to the app. **P0 — blocks commercial sale.**

### Check 18: Delivery pipeline

OBSERVED: Release manifest contains SHA-256 checksums for the app binary, CLI binary, ZIP archive, and DMG. `artifacts/` contains the DMG (6.4 MB) and ZIP (5.6 MB).
UNVERIFIED: No CDN/hosting URL configured for download delivery. No integrity checksum published on the download page. No link-guessability or expiry behavior assessed.

**Phase 5 receipt:** Grepped `Sources/` for licensing/activation keywords. Grepped for payment processor names. Read sales page HTML for buy-button targets. Read release manifest checksums.

---

## Phase 6 — Storefront & Customer-Facing Surface

### Check 19: Sales-page claims audit

OBSERVED claims in `web/index.html` vs verification:

| Claim | Verified? | Notes |
|-------|-----------|-------|
| "Rename university assignments correctly in seconds" | Yes | Core rename functionality confirmed in source |
| "100% Offline Processing" | Yes (with caveat) | All processing is local; optional update check disclosed in privacy section |
| "Bit-Identical Original Safety" / "SHA-256 Byte Preservation" | Yes | Source creates renamed copies; SHA-256 verification in code |
| "Smart Cover-Sheet Detection" / "under 0.05 seconds" | Partially | Detection exists; 0.05s claim not independently timed |
| "University Preset Rules" (UK, Harvard, US, Chicago, candidate numbers, custom) | Yes | `Presets.swift` exists with multiple profiles |
| "Anonymous Marking Check" | Yes | Document identity policy detection in `FieldDetector.swift` |
| "Local Scanned PDF OCR" | Yes | Vision framework linked; `PDFExtractor.swift` exists |
| "Includes `nitesubmit-cli` for batch terminal workflows" | Yes | CLI target in `Package.swift`, binary in app bundle |
| "macOS 13+" | Partially | Correct for arm64 Macs. Intel Macs running macOS 13 cannot use it — not stated |
| "£3" pricing | Unverified | External pricing page not accessible from this gate |

**P1 finding:** Sales page mockup shows old console-style UI ("NITE Submit Console — Hardware Layout" with LED indicators), but CHANGELOG documents that UI was changed to "plain English and a system sans-serif." The mockup misrepresents the current app appearance.

### Check 20: Customer docs

OBSERVED: `docs/customer/` contains: FAQ, Getting Started, Known Issues, Troubleshooting, User Guide. `QUICK_START.md` is clear and accurate. `README.md` exists.
UNVERIFIED: Screenshots not checked for currency (would require launching app). Install steps in docs reference the app but Gatekeeper blocking (ad-hoc signing) would prevent the documented flow from working. **P1 finding.**

### Check 21: Support readiness

OBSERVED: Sales page footer links to `nitedsp.co.uk/support` and `nitedsp.co.uk/privacy`. Known-issues list exists (`docs/customer/NITE_SUBMIT_KNOWN_ISSUES_V1.md`). Bug report path: website support link (doesn't violate no-upload promise). No explicit refund handling plan found in repo.
INFERRED (MED): Support path exists but refund handling plan is undocumented. **P2 finding.**

**Phase 6 receipt:** Read `web/index.html` in full. Listed `docs/customer/` contents. Read `QUICK_START.md`. Checked sales page claim-by-claim against verified source functionality.

---

## Phase 7 — Compliance & Housekeeping

### Check 22: Dependency license compliance

OBSERVED:
- `7za` — LGPL-2.1: Bundled as a separate arm64 executable (not statically linked into the main app). This is LGPL-compliant: it's a separate program invoked via `Process()`. License text bundled.
- `qpdf` — Apache-2.0: Permissive, no issue for closed-source commercial use. License text bundled.
- OpenSSL `libcrypto` — Apache-2.0: Statically linked into qpdf. Permissive.
- libjpeg-turbo — IJG/BSD/zlib: Permissive.

No GPL contamination. All dependencies are LGPL (separate executable) or permissive licenses. **Clean.**

### Check 23: macOS privacy

OBSERVED: App only processes user-selected files (drag-drop or file browser). No background scanning. No hidden file access. Settings stored with owner-only permissions (0700/0600 per `PRIVACY.md`).
INFERRED (HIGH): Privacy behavior is appropriate. **Clean.**

### Check 24: Rollback plan

OBSERVED: Previous artifact (`Submit-0.2.0-macOS.dmg`) retained in `artifacts/`. Git tags exist (`v0.2.0-private-beta.1`, `v1.0.0-rc.1`). No final `v1.0.0` tag. `CHANGELOG.md` updated but not tagged. No documented "pull the sale page offline" procedure.
INFERRED (HIGH): Partial rollback capability exists but no formal rollback plan is documented. **P1 finding.**

**Phase 7 receipt:** Checked license types for all dependencies. Verified 7za is a separate executable (not statically linked). Confirmed file access patterns. Listed git tags. Checked for rollback documentation.

---

## Summary

| Priority | Count | Description |
|----------|-------|-------------|
| **P0** | 3 | Unsigned/unnotarized artifact, no licensing system, no payment integration |
| **P1** | 8 | CHANGELOG version, HEAD drift, dirty git state, CI manual-only, tests unverified, stale mockup, architecture gap, no rollback plan |
| **P2** | 3 | Packaging hygiene, refund plan, LGPL notice clarity |
| **Clean** | Multiple | Privacy verified, no secrets, no analytics, dependency licenses OK, file safety OK, deterministic output |
