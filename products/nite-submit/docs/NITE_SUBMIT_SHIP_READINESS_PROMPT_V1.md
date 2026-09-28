# NITE SUBMIT — SHIP READINESS GATE — AGENT PROMPT (V1)

> **What this file is:** a reusable, self-contained prompt that drives an AI coding agent through the full pre-sale readiness check for **NITE Submit** before it is put on sale online.
>
> **How to use it:** open the workspace root and instruct the agent: *"Execute `NITE_SUBMIT_SHIP_READINESS_PROMPT_V1.md` against `Nite-DSP-Operations/monorepo/products/nite-submit`. Read-only on product source. Produce the deliverables in §7."*
>
> **Owner:** NITE DSP (Jack) · **Created:** 2026-09-17
> **Product root:** `Nite-DSP-Operations/monorepo/products/nite-submit`
> **Stack:** Swift / SwiftPM / macOS app bundle (`Submit-1.0.0-macOS.app`, `NITE_Submit.bundle`)

---

## 0. Role and mission

You are a **release engineer + security reviewer** performing the final ship gate for NITE Submit — a macOS app whose core commercial promises are: **fully local, no upload, no account, no analytics/telemetry**. The gate answers one question: **"Can this be sold online today, and if not, exactly what blocks it?"**

**Verdict format:** `READY` / `READY WITH CONDITIONS` / `NOT READY`, with a numbered, prioritized blocker list. Every finding must cite file path + line, command + observed output, or artifact hash. No uncited claims.

## 1. Ground rules

- **R1 — Read-only on product source.** Builds/test runs allowed only in existing build dirs. No `rm`, no `git push`, no publishing, no `swift package resolve` that mutates `Package.resolved` without flagging it.
- **R2 — Evidence or it doesn't exist.** Do not treat `RELEASE.md`, `NITE_SUBMIT_RELEASE_REPORT.md`, prior reports, or filenames as proof. Re-verify load-bearing claims against current source.
- **R3 — Never echo secrets.** Reference paths only; redact values to `***REDACTED***`. Any secret found committed in the repo is a **P0 finding**.
- **R4 — The local-only promise is the product.** Any network call, telemetry, third-party analytics SDK, or outbound request in the shipping binary is **P0** unless documented and customer-visible. Verify with source review AND binary inspection, not one or the other.
- **R5 — Timebox and publish receipts.** Per-phase receipt: commands run, files read, what was skipped and why.

## 2. Phases

### Phase 1 — Version, build & reproducibility
1. Confirm `VERSION`, `CHANGELOG.md`, `Package.swift`, and the built app (`artifacts/Submit-1.0.0-macOS.app`) all agree on version/build number. Mismatch = blocker.
2. Rebuild from clean state (`swift build` / bundle assembly script in `tools/`). Confirm the artifact builds reproducibly from HEAD of the default branch.
3. `git status` / `git log` on the product repo: working tree clean, latest commit is the release commit, no uncommitted hotfixes, no detached-HEAD builds.
4. Confirm CI workflows (`.github/workflows/`) are green and actually run the test suite (not just compile).

### Phase 2 — Correctness & safety
5. Run the full test suite. Report pass/fail counts, skipped and flaky tests. Any failing test = blocker (no "known failures" allowed at ship).
6. Verify safety guarantees in code: **no-upload guarantee**, safe file handling (no destructive/corrupting writes to user files), and crash-free behavior on `real_validation_corpus/` and `fixtures/` edge cases (corrupt files, empty files, huge files, wrong extensions, permission-denied paths).
7. Confirm deterministic behavior on same input → same output, and clean error messages on failure paths (no raw stack traces shown to users).

### Phase 3 — Privacy, security & the local-only promise
8. Grep `Sources/` for network APIs (`URLSession`, `NWConnection`, `Socket`, `http`, `upload`) and third-party SDKs in `Package.swift` / `.build/checkouts`. Any outbound call = P0 unless documented and customer-visible.
9. Inspect the shipped binary: `strings` / `otool -L` / `codesign -d --entitlements` on the actual `.app`. Check linked frameworks, embedded URLs, entitlements (no `com.apple.security.network.client` unless justified), and no analytics beacons.
10. Scan repo history and tree for committed secrets (Paddle keys, API tokens, `.p8`/`.p12`, SSH keys, `.env`). Report exposure path, never the value.
11. Verify `PRIVACY.md` and `THIRD_PARTY_NOTICES.md` are accurate against the code: every dependency listed with correct license; privacy claims match observed behavior. Any mismatch = blocker (legal exposure).

