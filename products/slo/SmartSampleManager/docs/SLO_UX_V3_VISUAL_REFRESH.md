# SLO UX V3 — Professional Control Surface Refresh

**Date:** 2026-09-14  
**Status:** implemented in the shared editor look-and-feel

## Intent

SLO should read like a focused pro-audio instrument: dense but calm, quick to
scan, and visually consistent at every window size.  The refresh keeps the
existing dark NITE DSP palette and interaction model, but removes the
platform-default JUCE bevels/gradients that made controls feel like a generic
utility application.

## Implemented

- Added `SLOLookAndFeel`, installed once at the editor root so controls in the
  inspector, browser, overlays, and smart collections share one rendering
  contract.
- Flat rounded controls with one-pixel warm borders and a clear amber focus /
  selected state; pressed and hover states use restrained surface washes.
- Compact bold button typography and consistent combo-box spacing/arrow
  geometry for a sharper, more legible scanning workflow.
- Focus-aware text-editor outlines and group-component treatment so editable
  metadata is visually distinct without adding noisy decoration.
- Neutral, narrow scrollbars that no longer fall back to JUCE's platform-blue
  chrome.
- Popup menus and tooltips inherit the same SLO surface/text ramp.
- View, transport, favorite, and similarity controls now explain their action
  and keyboard shortcut through contextual tooltips.
- Results, sort-preview, and Smart Collections overlays now explain their
  close/reset/save/copy/move actions with matching contextual tooltips.
- Refinement sliders and toggles now use a flat SLO renderer with explicit
  active tracks, compact thumbs, keyboard focus rings, and a clear checked
  state instead of stock JUCE chrome.
- Sound DNA aspect controls reflow to two rows of three in compact result
  overlays, keeping labels and touch targets readable at narrow widths.
- Sort/rename preview filters stack the search field above their safety tabs on
  compact windows, avoiding clipped controls while retaining the desktop row.
- Development AU, VST3, and Standalone bundles are re-signed after resource
  injection, so host-facing artifacts remain verifiable.
- The browser now has an intentional empty-state surface for an empty library,
  active scans, and zero-result searches instead of presenting a blank table.
- The map pane also has a first-launch onboarding card, so the default split
  view explains how to begin instead of showing an unlabelled empty canvas.
- The inspector now has a centered no-selection prompt and switches back to a
  left-aligned, high-contrast sample header as soon as a row is chosen.
- Category filters stay hidden until the scanned library provides real
  categories, keeping the first-launch toolbar focused on the actions that can
  actually make progress.
- Up/down navigation follows the visible filtered/sorted rows, and Escape clears
  the search field and returns focus to browsing.
- The selected-sample header exposes `HIGH CONFIDENCE`, `REVIEWABLE`, `NEEDS
  REVIEW`, `UNKNOWN`, or `UNCLASSIFIED` alongside the confidence value and
  winning evidence source, with state-aware colour and a full tooltip.
- Added a primary-toolbar `REVIEW QUEUE` action (also available with `R`) that
  opens low-confidence and classified-unknown samples in ranked order; user
  overrides and not-yet-scanned samples are intentionally excluded.
- Compact windows keep search, scan, and review actions reachable without
  crowding; infrequent sort controls yield their toolbar space at that size.
- At minimum-width windows, category filters now occupy a second horizontal
  pill row instead of disappearing, so filtering remains available without
  shrinking the primary actions below readable targets.
- Category pills expose their show/hide behavior through contextual tooltips,
  making the compact strip discoverable without adding another permanent label.
- An `ALL` pill (also available with `A`) restores every category filter in one
  click, so narrowing the map can always be reversed without manually
  re-enabling each category.
- Category-pill selections now filter the browser table as well as the map, and
  the result summary reports the filtered state consistently across LIST, MAP,
  and SPLIT.
- Category discovery during an active scan preserves the user's existing pill
  toggles, including an intentional all-off state, instead of resetting filters.
