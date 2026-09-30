# NITE SUBMIT — FULL CODE REVIEW V1

**Date:** 2026-09-30
**Scope:** `products/nite-submit` at `1.0.0` — 17 core files, 7 app + 5 CLI/keygen, 18 test files, 27 tools scripts, `Package.swift`, `web/appcast.xml`
**Reviewer:** read-only pass, then repair. Phase A findings below; Phase B/C repairs are in the commit history that follows.
**Verdict:** `READY WITH CONDITIONS` — the code blockers are fixed and tested; signing, notarization, payment fulfilment, and one feed signature remain owner actions.

Evidence discipline: every finding carries `file:line` or a command and its output. `UNVERIFIED` marks what I could not confirm from this machine.

---

## Phase A1 — Core (`Sources/NiteSubmitCore/`)

### Blockers, now fixed

| # | Finding | Evidence | Fix |
|---|---------|----------|-----|
| 1 | Custom organize templates interpolated raw `{filename}`/`{extension}`, so a filename containing `../` resolved outside the target folder | `OrganizationRulesEngine.swift:103-112` | `confinedRelativePath` + a `baseDir` prefix assertion; a blocked traversal is reported as a collision so the executor refuses it |
| 2 | `findLabels` used `contains("name:")`, firing the `name` label on `Filename:` and the `unit` label on `Community:` — invented fields the document never had | `FieldDetector.swift:1000-1015` | word-boundary anchored regex accepting `:` `：` `-`, and the `No.` abbreviation form; corpus `student_id` 215→219 hits at precision 1.0 |
| 3 | `executeOrganizationPlan` hardcoded `policy: .replace` for copy and move, ignoring the plan's own `hasCollision` flag | `FileOperations.swift:238-251` | collisions refused unless `forceOverwrite`; the CLI needs `--force` |
| 4 | Archive staging used `tempDir + lastPathComponent`, so two `report.pdf` files aborted the whole archive | `ArchiveEngine.swift:142-148` | `uniqueStagingTarget` hands out `report.pdf`, `report 2.pdf`, … |
| 5 | Archive password passed as `-p<password>` in argv, visible to every other process via `ps`; ZIPs used Info-ZIP `-P` (ZipCrypto) | `ArchiveEngine.swift:212,262` | bare `-p` with the secret over stdin, 7zAES-256 via `-mhe=on`, `-mem=AES256` for ZIP; no 7z means refusal, not a weak substitute |

### Major, now fixed

- `FieldDetector.swift:278-308` person-name shape was Latin-1 only, so a Cyrillic or CJK name was never detected even though `Localization.swift` advertises `ar/zh/ja/ko/hi/uk/ru`. Now `\p{L}`, with casing enforced only for scripts that have case. `UNVERIFIED`: a CJK name with no `Student Name:` label is still missed, because the title-page path requires casing.
- `FileOperations.swift` staged into `temporaryDirectory` (usually a different volume), so the move was copy-then-delete with a crash window; the `fileExists` check lost races; `resolvingSymlinksInPath()` on the source copied bytes from wherever a symlink pointed. Now: hidden sibling in the destination directory, `replaceItemAt`, `O_CREAT|O_EXCL` name claim, hash verified before install, symlinked sources refused.
- `OrganizationRulesEngine.swift:119-121` compared destinations case-sensitively, but APFS is case-insensitive by default, so `Report.pdf` vs `report.pdf` went unflagged and then destroyed one. Comparison key is now lowercased.
- `FolderScanner.swift:93-99` returned an empty manifest for a missing or unreadable root, so "no files" and "permission denied" looked identical. Now `FolderScanError`. `:101-127` returned filesystem enumeration order, making plans nondeterministic; now sorted by `relativePath` with an ordinal compare. `relativePath` was also mangled whenever the root contained a symlink — always true on macOS via `/var` → `/private/var` — because `standardizedFileURL` un-resolves it; now `realpath(3)`.
- `LicenseEngine.swift:23` decoded the issue timestamp with a native-endian unaligned `load(as: UInt32.self)`; `:33-42` swallowed write and chmod failures with `try?` and returned `true`, so the app activated with nothing saved. Now explicit little-endian, `storeLicense` throws, timestamps more than 24 h ahead are refused, and the keygen encodes the same way.
- `PDFExtractor.swift:63-68` materialised `page.string` before truncating, and the break threshold was `maxChars*maxPages/4` (100 M chars); `:81-96` skipped OCR entirely whenever *any* page had text, because an image-only page never enters `pages` at all — so identity fields on scans behind a typed cover sheet went missing. Now: truncate the raw page string first, OCR per empty page, and mark OCR-derived fields so they drop a confidence notch.
- `PDFOptimizer.swift:88-90` deleted the destination before `qpdf` ran, so a failure lost the user's previous file; `:85` coerced a stat failure to `originalSizeBytes = 0`, reporting 0 % saved. Now: temp sibling plus atomic replace, stat failures throw.
- `MediaExtractor.swift:27-38` decided file kind from the extension alone, so a renamed file was mislabelled; `:72-92` read `IMG_20240115.jpg` and `TAKE1234` as student IDs at `.medium`. Now: 16-byte header sniff (`.wav` that is really an MP3 reports `unknown`, not WAVE), filename-only matches are `.low`.
- `UpdateEngine.swift:126-139` parsed `sparkle:edSignature` and never verified it; `UpdateModalView.swift:93-97` opened the feed-supplied `downloadURL` with no scheme or host check. That is the app's only network path. Now: Ed25519 verification over `version + "\n" + URL`, `https` only, host allowlist, `shouldResolveExternalEntities = false`, fail closed.
- `UpdateEngine.swift:10-20` `SemanticVersion` dropped non-numeric components, so `1.2-beta` collapsed to `1.2.0` and a prerelease could present as a release. Now rejected.

