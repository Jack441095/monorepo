# NITE Submit — Student-Name Profile Validation v1

> Historical profile run recorded before the current guidance-classification
> hardening. The source/output hashes and 43-file figures below are retained
> as the original evidence; current release evidence is in
> `NITE_SUBMIT_RELEASE_REPORT.md` and the release manifest.

Validation date: 25 August 2026
Packaged build: NITE Submit 0.2.0

## Rule tested

`{student_id}_{full_name}_{project_title}`

The rule was exercised through the packaged CLI with an explicit approval
manifest. Approval was required because the public Berklee PDF contains
medium-confidence inferred name and title fields.

## End-to-end write result

Source:

`real_validation_corpus/public_examples/75589_An_Ecosystem_of_Custom_Laser_Controlled_Devices.pdf`

Output:

`real_validation_corpus/test_results/us_coursework_write_check_latest.KKWfGm/Gomez_Juan_The_Invisible_Carnival_An_Ecosystem_of_Custom_Laser_Controlled_Devices.pdf`

Result: **processed**
Source modified: **no**
Output type: **regular PDF file**
Source and output size: **27,011,497 bytes each**
Source SHA-256: `8aefbadc85fd554316868b65af0bb1343408b927486cc822d2b16a563e7c23a9`
Output SHA-256: `8aefbadc85fd554316868b65af0bb1343408b927486cc822d2b16a563e7c23a9`

The dry-run matrix for the same rule covered all 43 qualified PDFs: 24 had
complete required name/title values available for preview, while 19 remained
review-required because they were guidance/template documents with missing or
uncertain submission fields. No dry-run item wrote a PDF.

The rebuilt combined report is retained at
`real_validation_corpus/test_results/combined_name_classification.798bos/`.
Its JSON/CSV schema includes `document_type` and `document_reason`; 17 files
were classified as guidance/templates, 26 files exposed a detected student
name, and 41 exposed a detected project title. Required-field gaps remained
explicit: 17 student-name gaps and 2 project-title gaps.
