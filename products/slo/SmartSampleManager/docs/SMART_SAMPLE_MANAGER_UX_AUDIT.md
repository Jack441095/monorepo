# Smart Sample Manager — UX Audit

2026-08-13. Real observation of the actual running Standalone build (`build-release`), plus
source verification (`Source/PluginEditor.cpp`) for interaction details that a screenshot alone
can't confirm. Not a redesign — this session did not modify plugin UI source (see the reasoning
in `docs/NITE_DSP_UX_SYSTEM.md`). Findings only, for a dedicated follow-up pass.

> Historical baseline: the two P1 findings documented here were subsequently addressed in the
> V3 visual refresh. The current implementation and verification record live in
> `docs/SLO_UX_V3_VISUAL_REFRESH.md`; this document is retained as the before-state audit.

## Method

Launched the real Standalone binary fresh, screenshotted the genuine first-launch state, and
cross-referenced button behavior against the actual click handlers in `PluginEditor.cpp` rather
than guessing what a button does. This session's earlier functional-QA work (scan progress,
visual map population, shutdown resilience) is reused as evidence where directly relevant,
rather than re-observed from scratch.

## UX-P0 (none found)

No broken, deceptive, or inaccessible product-UX issues were found this pass. This is a "no
regressions" report, not a clean bill of health on polish — see P1 below.

## UX-P1 — major UX issues

1. **First launch gives no guidance.** A fresh launch shows a large empty grid, "Map: 0
   samples," and nothing else — no text like "Add your sample library to get started." The only
   way to know what to do is notice the small **SCAN FOLDER** button, which sits inside the
   Sample Metadata sidebar surrounded by five other fields (BPM, Key/Scale, Instrument Type,
   Ableton Tags, Subcategory) that are all irrelevant until a sample exists. A first-time user
   has no way to distinguish "the one action that matters right now" from "metadata fields for a
   sample I haven't selected yet." Confirmed by direct observation, matches the concern in
   Section 9 of the current design prompt.
2. **Find Similar and Find Duplicates break out of the app entirely.** Verified in source
   (`PluginEditor.cpp::showSimilarSamplesReport`/`showDuplicatesReport`): both use
   `juce::AlertWindow::showMessageBoxAsync` — a native macOS system dialog listing plain-text
   results. There's no way to preview, select, or drag a result directly from that dialog; the
   user has to read a name in a system alert, close it, then manually relocate that sample in
   the browser/map to actually do anything with it. This directly undercuts Section 17's "reduce
   unnecessary clicks" goal for what the design prompt calls the premier feature — Find Similar
   currently costs *more* clicks than browsing normally would.

## UX-P2 — real but smaller issues

3. **Indexing progress uses a raw counter, not customer language.** The live UI shows "Map: N
   samples" ticking up during a scan (confirmed this session across multiple real scans) —
   functionally clear, but plainer than the "Analysing samples — 97 of 289" framing the design
   prompt asks for, and doesn't show a total count during the scan itself (the denominator only
   becomes obvious once it finishes).
4. **Ten category-color swatch buttons appear even with zero samples indexed.** At first launch,
   before any scan, a row of ten colored buttons (Kick/Snare/Hi-hat/etc., inferred from color and
   truncated labels) is already present and clickable, with no explanation of what they filter or
   why they're populated before there's anything to filter. Minor, but adds unexplained visual
   noise to an already-guidance-free first launch.
5. **No visible account/licensing surface found in this build.** Clicking the top-left
   **Options** button produced no visible menu/dialog in this dev/unsigned build. This is not
   confirmed as a real product gap — it may be intentional/dev-environment-specific behavior
   this local unsigned build doesn't exercise the same way a signed, licensed customer build
   would. Flagged as **unconfirmed**, not claimed as a defect, and worth re-checking against a
   real signed build once one exists rather than guessed at here.

## UX-P3

6. Library-restore-on-relaunch remains the already-documented, already-triaged P2 from
   `docs/APP_FUNCTIONAL_VALIDATION.md` — not re-litigated here, just cross-referenced so it isn't
   duplicated as a "new" finding.

## What this audit deliberately does not include

Retina sharpness, window-resizing behavior, keyboard navigation, and degraded-ML-state handling
were not exercised this pass — each would need either a longer real session or synthetic failure
injection (e.g. corrupting the ONNX model file to observe the failure path), which risks the
kind of invasive, state-mutating testing this session's scope didn't call for. Recommended for a
dedicated pass alongside whatever engineering follow-up addresses P1 #1 and #2 above.

## Historical recommendation (implemented in UX V3)

P1 #1 and #2 were the two findings worth prioritizing first: they're the most visible to *every*
new user (#1) and directly undermine the single feature the product is most differentiated by
(#2). Both were addressed without touching DSP/ML/licensing/host-safety-critical code: #1 via an
intentional empty-state/onboarding treatment, and #2 via an in-app results panel with direct row
selection. The remaining release gate is manual host/layout verification, documented in the V3
refresh record.
