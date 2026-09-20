# SLO Ableton/DAW Workflow Validation V1

**Purpose:** validate what's genuinely checkable from source code and tests, and be explicit about what isn't — this task cannot be fully closed without a live Ableton GUI session, which this environment doesn't have (this is B-004 in the existing blocker register, already tracked as blocked on Jack, not re-litigated here as if it were new).

## What's statically verified (real code, read directly, not assumed)

| Requirement | Verdict | Evidence |
|---|---|---|
| Drag sample from SLO to Ableton uses a real native OS file drag, not JUCE's internal component-drag mechanism | **PASS** | `PrecisionBrowser.cpp`'s own comment: *"The table's built-in [JUCE] description starts JUCE's internal component drag. Ableton needs a native macOS file drag, initiated by mouseDrag()"* — this is a deliberate, documented design choice, not an accident. |
| Original file path preserved (no copy/rename before drag) | **PASS** | Both drag call sites (`PrecisionBrowser.cpp:305`, `SampleCanvas.cpp:1103`) pass `samples[...].filePath` — the sample's actual indexed path — directly into `performExternalDragDropOfFiles()`. No temp-file staging, no renaming. |
| No unexpected copy/move during drag | **PASS** | Both call sites pass `canMoveFiles=false` to `performExternalDragDropOfFiles()` — this tells the OS/host the drag is copy-semantics (the receiving DAW references/imports the file, SLO's own copy is untouched), not a move. |
| Missing-file guard before drag | **PARTIAL** | `PrecisionBrowser.cpp` checks `file.existsAsFile()` before starting the drag; `SampleCanvas.cpp`'s drag path does not have the same guard. Not a safety bug (a missing file would just fail the drag at the OS level, nothing corrupts), but an inconsistency worth fixing for polish — dragging a stale/missing entry from the canvas view would silently do nothing rather than give the user feedback. |
| Preview before dragging | **PASS (backend)** | `AudioTransportSource`-based preview playback exists in the engine/processor, with `PreviewHistoryEntry` tracking recent previews — confirmed present in `SampleManagerEngine.h`/`.cpp` and `PluginProcessor.h`. Whether the actual UI affordance (a play button before drag) is wired up and discoverable is a Task 6 UI-audit question, not re-verified here. |
| AU/VST3/Standalone targets build | **PASS** | All three formats (`FORMATS VST3 AU Standalone`) build from the same `SmartSampleManager_VST3`/`_AU`/`_Standalone` CMake targets, verified this session (all three were exercised during the earlier RT-deadline-stress test work, per this session's history). |

## What genuinely cannot be verified from here

- **Whether the drag actually lands correctly inside a real, running Ableton Live session** — this requires a live GUI DAW, real mouse interaction, and Ableton's own file-import behavior, none of which are scriptable from a CLI/test-binary environment. This is exactly B-004 in the existing blocker register.
- **Whether the preview-before-drag UX is actually discoverable/usable** in the real plugin window — requires either a live run or a UI code audit deeper than this task's scope (see Task 6).
- **Host-specific edge cases** (e.g. does Ableton's own drag-acceptance behavior differ for VST3 vs AU vs Standalone contexts) — genuinely unknown without testing in the actual host.

## Verdict

The code-level guarantees this task can actually check — original path preserved, no copy/move/rename, native OS-level drag semantics — are real and correctly implemented, and this was verified by reading the actual drag call sites, not inferred from higher-level behavior. The parts that require a live Ableton session remain honestly unverified, not claimed. Recommend closing the one small inconsistency found (missing-file guard in `SampleCanvas.cpp`'s drag path) as a cheap follow-up, and leaving B-004 exactly as already tracked — blocked on Jack's live Ableton access, not an engineering gap this pass can close.