- The browser summary reports `filtered` only when rows are actually excluded;
  an all-enabled category strip does not create a misleading filtered status.
- Persisted taxonomy categories (with legacy instrument labels as fallback) from
  cached rows also repopulate the category strip before a new DSP pass completes,
  so restored libraries do not lose filtering controls during hydration.
- The editor performs an explicit first UI sync even when a restored cache has no
  new-sample event/version bump, preventing a populated library from opening with
  an empty filter strip.
- Restored editor dimensions are clamped to the same 700×520 minimum enforced
  by the resize handles, preventing old saved sessions from reopening clipped.
- Results overlays now notify the editor when their selection changes, so the
  Review Queue and similarity lists can be driven with the keyboard as well as
  the mouse.
- Results, Sort Preview, and Smart Collections overlays now take keyboard focus
  when opened and close reliably with Escape, even if a child control was last
  focused.
- The live engine status now uses a distinct ready/loading/degraded/failed
  color and explanatory tooltip, making model availability explicit without
  interrupting the browse workflow.
- Compact windows keep that status visible as a concise header chip, with the
  full DAW/scan/map context available on hover.
- Failed embedding attempts are now labeled `AI RETRY` / `AI FAILED` in the
  browser, the inspector header calls them out directly, and the Review Queue
  includes them with the attempt count.
- Transient failures expose a contextual `RETRY AI` action beside the selected
  sample's transport controls; permanent failures remain diagnosis-only.
- Secondary inspector actions (reference search, write-to-file, duplicate
  report, sort preview, and Smart Collections) now explain their scope and
  safety in contextual tooltips.
- The selected-sample card contracts when no retry action is needed and expands
  only for retryable failures, keeping the normal inspector dense and balanced.
- Scan status now reports an honest `Analysing done/total` counter and failure
  count, then switches to `Finalising library` while the projection completes.
- Active scans also show a thin progress rule beneath the toolbar, giving long
  operations a quiet visual heartbeat without obscuring the workspace.
- Browser selection is now tracked by file path as well as visible row index,
  so temporarily hiding a sample with search/category filters does not lose the
  user's place; clearing the filter restores the same row when it returns.
- Category filtering distinguishes three states across LIST/MAP/SPLIT: ALL
  categories enabled, a narrowed subset, and an intentional all-off state
  with no matching rows. The `ALL` pill is the explicit way back to the full
  library, including uncategorized/in-progress rows.
- The map keeps filtered points as spatial context but adds a restrained
  `NO MATCHING SAMPLES` card whenever an active search/category constraint
  yields zero visible points, matching the browser's honest empty-state copy.
- The `ALL` pill now reflects its active state, making the full-library view
  immediately legible without relying on the individual category colors.
- Category pills explicitly accept keyboard focus, so the horizontal filter
  strip is fully reachable with Tab as well as the `A` reset shortcut.
- Drag-and-drop now advertises only folders and supported audio formats, so
  unsupported documents do not trigger a misleading import affordance or enter
  the scan queue.
- Keyboard browsing now supports Return/Enter as an audition shortcut alongside
  Space, keeping the select-and-preview loop efficient in LIST and SPLIT.
- Library-level actions remain reachable in the no-selection inspector, which is
  especially important in compact AU/VST3 hosts where the top sort controls and
  Standalone menu bar are unavailable.
- When a selected sample is temporarily excluded by search/category filters, the
  inspector now says `HIDDEN BY FILTERS` and explains how to reveal the row.
- Search now has a visible one-click clear affordance alongside the existing
  Escape shortcut, including when a query is restored from the previous session.
- The map now accepts keyboard focus and shows a restrained focus ring, making
  keyboard-driven browse commands legible in MAP and SPLIT views.
- The LIST browser uses the same outer focus treatment (including when its
  child table owns focus), keeping keyboard navigation visually consistent.
- Newly queued rows now show `ANALYSING` in the category column until their
  background DSP/AI pass completes, instead of looking like missing metadata.
