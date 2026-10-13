# Submit shipping status — 2026-10-11

The ongoing [operations plan](OPERATIONS_PLAN.md) lists verified completed work
and the ordered owner, tester and engineering tasks that remain.

## Shipping decision

Private tester beta **1.0.0 is verified locally**. Public paid distribution is
blocked by the owner requirements below. The app is arm64, targets macOS 13.0,
and was tested on macOS 27.0.1. It is ad-hoc signed and not notarised; clean
quarantined installation and macOS 13 compatibility remain unverified.

The handoff was executed through implementation, final packaging, delivery
integration, GUI checks and documentation. Nothing was committed, pushed,
published, charged or sent by email. No dependency, permission, CI or recurring
cost change was made. All source changes remain reviewable in the shared tree.

## Final artifacts and retained evidence

Artifact paths and all four SHA-256 hashes are recorded in
`NITE_SUBMIT_RELEASE_REPORT.md` and
`artifacts/Submit-1.0.0-release-manifest.json`. The manifest was created at
2026-10-11T13:14:27Z from `00f2ad604cd814a2bf6981b3a277dc188dec67a2` on main
with uncommitted changes. Its dirty-path count describes that build instant;
subsequent documentation and owner-only tool preparation did not change the
app or CLI. Do not treat HEAD alone as the certified source snapshot.

- App: `artifacts/Submit-1.0.0-macOS.app`.
- ZIP: `artifacts/Submit-1.0.0-macOS.zip`.
- DMG: `artifacts/Submit-1.0.0-macOS.dmg`.
- Verified rollback: `artifacts/shipping-2026-10-11/verified-private-beta-1.0.0/`,
  with complete `SHA256SUMS`; earlier `rollback-pre-task/` files are uncertified.
- Same-drive corpus backup: `artifacts/corpus-backups/rebuilt-2026-10-11.tar.gz`,
  SHA-256 `d3b8112993f1408a02068d7d70b132348d1eed3d32c033f684775db6f490322a`.
  All 58 members, including 48 selected PDFs, match their sources byte-for-byte.
  This does not satisfy independent disaster recovery.

Logs below are under ignored `artifacts/shipping-2026-10-11/`. Reports from the
successful release gate are under `release.eO1iFa/`. Earlier red and failed
attempts are preserved as diagnosis evidence, not final certification.

| Command or verification | Final result / evidence |
| --- | --- |
| `./tools/run_release_checks.sh` | Exit 0, `release-check=pass`; `release-complete.log` |
| `swift run nitesubmit-tests` | 534/534, included in final gate |
| `python3 -m unittest discover -s tools -p 'test_*corpus.py'` | 27 passed, included in final gate |
| `python3 -m unittest discover -s tools -p 'test_update_appcast.py'` | 5 passed, included in final gate |
| `python3 tools/check_rebuilt_corpus.py --cli <packaged-cli>` | All 47 pinned ordinary inputs pass with source, extracted ZIP and mounted DMG CLIs |
| Synthetic parity and write gates | 239 total cases; 172 writes / 61 holds for 233 ordinary ID+Project inputs; all 233 name-bearing cases held |
| Qualified batch and acceptance | 47 inputs, 45 previews, 2 holds, zero writes; 9 submissions / 26 guidance preserve required-field and naming holds |
| Bundle/archive/approval/matrix | Passed: helpers, libraries, resources, notices, privacy, path containment, collisions, source preservation, locked/malformed/image cases, ZIP/DMG parity and reproducibility |
| Bundled compression/optimization | Unicode 7z/ZIP/tar.gz, AES incorrect-password rejection and round trips, 25 MiB split volumes, qpdf-valid PDF with unchanged source; source/ZIP/DMG |
| Backend scoped / full tests | 87 / 139 passed; `backend-scoped.log`, `backend-full.log`; isolated PostgreSQL and captured email |
| Exact final-ZIP local delivery | 1 passed; `local-delivery.log`; simulated test-mode GBP 2.00 purchase, licence validation, signature/replay rejection, authenticated exact-checksum download and magic-link replay rejection |
| Native final-app checks | Passed; `gui-verification.json`, `first-launch-final.json`; fresh invalid-key rejection, picker, review/correction/approval, copy/collision, queue retention, two-entry archive and image-only recovery |
| Changed shell syntax and failure guards | Passed; `script-syntax.log`; missing signing identity preserves artifacts; invalid explicit intake CLI exits 2 |
| `./tools/check_distribution_readiness.sh --profile NITE_SUBMIT --require-ready` | Exit 1; `distribution-readiness.log`; no Developer ID identity or notary profile |
| Prepared signing workflow tests | 4 passed; `signing-workflow-fixed.log`; red and removal mutation each fail 2 tests; stub tools only, no Apple submission |
| Final integrity / cleanup | `final-integrity.json`: 4/4 artifact hashes, 17/17 rollback hashes, 58/58 backup members; private signer scan passed; disposable homes and GUI copies removed |
| Approved hosted staging rehearsal check | Exit 1; `staging-readiness.log`; temporary storage and console email, no durable customer rehearsal |

