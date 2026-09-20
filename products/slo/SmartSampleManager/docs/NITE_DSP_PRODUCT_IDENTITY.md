# NITE DSP Product Identity — Final Proposal (Phase 3)

Phase 2 Section 5 / Phase 3 Sections 4-6. Supersedes the Phase 2 draft of this document (same
proposal, now in Phase 3's exact required format, plus the additional customer/account/installer-
facing fields Phase 3 asks for that Phase 2 didn't cover).

**Still true as of Phase 3**: no beta has shipped, no installer has been distributed, no external
customer has referenced this plugin's identity. This remains the last safe window to change these
values. **This document is a proposal — nothing below has been applied to `CMakeLists.txt`.**

# HUMAN APPROVAL REQUIRED

Every row in the table below requires your explicit sign-off before implementation. Do not treat
anything here as decided.

## Compile-time plugin identity

| Field | CURRENT | PROPOSED | RISK | HOST CONSEQUENCE | FINAL DECISION |
|---|---|---|---|---|---|
| `COMPANY_NAME` | Audio Engineering Company | NITE DSP | None | Cosmetic only — not used by hosts for plugin identity matching | **HUMAN APPROVAL REQUIRED** |
| `PRODUCT_NAME` | Smart Sample Manager | Smart Sample Manager (unchanged) | None | None | N/A — no change proposed |
| `BUNDLE_ID` | `com.audioengineeringcompany.smartsamplemanager` | `com.nitedsp.smartsamplemanager` | macOS treats this as a distinct app identity | Old `~/Library/Application Support/`/preferences paths keyed to the old bundle ID become orphaned; every machine that built the old identity (including this dev machine) needs a fresh scan/re-cache after the switch | **HUMAN APPROVAL REQUIRED** |
| `PLUGIN_MANUFACTURER_CODE` | `AECO` | `NDSP` | Every DAW host treats this as a different plugin | Any host with the old identity cached shows it as "missing" and the new one as newly discovered; local test DAW sessions referencing `AECO`/`AtSm` need re-linking | **HUMAN APPROVAL REQUIRED** |
| `PLUGIN_CODE` | `AtSm` | `AtSm` (unchanged) | None | None | N/A — no change proposed, see rationale below |
| `COPYRIGHT` | not set | `Copyright (c) 2026 NITE DSP. All rights reserved.` | None (metadata only) | None | **HUMAN APPROVAL REQUIRED** |
| `COMPANY_WEBSITE` | not set | *(pending domain — see `docs/HUMAN_COMMERCIAL_REQUIREMENTS.md`)* | None (metadata only) | None | **BLOCKED on domain acquisition** |
| `COMPANY_EMAIL` | not set | *(pending support address — see `docs/HUMAN_COMMERCIAL_REQUIREMENTS.md`)* | None (metadata only) | None | **BLOCKED on domain acquisition** |
| `PLUGIN_DESCRIPTION` | not set | `AI-powered sample library manager with acoustic similarity search` | None | Shown in some host plugin browsers | **HUMAN APPROVAL REQUIRED** |

### Why `PLUGIN_CODE` (`AtSm`) is proposed unchanged

The plugin code identifies the *product*, not the company. `PRODUCT_NAME` isn't changing, only
the manufacturer. Hosts key plugin identity off the combination of manufacturer code + plugin
code + bundle ID — changing the manufacturer code alone already forces a "new plugin" re-scan in
every host, so there's no compatibility reason to also touch the plugin code. Keeping it stable
minimizes the blast radius to exactly the fields that need to change.

### Why `NDSP` is a valid manufacturer code

Exactly 4 characters, not JUCE's default placeholder (`Manu`), not all-lowercase (rejected by
Steinberg's VST3 SDK as reserved). Mixed/all-uppercase is accepted — the existing `AECO` code is
itself all-uppercase and already proven to build and pass AU validation in this exact project. No
registration authority exists for VST3/AU manufacturer codes, so any non-reserved 4-character
code is valid. Chosen for direct legibility (**N**ite **D****S**P) over an arbitrary string.

## Customer/account/installer-facing names (new for Phase 3)

Phase 3 asks these to be decided explicitly, separate from the compile-time codes above — these
are strings shown to a customer, not load-bearing plugin identity, so they carry no
DAW-compatibility risk and can be revised later without breaking anything.

| Field | PROPOSED | RISK | FINAL DECISION |
|---|---|---|---|
| Installer display name | "Smart Sample Manager" | None — cosmetic, `.pkg` display only | **HUMAN APPROVAL REQUIRED** |
| Application (Standalone) name | "Smart Sample Manager" (unchanged, matches `PRODUCT_NAME`) | None | N/A — no change proposed |
| Support-facing product name | "Smart Sample Manager" | None | **HUMAN APPROVAL REQUIRED** |
| Account-facing product name (NITE DSP Account "My Products" list) | "Smart Sample Manager" | None | **HUMAN APPROVAL REQUIRED** |

Recommendation: use the identical string ("Smart Sample Manager") everywhere a customer sees the
product name — installer, app, support docs, account dashboard, downloads page. A single
consistent name reduces support confusion ("is this the same thing I bought?") far more than any
marginal benefit from context-specific variants.

## What this document does NOT decide

- The actual domain name for `COMPANY_WEBSITE`/`COMPANY_EMAIL` — ownership must be confirmed
  first. Do not hardcode a guessed domain anywhere in source or on the website.
- Final legal company name / incorporation status of "NITE DSP" — a business/legal decision
  outside this codebase's scope.
- Whether `PRODUCT_NAME` itself should change (e.g. "NITE DSP Smart Sample Manager") — the
  website's own company-first hierarchy (`docs/NITE_DSP_WEBSITE_ARCHITECTURE.md`) already
  establishes NITE DSP as the brand context around the product without needing it folded into
  the plugin's own in-DAW name, which has limited display space in most host plugin lists.

## Recommendation

Adopt as proposed once you confirm. Once implemented (a single, well-scoped `CMakeLists.txt` edit
plus a rebuild — Phase 2's dependency-bundling and async-startup work is unaffected by an
identity change), treat `BUNDLE_ID`, `PLUGIN_MANUFACTURER_CODE`, and `PLUGIN_CODE` as permanently
immutable. This remains the last point before any real customer or beta tester DAW project can
reference them — see `docs/PRIVATE_BETA_PLAN.md`'s beta-readiness gate, which depends on this
decision being finalized first.
