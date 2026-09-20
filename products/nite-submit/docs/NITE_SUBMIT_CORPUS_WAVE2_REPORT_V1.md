# NITE Submit controlled corpus wave 2

**Date:** 2026-08-24
**Status:** PASS — acquisition and dry-run complete

## Acquisition

Four additional PDFs were downloaded from official University of Essex,
University of Exeter, University of Manchester, and University of Washington
domains. They are public institutional guidance or title-page examples, not
private student-portal submissions. Their provenance and SHA-256 values are in
`NITE_SUBMIT_CORPUS_WAVE2_MANIFEST_V1.json`.

The PDFs remain local and gitignored. Only the manifest and this QA report are
intended to be retained in version control.

## Full-load dry run

The complete local corpus, including the existing validation set and the four
wave-2 PDFs, was processed with the local CLI in dry-run mode:

```text
records: 39
dry_run: 26
review_required: 13
failed_or_image_only: 0
```

The run took approximately 90 seconds on the current machine because it also
included several long dissertations and previously generated validation copies.
No PDFs were copied, renamed, overwritten, or written by this run.

## Findings for the next detector phase

- All 39 PDFs produced a project-title value or a review-required result.
- All 39 received the supplied test student number, as intended for batch
  testing when a document has no student number.
- The official guidance PDFs expose a known false-positive class: ordinary
  prose headings such as “Temporary Policy”, font descriptions, or procedural
  text can resemble a person name or project title.
- The detector hardening now rejects those guidance headings as person-name
  fallbacks. The 13 incomplete cases remain review-required because the
  supplied naming template requires a student name.
- The existing review gate correctly prevented all incomplete cases from
  becoming approved output names.

The next detector change should make title-page/name fallback more conservative
for guidance documents while preserving explicit labelled fields and genuine
title pages.
