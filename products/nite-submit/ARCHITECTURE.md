# ARCHITECTURE — NITE Submit 0.1.0

> Historical architecture snapshot. Current OCR, batch, safety, and
> localization notes are maintained in source and the current `docs/` reports.

## Stack decision

**Swift 5 / AppKit + PDFKit, packaged with Swift Package Manager.**

Chosen over Electron/Tauri/Python-wrappers because it gives a native macOS
experience (real drag-and-drop), uses the system PDF parser (no bundled
runtime), produces a tiny binary, requires zero third-party dependencies, and
is fully offline-capable by construction. Python (`fpdf2`) is used only as a
dev-time corpus generator and is not shipped.

## Layers

```
PDF bytes
   │  PDFExtractor (PDFKit wrapper; bounds, control-char stripping)
   ▼
PDFTextDocument { pages → lines }
   │  FieldDetector (deterministic label + pattern heuristics)
   ▼
SubmissionMetadata { Detection: value + confidence + source + candidates }
   │  user correction (manual values always win)
   ▼
TemplateEngine ──► FilenameSanitizer ──► preview / final base name
   │
FileOperator (copy / rename / collision policy / hash verification / undo)
```

### Extraction

`PDFExtractor` wraps `PDFDocument`. Resource bounds: max 2000 pages, per-page
character caps. Control characters and default-ignorable code points are
stripped from untrusted text. Metadata is treated as an untrusted hint only.
Image-only and encrypted/malformed PDFs surface as friendly domain errors
(`imageOnly`, `encrypted`, `unreadable`) — never crashes, never stack traces.

### Detection

`FieldDetector` is deterministic: labelled-value matching (longest-label-first),
configurable student-ID regex patterns, staff-name exclusion lists for name
detection, module-code pattern matching, institution-name recognition plus a
page-1 heading heuristic, and a project-title pipeline
(explicit labels → repeated/heading ranking → metadata last resort).

Every field returns `Detection { value, confidence(high/medium/low/missing),
source, rule, candidates }`. Precision beats recall: nothing is reported HIGH
without strong evidence; missing values stay missing (no hallucination).

### Naming

`TemplateEngine` renders `{variable}` templates, gates on required fields
(blocks the rename instead of guessing), collapses separators left by empty
optionals. `FilenameSanitizer` strips forbidden/control characters, preserves
Unicode, offers case styles, caps length grapheme-safely.

### File safety

`FileOperator` defaults to non-destructive behaviour:
- CREATE COPY (default) copies via temp file then moves into place;
- RENAME ORIGINAL verifies SHA-256 before/after (content provably unchanged);
- collision policies: refuse (default), numbered copy, explicit replace;
- undo restores a renamed original to its previous path.
Operation receipts are kept for the session.

## Future-proofing (architecture only, not implemented)

- **Bundle mode:** `SubmissionMetadata` is file-type agnostic; one PDF can
  provide metadata that renames accompanying video/zip/audio files.
- **University presets:** `NamingPreset` schema already supports
  VERIFIED / CUSTOM / USER-CREATED statuses and required-field lists.
- ~~**OCR/local-AI fallback**~~ — implemented since this snapshot was written:
  `PDFExtractor` now falls back to Vision (`VNRecognizeTextRequest`) for
  image-only PDFs, feeding `FieldDetector` the same way as native text, at
  reduced confidence. See `PDFExtractor.swift` and `DetectorTests.swift`.
- **Entitlement hook:** `EntitlementProvider` protocol exists; V1 ships an
  always-open implementation. No DRM.
