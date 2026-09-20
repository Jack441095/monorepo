# SHIP BLOCKERS — NITE Submit 1.0.0

**Date:** 2026-09-18
**Verdict:** `NOT READY` — 3 P0 blockers, 8 P1 issues

> The sale does not go live until every P0 shows `VERIFIED FIXED` with evidence.

---

## P0 — Blocks the sale outright

### P0-1: Artifact is ad-hoc signed, not Developer ID signed or notarized

**Evidence:**
- `codesign -dv`: `Signature=adhoc`, `TeamIdentifier=not set`, `flags=0x2(adhoc)`
- `spctl -a -vv`: `rejected`
- `xcrun stapler validate`: `does not have a ticket stapled to it`
- `distribution-readiness.json`: `developer_id_identity_available: false`, `ready_for_public_distribution: false`
- `RELEASE.md` acknowledges ad-hoc status

**Impact:** Every customer who downloads the app via a browser will hit Gatekeeper blocking. Right-click-Open is not acceptable for a paid product — it signals "unsigned/untrusted" to the user.

**Fix steps:**
1. Obtain or configure a Developer ID Application certificate from the Apple Developer Program
2. Sign the app and all embedded binaries (`7za`, `qpdf`) with Developer ID and hardened runtime (`codesign --options runtime -s "Developer ID Application: ..."`)
3. Submit for notarization via `xcrun notarytool submit`
4. Staple the ticket: `xcrun stapler staple Submit-1.0.0-macOS.app`
5. Rebuild the DMG/ZIP from the signed+notarized app
6. Verify: `spctl -a -vv` must show `accepted` and `source=Notarized Developer ID`
7. Run `tools/check_distribution_readiness.sh --require-ready` — must pass

### P0-2: No licensing or activation system

**Evidence:**
- Zero results for licensing/activation/serial/trial code in `Sources/` (grep returned only PDF field-detection vocabulary and `NSApplication.setActivationPolicy`)
- No DRM, license key validation, trial period, or usage restriction of any kind

**Impact:** The app is fully functional without payment. Anyone with a copy of the binary can use it forever. The "£3 Mac licence" claim on the sales page has no enforcement mechanism.

**Fix steps (choose one approach):**
- **A) Honour-system / unlockable:** Accept that the free binary is the product, and the payment is voluntary. Remove "licence" language from the sales page; call it a "download" or "purchase." This is the simplest path but weakest commercially.
- **B) License-key gate:** Integrate a lightweight license system (Paddle, LemonSqueezy, or a self-hosted key server). On first launch, prompt for a license key. Validate locally or via a one-time server check. Store validation state in Keychain or a signed local file.
- **C) App Store distribution:** Submit to the Mac App Store (handles payment, DRM, signing, and notarization). Requires adapting to App Store sandbox rules.

Whichever path: the activation/purchase flow must work end-to-end before sale.

### P0-3: No payment processor or fulfillment pipeline

**Evidence:**
- No Paddle, Stripe, Gumroad, or any payment SDK in source or `Package.swift`
- Buy buttons link to `https://www.nitedsp.co.uk/pricing` — an external URL with no verified checkout
- No license delivery mechanism from payment → app

**Impact:** Even if a customer pays, there is no automated path to deliver the product or a license key. Manual fulfillment does not scale and has no audit trail.

**Fix steps:**
1. Choose and integrate a payment processor (Paddle recommended for macOS indie apps — handles tax, receipts, license keys)
2. Configure product, pricing (£3), and webhook for license delivery
3. Test the full flow: purchase → receipt → license key → app activation
4. Publish download link with integrity checksum
5. If using honour-system (P0-2 option A): at minimum, set up a payment page that delivers a download link after payment

---

## P1 — Must fix before or immediately at launch

### P1-1: CHANGELOG says `[Unreleased]`, not `[1.0.0]`

**File:** `CHANGELOG.md:7`
**Fix:** Rename `[Unreleased] - 2026-09-08` to `[1.0.0] - <release date>`.

### P1-2: Artifact built from stale commit

**Evidence:** Release manifest `git_sha: 2d63db2`, HEAD is `1e086a6` (2 commits ahead: `refactor: simplify Submit around three-step workflow`, `feat: harden Submit public release path`).
**Fix:** Rebuild the artifact from the final release commit after all fixes land. Re-run `tools/run_release_checks.sh`.

### P1-3: Git state not release-ready

**Evidence:** Branch `engineering/nite-submit-v1.1-beta`, dirty tree (deleted old artifacts, modified test results), no `v1.0.0` tag.
**Fix:** Clean the tree, commit or discard changes, create a `v1.0.0` release tag on the final release commit.

### P1-4: CI is manual-only with no recent evidence

**Evidence:** `ci.yml` triggers only on `workflow_dispatch`. No evidence of recent runs.
**Fix:** Run CI manually at minimum. Consider adding `push`/`pull_request` triggers for ongoing assurance.

### P1-5: Test suite not verified against current HEAD

**Evidence:** Release manifest tests recorded at `2d63db2`, HEAD is `1e086a6`.
**Fix:** Run `swift build -c release --product nitesubmit-tests && swift run nitesubmit-tests` on the final commit. Record results.

### P1-6: Sales page mockup shows old console-style UI

**Evidence:** `web/index.html:83` — "NITE Submit Console — Hardware Layout" with LED-style indicators. `CHANGELOG.md` documents UI was simplified from console jargon to plain English with system sans-serif.
**Fix:** Update the mockup in `web/index.html` to match the current app appearance.

### P1-7: arm64 only — Intel Macs excluded without disclosure

**Evidence:** `file` on binary: `Mach-O 64-bit executable arm64`. Sales page says "macOS 13+" without architecture caveat.
**Fix:** Either build Universal (arm64 + x86_64) or add "Apple Silicon" / "arm64 only" to the sales page system requirements.

### P1-8: No rollback plan documented

**Evidence:** No "pull the sale page offline" procedure. No formal rollback steps.
**Fix:** Document: (1) how to pull the download page, (2) how to revert to previous artifact, (3) how to notify customers of a recall.

---

## P2 — Nice-to-have before first marketing push

### P2-1: `.DS_Store` in artifacts directory

**File:** `artifacts/.DS_Store`
**Fix:** Add to `.gitignore`, remove from tree.

### P2-2: Refund handling plan undocumented

**Fix:** Document refund policy and procedure, align with payment processor terms.

### P2-3: LGPL source availability notice

**Evidence:** `THIRD_PARTY_NOTICES.md` mentions 7za LGPL-2.1 but could more explicitly state that source code is available from the upstream project and that customers may request it.
**Fix:** Add a sentence: "The source code for 7za is available at [upstream URL] and may be requested from NITE DSP."
