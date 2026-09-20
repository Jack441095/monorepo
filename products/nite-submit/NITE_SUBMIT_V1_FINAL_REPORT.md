# NITE_SUBMIT_V1_FINAL_REPORT

> Historical V1 snapshot. The current product is version 0.2.0 private beta;
> see `NITE_SUBMIT_RELEASE_REPORT.md` for current verification.

## Final status

**NITE SUBMIT V1: PASS WITH LIMITATIONS**

| Item | Status |
|---|---|
| REPOSITORY | NITE Submit product checkout |
| BRANCH | main |
| STACK | Swift 5 / AppKit + PDFKit (SPM), Python fpdf2 for dev-only corpus generation |
| APP VERSION | 0.1.0 (INTERNAL ALPHA) |
| MACOS APP | PASS — artifacts/NiteSubmit-0.1.0-macOS.app (ad-hoc signed) |
| DRAG/DROP | PASS |
| PDF TEXT EXTRACTION | PASS (PDFKit; image-only & encrypted detected gracefully) |
| STUDENT NAME | PASS — 100% precision on corpus (183/183) |
| STUDENT ID | PASS — 100% precision (189/189) |
| UNIVERSITY | PASS — 99.5% precision (202/203) |
| MODULE CODE | PASS — 100% precision (186/186) |
| PROJECT TITLE | PASS WITH LIMITATIONS — 98.4% precision on labelled/implicit set (190/193); implicit-title recall is the weakest area by design (precision-first) |
| CONFIDENCE SYSTEM | PASS — HIGH/MEDIUM/LOW/MISSING with human-readable source per field |
| MANUAL CORRECTION | PASS — every field editable; manual values always override extraction |
| TEMPLATE ENGINE | PASS — 11 variables, live preview, required-field gating |
| CUSTOM TEMPLATE | PASS — editable + persisted locally |
| PREVIEW | PASS — updates live while editing fields or template |
| SANITIZER | PASS — deterministic; forbidden/control chars, Unicode preserved, length caps |
| COLLISION HANDLING | PASS — refuse (default) / numbered copy / explicit replace |
| CREATE COPY | PASS — default mode; original untouched |
| RENAME ORIGINAL | PASS — explicit confirmation dialog; undoable |
| UNDO | PASS — restores renamed original to previous path |
| ORIGINAL BYTE PRESERVATION | PASS — SHA-256 verified in hard regression test |
| SYNTHETIC PDF CASES | 209 cases defined, 203 real PDFs (NITE_SUBMIT_PDF_CORPUS_V1) |
| FIELD EXTRACTION ACCURACY | see NITE_SUBMIT_PDF_EXTRACTION_REPORT.md |
| WRONG HIGH-CONFIDENCE RATE | 0.49% (1/203) — target < 1% |
| ADVERSARIAL CASES | PASS — staff names, reference IDs, path-like titles, multi-institution, whitespace, long titles |
| IMAGE-ONLY PDF | PASS — friendly message, manual entry, rename still possible |
| ENCRYPTED PDF | PASS — detected via header sniff + lock flag; no cracking attempted |
| LOCAL ONLY | YES |
| NETWORK REQUIRED | NO |
| PDF CONTENT UPLOADED | NO |
| TELEMETRY | NONE |
| ACCOUNT | NONE |
| BACKEND | NONE |
| AVERAGE PDF PROCESSING LATENCY | ~12 ms avg, ~210 ms max over 203-PDF corpus (debug build) |
| PEAK MEMORY | Not instrumented; PDFKit text-only extraction with page caps keeps footprint small |
| APP ARTIFACT | artifacts/NiteSubmit-0.1.0-macOS.app |
| SIGNED | Ad-hoc only |
| NOTARIZED | NO (owner policy before public distribution) |
| QUICK START | QUICK_START.md |
| LANDING COPY | docs/WEBSITE_COPY_AND_VALIDATION.md |
| OWNER DATA MODIFIED | NO |
| OTHER NITE REPOS MODIFIED | NO (read-only reference inspection only) |
| AI ATTRIBUTION | NONE |
| READY FOR PRIVATE BETA | YES WITH LIMITATIONS |

## Biggest success
A complete local-only pipeline — drop → extract → detect → correct → preview →
safe copy/rename — that never invents a value and provably preserves originals.

## Biggest limitation
Implicit (unlabelled) project titles rely on heading heuristics and remain the
weakest detection area; scanned PDFs need manual entry (no OCR).

## Recommended next step
Manual validation with real (authorised, non-sensitive) university PDFs, then
private beta.
