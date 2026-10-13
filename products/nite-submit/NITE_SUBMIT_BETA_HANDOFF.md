# Submit private beta handoff — 1.0.0

The private tester artifacts passed the local release gate on 2026-10-11.
They have not been published or sent to testers. Public paid release remains
blocked. Exact hashes and evidence are in
[NITE_SUBMIT_RELEASE_REPORT.md](NITE_SUBMIT_RELEASE_REPORT.md).

## Install and activate

Use `artifacts/Submit-1.0.0-macOS.zip` or
`artifacts/Submit-1.0.0-macOS.dmg`. Confirm the report's SHA-256 before opening.
The bundle is arm64 for Apple Silicon, targeting macOS 13.0. Tests ran on macOS
27.0.1; clean-Mac/quarantined installation and macOS 13 remain tester missions.
Intel is not supported by this artifact.

Extract the ZIP, or mount the DMG and copy Submit.app to Applications. The app
is ad-hoc signed, not Developer ID signed or notarised. Gatekeeper may reject a
quarantined download. An owner-supervised private test can use Finder's Open
flow or the macOS Privacy & Security Open Anyway control if offered. Do not
remove quarantine automatically or claim that public installation is verified.

Activation requires an owner-issued offline Submit licence matching the current
public key. Keep the key private; never send signing material to testers. The
first-run student-number prompt is optional. The number stays in local settings
and can be cleared. A fresh install defaults to `{student_id}_{project_title}`.

## Tester missions

Use a disposable copy of a document you own or have permission to process.
Check your brief's naming and anonymity rules before accepting a preset.

1. Open a text PDF through the picker or Finder. Check detected title, name and
   institution, including alternative suggestions. Correct anything uncertain.
2. Approve the filename, then Create submission. The GUI writes beside the input;
   use the CLI `--to` or `--out` when choosing another destination. Confirm the
   copy opens and the original is unchanged.
3. Repeat the copy to exercise the numbered-name collision prompt. Edit a field
   and verify approval is revoked before another write.
4. Add several files and switch between them. Review each independently; archive
   only approved entries. Try the bundled ZIP/7z options and PDF optimisation.
5. Try an image/scanned PDF, enter missing details manually, and approve again.
   Try a missing module/candidate number and verify the selected rule blocks.
6. Test authorized real IDs/modules, group submissions and anonymous work.
   Controlled fixtures cover these rules but are not real-document accuracy.
7. Verify activation rejection for an invalid key and normal relaunch. Test the
   clean-Mac and minimum-macOS install path before any public support claim.

Internal final-app checks passed picker/review/correction/copy, collisions,
queue state, a two-entry archive and image-only manual recovery. CLI checks also
cover locked/malformed input, invalid templates, Unicode and path containment.
The release report distinguishes those checks from new tester evidence.

## Privacy-safe feedback

Use [docs/BETA_FEEDBACK_TEMPLATE.md](docs/BETA_FEEDBACK_TEMPLATE.md). Report app
and macOS versions, field correctness, text/scanned layout, chosen profile,
warning behavior and whether the original/output opened correctly. Redact names,
IDs, titles and paths from screenshots or examples. Do not attach PDFs, manifests
or ordinary batch JSON/CSV without the document owner's permission.

Authorized intake stays under ignored `real_validation_corpus/beta_intake/`.
Copy its `manifest.template.json` to `real_manifest.json`, replace every example
path, and enter only independently reviewed truth. Omit unknown fields or mark
UNREVIEWED. Then run:

```sh
./tools/run_beta_intake.sh real_validation_corpus/beta_intake/real_manifest.json
```

Share only its aggregate result. Remove disposable input, manifest and generated
reports when their authorized retention ends. This task used public fixtures;
it did not access private student documents.

## Limits and rollback

Public reviewed coverage is 7 authors, 9 titles and 9 institutions, all passing.
Twenty-six guidance PDFs supply layout coverage only. Controlled coverage is
11 IDs, 10 modules and one explicit absent ID. Real ID/module/anonymous accuracy
needs authorized beta evidence. English OCR can make mistakes and suggestions
remain reviewable. Presets are editable starting points, not universal rules.

The signed-update feed is not ready: its matching offline key is unavailable.
Do not advertise the placeholder appcast or this ad-hoc beta as a public update.
Current hosted staging still needs durable storage/email and an actual Sandbox
purchase rehearsal; the final ZIP passed local captured-email delivery only.

If testing finds a release blocker, pause distribution and use the verified
snapshot at `artifacts/shipping-2026-10-11/verified-private-beta-1.0.0/` after
checking its SHA256SUMS. Keep earlier source files untouched. No older 0.2.0
artifact has been recertified for rollback. Publication and real invitations
remain owner actions; no message was sent by this task.
