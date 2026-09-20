# NITE SUBMIT — V1.1 BETA READINESS

## Product stage

PRIVATE BETA RC1 (version 0.2.0). Ad-hoc signed; not notarised.

## Safety posture (unchanged from V1, re-verified)

- Default action remains **Create Renamed Copy**.
- Rename Original requires an explicit confirmation dialog and supports undo.
- Collisions: refuse by default; numbered copy offered; replace never silent.
- Original bytes preserved (SHA-256-verified regression test).
- No content modification of any PDF.

## Privacy posture

Local-only. No network code exists in the product. Settings JSON stores the
template, preset, mode, case style, university profile, and optional saved
student number only. Extracted metadata is session-memory only. Real-document
validation harness reports anonymous IDs and status codes; private values are
withheld from machine-readable output by design.

## UX / accessibility audit

- Confidence is conveyed by **text + symbol**, not colour alone:
  "✓ Found" / "? Check" / "! Missing".
- Every field has a VoiceOver label ("<field> field"); confidence labels are
  separately accessible ("… confidence").
- Full keyboard flow: drop zone accepts click-to-browse alternative to drag &
  drop; Return triggers Create Renamed Copy.
- First-run comprehension: single window — drop zone → fields → rule →
  preview → one primary button. No onboarding tour required.
- Error messages are human sentences ("We couldn't read this PDF.",
  "This PDF appears to be scanned or image-only.", "This PDF is
  password-protected.").

## Performance & memory (Release build)

| Metric | Value |
|---|---|
| PDF processing p50 | 1.3 ms |
| p95 | 2.2 ms |
| p99 | 3.9 ms |
| max observed | ~215 ms (largest synthetic doc) |
| Peak RSS, 233-doc batch | ~38 MB |
| Memory growth across batch | none observed |

The app feels instantaneous for normal documents on Apple Silicon.

## Filesystem behaviour verified

Unicode/accents preserved · forbidden characters sanitised · length capped
grapheme-safely · collisions refused or numbered, never silently replaced ·
missing source/destination produce understandable errors · zero-byte files
handled · copy staged via temp file then moved (crash-safe against partial
copies).

## Installation experience (ad-hoc signed artifact)

1. Copy `Submit-0.2.0-macOS.app` anywhere (e.g. /Applications).
2. First launch: right-click the app → Open → Open (one time).
   Do NOT disable Gatekeeper globally.
3. Removal: delete the app; delete
   `~/Library/Application Support/NiteSubmit/settings.json` if desired.

No developer tooling, Python, or build artifacts are needed at runtime
(verified: release binary links only system frameworks).

## Beta missions

See docs/BETA_FEEDBACK_TEMPLATE.md (M1–M8) with matching feedback questions.

## Known limitations

- macOS 13+ only; Apple Silicon build.
- Bounded local English OCR covers the first few pages of image-only PDFs;
  OCR-derived fields remain review-required and manual entry is always
  available.
- Presets are generic patterns, not official university rules.
- Not Developer-ID signed / notarised (owner policy gate before public release).
- The macOS UI now supports a multi-file queue (each file keeps its own
  independent detection/review/approval state). The local CLI separately
  provides scriptable batch dry-run/processing, collision controls, and
  JSON/CSV reports.
