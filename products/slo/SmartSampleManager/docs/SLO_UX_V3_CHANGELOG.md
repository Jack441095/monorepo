# SLO UX/UI V3 Changelog

## UX-A2 — Website V3 brand handoff

- Aligned the native token vocabulary with the live Website V3 reference:
  green remains operational, while the Website V3 blue is reserved for
  product/discovery context.
- Kept amber for experimental/cautionary actions and red for stop/failure;
  no engine, cache, audio-thread or licensing behavior changed.

## UX-A — Design system and application shell

- Standardised semantic interaction surfaces, disabled text, large radius and
  compact-control tokens.
- Replaced remaining legacy KENN waveform colours with NITE DSP semantic
  tokens.
- Reframed the header as `NITE DSP / SLO`, with workspace modes and live
  context given clearer hierarchy.
- Made library search more prominent, labelled for its real filter scope and
  exposed its ⌘F shortcut.
- Increased inspector width and strengthened its selected-sample role.
- Corrected shortcut precedence so ⌘F focuses search rather than triggering
  the single-key favourite action.

## UX-B — Precision browser

- Clarified the core sample column and compact status columns.
- Introduced a deliberate table-header treatment and stronger sample-name
  hierarchy while retaining the virtualised browser implementation.

## UX-C — Discovery workspace

- Replaced the remaining legacy map palette and surfaces with the V3 token
  system.
- Made selection, hover and tooltip focus independent of category colour so
  map navigation is legible for more users and less visually noisy.
- Kept map filtering, spatial indexing, pan/zoom and engine ownership intact.

## UX-D — Sample context

- Moved Scan Library from the selected-sample inspector into the workspace bar,
  making it clear that scanning changes the library rather than the selected
  sample.

## UX-E — Search feedback

- Added live browser result counts and deliberate empty/no-results guidance,
  making search state visible without changing filtering or query execution.

## UX-F — Cross-view selection

- Made browser, result and collection selections visibly update the map’s
  selected point, completing the existing map-to-browser selection loop.

## UX-G — Responsive shell

- Added a compact-width breakpoint: live status and category chips step back
  before controls collide, while search, Scan Library, view modes, workspace
  and inspector remain reachable.
