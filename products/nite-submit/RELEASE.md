# Submit release procedure

Read VERSION for filenames. The current verified private beta is 1.0.0;
[NITE_SUBMIT_RELEASE_REPORT.md](NITE_SUBMIT_RELEASE_REPORT.md) records its hashes
and [NITE_SUBMIT_BETA_HANDOFF.md](NITE_SUBMIT_BETA_HANDOFF.md) its tester workflow.

## Local private-beta gate

From this product directory:

```sh
./tools/run_release_checks.sh
```

No corpus argument is accepted. The gate stages exactly 47 cases from the pinned
rebuilt qualification record and verifies the independent ignored review records
and source hashes. Public/controlled identities remain distinct. It never uses
private intake, rejected PDFs, renamed output or a directory-wide PDF scan as
qualification. The image-only edge is checked separately. Missing historical
manifests are not fabricated; see docs/CORPUS_REBUILD_2026-10-11.md.

The gate runs Swift and Python checks, synthetic parity, dependency integrity,
bundle/resources/notices, privacy, cleanup, deterministic ZIP, matrix, approval,
archive/password/volume/optimisation, acceptance and 233-PDF write checks.
It builds a fresh app, ZIP and DMG, then tests both extracted/mounted bundles and
their own CLI/helpers, including all 47 rebuilt inputs. It removes a stale pass
manifest before starting and writes a new one only at the end.

Outputs are `artifacts/Submit-<VERSION>-macOS.app`, `.zip`, `.dmg` and
`Submit-<VERSION>-release-manifest.json`. Packaging can remove older top-level
semver artifacts; preserve verified rollback copies in a separate ignored
subdirectory first. The current snapshot is under
`artifacts/shipping-2026-10-11/verified-private-beta-1.0.0/` with SHA256SUMS.

## Public signing preparation

The current artifacts are ad-hoc signed and unnotarised. Do not publish them as
Developer ID releases or remove quarantine in the tester install instructions.
Readiness fails closed without the owner identity/profile and stapled artifacts:

```sh
python3 -m unittest discover -s tools -p 'test_signing_workflow.py'
./tools/sign_and_notarize.sh --identity 'Developer ID Application: <owner identity>' --profile NITE_SUBMIT
./tools/check_distribution_readiness.sh --profile NITE_SUBMIT --require-ready
```

The prepared signing workflow checks credentials before changing artifacts,
runs the full local gate, signs libraries/helpers/executables inside-out with
hardened runtime, notarises and staples the app, rebuilds both delivery formats,
then signs/notarises/staples the DMG. It verifies the final ZIP/DMG, assesses the
app, checks public readiness and regenerates hashes with the measured test
counts. Apple submission could not be exercised without owner credentials.

The four signing-workflow tests use isolated artifacts and stub Apple tools.
They verify failure cleanup and ordering without submitting anything to Apple.
The pass manifest is removed before the first signature and recreated only
after notarisation and delivery verification succeed.

Signing changes the final hashes. Recheck delivery with the signed final ZIP,
record its new manifest, and verify clean-Mac/quarantined installation. The
arm64 artifact targets macOS 13; this run tested macOS 27.0.1. Do not claim Intel
or minimum-version testing until those checks actually run.

## Licensing, delivery and updates

Submit activates offline with Ed25519 licence keys. Developer-only keygen reads
`$XDG_CONFIG_HOME/nite-submit/license-private-key.base64`, defaulting to
`~/.config/nite-submit/`. Never put the signer into a bundle or source tree.

Stripe is the payment provider, with GBP 2 one-time intended for Submit. The
current host is Fly with production R2/Resend. Checkout remains closed pending
verified company details, legal/release approval and the active Stripe product,
price and environment. Local integration used simulated test-mode events and
captured email; a current-build hosted Sandbox purchase/inbox/download rehearsal
still needs approved durable staging and explicit real-email authorization.

The owner must provide the offline update key matching UpdateEngine's existing
pin. After final signing, review the enclosure version/URL and run:

```sh
./tools/update_appcast.sh --version "$(tr -d '[:space:]' < VERSION)" \
  --zip "artifacts/Submit-$(tr -d '[:space:]' < VERSION)-macOS.zip" \
  --key /path/to/offline-update-private-key.base64
```

The tool checks version, archive name, enclosure URL and key match before editing.
The signature covers version + URL; the app opens that approved URL and does not
verify downloaded archive bytes. Release SHA-256 is verified separately during
delivery. The current unsigned/zero-length feed is a placeholder, not release
approval. Do not rotate its public pin to manufacture a passing update.

## Publication and rollback

Finish the owner requirements in the release report, then present the exact
signed artifacts, checksums, legal details and delivery evidence for publication
approval. No public deployment, real email, charge, commit or push occurred here.

For a private beta issue, pause distribution and verify the saved snapshot's
SHA256SUMS before restoring it. Do not reset the shared working tree or use an
old unverified tag/artifact as a certified rollback. A future public rollback
must close the affected download/checkout and restore a previously verified
signed release; customer communication requires explicit owner instruction.

Refresh the selected corpus backup after any reviewed-record change and compare
all archive members with source bytes. Its same-drive archive does not replace
an independent backup.
