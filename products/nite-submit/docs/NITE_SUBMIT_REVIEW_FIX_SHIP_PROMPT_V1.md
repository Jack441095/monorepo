# NITE SUBMIT — REVIEW, FIX, SHIP PROMPT (V1)

> What this file is: a self-contained prompt that drives review of Nite Submit, repair of the load-bearing defects, and a final sale gate.
>
> How to use it: open the workspace and instruct the agent: *"Execute `NITE_SUBMIT_REVIEW_FIX_SHIP_PROMPT_V1.md` against `monorepo/products/nite-submit`. Produce all deliverables."*
>
> Owner: NITE DSP (Jack) · Created: 2026-09-29
> Product root: `monorepo/products/nite-submit`
> Stack: Swift / SwiftPM / macOS AppKit app · Ed25519 licence · Sparkle-style appcast · bundled 7za/qpdf

---

## 0. Role and mission

You are a release engineer + security reviewer for Nite Submit — a macOS app that renames university assignment PDFs from content, fully local. Core promises: no upload, no account, no telemetry.

Answer in order: (A) what is broken, (B) repair it with tests, (C) can this be sold today. Verdict format: `READY` / `READY WITH CONDITIONS` / `NOT READY`, with numbered blockers. Every finding cites file path + line, command + observed output, or artifact hash. No uncited claims.

Ground rules:

- R1 — Read-only first. Complete Phase A before editing. No `rm`, no `git push`, no publishing during review.
- R2 — Evidence or it does not exist. Re-verify report claims against current source. Prior `NITE_SUBMIT_*_REPORT.md` files are leads, not proof.
- R3 — Never echo secrets. Reference paths only, redact values to `***REDACTED***`. A committed secret is P0.
- R4 — The local-only promise is the product. Any outbound call beyond the user-initiated appcast fetch is P0 unless documented and customer-visible. Verify in source AND binary.
- R5 — Small diffs. Match surrounding file style. Comments explain why, with dates and measured behavior. Short sentences, concrete units.
- R6 — Receipts. Per phase: commands run, files read, what was skipped and why.

---

## Phase A — Reusable full review (read-only)

Run this phase verbatim on every future submit review. Cover all four surfaces.

A1. Core (`Sources/NiteSubmitCore/`): ArchiveEngine, DocumentClassification, FieldDetector, FilenameSanitizer, FileOperations, FolderScanner, LicenseEngine, MediaExtractor, Models, OrganizationRulesEngine, PDFExtractor, PDFOptimizer, Presets, Settings, TemplateEngine, UpdateEngine, Localization.
A2. App + CLI (`Sources/NiteSubmitApp/`, `Sources/nitesubmit-cli/`, `Sources/nitesubmit-keygen/`): approval gate, batch manifest, organize plan, destructive ops, licence gating, update flow, threading.
A3. Tests + tools + packaging: `Sources/NiteSubmitTests/*.swift`, `tools/*.sh`, `Package.swift`, `VERSION`, `web/appcast.xml`, `tools/bin`, `tools/lib`, `.gitignore`.
A4. Docs vs code: `SHIP_BLOCKERS.md`, `SHIP_READINESS_REPORT.md`, `PRIVACY.md`, `ARCHITECTURE.md`, `RELEASE.md` against actual code.

For each finding record: OBSERVED (file:line or command output) → INFERRED severity (blocker/major/minor) → UNVERIFIED (what you could not confirm).

Checklist for A:

- Rename collisions, sanitizer reserved names, template traversal, case-insensitive APFS collisions.
- PDF extraction bounds, mixed text+scan handling, encrypted detection, Vision threading.
- Archive determinism, staging collisions, password handling, streaming hashes, atomic writes.
- Licence endian/layout, persist errors, expiry/revocation story, key storage perms.
- Update feed: signature verify, https pin, XXE, version parse.
- Shell safety: `set -euo pipefail`, quoting, signing inside-out, `spctl` fail-closed.
- Corpus parity: `Sources/NiteSubmitTests/Fixtures` vs `tools/Fixtures` manifests must agree or a parity gate must exist.
- Privacy: grep `URLSession`, `NWConnection`, `Socket`, `http`, `upload`; inspect binary with `strings` / `otool -L` / `codesign -d --entitlements`.

---

## Phase B — Repair the known blockers (from 2026-09-29 review)

These were observed in source. Re-verify each before repairing, then repair with a regression test.

B1. Archive exports unapproved items — `Sources/NiteSubmitApp/MainView.swift:1143-1145` maps all `queueItems` after only the selected item is approved (`SubmitController.swift:279-282`). Fix: archive only the approved item or require a per-item approval set. Test: queue 3 files, approve 1, assert archive contains 1.

B2. Update signature parsed but never verified — `Sources/NiteSubmitCore/UpdateEngine.swift:126-139,161-177` captures `edSignature`, `checkStatus()` never verifies; `UpdateModalView.swift:93-97` opens feed URL with no scheme/host check. Fix: Ed25519-verify before modal, pin host `www.nitedsp.co.uk`, enforce `https`, fail closed. Add `edSignature` + `length` to `web/appcast.xml`. Test: tampered feed refuses; http URL refuses.

