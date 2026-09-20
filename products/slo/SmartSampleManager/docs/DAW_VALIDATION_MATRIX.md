# DAW Validation Matrix

Phase 5.5, Section 62. Structured template for recording REAL manual test results once a
signed build and clean machine are available. No row below is marked passing -- per Section 62,
"do not mark untested hosts as passing." This is a template, not a report.

Priority: Ableton Live first, Logic Pro second (AU), matching Section 41/62.

| DAW | Version | Format | Scan | Load | Audio | Drag/Drop | Save | Reopen | Result |
|---|---|---|---|---|---|---|---|---|---|
| Ableton Live | -- | VST3 | untested | untested | untested | untested | untested | untested | **NOT TESTED** |
| Logic Pro | -- | AU | untested | untested | untested | untested | untested | untested | **NOT TESTED** |
| Reaper | -- | VST3 | untested | untested | untested | untested | untested | untested | **NOT TESTED** |
| Bitwig | -- | VST3 | untested | untested | untested | untested | untested | untested | **NOT TESTED** |
| Studio One | -- | VST3 | untested | untested | untested | untested | untested | untested | **NOT TESTED** |
| Cubase | -- | VST3 | untested | untested | untested | untested | untested | untested | **NOT TESTED** |

## Column definitions

- **Scan**: DAW's plugin rescan finds Smart Sample Manager without errors.
- **Load**: Instantiating the plugin on a track succeeds, UI opens.
- **Audio**: Sample preview/playback produces correct audio.
- **Drag/Drop**: Dragging a sample from the plugin UI into the DAW's timeline/sampler works.
- **Save**: Saving a project with the plugin loaded succeeds.
- **Reopen**: Closing and reopening the DAW correctly recalls the plugin (not shown as
  missing/offline) -- this is the identity-immutability check from
  `docs/PRODUCT_IDENTITY_DECISIONS.md` in practice.

## How to fill this in

Follow `docs/CLEAN_MACHINE_TEST_PROCEDURE.md`'s steps 4-5 and 13-16 for each DAW/format
combination, recording PASS/FAIL per column and any notes (crash logs, error text) in a Result
column addendum. Only update a row after the test has actually been run.