### Minor, still open

- `TemplateEngine.swift:125-128` renders with `FilenameSanitizer`'s default case style, so a user's `caseStyle` preference is dropped unless the caller re-applies it.
- `Settings.swift:92-102` `load()` rewrites the file to repair permissions on every launch; `save()` swallows encode and write errors.
- `PDFExtractor.swift` maps the whole file just to sniff the first 2 KiB for `/Encrypt`.
- `Presets.swift:28-29` uses `id: "custom"` in both preset lists, and the "Harvard-style"/"Chicago-style" labels read as institutional endorsement.
- `DocumentClassification.swift:76-79` treats an unreadable or image-only PDF as `.unavailable`, which blocks under any identity policy with no override in that layer.
- `Models.swift:10-13` force-unwraps a rank lookup; `variableMap` drops middle names for "Mary Jane Smith".
- `ArchiveEngine.swift:303-318` archives embed mtimes, uids, and traversal order, so the receipt's SHA-256 is not reproducible across runs.
- `ArchiveEngine.swift:343-350` hashes with `Data(contentsOf:)`, loading the whole archive; the streaming `sha256` in `FileOperations` should be reused.

---

## Phase A2 — App and CLI

### Blockers, now fixed

- `MainView.swift:1143-1145` `doArchive` mapped every queued URL after the *selected* item alone was approved, so approving one document shipped the rest. The comment at `:685-688` promised the opposite. Now: `approvedArchiveSources` filters per queue row, refuses when nothing is approved, and reports how many unapproved files were skipped.
- `main.swift:83-111` `--policy replace` overwrote with no confirmation, and `copy` without `--to` wrote into the current directory. Now: `--force` is required for `replace`, `--to` defaults to the source folder, `--policy` parses through a strict switch, and an unknown `--rule` errors instead of falling back to `groupByCategory`.
- `Batch.swift:57,257,295` and `Validation.swift:76-77,180,190-203` used `try!`, so a full disk, a read-only `--out`, or a malformed manifest aborted with a Swift trap and no exit code. Now: `do`/`catch` with stderr and exit 2.
- `Batch.swift:26-42` an unreadable or bad-version approval manifest warned and continued with zero approvals, exiting 0. Now: exit 2 unless `--ignore-bad-manifest`.
- `Batch.swift:186-195` the `uncertain` gate checked only name/id/code/project confidence, so a low-confidence `module_code` still auto-processed. Now every templated variable, via `SubmissionMetadata.lowConfidenceVariables`.
- `Batch.swift:59-63` only excluded `output`-prefixed paths, so `--out` inside `--input`, or a symlinked directory, could re-scan outputs or escape the tree. Now `--out` under `--input` is rejected and sources are filtered through `pathIsInside`.

### Major, now fixed

- `MainView.swift:655-659` called `loadPDF` for every drop, bypassing `SubmitController.loadFile`, the only branch that handles non-PDF via `MediaExtractor` — a dropped `.mp4` could never load.
- All extraction and archiving ran on the main thread (Vision OCR and 7z compression included), which beach-balled the window. Now on a work queue with a `readToken` so stale completions cannot paint the wrong row, and the operation buttons disable while busy.
- `resetSession` called `controller?.reset()` but kept the queue, so item 0's captured state came back. Now cleared.
- One `lastRenameReceipt` for the whole session meant undo after switching rows undid the wrong file. Now scoped per queue item via `captureState`/`restore`.
- `Validation.swift:94` counted every extraction throw as "encrypted", so an I/O bug inflated the privacy-safe metric.

---

## Phase A3 — Tests, tools, packaging

