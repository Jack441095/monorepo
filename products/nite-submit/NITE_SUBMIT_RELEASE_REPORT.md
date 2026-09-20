# NITE_SUBMIT_RELEASE_REPORT

## Artifact

- App: `artifacts/Submit-0.2.0-macOS.app` (arm64; displayed as **Submit**)
- Tester archive: `artifacts/Submit-0.2.0-macOS.zip`
- Archive SHA-256: `64c503ebbbc975a8c839cb731ec158b9e0ef14029e84df23ff2e91dc5f0096a9`
- CLI helper bundled at `Contents/MacOS/nitesubmit-cli`
- Binary SHA-256 (app): `5192b9efb86ca72b6f1382db7711e1b62a50dada8c866221c54dff1b2dde76b4`
- Binary SHA-256 (cli): `3a5c088bc76241f9ebd95710eb77b256ad89235f55fa472c563b10fa675173f1`
- Bundle ID: `com.nitedsp.nitesubmit`
- Version: 0.2.0 · Channel: PRIVATE BETA INTEGRATION CANDIDATE
- Source revision and working-tree state: recorded in the machine-readable
  release manifest.
- This candidate is registered in isolated Railway staging and the exact
  checksum-bound remote download was independently reverified on deployment
  `4f14ba49-5cd0-48b4-86f0-b9bad3f6855a`. It has not been sent to testers or
  enabled in production; the owner send gate still requires explicit approval.
- Machine-readable provenance: `artifacts/Submit-0.2.0-release-manifest.json`

## Signing

Ad-hoc signed (`codesign -s -`). NOT Developer-ID signed or notarised — first
launch needs right-click → Open. Owner's NITE signing policy governs any public
distribution.

## Test evidence

`swift run nitesubmit-tests` → **252/252 checks passed**, including:
- 233-PDF corpus quality gates (all met)
- copy-mode original byte preservation (SHA-256 hard regression)
- rename-original content-hash identity + undo
- rename-original collision resolution retains a valid undo receipt and the
  active document path follows the final numbered filename
- rename verification failures attempt an immediate rollback to the original
  path before returning the safety error
- newly installed copies are removed if their post-write hash verification
  fails, while a pre-existing replacement target is left intact
- same-path operations are rejected before any move, and explicit replacement
  mode backs up and restores an existing target if installation fails
- collision / failure / Unicode / zero-byte cases
- OCR, candidate-number, assignment-code, localization, and filename-safety cases
- labelled five-digit student numbers and alternate registration labels
- low-confidence review-only module-code fallback and group-name ambiguity handling
- Finder/open PDF association and launch-time document loading
- repeatable bundle verification during packaging
- saved student number and naming-profile restoration across relaunch
- edited custom naming templates are saved immediately and restore as the
  Generic/Custom rule on relaunch
- deterministic settings round-trip coverage verifies that a custom template
  clears stale preset/profile identifiers rather than restoring a misleading
  profile selection
- first-run student-number prompt state and legacy settings migration
- owner-only permissions for the local settings directory and file
- repair of legacy settings permissions when an existing settings file is loaded
- packaged-app first-run prompt accepted `75589`, then applied it to a PDF
  without a student number; the user's original settings were restored after
  the check
- packaged-app end-to-end copy flow with byte-identical source/output PDFs
- packaged release launch with a real PDF: one visible window, document loaded,
  detected name/student number/university/project title shown, approval gate
  respected, and a regular byte-identical renamed copy created
- repeatable AppKit UI smoke check exercises Approve details → Create Renamed
  Copy against the real Berklee sample, writes the result only under
  `real_validation_corpus/test_results/app_ui_smoke_current/`, and verifies the
  source hash remains unchanged
- name-bearing filename explanations show the exact derived first and last
  name components used by the active template
- candidate alternatives are selectable through an explicit field menu and
  become manual choices before approval
- full-name filename profile writes an approved real PDF to `test_results`,
  preserving the source bytes exactly; see
  `docs/NITE_SUBMIT_NAME_PROFILE_VALIDATION_V1.md`
- missing required fields expose an entry prompt, manual values become
  high-confidence fields immediately, and the approval gate re-evaluates the
  completed name-bearing filename
- guidance classification recognises cover-sheet instructions, thesis
  title-page examples, research-project guidance, and capstone manuals;
  these cases remain review-held rather than becoming automatic filenames
- coursework headers labelled `Essay title`, `Paper title`, `Work title`,
  `Dissertation title`, `Thesis title`, or plain `Name` are covered by
  regression tests; placeholder names remain rejected
- combined name-profile batch evidence records document classification for all
  43 qualified PDFs; 21 guidance/template cases are explicitly identified in
  JSON/CSV rather than being silently treated as submissions
- UK coursework profile verified against a real Edge Hill UK PDF with module
  code `HEA3183`; it rendered a module-code-first preview while retaining the
  guidance warning and approval gate
- US coursework profile verified as a generic, editable
  `{last_name}_{first_name}_{project_title}` option for ordinary
  non-anonymous work; the saved ID-only default remains unchanged
- US coursework profile dry-run validation covered all 43 qualified PDFs,
  with 25 previewable results, 18 review-required results, and zero
  collisions/failures; a byte-identical real write is recorded in
  `docs/NITE_SUBMIT_US_PROFILE_VALIDATION_V1.md`
- US assignment-code profile safety validation held the official UW/Tacoma
  guidance fixture as `guidance_template` with a missing assignment-code gap;
  no output was written. A positive student-owned `LASTNAME_A#` case remains
  an authorised-beta evidence requirement. See
  `docs/NITE_SUBMIT_US_ASSIGNMENT_PROFILE_VALIDATION_V1.md`.
- explicit `Author` and standalone `Candidate` name labels are covered by
  regression tests, including a strict next-line value layout
