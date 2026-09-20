# SLO UX/UI V3 Reality Audit

Audited against the current `PluginEditor`, `PrecisionBrowser`, `SampleCanvas`,
`SmartCollectionsPanel`, `ResultsPanel`, waveform preview and Standalone UI on
the V3 branch. This is an implementation audit, not a reconstruction from
older planning documents.

## Functional baseline retained

- LIST, MAP and SPLIT share selection through the editor callbacks.
- Search is debounced and applies to both map and browser.
- Browser supports audition, favorite state, native file drag and a
  virtualised table.
- Sample detail provides metadata, waveform, tags, preview, similarity,
  reference search, duplicates and Smart Collections.
- The right inspector is viewport-backed, so narrow heights scroll rather
  than silently clipping controls.

## Prioritised findings

### P1 — workflow blockers

No current crash, data-loss or blocked core workflow was observed in source or
the Standalone smoke launch. Host drag/drop and Ableton interaction remain
manual review gates, not claimed by this audit.

### P2 — workflow clarity

1. Scan Folder was visually placed inside selected-sample metadata, obscuring
   its global-library effect. Fixed in UX-D.
2. The browser gave no result count or actionable empty/no-results message.
   Fixed in UX-E.
3. Command-F was previously shadowed by the one-key favourite handler. Fixed
   in UX-A.
4. The dense map depended too heavily on saturated category colours. Fixed in
   UX-C by separating category and interaction state.
5. Browser-driven selection did not visibly return to the selected map point.
   Fixed in UX-F without changing sample or engine state.

### P3 — polish and coherence

1. Legacy KENN colours remained in map and waveform rendering. Fixed through
   semantic V3 tokens.
2. Header, search, workspace modes and inspector had equal visual weight.
   UX-A establishes a stronger compact hierarchy.
3. Browser headers and sample name hierarchy were generic table chrome.
   UX-B introduces a dedicated professional browsing treatment.

## Remaining review targets

- Manual Standalone interaction in LIST, MAP and SPLIT at minimum/default/wide
  sizes.
- Results, Smart Collections, reference search and duplicates overlays under
  real user data.
- AU/VST3 host sizing, keyboard handling and native file drag in Ableton.
- Full release targets, auval and two-instance smoke before owner review.