- First-run MAP and LIST empty states now include a direct `SCAN LIBRARY` CTA,
  wired to the same folder workflow as the toolbar action.
- Those empty-state CTAs now provide pointer feedback and a hover surface, so
  the hand-drawn affordance behaves like the rest of the control system.
- Mixed drag-and-drop payloads now say that unsupported items will be skipped,
  matching the import filter instead of leaving the user to infer what happened.
- Folder, reference-search, and evidence pickers now use lifetime-safe editor
  callbacks, so closing a hosted instance while a picker is open cannot leave a
  stale UI callback behind.
- Results and Smart Collections overlays now use the full workspace bounds in
  SPLIT mode, rather than inheriting only the browser rectangle left after the
  map/divider layout pass.
- Results, Sort Preview, and Smart Collections overlays now show the same
  restrained focus ring as MAP/LIST when keyboard focus enters the card, making
  Escape and arrow-key ownership visible during modal workflows.
- The MAP/LIST split divider now has a subtle hover/focus treatment and a
  centered grab handle, making the resize affordance discoverable without
  adding permanent visual noise; Up/Down nudge the split when the divider has
  keyboard focus and honor the same minimum pane sizes as mouse dragging.
- Map search now includes the same physical-acoustics labels as the browser,
  keeping LIST/MAP/SPLIT results aligned for material and stiffness queries.
- The selected inspector refreshes from asynchronous engine updates for its
  file, so classification/confidence and metadata changes appear without
  requiring a reselection; active text edits are left untouched until commit.
- Map selection is also path-stable across full sample-list replacements, so a
  re-sort or UMAP re-anchor cannot move the highlight onto a different file.
- Category style references are stable while new scan categories arrive, so a
  live map rebuild cannot invalidate cached color pointers during rehash.

## Safety and verification

This is a UX/observability change: no classifier decisions, cache contents,
file operations, sort policy, or audio-processing behavior is changed.  The
native `SmartSampleManager_Standalone` and the presentation, precision-browser,
smart-collections, sort-preview, search-lexicon, label-free-evidence,
similarity, reference-search, map-cluster, timbre-refinement, duplicate,
favorite, history, and XMP-writer tests all pass after the change. The existing
colour tokens remain the single source of truth. Multi-instance, resilience,
read-only safety, real-time deadline, cache-integrity, and prune-missing tests
also pass. The audio-evidence, audio-similarity, audio-features,
physical-acoustics, taxonomy, classifier-input-safety, cache-version,
cached-reclassification, persisted-cache-hydration, format-aware-scan,
malformed-audio, and path-traversal tests pass as well. AU validation (`auval`)
and strict code-sign verification pass for all three Apple bundles.

## Follow-up visual work

Remaining high-value UX work is release-level verification across LIST, MAP, and
SPLIT at three window sizes (700×520 minimum, 960×640 default-class, and a wide
1400×900 view). For each size, verify search/filter reachability, selection sync,
scrollable inspector access, drag-over guidance, empty/no-results states, review
queue and result overlays, and split-divider behavior. Repeat the same smoke
path in AU and VST3 hosts, including keyboard focus, native file drag, and two
simultaneous instances. Bulk file actions should remain explicitly
user-confirmed. The current desktop automation surface timed out resolving the
local bundle, so these visual checks remain a manual release gate rather than a
claimed automated pass.

Current evidence does include a real Standalone render at 1116×765: the
dark/amber hierarchy, centered no-selection onboarding state, compact
toolbar/status chip, map, browser, category strip, and scrollable inspector are
visibly present. The LIST workspace was also selected successfully in that
render, showing the result count, category pills, browser rows, and inspector
state through the accessibility tree. The desktop bridge timed out during the
subsequent resize/control sequence, so this is observation evidence only, not a
substitute for the full host checklist above.

A refreshed local Standalone run also confirms the restored-library path: 1,624
cached samples load with category pills visible in SPLIT, and the pill state is
exposed to the accessibility tree for keyboard/mouse toggling.
