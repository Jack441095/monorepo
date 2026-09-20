# NITE Submit — Troubleshooting

**Product version:** 0.2.0 (Private Beta RC1)
**Audience:** Customers and support staff
**Last reviewed:** 2026-08-25
**Evidence boundary:** Symptom → fix entries verified against shipped 0.2 behaviour; escalation paths match the Support Documentation Plan.

---

## How to use this page

Find the symptom, apply the fix in order. If nothing helps, follow "Escalating to support" at the bottom — with a redacted report (see the FAQ entry "How do I report a problem safely?").

## Installation and launch

### macOS says the app "cannot be opened"
Beta builds are ad-hoc signed and not yet notarised.
1. Right-click Submit.app → **Open** → **Open** again.
2. If still blocked: System Settings → Privacy & Security → **Open Anyway**.
3. Still blocked after both: verify the app copied fully to /Applications (partial copy breaks code signature checks) — re-extract the zip and retry.

### Checksum doesn't match
Stop — do not open the app. Re-download; if it still mismatches, email `support@nitedsp.co.uk` immediately with the download source and time.

### App opens to a blank window
Force quit and reopen once. If it repeats, report with macOS version — graphics/OS-specific issues are tracked in Known Issues.

## Reading documents

### "Little or no selectable text" behaviour
The PDF is scanned or image-only. Expected: bounded local OCR runs on the first few pages and marks results for review; anything OCR can't read, you type manually. Handwriting is not recognised by design of current scope.

### Detection found the wrong value
Edit the field or pick the right candidate from its **Use…** menu, then approve again. Please report recurring wrong findings (field type + what layout looked like) — these feed the detector's regression corpus without needing your document.

### Detection found nothing for a field marked !
Type the value yourself; approval then proceeds normally. Required fields block preview until filled; module fields stay optional unless your template uses them.

### PDF is password-protected
Remove the password in Preview (File → Export, uncheck encrypt) first; protected documents cannot be read locally by the extractor.

## File operations

### Create Renamed Copy is disabled
The current document's required fields aren't approved yet. Click **Approve details**; editing any field afterwards re-locks until you approve again.

### Target filename already exists
Collision protection warns rather than overwriting. Choose another location/name, or move the old file first. Silent overwrite never happens by design.

### I renamed the original by mistake
Click **Undo Rename** while the window is still open — the original filename is restored ("Undone — original filename restored."). After closing the window, rename back manually; content was never altered, only the name.

### Created copy won't open
Hash verification should have caught any bad write before reporting success. If a created copy ever fails to open: keep both files untouched and escalate immediately as a safety report (top priority classification).

## Batch (command line)

### Batch skipped most of my files
Normal batch mode writes only fully confident, template-complete likely
submissions. Uncertain items appear in the JSON/CSV report instead, and PDFs
classified as guidance or templates are always held with a
`guidance_template_review` gap, even if their fields look complete. Inspect the
report, correct fields where needed, or use `--approved-manifest` to authorise
specific listed items. Missing required fields always block.

### Dry run wrote unexpected files
It shouldn't — `--dry-run` writes only JSON/CSV reports. If any PDF appeared, that's a safety bug: preserve state and escalate as a safety report.

## Escalating to support

Email `support@nitedsp.co.uk` including:
1. App version + macOS version;
2. What you did, expected, and saw;
3. Redacted screenshot or synthetic reproduction file;
4. For file-safety concerns: mark the subject line `SAFETY`.

Never attach real assignments. See Known Issues for problems already accepted before this build.
