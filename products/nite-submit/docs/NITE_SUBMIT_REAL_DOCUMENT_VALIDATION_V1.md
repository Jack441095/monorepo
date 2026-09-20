# NITE SUBMIT — REAL DOCUMENT VALIDATION V1

**STATUS: HISTORICAL — SUPERSEDED BY WAVE-3 VALIDATION**

> This document records the original pre-corpus state. The controlled corpus is
> now present and the governed first-wave and wave-3 runs pass for reviewed
> name/title/university fields. Field-specific review remains for student IDs,
> module codes, and group-author policy.

No owner-authorised real university/student PDFs were available during this
sprint. Per the privacy and authorisation policy, no documents were searched
for, scraped, or substituted. **No real-world accuracy claims are made.**
Synthetic results must not be extrapolated to real-world precision.

## How to supply the authorised corpus (owner instructions)

1. Collect 10–50 PDFs you are authorised to use (your own submissions,
   anonymised samples, or documents you have permission to test).
2. Place them in any local folder, e.g. `~/nitesubmit-real-corpus/`.
3. Create `real_manifest.json` alongside them:

```json
{
  "cases": [
    {
      "id": "case_001",
      "pdf": "/Users/you/nitesubmit-real-corpus/doc1.pdf",
      "category": "report",
      "truth": {
        "student_name": "Your Name",
        "student_id": "12345678",
        "university": "University of Example",
        "module_code": "ABC1234-30-3",
        "project_title": "Example Project Title"
      }
    }
  ]
}
```

- Fields genuinely not present in the document: use `"ABSENT"`.
- `category` values that help diversity: essay / report / dissertation /
  portfolio / cover-sheet / latex-exported / pages-exported / word-exported /
  template / short / long.
- The PDF paths stay on your machine; they are read locally at validation time
  and never copied into the repository or reports.

4. Run:

```sh
.build/release/nitesubmit-cli validate --manifest ~/nitesubmit-real-corpus/real_manifest.json \
    --out ~/nitesubmit-real-corpus/validation_results.json
```

Results JSON contains anonymous case IDs, status codes and confidence only —
no document text, personal values or private paths.

5. Optional ground-truth confirmation UI (avoids editing JSON):

```sh
.build/release/nitesubmit-cli review --manifest .../real_manifest.json \
    --progress .../review_progress.json
```

Walk each case with `[c]orrect / [w]rong / [m]issing / [s]kip`; progress is
saved after every case and can be resumed.

## Harness capabilities implemented this sprint

- Manifest-driven validation with anonymous case IDs and category tags
- Per-field precision / recall / HIGH-confidence precision
- Wrong HIGH-confidence case list (anonymised) for P0 forensics
- ABSENT-field handling (detected-when-absent counted as false positive)
- Image-only / encrypted / unreadable classification
- Latency percentiles (p50/p95/p99/max)
- Resumable keyboard review interface