B3. Organize overwrites — `Sources/NiteSubmitCore/FileOperations.swift:236-251` hardcodes `.replace`. Fix: default `.error`, surface collisions, keep undo receipts. Test: plan with collision → execute → no overwrite.

B4. CLI destructive defaults — `Sources/nitesubmit-cli/main.swift:83-111` `--policy replace` with no confirm, `copy` without `--to` writes to CWD. Fix: require `--force` for replace, default `--to` to source dir. Test: replace without force exits non-zero and writes nothing.

B5. CLI `try!` traps — `Sources/nitesubmit-cli/Batch.swift:57,257,295`, `Sources/nitesubmit-cli/Validation.swift:76-77,180,190-191,201-203`. Fix: do/catch, stderr + `exit(2)`. Test: read-only `--out` returns error, no trap.

B6. Archive staging collision — `Sources/NiteSubmitCore/ArchiveEngine.swift:142-148` flattens basenames. Fix: dedup with suffix, preserve structure. Test: `a/report.pdf` + `b/report.pdf` archives both.

B7. Password via argv + ZipCrypto — `Sources/NiteSubmitCore/ArchiveEngine.swift:212,262`. Fix: pass via stdin/env, use AES where available, document the crypto level to the user. Test: password absent from process args in test harness.

B8. Detector substring labels — `Sources/NiteSubmitCore/FieldDetector.swift:1000-1015` `contains("name:")` matches `Filename:`. Fix: word-boundary or start-of-line anchor; same for `remainder(of:)`. Test: `Filename: foo` yields no name hit; `community:` yields no unit hit.

B9. Template traversal — `Sources/NiteSubmitCore/OrganizationRulesEngine.swift:103-112` raw `{filename}` interpolation. Fix: sanitize each component, reject `..` and `/`. Test: filename `../evil` stays inside `baseDir`.

B10. Version truncation — `Sources/NiteSubmitCore/UpdateEngine.swift:10-20` drops prerelease. Fix: reject suffixes or parse them. Test: `1.2-beta` does not equal `1.2.0`.

Repair rules: one blocker per commit, single-line message stating what changed and why. Each repair ships a regression test named for the behavior it protects. Run `swift build` and `swift run nitesubmit-tests` after each group.

---

## Phase C — Major hardening (same branch, after B is green)

- C1. Person-name Unicode: `FieldDetector.swift:278-308` rejects non-Latin names. Use Unicode letter class.
- C2. File ops: close TOCTOU, symlink guard, temp sibling in dest dir + `replaceItemAt`, propagate hash errors.
- C3. Case-insensitive collision check for APFS.
- C4. Scanner: throw on unreadable dir, sort by `relativePath`.
- C5. Licence: explicit little-endian timestamp, reject far-future, surface store failures, `NSSecureTextField`, 0600 atomic write.
- C6. PDF bounds: truncate before materialize, per-page OCR for empty pages.
- C7. Optimizer/archive atomicity: temp sibling + replace, throw on stat fail, post-verify page count.
- C8. Media: extension + magic-byte check, filename-ID confidence `.low`.
- C9. App: `loadFile` for media drops, off-main extraction/archive, per-item receipts, clear queue on reset.
- C10. CLI: strict `--policy` switch, unknown `--rule` errors, manifest failure exits non-zero.
- C11. Tests: replace `try!`/force-unwrap with throwing checks, assert missing corpus files, fix vacuous `FailureTests`, unify corpora or add parity gate.
- C12. Packaging: sign `Resources/lib/*.dylib` inside-out, `spctl` fail-closed, `SHA256SUMS` pin for `tools/bin` + `tools/lib`, move `tools/license-private-key.base64` out of tree and add bundle-content guard.

---

## Phase D — Ship gate

D1. Versions agree: `VERSION`, `CHANGELOG.md`, `Package.swift`, built app, `web/appcast.xml` (version + enclosure + length + signature).
D2. Clean build from HEAD, full suite green with counts. No known failures.
D3. Source AND binary no-upload check. Entitlements reviewed.
D4. Secrets scan clean. Privacy + third-party notices accurate.
D5. Signed + notarized + `spctl -a -vv` clean on the actual artifact. arm64 disclosure matches ad.
D6. Install tested as written on a clean machine. No hardcoded `/Users/...` paths.
D7. Licence + purchase + fulfillment end-to-end. Keys not embedded in client.
D8. Sales claims audited. Docs current. Rollback plan in `RELEASE.md`.
D9. Refresh `SHIP_BLOCKERS.md` and `SHIP_READINESS_REPORT.md` with dated evidence.

Hard stop: any P0 → stop, deliver blocker report. Sale stays offline until every P0 shows `VERIFIED FIXED`.

---

## Deliverables (new files only, outside `Sources/`)

1. `docs/NITE_SUBMIT_REVIEW_V1.md` — Phase A per-file findings with citations.
2. Phase B + C repairs committed on a feature branch, with regression tests.
3. `SHIP_READINESS_REPORT.md` — Phase D per-phase findings.
4. `SHIP_BLOCKERS.md` — prioritized P0/P1 list with exact fix steps.
5. Sign-off checklist (ticked or crossed) + per-phase receipt.
