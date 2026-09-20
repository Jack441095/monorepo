# NITE Submit

Rename university assignments correctly in seconds.

Drop in your PDF. We detect the details. You check them. Get the correct
filename. Everything stays on your Mac.

NITE Submit reads a university assignment PDF locally, detects key identifying
information (student name, student number, university, module code/title,
project title), applies your naming rule, previews the result, and creates a
safely renamed copy or renames the original.

## Quick start

1. Open Submit.
2. Drop your assignment PDF.
3. Check the detected details.
4. Select a University profile if useful: Generic, Harvard-style, UK coursework,
   US coursework, Chicago-style, ID + student name, or Anonymous candidate number.
5. Choose or edit your naming rule.
6. Review any orange fields, evidence, and alternative candidates.
7. If a field shows alternatives, choose one from its **Use…** menu or edit
   the field manually; then click Approve details.
8. Preview and choose Create Renamed Copy.

For group work, select **Group ID + Project** from the naming-rule menu and
enter or confirm the explicit group ID. Multiple student names never become a
guessed group identifier.

Copying or renaming is disabled until the current document's required fields
have been explicitly approved. Module code and module title remain optional
unless the selected naming rule uses them; once used, every metadata-backed
field in the rule must be present before a filename can be created.

The Anonymous candidate number profile uses a separately detected candidate
number and never substitutes the saved student number for it. A missing
candidate number blocks the preview until it is entered or confirmed.

The **Document identity** setting is separate from the filename rule. Choose
**Name required in document** when the brief requires the student's name on the
submission, **Anonymous — name prohibited** when anonymous marking forbids it,
or **No rule (check brief)** when the department has not specified either. The
first two pages are checked; a conflict blocks approval and is shown in the
batch report.

Scanned PDFs receive bounded local English OCR on their first few pages. OCR
results are marked for review and never bypass the approval step.

The Harvard, UK coursework, US coursework, Chicago, and ID + student name profiles are generic, editable
starting points based on current public examples; they are not a claim that
every department uses one university-wide filename convention. Use the
student-name options for ordinary non-anonymous work only. If the assessment
requires anonymous marking, use the anonymous candidate profile or the exact
rule supplied by the department.

See [QUICK_START.md](QUICK_START.md).

Private beta testers: see [NITE_SUBMIT_BETA_HANDOFF.md](NITE_SUBMIT_BETA_HANDOFF.md)
for the artifact checksum, test missions, and privacy-safe feedback workflow.

## Privacy

Fully local. No upload, no account, no analytics, no network use.
Your assignment never leaves your computer. See [PRIVACY.md](PRIVACY.md).

## Build

Requires macOS 13+ and Swift command line tools.

```sh
swift build                 # debug build
swift run nitesubmit-tests  # full test suite + corpus evaluation
./tools/package_app.sh      # produce artifacts/Submit-1.0.0-macOS.app
./tools/run_full_corpus_write_check.sh  # verify both full 203-PDF write loads
```

## Command line

```sh
nitesubmit-cli suggest report.pdf --template "{student_id}_{module_code}_{project_title}"
nitesubmit-cli copy report.pdf --to ~/Desktop --name 12345678_Project
nitesubmit-cli batch real_validation_corpus/public_examples --out /tmp/nite-submit-results \
  --template "{student_id}_{full_name}_{project_title}" --student-id 75589 --dry-run
```

Batch dry-run writes only a JSON preview report; it does not create or rename
PDFs.
When `--template` is omitted, batch mode uses the same safe default as the app:
`{student_id}_{project_title}`. Use an explicit template or profile when the
course requires a student name in the filename.
Batch runs also write `batch_results.csv` beside the JSON report for quick review
in Numbers, Excel, or another spreadsheet application.
Each result records `document_type` (`likely_submission`, `guidance_template`,
`image_only`, or `unavailable`) and, when applicable, the classification reason.
With `--identity-policy name-required` or `--identity-policy name-prohibited`,
each result also records the document identity policy, status, and evidence;
conflicts are reported as `review_required` and are never written automatically.
Guidance/template warnings add review context; they do not replace the approval
gate. Normal batch mode writes only fully confident, template-complete likely
submissions; guidance/template documents are always held for explicit review,
and anything else requiring review is reported without creating a PDF.
After inspecting a batch report, an explicit local approval manifest can be
passed with `--approved-manifest` to allow only listed medium/low-confidence
items to be written; missing required fields still block. See
[docs/NITE_SUBMIT_BATCH_APPROVAL_V1.md](docs/NITE_SUBMIT_BATCH_APPROVAL_V1.md).

## Repository layout

- `Sources/NiteSubmitCore/` — extraction, detection, templates, sanitiser, safe file ops
- `Sources/NiteSubmitApp/` — macOS AppKit front end
- `Sources/nitesubmit-cli/` — CLI for scripted use and evaluation
- `Sources/NiteSubmitTests/` — deterministic test suite
- `tools/generate_corpus.py` — synthetic corpus generator (Python, dev-only)
- `tools/run_beta_intake.sh` — local-only authorised-PDF validation runner
- `tools/run_beta_intake_smoke_check.sh` — aggregate-only beta-validator privacy gate
- `tools/test_release_corpus_scope.sh` — fail-closed public/private corpus boundary check
- `tools/run_acceptance_sweep.sh` — categorized multi-PDF acceptance runner
- `tools/run_full_corpus_write_check.sh` — guarded 203-PDF ID/name write load
- `real_validation_corpus/beta_intake/` — ignored private beta intake workspace
- `docs/` — architecture, testing, release notes

## Status

Version 1.0.0 — PUBLIC RELEASE CANDIDATE, not yet cleared for sale. The app,
ZIP and DMG must pass the release-parity gate, then receive Developer ID
signing and Apple notarisation before public distribution. Governed real-file
validation passes for the reviewed fields, while naming presets remain generic
editable patterns rather than official university rules.