- group submissions now have an explicit labelled/manual Group ID field and
  Group ID + Project rule; multiple student names remain alternatives and
  cannot silently become a guessed group identifier
- group profile dry-run validation held both real Berklee PDFs because neither
  contained a labelled Group ID; no guessed group filename was written. See
  `docs/NITE_SUBMIT_GROUP_PROFILE_VALIDATION_V1.md`
- document identity policy checks distinguish ordinary work where a name is
  required from anonymous work where a name is prohibited; the first two pages
  are checked and a blocking result is reported for review
- every metadata-backed template field now blocks a render when its value is
  missing, including module code/title, university, and assignment title
- fresh app settings and the Generic profile now default to the safe
  `{student_id}_{project_title}` rule; module code is optional until a user
  explicitly selects a module-bearing template
- native AppKit visual alignment uses the website's dark Palette B tokens while
  retaining macOS 13 controls, keyboard behavior, and quiet long-session UX;
  see `docs/NITE_SUBMIT_UI_ALIGNMENT_V1.md`
- public-university title-page cases: explicit byline preference, placeholder
  rejection, awarding-university selection, and guidance-noise suppression
- symlink/alias input materialisation into an independent regular PDF copy

Targeted field-policy validation also passes: **12/12** generated fixtures,
with **11/11** student IDs and **10/10** module codes correct. Candidate-number
only input remains separate from student-number detection.

Governed corpus gates also pass: first wave **21/21** processed with zero unreadable
or wrong-high-confidence cases; clean accuracy set **9/9**; wave 3 **6/6**;
wave 4 **5/5**; wave 5 **6/6**.
The 43-PDF batch report using the safe CLI default contains **41 previews** and
**2 review-required** cases; explicit name-bearing profiles remain separately
review-gated and documented.
no low-confidence filename was written automatically.

A supplementary full synthetic write load over all **203** fixture PDFs is
retained in `real_validation_corpus/test_results/`: both the safe ID+Project
run and the explicit ID+Full Name+Project run wrote **152** regular PDFs,
held **51** incomplete/review cases, and recorded **0** collisions or
failures. All 304 written outputs are byte-identical to their sources; the
name-bearing run contains the expected first and last name in every output.
This is write-safety evidence, not a real-university accuracy claim.
The same check is now part of the canonical `tools/run_release_checks.sh`
gate and is reproducible with `tools/run_full_corpus_write_check.sh`.

Wave 4 adds five official US university title-page/guidance PDFs. Its
layout-only harness processed **5/5** with zero missing or unreadable files;
it is not counted as student-submission accuracy evidence because public sample
pages contain placeholders, committee names, and instructional prose.
Wave 4 is now included in the canonical no-argument release runner.

Wave 5 adds six official US university title-page/format samples from
Missouri, Yale, Illinois, and Utah. Its layout-only harness is included in the
canonical release runner for ongoing smoke coverage; these public samples do
not count as student-submission accuracy evidence.

The controlled normal-write check in
`real_validation_corpus/test_results/normal_batch_wave4/` processed 13 copied
synthetic fixtures: **12 regular PDF outputs**, **1 review-required item**,
zero symlink outputs, and byte-identical source/output hashes for all 12
written files. The missing-title fixture produced no output.

A separate normal-write run over all 43 qualified public PDFs is recorded in
`real_validation_corpus/test_results/normal_batch_public_wave5/`: **43
review-required, 0 written**, with zero collisions or failures. This confirms
that layout-inferred public names and titles cannot bypass the approval gate.

The packaged original-file load checks covered **16 explicitly approved public
dissertation/project originals** (12 in wave 3 and 4 in wave 4). Every written
output was a regular PDF with a byte-identical source hash; the source files
were staged read-only and were not modified. Superseded generated copies from
those waves have been moved to macOS Trash to keep `test_results` small; the
current release runner reproduces the checks when needed.

The batch approval handoff is also release-gated: an exact approval manifest
writes the selected uncertain public case as one regular byte-identical PDF,
leaves the other 42 cases held for review, and cannot override a required
field gap. Normal non-dry-run batch mode also holds every
`guidance_template` classification with a `guidance_template_review` gap;
complete-looking guidance/template fields do not authorise a write. See
`tools/run_batch_approval_check.sh` and
`docs/NITE_SUBMIT_BATCH_APPROVAL_V1.md`.

Every canonical release run now writes a machine-readable manifest binding the
artifact hashes to the source revision, working-tree state, deterministic test
count, batch summary, and signing status. The integration candidate receipt was
regenerated after the backend hardening commit and records the candidate source
revision and archive checksum.

The release runner also extracts the ZIP into a fresh temporary directory,
verifies the copied bundle, runs the staged CLI against a public sample, and
checks an approved output is a regular byte-identical PDF. This is a local
clean-install simulation; Developer ID signing and notarisation remain owner
gates.

The default release corpus staging explicitly excludes the ignored private
`real_validation_corpus/beta_intake/` workspace. A dedicated scope check
fails closed if a beta-intake PDF is ever staged accidentally, preventing
private tester values from entering release batch reports.

The beta-intake validator also has a release smoke gate against the governed
21-PDF public manifest. It requires 21 processed cases, zero unreadable or
missing files, zero wrong high-confidence cases, and the documented
aggregate-only result shape; it does not add those public fixtures to the
private intake workspace.

The local distribution readiness audit currently reports **not ready** with
zero Developer ID identities and no `NITE_SUBMIT` notarytool profile on this
Mac. The audit is fail-closed for a future public-release command and does not
expose keychain secrets.

## Reproducibility

```sh
swift run nitesubmit-tests && ./tools/package_app.sh
```
Corpus regeneration: `python3 tools/generate_corpus.py` (seeded, deterministic).
