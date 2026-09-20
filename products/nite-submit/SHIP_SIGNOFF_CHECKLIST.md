# SHIP SIGN-OFF CHECKLIST — NITE Submit 1.0.0

**Date:** 2026-09-18
**Gate verdict:** `NOT READY`

---

- [ ] **Clean build from HEAD; version numbers agree everywhere**
  FAIL — CHANGELOG says `[Unreleased]`, artifact built from stale commit (`2d63db2`, HEAD is `1e086a6`), git tree dirty, no `v1.0.0` tag.

- [ ] **Full test suite green**
  UNVERIFIED — Tests not re-run in this gate (R1 read-only constraint). Release manifest records 341/341 deterministic checks passing at `2d63db2`, but HEAD has moved 2 commits since.

- [x] **No-upload / no-telemetry verified in source AND binary**
  PASS — Only network call is user-initiated update check (disclosed in PRIVACY.md). Binary `strings` confirms only appcast URL. No analytics SDKs linked.

- [x] **No committed secrets**
  PASS — No `.p8`, `.p12`, `.env`, `.pem`, API keys, or tokens found in repo tree or source grep.

- [ ] **Signed + notarized + Gatekeeper-clean artifact**
  FAIL (P0) — Ad-hoc signed, no Developer ID, no notarization, no stapled ticket. `spctl` rejects. `distribution-readiness.json` confirms `ready_for_public_distribution: false`.

- [ ] **Install tested on a clean machine**
  UNVERIFIED — Cannot test (requires clean-machine environment and signed artifact). Current artifact would be Gatekeeper-blocked.

- [ ] **Activation/licensing flow verified end-to-end**
  FAIL (P0) — No licensing or activation system exists in the codebase. App is fully functional without payment.

- [ ] **Test purchase + fulfillment verified**
  FAIL (P0) — No payment processor integration. No license delivery pipeline. Buy buttons link to external URL with unverified checkout.

- [x] **Privacy + third-party notices accurate**
  PASS — `PRIVACY.md` accurately describes local-only processing and the one user-initiated network request. `THIRD_PARTY_NOTICES.md` lists all dependencies with correct licenses and bundled license texts.

- [ ] **Sales-page claims all verified**
  PARTIAL FAIL — Core feature claims verified. Mockup shows outdated console-style UI. Architecture requirement (arm64-only) not disclosed. Pricing page checkout unverified.

- [ ] **Customer docs tested as written**
  PARTIAL FAIL — Docs exist and are well-written. Install steps would fail due to Gatekeeper blocking on unsigned artifact.

- [ ] **Rollback plan documented**
  FAIL — No "pull the page offline" procedure documented. No formal rollback steps.

---

**Summary:** 3 items pass, 4 items fail (including 3 P0), 5 items partially fail or are unverified. The product cannot be sold until the P0 blockers (signing/notarization, licensing, payment) are resolved.
