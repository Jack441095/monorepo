# Phase 3 Plan — NITE DSP Commercial Platform + Distribution Preparation

Tracks the milestone order from the Phase 3 master prompt (Section 85), scoped against what this
development environment can actually do. Every milestone below is either **DESIGN** (a document
this environment can produce and verify for internal consistency) or **BLOCKED** (requires a
credential, account, or piece of hardware only you can provide — tracked in
`docs/HUMAN_COMMERCIAL_REQUIREMENTS.md`). Nothing in this phase enables live payments or public
distribution — per the master prompt's own Section 27/87, that's Phase 4.

## MILESTONE A — Current state + identity — DONE

- Read all Phase 0-2 audit docs (not redone from scratch).
- Reconfirmed clean build + full 12-test regression suite passes (this session).
- `docs/NITE_DSP_PRODUCT_IDENTITY.md` finalized in Phase 3's CURRENT/PROPOSED/RISK/HOST
  CONSEQUENCE/FINAL DECISION format, marked HUMAN APPROVAL REQUIRED.
- `docs/HUMAN_COMMERCIAL_REQUIREMENTS.md` rewritten in Phase 3's STATUS/OWNER/BLOCKS/REASON
  format, made authoritative.

## MILESTONE B — Distributable beta — PARTIALLY BLOCKED

- Dependency packaging: **already implemented and locally verified** (Phase 2).
- Installer: designed (`docs/INSTALLER_ARCHITECTURE.md`), not built — building the actual
  signed `.pkg` requires Apple Developer credentials (BLOCKED).
- Signing/notarization workflow: designed (`docs/MACOS_RELEASE_PROCESS.md`), scripts can be
  prepared, actual signing is BLOCKED on credentials.
- Clean-machine testing: **cannot be performed by this environment** — BLOCKED on hardware.
- Beta release channel: DESIGN this phase (`docs/PRIVATE_BETA_PLAN.md`).

## MILESTONE C — Commercial backend — DESIGN

- Database schema: `docs/NITE_DSP_DATABASE_SCHEMA.md` (new, detailed version of Phase 2's
  data-model sketch).
- Products/users/entitlements/activations: covered in the schema doc +
  `docs/NITE_DSP_COMMERCIAL_ARCHITECTURE.md` (Phase 2, updated this phase).
- Production licensing: `docs/PRODUCTION_LICENSING_ARCHITECTURE.md` (new),
  `docs/LICENSE_KEY_LIFECYCLE.md` (new).
- Authentication: `docs/NITE_DSP_ACCOUNT_ARCHITECTURE.md` (new).
- **Nothing deployed** — no production database, no production server, no production keys exist
  anywhere. Deployment is Milestone-gated on hosting/secrets infrastructure
  (`docs/HUMAN_COMMERCIAL_REQUIREMENTS.md`).

## MILESTONE D — Commerce — DESIGN, sandbox-ready architecture only

- Provider decision: `docs/COMMERCE_PROVIDER_DECISION.md` (Phase 2, reconfirmed this phase —
  Paddle recommendation stands, re-verified against current terms).
- Sandbox integration, webhook handling, purchase→entitlement flow: `docs/PAYMENT_FLOW.md` (new)
  — architecture and sequence, not a live integration (no Merchant of Record account exists yet
  to integrate against).
- Refund/chargeback handling: covered in `docs/PAYMENT_FLOW.md`.
- **No live or sandbox account exists** — even sandbox mode requires creating a provider account,
  which is a human action (KYC/business verification).

## MILESTONE E — NITE DSP website — DESIGN

- `docs/NITE_DSP_WEBSITE_ARCHITECTURE.md` (Phase 2, expanded this phase with pricing and legal-
  page structure per Phase 3's more detailed spec).
- Not built — per the master prompt's own Section 46 instruction not to build the website
  without a concrete reason to scaffold, and no hosting/domain exists yet to deploy it to.

## MILESTONE F — Customer experience — DESIGN

- Trial architecture: `docs/TRIAL_ARCHITECTURE.md` (new).
- Transactional email flows: covered in `docs/NITE_DSP_WEBSITE_ARCHITECTURE.md`'s support
  section + `docs/PAYMENT_FLOW.md`.
- Download architecture: `docs/DOWNLOAD_ARCHITECTURE.md` (new).
- Update/release API: covered in `docs/DOWNLOAD_ARCHITECTURE.md`.

## MILESTONE G — Private beta — DESIGN, execution BLOCKED

- `docs/PRIVATE_BETA_PLAN.md` (new): tester package contents, beta license type, feedback
  capture format, known-issues process.
- **Cannot actually distribute a beta** — requires the signed installer (Milestone B, BLOCKED)
  and, per the master prompt's own Section 74, testers must not be asked to install Homebrew —
  satisfied by Phase 2's dependency bundling, but still needs the real signed artifact to hand
  out.

## MILESTONE H — Final validation — PARTIALLY BLOCKED

- Security review: `docs/SECURITY_MODEL.md` (new) — reviews the *design* of auth/licensing/
  webhooks/admin/signing/updates. Cannot review a live deployment that doesn't exist.
- E2E sandbox purchase test (Section 86): **cannot be performed** — no sandbox commerce account
  exists. The full sequence is documented as a test plan in `docs/PAYMENT_FLOW.md` for when
  accounts exist.
- Commercial readiness rescore: done in `docs/PHASE_3_FINAL_SYNTHESIS.md`.

## What Phase 3 will NOT do (explicitly, per the master prompt's own directives)

- No live payment credentials, no real transactions (Section 27, 87).
- No live website deployment (no domain/hosting exists).
- No production database, no production signing key generation (no secure environment exists to
  generate them into — Section 20's explicit stop condition).
- No Windows work beyond what's already documented as unverified (Section 43 — macOS-first).
- No speculative re-hardening of Phase 2's product code without new evidence of a real problem
  (the master prompt's own final directive: "do not invent work simply to keep working").

## Documents this phase produces or updates

New: `docs/PHASE_3_PLAN.md` (this file), `docs/NITE_DSP_DATABASE_SCHEMA.md`,
`docs/NITE_DSP_ACCOUNT_ARCHITECTURE.md`, `docs/PRODUCTION_LICENSING_ARCHITECTURE.md`,
`docs/LICENSE_KEY_LIFECYCLE.md`, `docs/PAYMENT_FLOW.md`, `docs/TRIAL_ARCHITECTURE.md`,
`docs/DOWNLOAD_ARCHITECTURE.md`, `docs/PRODUCTION_BACKUP_RECOVERY.md`,
`docs/PRIVATE_BETA_PLAN.md`, `docs/SECURITY_MODEL.md`, `docs/PHASE_3_FINAL_SYNTHESIS.md`.

Updated: `docs/NITE_DSP_PRODUCT_IDENTITY.md`, `docs/HUMAN_COMMERCIAL_REQUIREMENTS.md` (done —
Milestone A), `docs/NITE_DSP_COMMERCIAL_ARCHITECTURE.md`, `docs/NITE_DSP_WEBSITE_ARCHITECTURE.md`,
`docs/COMMERCIAL_RELEASE_BLOCKERS.md`, `docs/RELEASE_MANIFEST.md`,
`docs/PRODUCT_READINESS_AUDIT.md`, `docs/TEST_COVERAGE_AUDIT.md`.
