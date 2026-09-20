# KENN system map — audit in progress

Audit date: 2026-09-17. Primary scope: this standalone KENN repository. This is a working evidence inventory, not a readiness verdict.

## Baseline

- Branch: `develop`.
- HEAD: `3c82fe9e7709e0f9bb8c0126f1db2e6e706b89e7`.
- Working tree: already dirty at audit start, including staged knowledge notes; modified backend, UI, audio-analysis and plugin files; deleted root handover/plan files; and untracked routes, tests, assets and scripts. Review targets the working tree, not just HEAD.
- Existing changes are user-owned and will be preserved. No application changes authorized.
- No AGENTS.md, CLAUDE.md or ancestor `.github/copilot-instructions.md` found in the inspected paths; scoped instruction search also found none.
- Existing README and historical reports contain claims requiring independent verification.

## Component inventory and investigation ownership

| Component | Initial scope | Current evidence status |
|---|---|---|
| `automix/` | Approval, execution boundary, receipts and external renderer dependency | Present; source trace pending |
| `mix-review/` | Local measurements, reference matching, numerical assumptions and tests | Present; request-to-result trace next |
| `chat/` | Chat entry points and overlap with main backend | Present; source trace pending |
| `evaluation/` | Qualification methods, fixtures and provenance of release claims | Present; source trace pending |
| `apps/backend/src/kenn/` | Server, routes, retrieval, action policy, Ableton orchestration | Present; source trace pending |
| `UX/` | Served frontend, API/streaming contracts, error states | Present; source trace pending |
| `plugins/kenn-vst3-au/` | JUCE host integration, real-time DSP and server client | Present; source trace pending |
| `apps/desktop/macos/`, `integrations/ableton-remote-script/` | Companion startup and Live bridge | Present; source trace pending |
| `common/`, `scripts/`, deployment manifests | Shared contracts, build/release reproducibility | Present; source trace pending |

## Guardrails and evidence limits

No secrets, user audio or private review responses will be read. No external services, model downloads, installations, DAW operations or deployments will be invoked. Static implementation, tests executed in this audit, historical runtime reports, and human validation will remain separate evidence classes.

Tool discovery found Node, CMake, CTest and Clang. No build or test has run yet. A shell glob for `plugins/kenn-vst3-au/build*` had no matches; this is not proof that no build artifacts exist elsewhere.

## Next evidence

Trace mix-review submission through the actual served API, local analysis and response. Parallel read-only reviews will cover backend/retrieval, plugin, and delivery/evaluation. This document will be replaced with the verified component and data-flow map after reconciliation.
