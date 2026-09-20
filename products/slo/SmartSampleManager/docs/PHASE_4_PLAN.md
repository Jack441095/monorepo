# Phase 4 Plan — Production Enablement + Private Beta Preparation

Implementation phase. Builds real, running code on top of Phase 3's architecture — not more
design documents. Location: `Audio_Too/nitedsp/` (new top-level directory, isolated from
`business/`, `studio/`, and every other WIP project per Section 8's boundary requirement).

## Stack decision

**Backend: Python/FastAPI + SQLAlchemy + Alembic + PostgreSQL + PyNaCl**, not the Node/TypeScript
backend Phase 3 sketched. Reasoning: Section 17 explicitly requires reusing the existing
Ed25519 architecture rather than replacing it — `licensing_server/`'s proven stack (Python,
FastAPI, PyNaCl for Ed25519) is the direct ancestor of the production licensing service, and
building the commercial backend in the same language/crypto library keeps the "reuse, don't
replace" instruction literal rather than merely conceptual. Postgres (not the dev server's
SQLite) for the reasons already established in `docs/NITE_DSP_DATABASE_SCHEMA.md`.

**Website: Next.js + TypeScript + React**, per Phase 3's recommendation, calling the Python
backend's API.

**Local staging environment** (Section 76): Node.js and PostgreSQL 16 installed via Homebrew
(same low-risk pattern already used for TagLib/ONNX Runtime/libsodium), a real local Postgres
database (`nitedsp_staging`) created and migrated, a real FastAPI process, a real Next.js dev
server. This is a genuine, runnable, testable local staging environment — not a description of
one. No cloud hosting, domain, or real Paddle account exists, so nothing here is reachable from
the public internet; that's the correct staging/production boundary per Section 6/7.

## What's genuinely testable this phase vs. what isn't

**Testable now, locally**: database schema + migrations, user/product/entitlement/activation
CRUD, magic-link auth flow (console-logged "email" instead of a real send), license
activate/validate/deactivate against real Ed25519 signing (using a staging keypair, never the
production one, which doesn't exist), the full purchase→entitlement transaction logic driven by
a *simulated* webhook payload matching Paddle's documented schema, signed download URL
generation against local mock storage, the release/update API, admin operations.

**Not testable without a human action**: anything requiring a real Paddle sandbox account
(actual checkout UI, actual webhook delivery from Paddle's servers), anything requiring a real
domain/hosting (public reachability, TLS), Apple code signing/notarization, the real
clean-machine test. Every one of these is called out explicitly at the point it's relevant,
matching `docs/HUMAN_COMMERCIAL_REQUIREMENTS.md`.

## Identity

**Not applied.** `docs/NITE_DSP_PRODUCT_IDENTITY.md` remains AWAITING USER approval — no row has
been explicitly approved by you, so per Section 5's own conditional ("If NITE DSP identity has
been explicitly approved") this phase does not touch `CMakeLists.txt`. `docs/FINAL_PRODUCT_IDENTITY.md`
is not created this phase for the same reason — it would have nothing final to record.

## Implementation order

Follows the master prompt's Milestone A-J structure. Milestone A (verify + human-action
classification) is done — see `docs/HUMAN_COMMERCIAL_REQUIREMENTS.md`. Milestones B-H proceed in
this document's implementation order; Milestones I (macOS signing) and J (real private beta
distribution) remain BLOCKED on Apple Developer credentials and the clean-machine test exactly as
`docs/HUMAN_COMMERCIAL_REQUIREMENTS.md` already states — not attempted this phase beyond what's
already prepared (`docs/MACOS_RELEASE_PROCESS.md`, `docs/INSTALLER_ARCHITECTURE.md`).
