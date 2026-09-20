# NITE Submit Public Signing Checklist

**Status:** Waiting for Apple Developer access
**Product:** NITE Submit 0.2.0
**Purpose:** Convert the current ad-hoc private-beta artifact into a trusted public candidate.

## Owner prerequisites

- Apple Developer Program membership active.
- Developer ID Application certificate available on the release Mac.
- Notarisation credentials stored in a named `notarytool` keychain profile.
- Release Mac backup/recovery path documented; private credentials are not placed in source control or ordinary backups.

## Release sequence

1. Start from a clean, reviewed release tag and record repository SHA.
2. Run `./tools/run_release_checks.sh` and retain the output receipt.
3. Build/package the app and verify bundle identifier, executable, PDF association, and architecture.
4. Sign with Developer ID Application using hardened runtime and timestamp.
5. Verify with `codesign --verify --deep --strict --verbose=2` and `spctl --assess --type execute`.
6. Submit the zipped artifact with `xcrun notarytool submit --wait --keychain-profile <profile>`.
7. Staple the ticket with `xcrun stapler staple` and validate with `xcrun stapler validate`.
8. Re-run Gatekeeper assessment on the stapled artifact.
9. Test install, launch, PDF workflow, copy/rename safety, uninstall, and rollback on a clean supported Mac.
10. Run `./tools/check_distribution_readiness.sh --require-ready`.
11. Write the release manifest with source SHA, dirty state, toolchain, artifact hashes, signing mode, notarisation result, and limitations.

Never paste certificates, private keys, notarisation secrets, or keychain output into Markdown, issues, or support tickets.
