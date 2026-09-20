# NITE Submit — Private Technical Preview V1

**Status:** PRIVATE TECHNICAL PREVIEW — invite-only, 1–3 trusted testers
**Build:** 0.2.0 · PRIVATE BETA RC1
**Platform:** macOS 13 or later, Apple Silicon

This is a controlled technical preview, not a public beta, commercial launch,
or normal consumer installation. Please do not forward the archive or post the
checksum publicly.

## Important launch limitation

This build is ad-hoc signed. It is **not Developer ID signed and not notarised**
yet. macOS Gatekeeper may block the first launch. This is expected for this
private preview.

In Finder, unzip the archive, move the app to a local folder such as
`/Applications`, then Control-click or right-click **Submit.app**, choose
**Open**, and confirm **Open**. Do not disable Gatekeeper globally. If macOS
still blocks the app, use **System Settings → Privacy & Security → Open Anyway**
only after checking the supplied SHA-256 checksum.

## What Submit does

NITE Submit is a local-first document preparation and verification assistant. It
reads an assignment PDF on your Mac, detects likely identifying details such as
name, student number, university, module code/title, project title, or an
anonymous candidate number, and shows the evidence and confidence for review.
You can edit fields, select an alternative candidate, choose or edit a naming
rule, approve the details, and create a renamed copy. **Create Renamed Copy** is
the default and leaves the original untouched.

Scanned or image-only PDFs receive bounded local English OCR on the first few
pages. OCR-derived fields remain review-required. Manual entry is always
available.

## What Submit does not do

- It does not submit work to a university, LMS, plagiarism service, or any
  other destination.
- It is not automatic submission software.
- It is not an academic guarantee, compliance, or marking system.
- It does not guarantee that a detected value is correct or that a naming
  preset matches a department's official rule.
- It makes no unsupported AI or accuracy guarantee claims. Treat every result
  as a suggestion to verify.

## Privacy boundary

Processing is local-first and the product has no document upload path. User
documents, extracted document values, and filenames must not be sent to a
backend. The app has no account, analytics, telemetry, or crash reporting.
The only network request the app makes is the user-initiated "Check for
Updates…" menu item, which fetches a release feed and sends none of the
user's data. Session-extracted details are discarded when the window closes.

The app may store only local settings that the user explicitly chooses,
including the naming template, profile, rename preference, and optional saved
student number. Do not use real sensitive material unless you own it or have
explicit permission to process it.

## Safe test workflow

1. Confirm that the Mac is macOS 13+ on Apple Silicon and verify the archive
   checksum supplied with the invite.
2. Launch the app using the right-click **Open** path above.
3. Use a synthetic, redacted, or explicitly authorised assignment PDF. Do not
   use a document that you are not allowed to process.
4. Review every detected field, evidence note, confidence marker, and
   alternative. Correct or manually enter anything uncertain.
5. Choose a generic preset or enter the actual naming rule supplied by the
   department. Presets are editable starting points, not official rules.
6. Click **Approve details**, inspect the preview, and use **Create Renamed
   Copy**. Keep the source file unchanged for the first test.
7. Open the output and confirm that it is the expected PDF with the expected
   filename. Try collision handling only with disposable test copies.
8. Close the app when finished. Delete test copies and local intake material
   when retention is no longer authorised.

Do not disable Gatekeeper globally, overwrite an original as a first test, or
use production submission systems as part of this preview.

## What feedback to send

Use [NITE_SUBMIT_PRIVATE_FEEDBACK_TEMPLATE_V1.md](../NITE_SUBMIT_PRIVATE_FEEDBACK_TEMPLATE_V1.md).
Send the completed text through the owner-approved private channel. Include the
app version, macOS version, mission(s) attempted, expected result, observed
result, and whether the original file remained unchanged.

Please send redacted screenshots or synthetic reproductions where possible.
Never send the original PDF, its extracted text, a screenshot containing names
or student numbers, private filenames, or a private feedback export unless the
owner has explicitly authorised that exact material. A description of the
layout and the field that was wrong is usually enough.

For a possible data-safety issue, stop testing, preserve the local state, and
label the report **SAFETY**. Do not retry the operation on the original file.

## Known preview limits

- macOS 13+ and Apple Silicon only.
- First launch requires the Gatekeeper right-click **Open** flow.
- The build is not Developer ID signed or notarised.
- OCR is bounded, local, English-only, and review-required.
- Handwriting is not recognised.
- Naming presets are generic and not official university rules.
- The app window is single-document; this preview is about the core local
  workflow, not batch UI or commercial distribution.
