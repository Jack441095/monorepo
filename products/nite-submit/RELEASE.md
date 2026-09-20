# RELEASE — NITE Submit 1.0.0

## Build the artifact

```sh
./tools/package_app.sh
```

Produces `artifacts/Submit-1.0.0-macOS.app` containing the app plus the
`nitesubmit-cli` helper. Record version, source SHA, architecture and SHA-256
in `NITE_SUBMIT_RELEASE_REPORT.md`.

Packaging removes stale semver-named NITE Submit app bundles and ZIP archives
from `artifacts/` after the current bundle has passed verification. It keeps
the current version, test evidence, metadata, and the Swift `.build` cache.
The release gate also runs `tools/test_artifact_cleanup.sh` in an isolated
temporary directory to verify that boundary.
ZIP creation normalises timestamps in a temporary staging copy, and the gate
runs `tools/test_deterministic_archive.sh` to verify repeatable checksums.
The release gate also runs `tools/run_pdf_matrix_check.sh` across dissertation,
capstone, guidance, anonymous-candidate, and image-only PDFs.
It also runs `tools/run_full_corpus_write_check.sh`, which writes and verifies
both the safe ID+Project and explicit name-bearing rules across all 203
synthetic fixture PDFs without modifying the source corpus.

Packaging automatically runs `tools/verify_app_bundle.sh`, which checks the
bundle identifier, executable/CLI presence, PDF association, and code-signature
validity.

For a private tester handoff, run `./tools/package_beta_zip.sh`. It produces a
single ZIP archive, tests the archive contents, and prints its SHA-256 checksum.

The full local gate is `./tools/run_release_checks.sh`. With no argument it
automatically stages the approved PDFs under `real_validation_corpus/`,
excluding rejected documents and generated results. An explicit controlled
corpus directory may be passed as the first argument when needed.

The gate also extracts the exact ZIP into a temporary directory, verifies the
copied bundle, and exercises the staged CLI through detection and an explicitly
approved byte-identical copy.

Before public distribution, run
`./tools/check_distribution_readiness.sh --require-ready`. It reports only
boolean/key-count status (never secrets) and fails closed until a Developer ID
Application identity, a configured `notarytool` keychain profile, and a
Developer ID-signed app are all present. The private-beta gate intentionally
does not require those owner-controlled credentials.

The private-beta tester checklist is [NITE_SUBMIT_BETA_HANDOFF.md](NITE_SUBMIT_BETA_HANDOFF.md).

## Signing status

- Ad-hoc signed (`codesign -s -`). Not Developer-ID signed, not notarised.
- First launch requires right-click → Open (Gatekeeper bypass).
- The `tools/install.sh` curl installer removes quarantine automatically.
- The sales page guides users through Download → Unzip → Right-click Open.

## Release channel

PUBLIC RELEASE CANDIDATE → commercial release. Core workflows pass the deterministic
synthetic corpus. The governed first-wave run and wave-3 run both pass for
reviewed name/title/university fields. Targeted synthetic field-policy coverage
passes for student-ID/module-code formats, and group-author approval is
explicit; real student-ID/module-code accuracy still requires authorised tester
PDFs before a broader real-document claim.

## Known limitations (honest list)

- macOS only, macOS 13+.
- Local English OCR covers the first few pages of scanned PDFs; OCR-derived
  fields remain review-required and manual entry is still available.
- Presets are generic patterns, not official university rules; users should
  enter their university's own rule.
- Unsigned/un-notarized artifact for controlled testing only.
- The macOS UI now supports a multi-file queue (drop/select several files,
  each keeps its own independent detection/review/approval state); the local
  CLI separately provides scriptable batch dry-run and processing with
  CSV/JSON reports and collision controls.
- Real tester PDFs must be supplied through the ignored
  `real_validation_corpus/beta_intake/` workflow; they are never part of the
  committed corpus.

## Licensing

Ed25519 offline licence key system (`LicenseEngine.swift`). The app gates
behind activation on first launch. Keys are generated with the developer-only
`nitesubmit-keygen` CLI (reads `tools/license-private-key.base64`). The
private key is gitignored and never shipped.

Price: £3 one-time (lifetime student licence). Payment/checkout lives in the
website + payment processor, not in the product code.

## Rollback plan

If a critical issue is discovered after launch:

1. **Pull the download.** Remove `Submit-1.0.0-macOS.zip` and `install.sh`
   from the hosting location (`releases.nitedsp.co.uk/submit/`). Replace
   with a static page explaining the temporary removal.
2. **Revert the artifact.** The previous artifact (`artifacts/Submit-0.2.0-macOS.dmg`)
   is retained in the repo. Restore from the `v0.2.0-private-beta.1` tag if
   needed: `git checkout v0.2.0-private-beta.1 -- artifacts/`.
3. **Notify customers.** Email purchasers via the payment processor's customer
   list. Update the sales page with a banner.
4. **Fix and re-release.** Apply the fix, bump to 1.0.1, rebuild, retest,
   re-upload. Update `appcast.xml` so the update checker picks it up.
