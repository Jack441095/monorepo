# NITE Submit — Private Beta Handoff

**Version:** 0.2.0 · PRIVATE BETA INTEGRATION CANDIDATE
**Platform:** macOS 13+, Apple Silicon
**Purpose:** Validate real university PDFs locally before wider distribution.

This candidate is registered in isolated Railway staging, and the exact
checksum-bound remote download has been independently reverified. It has not
been sent to testers or enabled in production; the owner send gate still
requires explicit approval.

## Tester artifact

Archive: `artifacts/Submit-0.2.0-macOS.zip`

SHA-256:

```text
64c503ebbbc975a8c839cb731ec158b9e0ef14029e84df23ff2e91dc5f0096a9
```

The build is ad-hoc signed, not Developer-ID signed or notarised. On first
launch, use Finder: right-click the app → **Open** → **Open**.

## Five-minute product check

1. Open Submit, or open a PDF with it from Finder.
2. On first launch, optionally enter the student number to reuse when a PDF
   does not contain one. This value stays in the local settings file and can
   be cleared in the app.
3. Load an authorised assignment PDF.
4. Check every detected field, evidence note, confidence marker, and candidate
   alternative. Choose an alternative from the field's **Use…** menu or
   correct anything missing or uncertain manually.
5. Try **Harvard-style (generic)**, **US coursework (generic)**, and
   **Chicago-style (generic)**
   profiles. They are editable filename starting points, not claims of a
   universal university rule.
6. Click **Approve details**, inspect the preview, then choose **Create Renamed
   Copy**. Keep the original unchanged for the test.

## Missions

- [x] Normal text-based assignment PDF (internally verified)
- [x] PDF with a missing student number, using the saved-number fallback (internally verified)
- [x] PDF with a missing module code or title, entered manually (internally verified)
- [x] Harvard-style profile and preview (internally verified)
- [x] Chicago-style profile and preview (internally verified)
- [x] Candidate-number/anonymous profile, if the PDF has a candidate number (synthetic fixture internally verified)
- [x] Alternative candidate menu on a group or ambiguous title-page PDF (internally verified)
- [x] Filename collision (confirm the numbered-copy behaviour) (internally verified)
- [x] Scanned or image-only PDF, if available (internally verified)
- [x] Rename Original followed by Undo Rename (internally verified)

The checked items are engineering smoke evidence from the packaged RC1 build;
beta testers can still repeat them on their own authorised documents. The
anonymous profile has been verified in both directions: approval stays blocked
when no candidate number is available, while a synthetic `Candidate No.:
A12345678` fixture renders `A12345678_Soundscape_Study_1.pdf` and does not use
the saved student number. A positive authorised university document remains a
tester mission because no such local example is available.

## What to report

Use [docs/BETA_FEEDBACK_TEMPLATE.md](docs/BETA_FEEDBACK_TEMPLATE.md). Please
report field-level behaviour and the suggested filename; do not attach a PDF
unless its owner has explicitly authorised sharing it.

Useful details include:

- macOS version and beta version;
- which fields were correct, missing, or wrong;
- whether the first page contained a cover sheet/title page;
- whether the PDF was text-based or scanned;
- which university/profile/template was selected;
- whether the original stayed unchanged and the output opened normally.

## Optional authorised corpus validation

Only use this path for PDFs the tester owns or has explicitly authorised for
local processing. The validator reads files in place and writes aggregate
metrics only; it does not copy, rename, upload, or log document text.

1. Put authorised PDFs in the ignored `real_validation_corpus/beta_intake/`
   folder.
2. Copy `manifest.template.json` to `real_manifest.json`.
3. Replace every example path and fill only manually confirmed truth values;
   leave unknown fields as `UNREVIEWED` or omit them.
4. Run:

```sh
./tools/run_beta_intake.sh \
  real_validation_corpus/beta_intake/real_manifest.json
```

5. Share aggregate results or the feedback form, not the PDFs or manifest.
   Remove the local PDFs, manifest, progress file, and results when the test
   is finished unless retention is explicitly authorised.

## Current evidence and limitations

- 252/252 deterministic checks pass.
- Railway staging deployment `4f14ba49-5cd0-48b4-86f0-b9bad3f6855a` passed
  health/readiness checks and the authenticated magic-link → entitlement →
  licence → signed-download journey. The downloaded ZIP matched the release
  SHA-256 `64c503ebbbc975a8c839cb731ec158b9e0ef14029e84df23ff2e91dc5f0096a9`.
- 43 public university PDFs pass the controlled batch safety gate.
- 12/12 targeted beta-harness fixtures process with zero wrong
  high-confidence cases.
- The private-beta validator path has also been smoke-tested against the
  governed 21-PDF manifest: 21 processed, zero unreadable/missing files, zero
  wrong high-confidence cases, and aggregate-only output. This is a harness
  check using public fixtures, not a substitute for authorised student PDFs.
- 16 public dissertation/project originals have now been explicitly approved
  and copied in the packaged real-file load waves, with byte-identical output
  hashes and no source modifications.
- The packaged UI has completed the normal, saved-number fallback, manual
  module-field, Harvard, Chicago, alternative-candidate, collision,
  image-only, and rename/undo smoke paths.
- Public university samples rarely contain real student numbers or module
  codes, so those fields still require authorised tester PDFs.
- Every inferred filename remains behind the app's explicit approval gate.
- CLI batch mode defaults to ID + Project; name-bearing output requires an
  explicit template or profile.
- A fresh app install also defaults to ID + Project, so a missing module code
  does not block ordinary preparation unless the tester chooses a
  module-bearing rule.
- Batch review can be handed off through the exact-source
  `BATCH_APPROVAL_V1` manifest; required-field gaps remain blocked.

## Next beta evidence to collect

The next useful test set is 10–20 tester-owned or explicitly authorised PDFs,
kept only in the ignored `real_validation_corpus/beta_intake/` workspace. Aim
for a mixture of essays, reports, dissertations, scanned documents, group
submissions, and anonymous-marking work. The set should deliberately include:

- documents with a real student number and documents where the saved-number
  fallback is needed;
- labelled module/course codes and documents where the code is absent;
- a visible student name, a name-required title page, and an anonymous file
  where a name must not be used;
- titles on the first page, later title pages, and titles requiring manual
  correction; and
- at least one group identifier and one document with multiple author names.

For each case, confirm the truth values visually and record only aggregate
results or redacted feedback. Do not commit the manifest or PDFs. This is the
remaining evidence needed before making stronger claims about real-world
student-number, module-code, group, and identity-policy accuracy.

See [NITE_SUBMIT_RELEASE_REPORT.md](NITE_SUBMIT_RELEASE_REPORT.md) for the
complete release evidence and [real_validation_corpus/beta_intake/README.md](real_validation_corpus/beta_intake/README.md)
for the privacy boundary.
