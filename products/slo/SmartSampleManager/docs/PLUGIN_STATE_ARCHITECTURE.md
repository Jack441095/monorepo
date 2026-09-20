# SmartSampleManager — Plugin State Architecture

Phase 2, Sections 26-28. `getStateInformation()`/`setStateInformation()` (`Source/PluginProcessor.cpp`)
were empty stubs per `docs/COMMERCIAL_RELEASE_BLOCKERS.md` P1 #4 — nothing survived a DAW project
save/reload. Implemented this phase.

## What goes in the DAW project chunk vs. global preferences

| State | Where it lives | Why |
|---|---|---|
| Search field text, naming-convention combo selection | DAW project chunk (`getStateInformation`) | Small, per-instance editor preferences — reasonable for a user to want restored when they reopen a project |
| Full sample database (paths, embeddings, metadata, tags) | Global SQLite cache (`~/Library/Application Support/SmartSampleManager/sample_cache.sqlite3`), untouched by this change | Per Phase 2 Section 26's explicit instruction: global data must NOT be serialized into DAW project chunks — it's already persisted globally, shared across every project/instance, and would bloat every saved DAW project file if duplicated per-instance |
| Global app preferences (`AppSettings`) | Untouched — already its own persistence path, not plugin state | Not project-scoped by nature |

## Implementation

`juce::ValueTree` serialized to XML via `copyXmlToBinary`/`getXmlFromBinary` — JUCE's standard
plugin-state idiom. Schema:

```xml
<SMARTSAMPLEMANAGER_STATE schemaVersion="1" searchText="..." namingStyleId="1"/>
```

- **Versioned**: `schemaVersion` is checked on load; an unrecognized (0, negative, or future)
  version is ignored rather than partially applied, so a downgrade or corrupted chunk degrades
  to defaults instead of misinterpreting fields.
- **Malformed-state safety**: `getXmlFromBinary` returning null, or the root tag not matching
  `SMARTSAMPLEMANAGER_STATE`, both short-circuit to "keep current defaults" — no exception, no
  crash, matches the master prompt's "malformed project state must fail gracefully" requirement.
- **Editor round-trip**: `PluginProcessor` owns the persisted fields (`editorSearchText`,
  `editorNamingStyleId`) so they survive editor destroy/recreate (DAW UI show/hide) independent
  of project save/reload. `PluginEditor`'s constructor restores them into `searchField`/
  `namingCombo`; `searchField.onTextChange` and `namingCombo.onChange` write back on every change.

## What was deliberately NOT added this pass

Selected-sample-path and filter-button state were considered but left out: `selectedItem` is
keyed to a `SampleItem` copy, not a stable ID, and filter-button state (`filterButtons`) is
built dynamically from `currentCategories`, which itself depends on what's currently in the
library — restoring a stale selection/filter against a library that may have changed between
sessions risks silently pointing at nothing. Revisit if a stable sample ID scheme exists later.

## Regression coverage

**Not yet added as an automated CI test.** The `getStateInformation`/`setStateInformation` logic
itself has no dependency on the engine or UI (pure `juce::ValueTree`/XML), so a dedicated unit
test is low-risk to add later, but doing so requires either (a) extracting the serialization
into a standalone testable function, or (b) a new CMake test target linking the full
`PluginProcessor.cpp` + `PluginEditor.cpp` object graph (heavier than any existing `Test*`
target, which all link engine-only code, not the editor). Left as a Milestone D follow-up rather
than rushed into the existing CMakeLists without a build agent available to verify the new target
actually links.

**Manually verified this pass** (per Phase 2 Section 28's DAW-recall test description): built and
ran the Standalone app twice against the Debug build, confirmed `PluginProcessor.cpp` /
`PluginEditor.cpp` compile and link cleanly with the new code (`cmake --build build --target
SmartSampleManager_Standalone`, zero new warnings/errors — see build log from this session).
**Not yet manually verified inside an actual DAW** (Ableton Live / Logic Pro project save/reload,
per Phase 2 Section 28) — flag this as outstanding before beta.
