# PX-C - DAW / Ableton Integration Report

## Status

**PASS WITH LIMITATIONS**

The safe value is context-aware audition and drag. Richer session understanding exists only through an optional Ableton-specific bridge and must remain explicit, permissioned, and portable by design.

## Portable DAW Context

Observed in the SLO JUCE host path:

- Host BPM.
- Host playing state.
- PPQ/playhead position, used for quantised audition starts.
- Plugin audio buffer channel/sample context needed for playback, but not a complete project model.
- Plugin project state for search text and naming-style preference only.

These are the portable context items found in the audited SLO integration. They do not imply access to the selected track or project arrangement.

## Ableton-Specific Context

Observed in the KENN Ableton OSC bridge and package documentation:

- Session track data and track indexes.
- Track volume, pan, mute, solo, and arm.
- Device parameter read/write and device creation.
- Clip load/launch and scene launch.
- Transport play/stop and tempo setting.
- A sidechain command and an optional Remote Script installation path.
- Ableton Folder Info XMP sidecar writing through the separate SLO writer utility.

Ableton Live 12 is the documented target. Writes are opt-in and the package documentation requires an explicit environment opt-in for live control.

## Unavailable / Unreliable in Portable SLO

The following were not found in the audited portable SLO host path and must not be claimed as automatic context:

- Selected track identity or track name.
- Selected clip and clip contents.
- Device chain topology and routing.
- Project key/scale.
- Project-level MIDI notes.
- Full track/master audio capture.
- Arrangement semantics and project file context.
- Reliable cross-instance project ownership.

The Ableton bridge may supply some of these through host-specific mechanisms, but that is a separate availability and permission state, not a portable plugin guarantee.

## Plugin / Companion Boundary

**Plugin owns:** immediate sample search result state, audition, transport-aware preview, keyboard focus, native file drag, and small project-scoped UI preferences.

**Companion or shared local runtime owns:** large model copies, library indexing, embeddings, background analysis, cross-instance coordination, and capability routing. The existing `nite_ai` Unix-domain runtime is the correct architecture to extend; do not introduce another IPC system.

**Ableton bridge owns:** explicitly enabled Ableton-specific read/write commands and their receipts. It must not silently broaden the portable plugin contract.

## Best DAW Integration Opportunity

A **transport-aware audition-to-drag handoff**: SLO uses portable BPM/playing/PPQ state to start previews predictably, keeps original versus rendered preview explicit, and initiates a native file drag without requiring the user to switch to a browser or manually locate the file. A second-stage evidence reference can be offered to KENN, but should not be required for the common path.

## Research Gaps

- Run a real Ableton Live 12 fixture with a test project and record context availability, drag behavior, undo, latency compensation, and failure recovery.
- Verify the native file drag and optional XMP sidecar workflow with a disposable synthetic library.
- Define a cross-DAW capability matrix before any portable API is expanded.

## Promotion Decision

Promote transport-aware preview and drag reliability to engineering discovery. Continue R&D on the Ableton bridge and companion boundary. Park automatic full-project interpretation until host availability, privacy, and human value are demonstrated.
