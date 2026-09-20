# NITE SUBMIT — FINAL SHIP PHASE — AGENT PROMPT (V1)

> **What this file is:** a self-contained prompt that drives the final push to get NITE Submit uploaded and on sale.
>
> **How to use it:** open the workspace and instruct the agent: *"Execute `NITE_SUBMIT_FINAL_SHIP_PROMPT_V1.md` against `Nite-DSP-Operations/monorepo/products/nite-submit`. Produce all deliverables."*
>
> **Owner:** NITE DSP (Jack) · **Created:** 2026-09-18
> **Product root:** `Nite-DSP-Operations/monorepo/products/nite-submit`
> **Stack:** Swift / SwiftPM / macOS AppKit app · Ed25519 licence system · No Apple Developer ID

---

## 0. Context — where we are

A ship-readiness gate has been run. The following P0 blockers were identified and partially resolved:

- **P0-1 (Signing):** RESOLVED by design — no Apple Developer ID. Distribution is via direct ZIP download with right-click > Open instructions. A `tools/install.sh` curl installer also exists. The sales page (`web/index.html`) guides users through Download > Unzip > Right-click Open > Activate.
- **P0-2 (Licensing):** RESOLVED — Ed25519 licence key system added (`Sources/NiteSubmitCore/LicenseEngine.swift`). App gates behind activation on first launch (`LicenseView.swift`). Developer-only keygen tool at `Sources/nitesubmit-keygen/main.swift`. Private key at `tools/license-private-key.base64` (gitignored).
- **P0-3 (Payment):** PARTIALLY RESOLVED — app side done (licence entry + validation). **Still needed:** a payment processor (Paddle, LemonSqueezy, or Gumroad) connected to deliver licence keys after purchase. This prompt covers that integration.

Outstanding P1 issues from the ship gate (`SHIP_BLOCKERS.md`):
- CHANGELOG says `[Unreleased]` not `[1.0.0]`
- Artifact built from stale commit (HEAD has moved)
- Git tree dirty, no `v1.0.0` release tag
- Sales page mockup shows old console-style UI
- arm64 only not disclosed
- No rollback plan documented

**Build status:** 341/341 tests pass. Clean release build confirmed.

---

## 1. Phases

### Phase A — Payment processor integration

1. **Choose a processor.** Recommend LemonSqueezy (simplest for indie, handles EU VAT, provides licence key delivery via webhook). Paddle is also good but has more setup. Document the choice.
2. **Set up the product page** on the chosen processor: £3 one-time purchase, "NITE Submit — Lifetime Student Licence", no subscription.
3. **Webhook for licence key delivery:** after successful payment, generate a licence key (using the keygen tool or a server-side equivalent) and deliver it via the purchase confirmation email. Document the webhook endpoint and payload format.
4. **Update `web/index.html`** buy buttons to point to the real checkout URL (currently `https://www.nitedsp.co.uk/pricing`).
5. **Test the full flow:** purchase → email with licence key → paste key in app → app activates.

### Phase B — Fix remaining P1 issues

6. **CHANGELOG:** Rename `[Unreleased] - 2026-09-08` to `[1.0.0] - <today's date>`.
7. **Sales page mockup:** The preview window in `web/index.html` (id `app-mockup-preview`) shows "NITE Submit Console — Hardware Layout" with LED-style indicators. The actual app now uses plain English and system sans-serif. Update the mockup to match the current app appearance — use the three-step workflow (drop zone → review fields → renamed copy preview).
8. **Architecture disclosure:** Add "Apple Silicon" or "Requires Apple Silicon (M1 or later)" to the pricing card's system requirements line (currently says only "macOS 13+").
9. **Rollback plan:** Document in `RELEASE.md`: (a) how to pull the download page offline, (b) how to revert to the previous artifact, (c) how to notify customers.

### Phase C — Code quality pass

