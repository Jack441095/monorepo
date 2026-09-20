# PRIVACY — NITE Submit

**Your assignment never leaves your computer.**

## What the app does

- Reads PDF text using Apple's PDFKit, entirely on-device.
- Extracts fields (name, student number, university, module, project) with
  deterministic rules running in the app process.
- Copies or renames files on your local disk.

## What the app never does

- Your documents and extracted data never touch the network. All PDF reading,
  field extraction, and file renaming happens entirely on-device.
- No analytics, telemetry, crash reporting or tracking.
- No accounts, sign-in or licensing server calls.
- No document history. Extracted details live in memory for the session only
  and are discarded when you close the window.

## The one network request the app makes

If you choose **Check for Updates…** from the app menu, NITE Submit fetches a
small release feed from `releases.nitedsp.com` to see whether a newer version
exists. This request contains no document content, extracted data, or
identifying information — just a plain HTTP GET for the feed. It only happens
when you click that menu item; the app never checks for updates automatically
or in the background.

## What is stored locally

`~/Library/Application Support/NiteSubmit/license.key` contains your licence
key (the string you pasted during activation). It is stored with owner-only
permissions (`0600`) and contains no personal data beyond the key itself.

`~/Library/Application Support/NiteSubmit/settings.json` contains **only**:

- your naming template,
- your selected naming preset and university profile,
- your preferred rename mode and case style.
- the student number you explicitly enter for first-launch fallback.

It contains no document content, extracted student names, or file paths. The
student number is stored only because you explicitly asked NITE Submit to reuse
it when a PDF has no number. You can clear it from the app or remove the local
settings file. The settings directory is written with owner-only permissions
(`0700`) and the settings file with owner-only read/write permissions (`0600`).

## Logging

Local diagnostics only. Document text is never logged by default; extracted
student identifiers are not logged.

## Third parties

No network-based third parties — see "The one network request the app makes" above for the
sole exception. The app bundles two third-party open-source components, both used entirely
locally with license text included under Contents/Resources/bin/:

- `7za` from the p7zip project (LGPL 2.1) — creates real 7z archives when you choose that
  format.
- `qpdf` (Apache 2.0), used when you choose to losslessly optimize a PDF's file size — it
  restructures the file's internal compression, never its visible content.
- `libcrypto` from OpenSSL (Apache 2.0) and `libjpeg` from libjpeg-turbo
  (IJG/BSD/zlib terms), used locally by qpdf. See the bundled
  `THIRD_PARTY_NOTICES.md` for attribution and upstream source links.

Neither sends data anywhere; both only run on-device on the files you select.