The optional System Events UI script was prepared but not run; no automation
permission was enabled. Native accessibility checks used disposable settings,
public/controlled inputs and an isolated test licence. GUI copies save beside
the source; explicit destinations are verified through CLI `--to` / `--out`.
Test homes, test activation material and GUI fixture copies were removed after
the checks. The final matrix rerun passed after correcting its replacement
fixture alias to Stacey; see `matrix-final-review.log`.

## Accuracy and provenance

Public reviews pass authors 7/7, titles 9/9 and institutions 9/9: 25 assertions
on nine submissions. The other 26 public documents provide layout coverage.
Controlled reviews pass 11 IDs, one explicit absent ID and ten module codes:
22 assertions on 12 cases. Unknown fields are omitted. Controlled cases do not
establish accuracy on real private student documents.

Twenty-two public PDFs match historical hashes; 13 are new institutional
acquisitions. Nine original acquisitions remain unrecovered. Identities are
`REBUILT_PUBLIC_2026_10_11_V1` and `REBUILT_FIELD_POLICY_2026_10_11_V1`.
The tracked qualification file pins exact cases, PDF hashes, modes, reviewed
fields and truth fingerprints. Old manifests were not fabricated and historical
parity is not claimed. Sheffield Stacey/Long replace unavailable UTAR/Berklee
smoke inputs; provenance and independently derived expectations are recorded in
`docs/CORPUS_REBUILD_2026-10-11.md`.

The MIT scan now passes without changing truth or lowering confidence. OCR
geometry, staff/prior-degree ranking, wrapped years and colonless candidate
labels have reproduced-red regressions. Critical mutations were rejected;
`ocr-mutation-check.log`, `candidate-mutation.log` and `mutation-check.log`
retain the evidence. Signing/notary failure now discards pre-signing pass
metadata; its regressions reproduced red and rejected the guard-removal
mutation in `signing-workflow-mutation.log`. Existing linker/CoreGraphics diagnostics and macOS 27
sandbox/hdiutil diagnostics remain visible; the final affected checks pass.

## Engineering changes

- Preserve the incoming split-title fix and ambiguous-name holds. Separate
  adjacent OCR rows; reject staff headings and dated prior degrees as work
  metadata; use matching repeated OCR titles while keeping alternatives under
  review. Recognise a whole-line candidate label without accepting prose.
- Expose the actual PDF browse action to accessibility clients.
- Migrate QA to approved rebuilt records and fail on wrong reviewed values at
  any confidence, changed hashes, missing cases or stale child reports. Stage
  copies for writing while retaining production symlink rejection. Verify
  actual delivered bundles with their own helpers and libraries.
- Resolve the external licence signer in activation tests. Test the current
  ZIP through isolated purchase/delivery paths. Reject inconsistent update
  version/name/URL/key, and prepare signing/notarisation with credential
  preflight, fresh gates, app/DMG stapling and measured final metadata.
- Refresh install guidance, tester missions, privacy-safe feedback, rollback,
  operating evidence and the local corpus backup.

## Owner-only next actions

1. Supply Developer ID Application credentials and the `NITE_SUBMIT` notary
   profile; execute `tools/sign_and_notarize.sh`, then clean-Mac installation
   testing including macOS 13 before claiming that minimum has been tested.
2. Supply the offline update key matching the existing public pin; stamp and
   review the final signed ZIP metadata without rotating the pin.
3. Verify exact UK registered name, number and office, approve legal text,
   align Stripe business classification and the intended active Submit GBP 2
   product/price. Incorporation was asserted; those details remain unverified.
4. Provide approved durable staging R2/Resend and Stripe Sandbox configuration,
   authorize real email, and complete the current-build purchase/inbox/download
   rehearsal. Local simulation is not a hosted Sandbox purchase.
5. Retain an independent corpus backup and authorized tester PDFs for broader
   real ID/module/anonymous coverage. Make a separate publication decision
   after the public requirements pass.

