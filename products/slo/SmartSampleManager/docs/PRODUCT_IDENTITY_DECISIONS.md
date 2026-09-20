# SmartSampleManager — Product Identity Decisions

Phase 1, Sections 28-29. Plugin identifiers are load-bearing for DAW host compatibility — once real customer projects exist referencing this plugin, changing these breaks saved sessions. This must be finalised before any public beta, not after.

**Superseded, Phase 5.5**: the Phase 1 recommendation below to lock the original
`AECO`/`com.audioengineeringcompany.smartsamplemanager` identity was for a scenario where no
rebrand was pending. Jack subsequently approved the NITE DSP rebrand proposed in
`docs/NITE_DSP_PRODUCT_IDENTITY.md`, applied to `CMakeLists.txt` in Phase 5.5 (still before any
beta tester's DAW project could reference the plugin — the exact safe window this document warns
about). Current identity: `COMPANY_NAME "NITE DSP"`, `BUNDLE_ID
com.nitedsp.smartsamplemanager`, `PLUGIN_MANUFACTURER_CODE NDSP`, `PLUGIN_CODE AtSm` (unchanged).
See `docs/FINAL_PRODUCT_IDENTITY.md` for the decision record. The content below is retained as
the historical Phase 1 assessment, not the current state.

## Current identity (from `CMakeLists.txt:107-121`)

```text
project(SmartSampleManager VERSION 1.0.0 LANGUAGES C CXX)
COMPANY_NAME              "Audio Engineering Company"
PRODUCT_NAME               "Smart Sample Manager"
BUNDLE_ID                  com.audioengineeringcompany.smartsamplemanager
PLUGIN_MANUFACTURER_CODE   AECO
PLUGIN_CODE                 AtSm
FORMATS                     VST3 AU Standalone
ICON_BIG                    Resources/AppIcon-1024.png
```

## Assessment: these are NOT development placeholders

None of these look like JUCE's default scaffolding values (`Manu`/`Aten0`/`com.yourcompany.*`) — they're real, deliberately chosen values consistent with the actual company. This is good news: there is no "oops, we shipped `com.yourcompany.plugin`" risk here. The identity work already done is sound.

## Why these specific fields matter (and must not casually change)

- **`PLUGIN_MANUFACTURER_CODE` (`AECO`) / `PLUGIN_CODE` (`AtSm`)** — VST3/AU hosts use these (alongside the bundle ID) to identify a specific plugin across sessions. Changing either after a customer has saved a DAW project referencing this plugin will make that host treat it as a *different* plugin — the project will show a missing-plugin error, not gracefully re-link to an "updated" version.
- **`BUNDLE_ID`** — same risk on macOS; also affects `~/Library/Application Support/` paths some installers/updaters key off of.
- **`PRODUCT_NAME`** — shown in DAW plugin lists; changing it post-launch is a user-facing rename, not silently free even if the underlying codes stay stable.

## Gaps found (minor, worth closing before release — not identity-breaking)

| Field | Status | Recommendation |
|---|---|---|
| `COPYRIGHT` | Not set in `juce_add_plugin(...)` | Add before release — affects plugin metadata shown in some DAWs/AU validators |
| `COMPANY_WEBSITE` / `COMPANY_EMAIL` | Not set | Optional but commonly expected for a commercial listing; add once the website/support address exists |
| `PLUGIN_DESCRIPTION` | Not set | Optional, shown in some host plugin browsers |
| `VERSION` | Not passed explicitly to `juce_add_plugin` | Currently inherits the top-level `project(... VERSION 1.0.0 ...)` correctly via JUCE's CMake default — functional, but passing it explicitly would remove any ambiguity for a future contributor reading only the `juce_add_plugin` call |

## Decision required before public beta

**Recommendation: treat the current `COMPANY_NAME`, `PRODUCT_NAME`, `BUNDLE_ID`, `PLUGIN_MANUFACTURER_CODE`, and `PLUGIN_CODE` as final now**, since they're already real values with no placeholder risk, and lock them — do not let a later "let's rename it before launch" branding pass touch these four-character codes or the bundle ID. If a rename is wanted (different product name, different manufacturer code), it must happen **before** any beta tester's DAW project references this plugin, per Phase 29 of the master prompt. Adding the missing `COPYRIGHT`/company URL fields is a small, low-risk change that can happen any time before release without this constraint.
