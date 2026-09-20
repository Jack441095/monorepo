# NITE Submit accuracy validation v2

**Date:** 2026-08-25
**Status:** PASS FOR REVIEWED NAME/TITLE/UNIVERSITY SUBSET

## Scope

`real_validation_corpus/manifests/accuracy_manifest_v2.json` contains nine
public, single-author documents from UK repositories and public university
examples. Truth was reviewed for student name, university, and project title.
Student IDs and module codes are explicitly `UNREVIEWED` and are excluded from
metrics; they are not treated as absent.

## Result

```text
processed:              9
missing/unreadable:     0
wrong high-confidence:   0
student name:           precision 1.0000 / recall 1.0000
university:             precision 1.0000 / recall 1.0000
project title:          precision 1.0000 / recall 1.0000
```

The machine-readable result contains anonymous case IDs and metrics only:
`real_validation_corpus/manifests/accuracy_validation_v2.json`.

## Validator hardening

The validator now distinguishes:

- `ABSENT`: the field was reviewed and is not present;
- `UNREVIEWED` or an omitted key: the field is excluded from precision/recall;
- any other value: reviewed ground truth.

This prevents partial truth review from producing misleading false positives or
false negatives.

## Boundary

This is a reviewed subset result, not a claim about every university layout.
The older mixed 21-case manifest still contains guidance documents and
unresolved truth/normalization cases, so it remains an owner-review gate.
