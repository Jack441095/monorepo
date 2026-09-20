# NITE_SUBMIT_PRIVACY_REPORT

## Claim audit

| Claim | Evidence |
|---|---|
| No network access | No networking APIs anywhere in Sources/; no third-party dependencies |
| No document upload | Nothing to upload to — no backend exists |
| No telemetry/analytics | None integrated (deliberately excludes NITE Telemetry Foundation) |
| No accounts | None |
| Local-only persistence | `AppSettings` writes only template/preset/mode/case-style JSON |
| No document history | Extracted metadata lives only in session memory; nothing persisted |
| No logging of document text or identifiers | Product code performs no logging |

## Data flow

PDF → PDFKit (on-device) → in-memory text → in-memory detections → user-visible
UI → local file copy/rename. Nothing leaves the process except window contents.

## Stored data inventory

`~/Library/Application Support/NiteSubmit/settings.json`
keys: `template`, `presetId`, `renameMode`, `caseStyle`, `universityPresetId`.
No names, IDs, paths or content.

## Crash safety

File operations stage through temp files and verify SHA-256 content hashes;
a crash cannot corrupt the original document.

## Residual risks

- A future OCR or cloud feature would invalidate the "never leaves your
  computer" claim unless re-reviewed (positioning copy depends on this).
- macOS itself may cache recent-document metadata at the OS level outside the
  app's control.