- The test runner force-unwrapped values and used `try!` in ~22 places, so one regression killed the run instead of reporting a failure. Now a `scenario` scope records a throw as one failed check, and `eq` forwards the caller's `file:` so failures point at the suite that broke.
- `CorpusTests.swift:42,45` skipped missing PDFs with `continue`, so a deleted fixture directory still passed the `>= 150` gate. A missing fixture is now a failed check, and `extracted == renderable.count` is asserted.
- `FailureTests.swift:20` asserted nothing (`_ = try? … ; _checks += 1`). Now switches on the outcome and fails on `.success`.
- Two corpora had drifted: `Sources/…/Fixtures` held 239 cases, `tools/Fixtures` held 209, and the manifests differed — the unit tests measured documents the release gate never ran. `tools/generate_corpus.py` is now authoritative (it had itself fallen stale and needed three `project_title` truths restored), and `tools/check_corpus_parity.sh` runs first in both release gates. `run_full_corpus_write_check.sh` derives its counts from the manifest instead of hardcoding 203/152/51.
  - One correction to the parity gate as first written: it compared PDF bytes, which can never match because each fixture embeds its own `/CreationDate`. It now compares extracted text, and I verified it still fails on a real content change.
- `tools/bin/7za`, `tools/bin/qpdf` and three dylibs are hand-dropped blobs with no integrity check. `tools/SHA256SUMS` now pins all five and `package_app.sh` verifies before copying; I confirmed the guard fires by tampering with `qpdf`.
- `sign_and_notarize.sh` relied on `--deep` to cover `Resources/lib/*.dylib` and ended with `spctl || true`, swallowing a Gatekeeper rejection. Now inside-out signing and fail-closed assessment.
- `tools/license-private-key.base64` is a live 32-byte Ed25519 key. It was correctly gitignored and untracked, but it sat inside `tools/` beside the packaging scripts, so any future sweep of that directory into the bundle would have shipped it. Now resolved from `$XDG_CONFIG_HOME/nite-submit/`, with `package_app.sh` and `verify_app_bundle.sh` both refusing a bundle containing any `*private-key*` file.
- `web/appcast.xml` shipped no `edSignature` and no `length`, so the new verification gate can never pass in production. Both attributes are now present, `tools/update_appcast.sh` writes them and refuses a key that does not verify against the shipped public key, and `UpdateEngineTests` parses the real feed and fails if either attribute disappears.
  - `UNVERIFIED`: the shipped `length` and `edSignature` are empty, because the release private key is offline and is a *different* key from the licence key in `tools/`. The owner must run `tools/update_appcast.sh` before the feed goes live. This is the intended fail-closed pre-signing state.

---

## Phase A4 — Docs against code

| Claim | Code | Action |
|-------|------|--------|
| `SHIP_BLOCKERS.md:32-45` P0-2 "No licensing or activation system" | `LicenseEngine.swift` verifies `NTSUB1-` keys with Ed25519; `main.swift` gates first launch | closed in this report |
| `SHIP_READINESS_REPORT.md:166-174` check 16 "no license key validation" | same | closed |
| `PRIVACY.md:24` feed is `releases.nitedsp.com` | `UpdateEngine.swift:82` fetches `www.nitedsp.co.uk/submit/appcast.xml` | corrected, and the signature gate is now documented |
| `ARCHITECTURE.md:80` "V1 ships an always-open implementation. No DRM." | `LicenseEntitlement` gates the app | corrected; no trial clock, no revocation |
| `SHIP_READINESS_REPORT.md:61` "Rename Original … documented as undoable" | undo covers one interactive rename; batch, organize, archive and copy have no undo | narrowed in this report |

`UNVERIFIED`: `web/index.html` sales claims were audited for code support only; pricing, refund policy and the checkout URL still need the payment integration to be live.

---

## What was verified clean

- No secrets in the tree. The only match for "key" in `git ls-files` is the keygen source.
- One network path: `NiteSubmitApp/main.swift:123`, a user-initiated `URLSession` GET for the appcast. No telemetry, no third-party network dependency.
- No hardcoded `/Users/...` paths in `Sources/` or `tools/`.
- The batch manifest supplies source labels only and never field values; uncertain-and-unapproved still never writes.
- The app gate still requires `reviewApproved` plus template re-validation before any operation.
- `DetectorTests.swift` and `FileOperationTests.swift` read as executable documentation and set the bar for the rest.

## Test and gate state

```
swift build                                   Build complete
swift run nitesubmit-tests                    475/475 checks passed
tools/check_corpus_parity.sh                  corpus-parity=pass cases=239
tools/run_full_corpus_write_check.sh          pass, 233 sources, 172/61 and 162/71
tools/package_app.sh + verify_app_bundle.sh   pass, 15M artifact
tools/check_distribution_readiness.sh         ready_for_public_distribution: false
```

Corpus precision stayed at 1.0 with zero wrong-high-confidence cases across all five fields. Latency rose from 0.0014 s to 0.044 s average per document, which is the cost of OCR'ing the scanned pages in a mixed document.
