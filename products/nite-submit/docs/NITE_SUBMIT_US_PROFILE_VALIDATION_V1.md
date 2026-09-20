# NITE Submit US coursework profile validation v1

Validation date: 25 August 2026

## Profile

Display name: **US coursework (generic)**

Template:

```text
{last_name}_{first_name}_{project_title}
```

This is an editable, non-anonymous starting point based on public US
coursework examples. It is not an official university-wide rule. The existing
ID-only profile remains the default, and the anonymous candidate profile does
not include personal names.

## Qualified corpus dry run

Command:

```sh
artifacts/Submit-0.2.0-macOS.app/Contents/MacOS/nitesubmit-cli batch \
  <qualified-pdf-staging-dir> \
  --out real_validation_corpus/test_results/us_coursework_qualified_latest.1Z2Olm \
  --template '{last_name}_{first_name}_{project_title}' \
  --student-id 75589 --dry-run
```

Result: `real_validation_corpus/test_results/us_coursework_qualified_latest.1Z2Olm/`

- 43 PDFs inspected
- 25 previewable dry-run results
- 18 review-required results
- 0 collisions or failures
- 27 documents with a detected student name
- 41 documents with a detected project title
- 17 documents classified as guidance/template material

The review-required cases remain held because a name-bearing filename must not
be invented from weak or ambiguous evidence. Public university samples often
contain placeholders or guidance prose instead of a real student identity.

## Real write check

Source:

```text
real_validation_corpus/public_examples/75589_An_Ecosystem_of_Custom_Laser_Controlled_Devices.pdf
```

Output:

```text
real_validation_corpus/test_results/us_coursework_write_check_latest.KKWfGm/Gomez_Juan_The_Invisible_Carnival_An_Ecosystem_of_Custom_Laser_Controlled_Devices.pdf
```

The source and output are both regular PDF files. Their SHA-256 hashes match:

```text
8aefbadc85fd554316868b65af0bb1343408b927486cc822d2b16a563e7c23a9
```

The source remained unchanged. The test confirms that the student name and
project title are carried into the filename when the non-anonymous profile is
explicitly selected.
