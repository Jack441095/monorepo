# NITE Submit beta validation report v1

**Date:** 2026-08-25
**Status:** Historical first-wave snapshot; superseded by the current release
report and private-beta handoff

> Current release evidence is recorded in
> [NITE_SUBMIT_RELEASE_REPORT.md](../NITE_SUBMIT_RELEASE_REPORT.md) and
> [NITE_SUBMIT_BETA_HANDOFF.md](../NITE_SUBMIT_BETA_HANDOFF.md). The current
> packaged build passes **244/244** deterministic checks; the qualified public
> batch contains **43 PDFs: 41 dry-run previews and 2 review-required cases**.
> This file preserves the original first-manifest harness result below and is
> not a current release scorecard.

## Harness result

The real-document validation harness processed all 21 documents in the first
manifest after relocating its stale absolute paths to the current checkout:

```text
processed:              21
missing files:           0
encrypted/unreadable:    0
wrong high-confidence:  10
```

The zero missing-file result confirms that the corpus can be validated from a
different checkout location. The harness continues to emit anonymous metrics
only; it does not write document text or personal values to the results.

## Interpretation

The precision/recall values from this run are not yet a release gate. Many
manifest truth values remain `UNREVIEWED`, and the corpus intentionally contains
guidance documents whose prose is not a student submission. Those cases are
useful adversarial fixtures but cannot be scored as definitive student-field
truth without review.

At the time of this original snapshot, the operational gate was therefore:

- 21-PDF first-manifest full-load run (the figures above are historical and
  are not the current 43-PDF release batch);
- Wave 4 official-US layout corpus: 5 processed, 0 missing/unreadable, 0 wrong
- Wave 5 official-US layout corpus: 6 processed, 0 missing/unreadable, 0 wrong
  high-confidence cases. These are layout-only samples, not student-submission
  accuracy evidence;
- dedicated wave-3 validation: 6 processed, 0 missing/unreadable, 0 wrong
  high-confidence cases, and 100% name/title/university precision and recall
  across 3 reviewed thesis cases;
- expanded accuracy validation: 9 processed, 0 missing/unreadable, 0 wrong
  high-confidence cases, and 100% name/title/university precision and recall;
- governed first-wave validation: 21 processed, 0 missing/unreadable, 0 wrong
  high-confidence cases, and 100% precision/recall for every reviewed name,
  title, and university field;
- targeted synthetic field-policy validation: 12 processed, 0 missing/unreadable,
  0 wrong high-confidence cases, 11/11 reviewed student IDs and 10/10 reviewed
  module codes correct; candidate-number separation explicitly preserved;
- 0 extraction failures or image-only failures;
- review-required items never written by batch mode;
- original-snapshot core regression suite at 189/189 checks;
- no wrong high-confidence values in the synthetic scored corpus.

The remaining accuracy gate is field-specific review of student IDs and module
codes, plus a deliberate group-author policy. Official guidance waves remain
explicitly labelled layout-only fixtures rather than student-submission
accuracy evidence.
