# NITE Submit document identity validation v1

Validation date: 25 August 2026

Document identity is an optional policy separate from the filename template:

- **No rule** leaves the decision to the assessment brief.
- **Name required** checks the first two pages for a student name, where a
  cover sheet or title page normally appears.
- **Name prohibited** checks those opening pages plus explicit identity labels
  anywhere else in the extracted text. An unlabelled person name in body text
  is not treated as student identity because it may be a cited author.

## Real-PDF check

The final packaged CLI was run against the two PDFs in
`real_validation_corpus/public_examples`:

| Policy | Results | Outcome |
| --- | ---: | --- |
| `name-required` | 2 | 2 dry-run previews; both had a name in the first two pages |
| `name-prohibited` | 2 | 2 review-required; both reported `name_present` |

Reports:

- `real_validation_corpus/test_results/document_identity_name_required_final/`
- `real_validation_corpus/test_results/document_identity_name_prohibited_final/`

The anonymous-policy evidence is explicit: “Student name found in the first
two pages; anonymous work must not contain a name”. Conflicting files are not
written automatically. The JSON and CSV reports include the policy, status,
and evidence fields for audit. Explicit identity labels on later pages are
also held for review; body-text names without an identity label are not enough
to claim a reliable student-identity match.

This is a configurable safeguard, not a universal university rule. The user
must follow the current assignment brief: some non-anonymous work requires a
name on the document, while anonymous marking normally prohibits it.
