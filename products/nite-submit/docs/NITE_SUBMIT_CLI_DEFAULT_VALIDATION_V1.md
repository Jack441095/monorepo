# NITE Submit CLI default validation v1

Validation date: 25 August 2026

The CLI batch command now uses the same safe default as the app when no
`--template` is supplied:

```text
{student_id}_{project_title}
```

The student name remains available through an explicit template, for example
`{student_id}_{full_name}_{project_title}`, or through the app’s name-bearing
profiles.

## Real-PDF check

Command:

```sh
nitesubmit-cli batch real_validation_corpus/public_examples \
  --out real_validation_corpus/test_results/cli_default_validation.nkvENM \
  --student-id 75589 --dry-run
```

Result: `real_validation_corpus/test_results/cli_default_validation.nkvENM/`

- 2 real PDFs inspected
- 2 previewable dry-run results
- 0 review-required results
- 0 default outputs containing the detected student name

The report still records `student_name` as detected metadata, so a reviewer can
choose an explicit name-bearing rule without the default workflow silently
adding personal identity to the filename.

## Document identity policy

The CLI can also check whether the opening pages contain a student name, and
anonymous mode additionally flags explicit identity labels on later extracted
pages:

```sh
nitesubmit-cli batch real_validation_corpus/public_examples \
  --out /tmp/nite-submit-identity-results \
  --student-id 75589 --identity-policy name-prohibited --dry-run
```

This policy is separate from the filename template. `name-required` reports a
missing name for review; `name-prohibited` reports a present name for review.
The JSON and CSV reports include `document_identity_policy`,
`document_identity_status`, and `document_identity_reason`. No conflicting PDF
is written automatically.
