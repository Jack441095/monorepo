# PX-E - Onboarding / Accessibility / Localisation Report

## Status

**PASS WITH LIMITATIONS**

The structural checks pass for naming, keyboard reachability, redundant state encoding, and reduced motion. The localisation stress test intentionally found overflow risks that must be handled by adaptive layout before UI promotion.

## Required Closeout

### ONBOARDING

The first-run journey is: install -> open -> select library -> scan -> understand classification -> search -> audition -> drag sample into DAW. Each stage needs a next action and a bounded failure state. The most important first-run explanation is what classification does and what remains unknown; it should not be a tutorial wall.

Required empty states: no library, scanning, no results, no favourites, no history, no similar samples, unknown/OOD, offline model unavailable, analysis failed, and permission denied. Each must state the next safe action.

Recommended progressive disclosure:

- Always visible: search, current results, audition, drag, and one clear status.
- Contextual: Find Similar, Find Complement, evidence, and proposal controls for the selected object.
- Advanced: weighting, reference controls, preview transforms, and model diagnostics.
- Hidden until needed: destructive or host-writing actions, with explicit permission and receipt.

### KEYBOARD

The audited SLO editor supports search focus, arrow movement in the browser, Space audition, F favourite, S similar, and Escape panel dismissal. The MAP has no equivalent complete keyboard path in the audited source. This is the biggest direct accessibility gap: a user can reach the list but cannot perform the same discovery workflow on the MAP.

### ACCESSIBILITY

The structural probe passed:

- Unique focus order.
- Named and keyboard-reachable controls.
- At least two encodings for each semantic state.
- Reduced-motion rule of instant transforms plus opacity only.
- No reliance on a colour-only state in the probe.

EMBER's frozen token system remains authoritative. Do not create a competing token system in this R&D home.

### LOCALISATION

The pseudo-locale fixture tested English, German-like expansion, Spanish, French, CJK-like expansion, and RTL-like expansion. It detected **9 width overflows** across the control fixture. CJK-like expansion produced 4; the English empty-state string itself exceeded its 320 px estimate. At 150% text scale, `Reject` and the empty-state copy required adaptive layout.

This is a structural estimate, not a font-rendering result. The implementation response should be wrapping, minimum-width adaptation, or a layout change, never truncation that hides an action. Technical notation remains Hz, kHz, dB, LUFS, ms, and BPM per the frozen localisation convention.

## Biggest UX Failure

The largest current failure is the gap between the mouse-friendly MAP and the editor's partial keyboard model, compounded by empty states that can become long or ambiguous under localisation.

## Highest-Value Fix

Define one focusable selected-sample object and make list, MAP, audition, favourite, similar, complement, and drag operations available through the same keyboard state machine.

## Promotion Decision

Promote focus order, semantic state redundancy, reduced-motion behavior, and adaptive text sizing as acceptance criteria. Require rendered JUCE testing, actual screen-reader verification where supported, real translated strings, and a 150% text-scale pass before release.

## Artifact

- [onboarding_accessibility_localisation_probe.py](../experiments/onboarding_accessibility_localisation_probe.py)
- [onboarding_accessibility_localisation_results.json](../experiments/onboarding_accessibility_localisation_results.json)
