# NITE Submit first-wave validation v2

**Date:** 2026-08-25
**Status:** PASS FOR REVIEWED FIELDS

## Scope

The governed manifest contains all 21 first-wave documents. Nine official
guidance/template PDFs are marked `layout_only`. The 12 public submission cases
are scored only for fields with reviewed truth. Group-author ambiguity, student
IDs, and module codes remain `UNREVIEWED` where they were not safe to assert.

## Result

```text
processed:              21
missing/unreadable:     0
wrong high-confidence:   0
student name:           10/10 precision and recall
university:             11/11 precision and recall
project title:          11/11 precision and recall
```

The machine-readable result is
`real_validation_corpus/manifests/first_wave_validation_v2.json`.

This is a field-scoped real-document gate. It does not claim that the detector
has been benchmarked for student-number or module-code recall on every source.
