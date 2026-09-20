# Final Product Identity — Decision Record

The current product-facing display identity is SLO. It is applied to `CMakeLists.txt`, the
product UI, and release tooling. The legacy project name and load-bearing host identifiers are
retained for compatibility.

## Applied identity

| Field | Value |
|---|---|
| `COMPANY_NAME` | NITE DSP |
| `COMPANY_COPYRIGHT` | Copyright (c) 2026 NITE DSP. All rights reserved. |
| `PRODUCT_NAME` | SLO |
| `BUNDLE_ID` | `com.nitedsp.smartsamplemanager` |
| `PLUGIN_MANUFACTURER_CODE` | `NDSP` |
| `PLUGIN_CODE` | `AtSm` (unchanged) |
| `COMPANY_WEBSITE` | `https://nitedsp.co.uk` (added Phase 5.6) |
| `COMPANY_EMAIL` | `nitedsp@outlook.com` (added Phase 5.6) |

`COMPANY_WEBSITE`/`COMPANY_EMAIL` were unset through Phase 5.5 -- no domain or email address had
actually been supplied to this codebase (confirmed by a repo-wide search that phase). Jack
supplied both directly in Phase 5.6; applied to `CMakeLists.txt` and rebuilt. Verified in the
generated artifacts: `moduleinfo.json` (VST3) shows `"URL": "https://nitedsp.co.uk"` and
`"E-Mail": "nitedsp@outlook.com"`; these two fields don't appear in the bundle's `Info.plist`
(JUCE surfaces them only via `JucePlugin_ManufacturerWebsite`/`JucePlugin_ManufacturerEmail`
preprocessor macros and the VST3 moduleinfo, not the Info.plist) -- confirmed by inspecting both
directly rather than assuming.

`PLUGIN_DESCRIPTION` was not applied -- this JUCE version's `juce_add_plugin()` has no
corresponding `DESCRIPTION` argument (verified against the vendored JUCE CMake source,
`JUCEUtils.cmake`); the field is cosmetic/optional per the original proposal, so this is not a
blocking gap.

## Status: applied and permanently immutable from this point

`BUNDLE_ID`, `PLUGIN_MANUFACTURER_CODE`, and `PLUGIN_CODE` are load-bearing compatibility
identifiers. Per `docs/PRODUCT_IDENTITY_DECISIONS.md`, treat them as frozen. The legacy CMake
project name `SmartSampleManager` is likewise retained for target/build compatibility; only the
display/product name is SLO.

## Enforcement

`scripts/verify_identity_manifest.py` checks `CMakeLists.txt` against
`docs/APPROVED_IDENTITY_MANIFEST.json` and fails CI on any unreviewed drift, in either direction.
The manifest now records the current SLO display identity while retaining the legacy
compatibility identifiers.

## Verification after applying

The current qualification build emits `SLO.vst3`, `SLO.component`, and `SLO.app`; the identity
guard and release manifest are now defined against those actual paths. A release-candidate
build (with bundled frameworks) must still be executed before claiming release-manifest passes.
The qualification preset intentionally omits bundled frameworks, so its manifest failure is an
expected configuration boundary rather than evidence that the SLO bundle naming is wrong.

## Where else the identity appears

`app/config.py`'s `email_from_name` and the website's copy (`nitedsp/website/app/layout.tsx`,
`page.tsx`, legal pages) already said "NITE DSP" from Phase 4 -- written ahead of formal
identity approval since the website/backend were always understood to represent the NITE DSP
commercial platform (`docs/PHASE_4_PLAN.md`), distinct from the plugin's own compile-time
identity which required this explicit approval step. No changes needed there this phase.
