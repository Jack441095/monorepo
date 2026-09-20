# NITE Submit controlled corpus wave 3

**Date:** 2026-08-24
**Status:** VALIDATION PASS WITH ONE PRIVACY REJECTION

## Acquisition

Three official US guidance PDFs and three openly licensed White Rose theses
were downloaded for local QA. The guidance documents are layout-only fixtures;
the theses are accuracy candidates with reviewed title/name truth.

The qualified PDFs remain local and gitignored. Manifests and this report are
the retained provenance; source PDFs are not redistributed.

## Screening

- 6 qualified PDFs added.
- 1 publicly accessible thesis rejected after inspection because its title page
  exposed a student number; it is retained only under
  `real_validation_corpus/rejected/wave3/` for auditability and is not in the
  qualified manifest.
- 1 host returned HTTP 403 to automated download; no bypass was attempted.
- No authentication or private student portal was used.

## Early detector observations

- The licensed theses provide real title-page names and long project titles.
- Three thesis names and full titles were detected at medium confidence after
  the evidence-backed detector correction pass.
- One thesis used a standalone `Author:` line with a middle initial; it is now
  protected by a regression test and remains medium confidence for approval.
- `The University of Sheffield` and all-uppercase university headings are now
  retained without truncation.
- Official guidance remains valuable for heading false positives and spaced or
  placeholder text extraction, but is not scored as student work.

## Next action

The full qualified corpus has now been run in dry-run mode. No batch output is
approved when required fields remain medium/low confidence; the next gate is
review of the remaining first-wave unreviewed truths. The reviewed thesis set has now passed
its dedicated validation gate:

```text
processed:              6 (3 accuracy candidates + 3 layout-only fixtures)
missing/unreadable:     0
wrong high-confidence:   0
name/title/university:  100% precision and recall on 3 thesis cases
approved test copies:    3, byte-identical to their sources
```
