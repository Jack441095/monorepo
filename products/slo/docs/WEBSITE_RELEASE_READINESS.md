# Website release readiness

Branch: `web/nitedsp-world-class-v3`

## Completed on this branch

- Product-led homepage, product page, pricing, support, and learn index share one responsive visual system.
- The UI uses an actual Smart Sample Manager screenshot, not a fabricated product mock-up.
- Existing checkout, magic-link sign-in, entitlement, and download logic were left functionally unchanged.
- `npm run lint`, `npm run audit:copy`, and `npm run build` pass locally.
- The Playwright release journey passes 28 of 28 checks against a local production-style build.
- Backend commerce, webhook, entitlement, and download contract tests were run only against the isolated test database. Thirty-one passed. One signature-verification test requires the matching local staging keypair, intentionally absent from this clean checkout; no production key or data was used.
- Desktop and mobile visual checks were completed for the redesigned routes.

## Before any public launch

- Obtain a lawyer-reviewed Privacy Policy appropriate for the company, its processor relationships, and UK/EU obligations. The current `/privacy` page explicitly remains a pre-launch placeholder and must not be represented as final.
- Confirm the final price, launch status, refund process, and Merchant of Record details with the owner.
- Complete production payment and account-flow testing against the intended Merchant of Record configuration.
- Perform final browser/device accessibility review and production deployment review.
- Provide an owner-approved staging keypair or test-only equivalent before treating the backend suite as fully green in a fresh checkout.

This document is a release-readiness record, not legal advice or a claim that the website is ready to launch.
