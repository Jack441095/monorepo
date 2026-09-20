# NITE Submit Changelog

All notable changes to **NITE Submit** will be documented in this file.

---

## [1.0.0] - 2026-09-18

### Fixed
- Queue-selection state bug: the first real file added to an empty multi-file
  queue could have its review state wrongly captured before ever loading,
  showing a blank review screen instead of real detected data.
- Duplicate-launch bug: opening a file via Finder/"Open With" could process
  the same file twice, from a redundant hand-rolled argument parser
  duplicating what AppKit already delivers.
- `module_code` detection: real department codes longer than 6 letters (e.g.
  Cardiff Business School's "MANGTBL") were silently missed even right after
  an explicit label.
- `.7z` archives now use real bundled LZMA2 compression (via a bundled arm64
  `7za`) instead of silently falling back to a ZIP mislabeled as ".7z" when
  no system 7z tool was installed — the default on virtually every Mac.
  Password protection and volume splitting now fail loudly instead of
  silently shipping unencrypted/unsplit output when that fallback would have
  been needed.
- `UITheme.success` was defined as a second shade of red, undermining the
  red=bad/green=good status-LED convention throughout the app. Now green.
- Candidate-number and student-ID detection gaps affecting real ID/number
  shapes right after an explicit label (short candidate numbers, two-letter
  ID prefixes, single-word/mononym names).

### Added
- Lossless PDF size optimization (bundled `qpdf`) as an explicit, off-by-
  default archive option — verified 5-30%+ reduction on real documents with
  zero content change.
- Real app icon (previously a placeholder).
- Corruption/round-trip test coverage for WAV, MP4, and DOCX through the
  actual archive + extract path, and for large files (288MB verified).
- US-university label vocabulary ("roll number", "banner id", "campus id",
  "course number") alongside the original UK/exam-board-centric terms.

### Changed
- UI language simplified from console/terminal-style jargon (ALL-CAPS
  "MODULE 01 // ...", monospace throughout) to plain English and a system
  sans-serif, matching a cleaner overall visual direction.

### Security
- Ed25519 offline licence key system — activation required on first launch,
  validated entirely on-device with no server calls.
- `nitesubmit-keygen` developer-only CLI for licence key generation (not
  shipped to customers).

---

## [0.2.0] - 2026-09-02

### Added
- **Native 7z LZMA2 Archive Engine**: Added `archiveWith7z` method utilizing 7-Zip CLI (`/opt/homebrew/bin/7zz`) with ultra-compression mode (`-mx=9`) and solid archiving (`-ms=on`).
- **AES-256 Volume Password Encryption**: Integrated password protection (`-p<password>`) and header encryption (`-mhe=on`) for high-security student submissions.
- **Multi-Volume Splitting Engine**: Added support for multi-part archives (`-v<size>`), enabling splitting large submissions across strict upload limits (e.g. 50MB canvas/blackboard limits).
- **Batch Folder Drag & Drop GUI**: Built native AppKit `DropZoneView` and `MultiFolderQueueView` allowing drag and drop of multiple assignment folders.
- **Developer ID & Apple Notarization Pipeline**: Updated `tools/create_release_dmg.sh` with `codesign --deep` Developer ID signing, Apple Notarization (`xcrun notarytool submit`), and ticket stapling (`xcrun stapler staple`).
- **12-Gate Automated Release Suite**: Integrated `tools/run_release_checks.sh` running 275 automated unit assertions across Swift core, 7z compression, AES encryption, and DMG creation.

---

## [0.1.0] - 2026-08-15

### Added
- Initial release of NITE Submit core archive engine and CLI interface.
