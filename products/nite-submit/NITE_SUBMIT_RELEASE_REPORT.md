# Submit 1.0.0 verification report — 2026-10-11

Private tester beta ready locally. Public paid release remains blocked by the
owner requirements below. Nothing was committed, pushed, published, emailed or
charged. Earlier 0.2.0 results do not certify this build.

## Final artifacts

Paths are relative to this product directory. VERSION is 1.0.0. The arm64
bundle targets macOS 13.0 and displays as Submit.

| Artifact | SHA-256 |
| --- | --- |
| `artifacts/Submit-1.0.0-macOS.zip` | `a82f66279d64e34a0dd95298bce040a28ad44072ba163ae44005b3a418c06129` |
| `artifacts/Submit-1.0.0-macOS.dmg` | `aba53fc83d2865c38b25fb0b76f38a0342d01b50e043d2c8b5e90bd5b38d64b4` |
| `artifacts/Submit-1.0.0-macOS.app/Contents/MacOS/NiteSubmit` | `4e3b88e792b1e50f9baf321062b60fcd7254f8520c1d64874dadd11bfc3437b8` |
| `artifacts/Submit-1.0.0-macOS.app/Contents/MacOS/nitesubmit-cli` | `482f20d8b8d2344310346f9d44827e1083fceff87150a4d1d64ce1f1dd11c5e0` |

Provenance: `artifacts/Submit-1.0.0-release-manifest.json`, created at
2026-10-11T13:14:27Z from main at `00f2ad604cd814a2bf6981b3a277dc188dec67a2`
with uncommitted changes. A directory has no single file hash; the table hashes
the executable. Complete file hashes and modes matched across the source app,
extracted ZIP and mounted DMG.

Ad-hoc signed; neither app nor DMG is notarised. Public distribution readiness
correctly exits 1: zero Developer ID identities and no `NITE_SUBMIT` notary
profile. `notarytool` itself is available.

## Final verification

Evidence is retained under ignored `artifacts/shipping-2026-10-11/`.

| Check | Result |
| --- | --- |
| `./tools/run_release_checks.sh` | Exit 0; `release-check=pass` |
| Swift / corpus Python / update-feed tests | 534/534; 27 passed; 5 passed |
| Public rebuilt corpus, source/ZIP/DMG CLI | 35 extracted; authors 7/7, titles 9/9, institutions 9/9 |
| Controlled rebuilt corpus, source/ZIP/DMG CLI | 12 extracted; IDs 11/11, explicit absent ID 1/1, modules 10/10 |
| Synthetic parity | 239 cases including edges; 233 ordinary PDFs |
| Synthetic ID + Project write | 172 byte-identical copies, 61 holds, zero collisions/failures |
| Synthetic name-bearing write | All 233 ambiguous-name cases held |
| Combined qualified dry run | 47 inputs, 45 previews, 2 holds, zero writes |
| Acceptance | 9 submissions and 26 guidance; anonymous/image cases; all 9 name-prohibited and module-required cases held |
| Approval/archive/matrix | Source preservation, explicit approval, missing fields, candidate number, Unicode, collisions, path containment, locked/malformed/image cases passed |
| Bundled tools, source/ZIP/DMG | Unicode 7z/ZIP/tar.gz, AES wrong-password rejection and round trips, 25 MiB split volumes, qpdf validity and unchanged originals passed |
| Bundle, dependency integrity and delivery parity | Passed, including resources, notices and deterministic ZIP |
| Beta intake privacy | 35 public fixtures; aggregate-only report passed; invalid explicit CLI exits 2 |
| Backend scoped / full tests | 87 / 139 passed in isolated test PostgreSQL |
| Exact final-ZIP local delivery integration | 1 passed: simulated Stripe test event, GBP 2.00, captured email, licence matching client key, webhook signature/replay rejection, magic-link replay rejection and authenticated exact-checksum download |
| Native final-app GUI | Fresh unlicensed launch/invalid-key rejection; picker, review/correction, approval invalidation, copy/collision, independent queue state, two-file archive, image-only hold and manual recovery passed |
| Prepared signing workflow | 4 isolated stub tests pass; signing/notary failure removes stale pass metadata, stapling precedes Gatekeeper, measured counts survive success; actual Apple submission remains blocked |
| Final retention / secret scan | 4 artifact hashes and 17 rollback file hashes match; 58 backup members byte-identical; no owner signer material detected; disposable test homes removed |
| Public distribution readiness | Expected exit 1, missing owner prerequisites |

