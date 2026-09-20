# Human Commercial Requirements — NITE DSP / SmartSampleManager

Phase 2 Section 75 / Phase 3 Section 7 / Phase 4 Section 4. **The authoritative register.**
Actions that require you personally — payment, an external account, a certificate, domain
ownership, a legal agreement, or a physical/clean machine — that no amount of code changes can
complete. Nothing here is marked done until you confirm it. Each item carries
STATUS / OWNER / BLOCKS / REASON. STATUS uses Phase 4's five-state classification:
`COMPLETE` / `AVAILABLE` / `AWAITING USER` / `BLOCKED` / `NOT REQUIRED YET`.

**Post-implementation note (Phase 4 close):** every item below is unchanged by Phase 4's actual
implementation work. Building the real backend, licensing service, commerce sandbox, download
system, and website (`docs/NITE_DSP_BACKEND_IMPLEMENTATION.md` et al.) does not resolve any
human-credential blocker -- it means those blockers are now the *only* thing separating a working
system from a real private beta tester. See `docs/PRIVATE_BETA_RELEASE.md`.

**Phase 5 note:** re-reviewed against the Phase 5 master prompt's own checklist (identity, Apple
Developer credentials, clean macOS machine, domain, commerce account/credentials, JUCE license).
Every item's status below is unchanged -- no new credentials, approvals, or accounts were
supplied this phase, and per the Section 88 STOP RULE, none are fabricated here. What Phase 5
*did* genuinely add: an identity regression guard, rate limiting, a verified backup/restore +
migration rehearsal (which found and fixed a real bug), and a config-leak scan of shipped
artifacts -- see `docs/PHASE_5_FINAL_SYNTHESIS.md`.