10. **Audit `LicenseEngine.swift`:** Verify the Ed25519 validation is not trivially bypassable (e.g. check that `isLicensed()` is called on the critical path, not just checked once and cached in a mutable bool). The key validation itself is sound (CryptoKit Ed25519), but check the integration.
11. **Audit `LicenseView.swift`:** Verify the activation UI handles edge cases — empty input, whitespace-only input, partial keys, keys with trailing newlines from email copy-paste.
12. **Audit `main.swift` licence gating:** Verify that `application(_:openFile:)` and `application(_:openFiles:)` respect the licence check — currently they queue PDFs into `pendingOpenURLs` which get processed in `showMainUI()`, so they should be gated. Confirm this.
13. **Remove `OpenEntitlement` if unused.** If nothing references it after the licence system, remove the dead code from `Settings.swift`.
14. **Keygen tool:** The private key placeholder in `Sources/nitesubmit-keygen/main.swift` is `***REDACTED***`. Before shipping, verify this is intentional (the real key is in `tools/license-private-key.base64` and must be pasted in manually). Consider making the keygen read the key from a file path argument instead of hardcoding.

### Phase D — Rebuild, tag & upload

15. **Clean the git tree:** Commit or discard all uncommitted changes (deleted 0.2.0 artifacts, modified test results).
16. **Rebuild the artifact:** Run `tools/package_app.sh` to produce a fresh `Submit-1.0.0-macOS.app` from HEAD.
17. **Run all checks:** `swift run nitesubmit-tests`, `tools/run_release_checks.sh`, `tools/verify_app_bundle.sh`.
18. **Create release tag:** `git tag v1.0.0` on the final commit.
19. **Package for distribution:**
    - ZIP: `(cd artifacts && zip -r Submit-1.0.0-macOS.zip Submit-1.0.0-macOS.app)`
    - Compute SHA-256: `shasum -a 256 artifacts/Submit-1.0.0-macOS.zip`
    - Update `tools/install.sh` with the new SHA-256 if it changed.
20. **Upload:** Upload `Submit-1.0.0-macOS.zip` and `tools/install.sh` to `releases.nitedsp.co.uk/submit/`. This could be:
    - GitHub Releases on the private repo
    - Cloudflare R2 / S3 bucket
    - A static hosting path on nitedsp.co.uk
    Document the chosen hosting and verify the download URL works.
21. **Write release manifest:** Run `tools/write_release_manifest.sh`.
22. **Deploy the sales page:** Upload `web/index.html` and `web/styles.css` to `nitedsp.co.uk/submit/` (or wherever the product page lives).

### Phase E — Verify the live flow

23. **End-to-end test from a clean perspective:**
    - Visit the sales page
    - Click the download link — verify it downloads
    - Follow the install steps as written
    - Verify the app launches and shows the licence screen
    - Enter a valid test licence key
    - Verify the app activates and processes a PDF correctly
24. **Verify the purchase flow** (if payment processor is set up):
    - Complete a test purchase
    - Verify licence key arrives in the confirmation email
    - Activate with that key
    - Process a test refund

---

## 2. Optimizations to consider

- **Keygen as a server function:** Instead of a CLI tool, deploy the keygen as a Cloudflare Worker or simple serverless function that the payment processor webhook calls. This automates key delivery without manual intervention.
- **Licence key format:** Current keys are ~95 characters (base64url). Consider a human-friendlier format with dashes (e.g. `NTSUB-XXXXX-XXXXX-XXXXX-XXXXX`) if students will type rather than paste. The current format is fine for email copy-paste.
- **Update checker URL:** `UpdateEngine.defaultAppcastURL` points to `https://www.nitedsp.co.uk/submit/appcast.xml`. Verify this URL will exist and serve a valid appcast when the product ships. Create the initial `appcast.xml` if it doesn't exist.
- **Universal binary:** Currently arm64 only. If you want Intel Mac support, rebuild with `--arch arm64 --arch x86_64` and update the bundled `7za` and `qpdf` binaries to Universal as well. This widens the addressable market but requires sourcing or building x86_64 versions of the bundled tools.

---

## 3. Deliverables

1. All P1 fixes applied and committed.
2. Payment processor configured (or documented what remains if external setup needed).
3. Fresh release artifact built, tested, and ready to upload.
4. `v1.0.0` git tag created.
5. Updated `SHIP_READINESS_REPORT.md` with the current state.
6. Deployment checklist: exactly which files go where, with URLs.
