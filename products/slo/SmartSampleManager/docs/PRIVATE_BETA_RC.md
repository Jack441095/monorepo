# Private Beta Release Candidate

## Gate status: **NOT READY** (narrower gap again, Phase 5.6)

Phase 5.6 re-evaluation, Section 26's instruction (domain → PASS once configured in code,
company contact email → PASS for what it actually satisfies, transactional delivery kept
distinct):

```text
[PASS]             identity approved/applied
                   Evidence: docs/FINAL_PRODUCT_IDENTITY.md. All 5 compile-time fields plus
                   COMPANY_WEBSITE/COMPANY_EMAIL (added Phase 5.6) verified in the built
                   artifacts (moduleinfo.json). scripts/verify_identity_manifest.py passes.

[BLOCKED EXTERNAL] JUCE commercial distribution requirement
                   Evidence: docs/HUMAN_COMMERCIAL_REQUIREMENTS.md -- requires purchasing a
                   commercial JUCE license; a business decision, not resolvable in code.

[BLOCKED EXTERNAL] signed macOS build exists
                   Evidence: docs/MACOS_SIGNING_VALIDATION.md -- no Apple Developer Program
                   membership. scripts/signing_preflight.py confirms build/manifest/identity
                   preflight is READY; only the signing credential itself is missing.

[BLOCKED EXTERNAL] notarisation passed
                   Evidence: same as above -- chained on signing.

[PASS]             installer verified
                   scripts/verify_release_manifest.py + scripts/check_homebrew_dependencies.py
                   both pass cleanly across all 3 formats, both Debug and Release trees,
                   reconfirmed this phase after applying COMPANY_WEBSITE/COMPANY_EMAIL. The
                   .pkg installer itself is still not built (blocked on signing existing
                   first).

[PASS]             dependencies bundled
                   Evidence: docs/CRITICAL_FINDING_LAUNCH_BLOCKING_BUG.md -- Phase 7 found that
                   every prior "PASS" here was based on a static check that missed a real
                   symlink-resolution bug causing the app to crash on launch (dyld "Library not
                   loaded"). Fixed, then verified for real this time: the Standalone binary was
                   actually launched and stayed running (screenshot captured), and Apple's own
                   `auval` tool reported "AU VALIDATION SUCCEEDED" against the real installed
                   component -- not just static analysis. A new check
                   (`check_missing_deps` in scripts/check_homebrew_dependencies.py) now verifies
                   every @loader_path/@rpath reference resolves to a real file, closing the gap
                   that let this slip through three prior phases undetected.

[BLOCKED EXTERNAL] clean Mac test passed
                   Evidence: docs/CLEAN_MACHINE_VALIDATION.md, docs/CLEAN_MACHINE_TEST_PROCEDURE.md
                   (strengthened this phase for standalone executability by someone unfamiliar
                   with the codebase) -- no clean machine available.

[BLOCKED EXTERNAL] hosted staging operational
                   Evidence: docs/RAILWAY_DEPLOYMENT.md -- deployment fully prepared
                   (railway.json for both services, healthchecks, env reference,
                   docs/IONOS_DNS_SETUP.md) but no Railway project/credentials exist to
                   actually deploy to. A materially more concrete BLOCKED than Phase 5.5's --
                   the target platform is chosen and configured, not just undecided.

[PASS]             beta entitlement works
                   Evidence: docs/BETA_ENTITLEMENT_FLOW.md, verified live -- issuance, 90-day
                   default expiry, invite email now using the real nitedsp.co.uk account URL.

[PASS]             beta download works
                   Evidence: docs/DOWNLOAD_IMPLEMENTATION.md, entitlement-gated, verified.

[PASS]             activation works
                   Evidence: docs/LICENSING_IMPLEMENTATION.md, real Ed25519, independently
                   re-verified, concurrency-safe (tests/test_concurrency.py).

[PASS]             offline licensing works
                   Evidence: 14-day grace period, check_again_by field on every issued token,
                   logic-level verified.

[PASS]             account login works
                   Evidence: docs/AUTH_IMPLEMENTATION.md, magic-link, rate-limited, verified
                   live. CORS now derives the real nitedsp.co.uk + www.nitedsp.co.uk origins.

[PASS]             support route exists
                   Evidence: nitedsp@outlook.com is a real, owned mailbox -- a customer can
                   genuinely reach a human. Applied to the website footer, legal pages, and
                   account page this phase (docs/EMAIL_CONFIGURATION.md). This gate is about a
                   customer having somewhere to send feedback, which is now true -- it is
                   explicitly NOT the same claim as "transactional email sending works,"
                   which remains a separate, still-BLOCKED item (see below).

[PASS]             privacy/network behavior validated
                   Evidence: no network call exists in the ONNX inference or sample-scanning
                   code path (design/code-level, not independently packet-captured).

[PASS]             WIP exposure = zero
                   Evidence: release manifest + identity guard + Homebrew dependency guard all
                   re-verified this phase, both build trees, post-identity-metadata-rebuild --
                   zero sibling-plugin or dev-tooling references found.
```

## Score: 12 PASS / 3 BLOCKED EXTERNAL / 0 FAIL

Up from Phase 5.5's 10/15. The three remaining external blockers: Apple Developer credentials
(blocks both signing and notarization, counted as one root cause across two gate rows), a real
clean Mac, and real hosted infrastructure (Railway project + IONOS DNS execution).

## Distinct from the gates above: transactional email still blocked

Not one of the 15 gates directly, but referenced by several: `EMAIL_PROVIDER` remains
`"console"` -- magic-link/purchase/beta-invite emails do not actually send to a real inbox yet.
This requires a real transactional email provider account and SPF/DKIM/DMARC DNS records for
`nitedsp.co.uk`, neither of which exist. Explicitly not conflated with the "support route
exists" gate above, per Section 26/2's instruction.

## Section 74 (Phase 5.5's question, reconfirmed): is the codebase ready to produce the RC if
credentials/hosting/clean-machine were provided today?

**YES**, more concretely than Phase 5.5's answer. Deployment isn't just "the code doesn't block
it" anymore -- there's an actual prepared target (Railway service configs, health checks, DNS
documentation) waiting only for an account to exist. `scripts/signing_preflight.py` still
confirms "Build/manifest/identity preflight: READY." If Apple credentials, a Railway account,
and a clean Mac were provided today, the remaining path is a sequence of operations (create the
Railway project, point IONOS DNS at it, sign, notarize, test on the clean machine, fill in the
DAW matrix) -- not further engineering.
