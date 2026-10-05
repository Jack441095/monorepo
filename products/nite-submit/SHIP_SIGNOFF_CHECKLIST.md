# SHIP SIGN-OFF CHECKLIST — NITE Submit 1.0.0

**Date:** 2026-10-05
**Gate verdict:** `NOT READY`

---

- [ ] **Clean build from HEAD; version numbers agree everywhere**
  PARTIAL — `swift build` completes from the current tree (21.15 s, 51/51 targets). `VERSION` says `1.0.0` and CHANGELOG is `[1.0.0] - 2026-09-18`. But the monorepo tree still has 8 modified files under `products/nite-submit` and no `v1.0.0` tag exists.

- [x] **Full test suite green**
  PASS — `swift run nitesubmit-tests` run 2026-10-05: **508/508 checks passed**. Corpus metrics in that run: 233 extracted, all precision 1.0 (student_name 233/233, student_id 219/219, university 233/233, module_code 216/216, project_title 223/223). No App UI tests exist on the SwiftPM path.

- [x] **No-upload / no-telemetry verified in source AND binary**
  PASS — Only network call is user-initiated update check (disclosed in PRIVACY.md). Binary `strings` confirms only appcast URL. No analytics SDKs linked. `UpdateEngine` now verifies Ed25519 signatures and refuses future-dated `pubDate` entries (clock gate) before offering an update.

- [x] **No committed secrets**
  PASS — No `.p8`, `.p12`, `.env`, `.pem`, API keys, or tokens found in repo tree or source grep.

- [ ] **Signed + notarized + Gatekeeper-clean artifact**
  FAIL (P0) — Still open: P0-1 in SHIP_BLOCKERS.md. `check_distribution_readiness.sh` reported `ready_for_public_distribution: false`; no re-run has proven otherwise.

- [ ] **Install tested on a clean machine**
  UNVERIFIED — Cannot test (requires clean-machine environment and signed artifact). Current artifact would be Gatekeeper-blocked.

- [ ] **Activation/licensing flow verified end-to-end**
  PARTIAL — A licensing system now exists on the SwiftPM path: `LicenseEngine` validates Ed25519 `NTSUB1-` keys, reads an explicit little-endian timestamp, and refuses keys skewed more than 24 h. It is wired into the test suite. What remains unverified is the end-to-end path: mint key → deliver to customer → activate on first launch.

- [ ] **Test purchase + fulfillment verified**
  FAIL (P0) — Still open: P0-3 in SHIP_BLOCKERS.md. No payment processor; nothing mints a key for a customer. Key tooling (`nitesubmit-keygen`) is ready and tested.

- [x] **Privacy + third-party notices accurate**
  PASS — `PRIVACY.md` accurately describes local-only processing and the one user-initiated network request. `THIRD_PARTY_NOTICES.md` lists all dependencies with correct licenses and bundled license texts.

- [ ] **Sales-page claims all verified**
  PARTIAL PASS — Core feature claims verified. Mockup updated to the current drop → review → preview flow (P1-3 closed), arm64 requirement disclosed (P1-4 closed). Pricing page checkout still unverified.

- [ ] **Customer docs tested as written**
  PARTIAL FAIL — Docs exist and are well-written. Install steps would fail due to Gatekeeper blocking on the unsigned artifact (P0-1).

- [x] **Rollback plan documented**
  PASS — Documented in `RELEASE.md` (P1-5 closed).

---

**Summary:** 6 items pass, 2 items fail (the signing and payment P0s), 4 items partially fail or are unverified. Full suite green at 508/508 as of 2026-10-05. Licensing (`LicenseEngine`, Ed25519 + skew check) and update verification (`UpdateEngine`, Ed25519 + pubDate clock gate) exist and are tested on the SwiftPM path; no App UI tests exist. Retrieval precision on the extraction corpus is 1.0 on 233 extracted documents. The product still cannot be sold until the P0 blockers (signing/notarization, payment fulfilment) are resolved.