Production Fly probes show durable R2/Resend but checkout/legal/release false;
a 503 followed by a 200 retry is not an uptime guarantee. Staging is the
existing approved Fly service; no new deployment was made. The unsigned
zero-length appcast placeholder is not a valid published update. UpdateEngine
verifies signed version + HTTPS URL metadata and opens that URL; it does not
verify downloaded archive bytes itself. The previous live GBP 2 payment does
not certify this build. No live charge or real email was used here.

## Exact changed-file inventory

These are the cumulative Submit files continued or added for this handoff;
the inventory includes incoming Submit work rather than claiming every line
was authored in this run. Git-ignored artifacts, corpus PDFs, source URLs,
reviews and reports are retained locally and are not Git additions.

- `products/nite-submit/.gitignore`
- `products/nite-submit/NITE_SUBMIT_BETA_HANDOFF.md`
- `products/nite-submit/NITE_SUBMIT_RELEASE_REPORT.md`
- `products/nite-submit/README.md`
- `products/nite-submit/RELEASE.md`
- `products/nite-submit/Sources/NiteSubmitApp/DropZoneView.swift`
- `products/nite-submit/Sources/NiteSubmitCore/FieldDetector.swift`
- `products/nite-submit/Sources/NiteSubmitCore/PDFExtractor.swift`
- `products/nite-submit/Sources/NiteSubmitTests/DetectorTests.swift`
- `products/nite-submit/Sources/NiteSubmitTests/Fixtures/corpus/manifest.json`
- `products/nite-submit/Sources/NiteSubmitTests/LicenseEngineTests.swift`
- `products/nite-submit/Sources/NiteSubmitTests/PDFExtractorTests.swift`
- `products/nite-submit/Sources/nitesubmit-cli/Validation.swift`
- `products/nite-submit/docs/CORPUS_REBUILD_2026-10-11.md`
- `products/nite-submit/docs/OPERATIONS_PLAN.md`
- `products/nite-submit/docs/SHIPPING_STATUS_2026-10-11.md`
- `products/nite-submit/tools/Fixtures/corpus/manifest.json`
- `products/nite-submit/tools/Fixtures/rebuilt_qualification_v1.json`
- `products/nite-submit/tools/build_reviewed_corpus.py`
- `products/nite-submit/tools/check_rebuilt_corpus.py`
- `products/nite-submit/tools/generate_corpus.py`
- `products/nite-submit/tools/restore_public_corpus.py`
- `products/nite-submit/tools/run_acceptance_sweep.sh`
- `products/nite-submit/tools/run_app_ui_smoke_check.sh`
- `products/nite-submit/tools/run_archive_smoke_check.sh`
- `products/nite-submit/tools/run_batch_approval_check.sh`
- `products/nite-submit/tools/run_beta_intake.sh`
- `products/nite-submit/tools/run_beta_intake_smoke_check.sh`
- `products/nite-submit/tools/run_bundled_tools_check.sh`
- `products/nite-submit/tools/run_full_corpus_write_check.sh`
- `products/nite-submit/tools/run_pdf_matrix_check.sh`
- `products/nite-submit/tools/run_release_checks.sh`
- `products/nite-submit/tools/sign_and_notarize.sh`
- `products/nite-submit/tools/stage_release_corpus.py`
- `products/nite-submit/tools/test_build_reviewed_corpus.py`
- `products/nite-submit/tools/test_check_rebuilt_corpus.py`
- `products/nite-submit/tools/test_release_corpus_scope.sh`
- `products/nite-submit/tools/test_restore_public_corpus.py`
- `products/nite-submit/tools/test_signing_workflow.py`
- `products/nite-submit/tools/test_stage_release_corpus.py`
- `products/nite-submit/tools/test_submit_delivery.py`
- `products/nite-submit/tools/test_update_appcast.py`
- `products/nite-submit/tools/test_validation_identity.sh`
- `products/nite-submit/tools/update_appcast.sh`
- `products/nite-submit/tools/verify_release_artifacts.sh`
- `products/nite-submit/tools/write_release_manifest.sh`

`docs/OPERATIONS_AUDIT_2026-10-08.md` also received a Submit shipping addendum;
its earlier operations work was preserved. The following unrelated dirty work
was left in place without edits by this task: `backend/app/config.py`,
`backend/tests/test_config.py`, `backend/cloudflare/`, `backend/fly.staging.toml`,
`backend/wrangler.staging.toml` and `products/kenn/KENN_PLAN.md`.

Do not reset or stash this shared tree. The next independent work requires an
owner credential/configuration or clean-Mac test above; final beta gates do not
need another rerun unless source, artifacts or qualified inputs change.