**Phase 5.5 note:** identity is now COMPLETE (Jack's explicit approval this phase). Domain and
company email were reported by the Phase 5.5 prompt as "sorted," but a repo-wide search found no
actual value for either -- both remain AWAITING USER, now with an explicit "VALUE REQUIRED"
report (`docs/DOMAIN_CONFIGURATION.md`, `docs/EMAIL_CONFIGURATION.md`) rather than a guessed
value. Everything else is unchanged in kind, though the engineering side of what's left narrowed
significantly this phase -- see `docs/PHASE_5_5_FINAL_SYNTHESIS.md`, including a major
dependency-bundling gap found and fixed (ONNX Runtime's transitive Homebrew dependencies were
never bundled) and two real concurrency bugs found and fixed.

## BEFORE PRIVATE BETA

### Confirm the NITE DSP identity proposal
```text
STATUS: COMPLETE — approved by Jack, Phase 5.5. Applied to CMakeLists.txt and verified
        (scripts/verify_identity_manifest.py). See docs/FINAL_PRODUCT_IDENTITY.md.
OWNER:  You
BLOCKS: (formerly) Any CMakeLists.txt identity change — now applied, treat as permanently
        immutable from this point forward.
REASON: N/A — resolved.
```

### Apple Developer Program membership
```text
STATUS: AWAITING USER
OWNER:  You
BLOCKS: Developer ID signing, notarization, macOS installer, private beta distribution
REASON: Required for Developer ID Application/Installer certificates and notarytool
        credentials; ~$99/yr as of Phase 1's research — verify current pricing at
        developer.apple.com before enrolling
```

### Developer ID Application certificate (macOS code signing)
```text
STATUS: BLOCKED — depends on Apple Developer Program membership above
OWNER:  You
BLOCKS: Signing every plugin bundle (VST3/AU/Standalone) before packaging
REASON: Issued only once Apple Developer Program membership exists
```

### Notarization credentials (app-specific password or API key for notarytool)
```text
STATUS: BLOCKED — depends on Apple Developer Program membership above
OWNER:  You
BLOCKS: The installer pipeline's notarize+staple step (docs/MACOS_RELEASE_PROCESS.md)
REASON: Generated from the same Apple Developer account
```

### A genuinely clean macOS test machine (or VM)
```text
STATUS: AWAITING USER
OWNER:  You
BLOCKS: The mandatory clean-machine release gate — cannot be waived; docs/CLEAN_MACHINE_VALIDATION.md
REASON: Must have never had Homebrew, CMake, ONNX Runtime, TagLib, or libsodium installed.
        This development environment cannot fabricate this result — the dependency-bundling
        implementation was verified via a strong local proxy (hiding this machine's own
        Homebrew paths), which is evidence, not the real test. Requires either a spare Mac,
        a fresh VM you provision, or a cloud macOS runner.
```

### Company/product website domain
```text
STATUS: COMPLETE — nitedsp.co.uk. Supplied by Jack, Phase 5.6, applied throughout: website
        metadata/canonical/OG/sitemap/robots, backend CORS allow-list derivation,
        docs/PRODUCTION_CONFIG_REFERENCE.md, docs/RAILWAY_DEPLOYMENT.md,
        docs/IONOS_DNS_SETUP.md. Registered at IONOS. Domain ownership/registration itself is
        not verified by this environment (no way to check WHOIS/registrar state from here) --
        this status reflects "the value is known and applied in code," not an independent
        ownership check.
OWNER:  You
BLOCKS: (formerly) COMPANY_WEBSITE plugin metadata, real (non-staging) website deployment.
        COMPANY_WEBSITE itself remains unset in CMakeLists.txt -- see docs/FINAL_PRODUCT_IDENTITY.md's
        Phase 5.6 note; this is a small remaining action, not a blocker.
REASON: N/A — resolved for configuration purposes. Real DNS records still need creating at IONOS
        once Railway exists (docs/IONOS_DNS_SETUP.md) — that step remains yours.
```

### Support email address
```text
STATUS: COMPLETE (as a real, owned contact address) — nitedsp@outlook.com. Supplied by Jack,
        Phase 5.6, applied to website footer/legal pages/account page, backend
        NITE_DSP_SUPPORT_EMAIL production reference value.
        NOT the same as: a verified transactional-sending domain/provider (still AWAITING
        USER, see docs/EMAIL_CONFIGURATION.md's Phase 5.6 update) — EMAIL_PROVIDER stays
        "console" until a real provider account + SPF/DKIM/DMARC for nitedsp.co.uk exists.
        Do not conflate "a mailbox someone reads" with "authenticated production email
        sending," per Phase 5.6's own Section 2 instruction.
OWNER:  You
BLOCKS: (formerly) COMPANY_EMAIL plugin metadata, account/support UI contact text -- both now
        resolved. Real transactional sending remains blocked, see above.
REASON: N/A for the contact-address use — resolved.
```

## BEFORE PAID RELEASE

### Approve final launch pricing
```text
STATUS: AWAITING USER — new item, Phase 6, tracked explicitly per that phase's Section 38/95
OWNER:  You
BLOCKS: Live checkout; the pricing page currently displays a flagged
        "HUMAN PRICING APPROVAL REQUIRED" notice alongside the recommended figures
REASON: £59 launch / £79 regular was a Phase 3 design-phase recommendation, never explicitly
        approved as a business decision. Also needs: currency presentation, any introductory
        discount, upgrade policy, activation count, refund policy — see
        docs/LIVE_COMMERCE_GO_NO_GO.md
```

### Purchase a commercial JUCE license
```text
STATUS: AWAITING USER
OWNER:  You
BLOCKS: Any closed-source commercial distribution of SmartSampleManager
REASON: JUCE 8.0.2 is AGPLv3-or-commercial (docs/THIRD_PARTY_LICENSES.md); AGPLv3 is
        incompatible with closed-source distribution. Pricing is tiered by company
        revenue/size — check current terms at juce.com; tier eligibility depends on NITE
        DSP's actual revenue/size at time of purchase, which this environment cannot determine
```

### Confirm current JUCE commercial terms and revenue tier
```text
STATUS: AWAITING USER
OWNER:  You (with JUCE directly)
BLOCKS: The JUCE license purchase above
REASON: Requires direct contact with JUCE; cannot be resolved from this codebase
```

### Retain proof of the JUCE commercial license
```text
STATUS: NOT REQUIRED YET — nothing to retain until purchased
OWNER:  You
BLOCKS: Nothing immediately, but needed if licensing status is ever questioned
REASON: Durable business record-keeping, not a code concern
```

### Merchant of Record account (Paddle)
```text
STATUS: AWAITING USER
OWNER:  You
BLOCKS: Any real (non-mocked) commerce testing — Phase 4's sandbox commerce code
        (docs/COMMERCE_IMPLEMENTATION.md) is written and unit-tested against simulated
        webhook payloads, but cannot be exercised end-to-end against Paddle's actual
        sandbox without an account existing first
REASON: Creating and verifying a business account (even for test/sandbox mode) involves
        KYC/business verification this environment cannot complete on your behalf
```

### Production hosting account (website + licensing backend + database)
```text
STATUS: AWAITING USER
OWNER:  You
BLOCKS: Any real (non-local) deployment — Phase 4's staging environment runs entirely on
        this local machine (local Postgres, local FastAPI/Next.js processes); a real
        staging/production deployment needs real hosting
REASON: Requires a real payment method and account ownership (VPS/PaaS provider, managed
        Postgres) — see docs/PRODUCTION_LICENSING_ARCHITECTURE.md for requirements this
        hosting choice must satisfy
```

### Production secrets storage
```text
STATUS: BLOCKED — depends on production hosting account above
OWNER:  You
BLOCKS: Generating/storing the production Ed25519 signing key (docs/LICENSE_KEY_LIFECYCLE.md)
REASON: The production private key must never exist in the repo, client, installer, or CI
        logs — needs a real managed secrets store (often bundled with the hosting choice
        above) before key generation is safe to perform at all
```

### Legal document review (EULA, privacy policy, refund policy, terms of service)
```text
STATUS: AWAITING USER — structural placeholders implemented this phase, marked
        "PROFESSIONAL REVIEW REQUIRED" on every page
OWNER:  You (with a lawyer)
BLOCKS: Public sale; the /privacy, /terms, /eula, /refund-policy website pages going live
        for real customers (staging/beta can display the reviewed-pending placeholders)
REASON: EU/UK VAT and consumer-protection obligations for digital products sold to
        individuals need real legal review, not AI-drafted text treated as final
```

### Trademark check on "NITE DSP" and "Smart Sample Manager"
```text
STATUS: AWAITING USER
OWNER:  You (public-database search can be assisted; a real freedom-to-operate opinion
        needs a trademark attorney)
BLOCKS: Public commitment to these names on the storefront/branding
REASON: Basic clearance before public launch reduces later rebranding risk
```

### UK/international business/tax setup
```text
STATUS: AWAITING USER
OWNER:  You (with an accountant)
BLOCKS: Real commerce launch
REASON: UK company/VAT registration, international sales tax obligations. A Merchant of
        Record (Paddle) reduces tax *administration* but does not eliminate all business/
        legal obligations — see docs/COMMERCE_PROVIDER_DECISION.md
```

## BEFORE WINDOWS RELEASE

### A real Windows x64 build/test machine
```text
STATUS: NOT REQUIRED YET — Phase 4 beta is explicitly scoped macOS-first
OWNER:  You
BLOCKS: Any Windows build/test work at all — docs/WINDOWS_READINESS.md
REASON: All Phase 1-4 work has run exclusively on macOS (Apple Silicon); this environment
        cannot build or test Windows without one. Not required for the macOS private beta.
```

### Windows code-signing certificate
```text
STATUS: NOT REQUIRED YET — same reasoning as above
OWNER:  You
BLOCKS: A Windows installer that doesn't trigger SmartScreen warnings on every download
REASON: EV or standard Authenticode cert from a CA — must not be assumed/fabricated in code
```

## OPTIONAL / LATER

- [ ] Registering "NITE DSP" as a formal legal business entity (if not already the case) —
  relevant to contracts, the Merchant of Record account, and tax reporting, but not a code
  blocker.
- [ ] A physical or cloud Windows Store / Mac App Store listing, if ever pursued — out of scope
  for the current direct-download distribution model.

## What is NOT on this list

Everything across Phase 2-4 that this environment can do without your direct action (product
hardening, architecture design, local staging implementation — real code, a real local
Postgres database, real API endpoints, all runnable and tested on this machine) is tracked in
`docs/COMMERCIAL_RELEASE_BLOCKERS.md` and the relevant phase's milestone list instead of here.
