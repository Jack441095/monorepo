# NITE Submit field-policy validation v1

Status: PASS for the targeted synthetic regression set.

The manifest contains 12 generated local PDFs: labelled student-number cases,
institution-style ID variants, reference-noise cases, and one anonymous
candidate-number case. It is deliberately separate from the public-document
accuracy claims.

Latest result:

- processed: 12
- missing/unreadable: 0
- wrong high-confidence values: 0
- student ID: 11/11 reviewed values correct; precision 1.0000, recall 1.0000
- module code: 10/10 reviewed values correct; precision 1.0000, recall 1.0000

The anonymous candidate-number case is not scored as a student ID. This is an
intentional safety check: `Candidate No. A12345678` must remain a candidate
number and must never be silently substituted into a student-number filename
profile.

The source manifest is
`real_validation_corpus/manifests/field_policy_manifest_v1.json`. Values in
this set are generated test data, not real student records.