### Phase 4 — Distribution, signing & notarization
12. Verify the app is **signed with a Developer ID certificate** and **notarized** (`xcrun stapler validate` / `spctl -a -vv` on the actual artifact, not just a report). Unsigned/unnotarized = Gatekeeper blocks the sale — P0.
13. Verify hardening runtime is enabled, and architecture coverage (arm64 / Universal) matches what you advertise.
14. Verify packaging: DMG/bundle mounts cleanly, no `.DS_Store` clutter, correct name/icon, and a clean quarantine test from a fresh machine.
15. Verify the app launches on a clean machine and the first-run experience works (no dev-mode paths; grep for hardcoded `/Users/jack/...` absolute paths = blocker).

### Phase 5 — Licensing, payments & fulfillment
16. Verify licensing/activation end-to-end: key generation → validation → grace/undo path; confirm validation is tamper-resistant (not a trivially-patched equality check) or that you explicitly accept that risk.
17. Verify Paddle (or chosen processor) integration: prices, product ID, tax handling, receipt/license delivery, and that a test purchase + refund works. Confirm provider keys are NOT embedded in the client.
18. Verify delivery pipeline: download URL on hosting/CDN, integrity checksum published, link not guessable, expiry behavior understood.

### Phase 6 — Storefront & customer-facing surface
19. Sales-page claims audit (`web/`): every feature claim must be verified working in this gate. Overclaiming = blocker. Check OS requirements, pricing, refund policy, and support contact are stated.
20. Customer docs (`docs/customer/`, `QUICK_START.md`, `README.md`): install steps tested as written, screenshots current (not dev/beta UI), troubleshooting section exists.
21. Support readiness: a bug-report path for users that does NOT violate the no-upload promise, refund handling plan, known-issues list.

### Phase 7 — Compliance & housekeeping
22. Dependency license compliance (MIT/Apache/GPL — GPL contamination in a paid closed product = blocker). Verify `THIRD_PARTY_NOTICES.md` coverage.
23. macOS privacy: the app only touches user-selected files, permission prompts have clear UX, no hidden scanning.
24. Rollback plan: previous artifact retained, git release tag, `CHANGELOG.md` updated, documented "pull the sale page offline" step.

## 3. Evidence discipline
Same as the estate audit: `OBSERVED:` (command + output, file:line) → `INFERRED:` (HIGH/MED/LOW) → `UNVERIFIED:` (what you couldn't confirm and why). Contradictions between the `NITE_SUBMIT_*_REPORT.md` files and current code are findings.

## 4. Prioritization
- **P0** — blocks the sale outright (failing tests, committed secrets, network calls breaking the local promise, unsigned artifact, broken activation/payment).
- **P1** — must fix before or immediately at launch (docs mismatch, missing notices, flaky tests).
- **P2** — nice-to-have before the first marketing push.

## 5. Sign-off checklist (print at the end, ticked or crossed)
- [ ] Clean build from HEAD; version numbers agree everywhere
- [ ] Full test suite green
- [ ] No-upload / no-telemetry verified in source AND binary
- [ ] No committed secrets
- [ ] Signed + notarized + Gatekeeper-clean artifact
- [ ] Install tested on a clean machine
- [ ] Activation/licensing flow verified end-to-end
- [ ] Test purchase + fulfillment verified
- [ ] Privacy + third-party notices accurate
- [ ] Sales-page claims all verified
- [ ] Customer docs tested as written
- [ ] Rollback plan documented

## 6. Hard stop
If any P0 is found, stop and deliver the blocker report immediately. The sale does not go live until every P0 shows `VERIFIED FIXED` with evidence.

## 7. Deliverables
Write (as new files only, outside `Sources/`):
1. `SHIP_READINESS_REPORT.md` — full per-phase findings with citations.
2. `SHIP_BLOCKERS.md` — the prioritized P0/P1 blocker list with exact fix steps.
3. The completed §5 sign-off checklist.
4. A per-phase receipt of commands run and files read.


