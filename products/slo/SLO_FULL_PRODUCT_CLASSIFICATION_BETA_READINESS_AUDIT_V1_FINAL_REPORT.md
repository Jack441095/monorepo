# SLO Full Product, Classification & Beta-Readiness Audit V1

## Executive decision

**Decision: E — BLOCKED BY EXTERNAL CREDENTIAL / DISTRIBUTION DEPENDENCY.**

SLO is a coherent local macOS product and a credible candidate for a tightly controlled, read-only internal classification beta. It is not release-qualified for an external/private beta distribution yet. The blockers are Developer ID/notarization/installer readiness, clean-machine validation, production licensing configuration and credentials, and an unqualified Ableton Live host path. Classification evidence also has material limitations: single-vendor evaluation, filename/folder leakage, weak Vocal Loop recall, and residual OOD false-known rates.

## Scope and safety receipt

- Mode: read-mostly qualification audit.
- Canonical repo: `/Volumes/Jack_Gandy_1TB_SSD/NITE_DSP/products/slo`.
- Branch: `engineering/build-system-optimisation`.
- HEAD at precheck: `dd60ddb31c66d8ee43f318764c0ac1f9eb972eef`.
- RC1 qualified worktree: `533849894660c2a42b08217f5d044367c3db68a5`.
- Audio-foundation probe: `301ad0a070b6d522b526d3809fcfd0f3a77035c4`.
- Owner/customer audio accessed: **No**.
- Protected holdouts rerun: **0**.
- Production plugin overwritten: **No**.
- Features added: **0**.
- Force pushes: **0**.

The checkout was already dirty before the audit. Existing worktree changes were preserved.

## Product classification

SLO is one product: Sample Library Optimiser, formerly Smart Sample Manager. Its shipping path is JUCE AU/VST3/Standalone plus a shared engine. CLAP, CLAP/foundation, V5, and other research artifacts are not shipping classifiers.

The production classifier is a hybrid: heuristic evidence from metadata/filename/folder/DSP, PANNs CNN10 embedding inference, a 16-class linear head, confidence/entropy diagnostics, nearest-centroid OOD gating, and a higher-priority evidence fusion path. This is useful product architecture, but it means audio-only accuracy and fused production accuracy are different claims.

## Strongest evidence

- Clean isolated Release configure completed for arm64 with plugin auto-install disabled.
- CMake now expresses explicit dependencies for generated `JuceHeader.h` and shared engine consumers; the known parallel build-order failure did not reproduce before this report was written.
- Fresh aggregate and fast qualification exposed a target-linkage blocker: helper-based engine tests fail with 13,044 duplicate JUCE symbols because JUCE module objects are linked both directly and through the shared engine-core linkage shape.
- Existing AU validation passed with `AU VALIDATION SUCCEEDED`.
- Installed AU/VST3 bundles are arm64, dependency-bundled, manifest-accounted, and have no Homebrew-path dependency leaks.
- Cache integrity, path traversal, malformed audio, XMP, taxonomy, and production-cache guard tests passed in the existing test tree; the clean-tree matrix is recorded separately.
- The core classifier, cache identity/versioning, async ownership, and path containment logic are visible and reviewable.

## Weakest evidence

- Ableton Live scan/load/render/drag/save/reopen was not qualified in this audit.
- Current clean-machine validation was not completed; the machine has Command Line Tools rather than full Xcode and no distribution signing identity.
- Licensing tests require a real server/key state and were not run.
- Historical V4-H evidence shows known accuracy of 76.4% overall, Vocal Loop recall 7.5%, and OOD false-known 41.6% on a thin, single-vendor corpus.
- Historical broad benchmark numbers are not general-library population accuracy and are vulnerable to filename/folder evidence.
- Historical performance evidence peaks at approximately 2.44 GB RSS for 170 files and leaves approximately 1.36 GB resident; current full-scale 1,000/10,000-file evidence was not regenerated.

## Beta recommendation

Approve only a **read-only classification beta** with explicit user confirmation before any move/rename operation, visible uncertainty/OOD states, no automatic deletion, synthetic or tester-owned fixtures, and a rollback/export path. Do not describe the classifier as audio-only or population-general until leakage-controlled, cross-vendor, blind-reviewed evaluation is complete.

## Required release gates

1. Remove duplicate JUCE module linkage from the affected test targets and rerun the clean aggregate Release qualification.
2. Configure production HTTPS licensing endpoint and validate entitlement/error paths with authorized credentials.
3. Obtain and verify Developer ID signing, notarization, installer/update flow, and clean Mac installation.
4. Qualify AU and VST3 in the supported Ableton Live version, including state persistence and project reopen.
5. Run a fresh leakage-controlled, cross-vendor classifier evaluation; complete blind AL-002 review before publishing a user-facing accuracy claim.
6. Add current RT instrumentation and a representative memory/soak gate.

See the linked subordinate reports and machine receipts in this directory.