The 26 public guidance PDFs are layout coverage only. Unknown fields are omitted.
Controlled IDs/modules do not establish real student-document accuracy. Nine
historical sources remain unrecovered. New identities are
`REBUILT_PUBLIC_2026_10_11_V1` and `REBUILT_FIELD_POLICY_2026_10_11_V1`;
no historical-manifest parity is claimed.

Regressions were reproduced red for OCR/staff/dated qualifications, wrapped
qualification years and candidate labels. Critical mutations were rejected,
including OCR row merging (526/529) and candidate detection (532/534).
Corpus hash/review/report, update URL and signing-manifest guards also reject
mutations. The signing/notary failure regressions reproduced red before the
manifest guard and reject its removal (2/4 failures).

Existing linker search-path and CoreGraphics diagnostics remain visible.
Extracted app processes emit macOS sandbox-extension diagnostics; macOS 27
also deprecates the hdiutil attach spelling. The affected checks passed.
Testing used Apple Silicon and macOS 27.0.1, not a clean quarantined macOS 13
installation. Intel is not built or claimed.

## Changed behavior

The existing split-title fix is preserved. OCR separates adjacent rows, strips
a terminal byline marker, rejects staff roles and dated prior degrees, and can
use a matching repeated title above an abstract. Original suggestions remain
alternatives requiring review. Whole-line `Candidate No. A12345678` supports
anonymous identity without matching prose. The browse control exposes its
actual action to accessibility clients.

QA pins reviewed cases, PDF hashes and truth fingerprints instead of discovering
folder contents. Missing UTAR/Berklee smoke inputs now use independently reviewed
Sheffield Stacey/Long covers. Write smokes stage regular copies; production
symlink rejection remains intact. Obsolete manifests were not fabricated.
Licence tests use the external signer location. Update stamping refuses a wrong
version, archive name, URL or signing key before changing the feed.

GUI exports save beside the input. Explicit destinations are the CLI `--to` and
`--out` workflow; no destination-picker feature was added. The optional System
Events smoke was prepared but not run or permission-enabled. Recorded GUI checks
used native accessibility control with disposable settings and public fixtures.
See `docs/SHIPPING_STATUS_2026-10-11.md` for the exact changed-file inventory.

## Delivery and owner requirements

Fly is the current backend. Production probes report durable R2 and configured
Resend, with checkout/legal/release false. A 503 followed by a 200 retry is not
an uptime guarantee. Approved Fly staging returns 200 but uses temporary local
storage and console email; its durable-rehearsal check exits 1. No new deployment
was made. Stripe is the payment provider; Paddle and Railway are obsolete.

Local delivery is a simulated test-mode webhook through the backend, not an
actual hosted Stripe Sandbox purchase. The older live GBP 2 payment is not
current-build shipping evidence. No real email was sent.

UpdateEngine verifies signed version + URL metadata and opens an approved HTTPS
URL; it does not download and verify archive bytes itself. Five feed-tool tests
use temporary keys. The real pinned update private key is unavailable. The
unsigned zero-length appcast placeholder was not published as a valid update.

The owner must supply/approve:

1. Developer ID Application identity and `NITE_SUBMIT` notarisation profile;
   run the prepared signing workflow, then clean-Mac installation testing,
   including macOS 13 before claiming that minimum has been tested.
2. The update private key matching the existing pin; stamp and review the final
   signed public ZIP metadata without rotating the pin.
3. Exact UK registered name, number and office, legal approval, Stripe business
   classification and intended active Submit product/GBP 2 price.
4. Durable approved staging R2/Resend and Stripe Sandbox configuration, real-email
   authorization, and the current-build purchase/inbox/download rehearsal.
5. An independent corpus backup and authorized tester PDFs for broader real
   ID/module/anonymous coverage. Publication needs a separate owner decision.

## Retention and rollback

The same-drive `artifacts/corpus-backups/rebuilt-2026-10-11.tar.gz` was refreshed:
58 files including 48 selected PDFs, all compared byte-for-byte with sources.
SHA-256: `d3b8112993f1408a02068d7d70b132348d1eed3d32c033f684775db6f490322a`.
It includes current review/provenance/reports and qualification fingerprints;
private intake and generated copies are excluded. It does not cover drive loss.

The verified beta is preserved under
`artifacts/shipping-2026-10-11/verified-private-beta-1.0.0/` with complete
`SHA256SUMS`. Verify these sums before restoring or distributing the copy.
`rollback-pre-task/` contains earlier unqualified artifacts and is not the
certified rollback target. Nothing has been published to roll back remotely.
