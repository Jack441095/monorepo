# SmartSampleManager — Installer Architecture (Design)

Phase 2, Sections 35-38. **Design document — no installer has been built this pass.** Building a
real, signed, notarized installer requires the dependency-bundling work
(`docs/RUNTIME_DEPENDENCY_STRATEGY.md`) to land first, plus Apple Developer credentials flagged
in `docs/HUMAN_COMMERCIAL_REQUIREMENTS.md` — neither exists yet, so an installer built now would
either be untestable on a clean machine or unsigned, and shipping either silently would violate
the "do not fake completion" instruction.

## Target shipped formats (unchanged from `docs/RELEASE_MANIFEST.md`)

VST3, AU, Standalone — all three already build correctly per Phase 1's verification; this
document only concerns *packaging and installing* them, not building them.

## macOS: `.pkg` via `productbuild`

**Recommendation: a standard Apple `.pkg` installer**, built with `pkgbuild`/`productbuild`
(both are macOS-native, no third-party tool needed — simpler than a `.dmg`-with-drag-to-Applications
approach for a plugin, since plugins install to fixed OS-standard locations rather than a
user-chosen one).

```text
pkgbuild --root <staging-dir> --identifier com.nitedsp.smartsamplemanager.pkg \
    --version <version> --install-location / component.pkg
productbuild --distribution distribution.xml --package-path . SmartSampleManager-Installer.pkg
```

### Standard install destinations (never requiring the user to know these paths)

```text
~/Library/Audio/Plug-Ins/VST3/Smart Sample Manager.vst3
~/Library/Audio/Plug-Ins/Components/Smart Sample Manager.component
/Applications/Smart Sample Manager.app                    (Standalone)
```

Per-user (`~/Library/...`) rather than system-wide (`/Library/Audio/Plug-Ins/...`) for VST3/AU —
avoids requiring admin/sudo for the plugin formats, matching how most indie JUCE plugins already
install. The Standalone app going to `/Applications` does require admin, which `productbuild`
handles via its own privilege-escalation prompt — standard, expected macOS installer behavior.

### Uninstall

macOS has no built-in "uninstall" concept for `.pkg`-installed files (unlike Windows). Two
options: (a) ship a small uninstall script under the app's own Resources, invoked from a menu
item, or (b) document manual removal (delete the three paths above). **Recommendation: (a)** —
low effort, meaningfully better UX than telling a customer to hand-delete plugin bundles.

### Update strategy

Re-running the same `.pkg` with a newer version overwrites the existing install cleanly, since
`pkgbuild`'s `--identifier` stays stable across versions (this is exactly what
`docs/NITE_DSP_PRODUCT_IDENTITY.md`'s bundle-ID/manufacturer-code immutability guarantees —
nothing about install *identity* changes between versions, only the binary contents).

## Signing and notarization (blocked on human action)

```text
Build unsigned .pkg
    ↓
codesign each bundle (VST3/AU/Standalone) with Developer ID Application cert
    ↓
productsign the .pkg with Developer ID Installer cert
    ↓
xcrun notarytool submit --wait
    ↓
xcrun stapler staple (attaches the notarization ticket so it works offline)
```

**Every step above requires an Apple Developer Program membership and the two Developer ID
certificates** — already flagged in `docs/HUMAN_COMMERCIAL_REQUIREMENTS.md` as "REQUIRED BEFORE
BETA." This document defines the pipeline; it cannot run until those credentials exist.

## CI integration boundary

Per Section 43-45 of the master prompt: this installer/signing pipeline must be a **separate
release workflow** from the existing `smart-sample-manager.yml` CI (which builds+tests on every
push) — not folded into it. The release workflow should:

1. Trigger only on a deliberate version tag, not every push.
2. Build the explicit SmartSampleManager targets only (already CI's pattern — see
   `docs/RELEASE_MANIFEST.md`'s sibling-exclusion note).
3. **Assert no sibling-plugin artifact exists in the output directory** before packaging — fail
   loudly rather than silently including `AudioToo_Reverb`/`KENNMixAssistant`/`MidiGenerator`
   output if the umbrella build ever accidentally produced it.
4. Require a manual approval gate before the signed/notarized package is published anywhere
   public.

**Not built this pass** — the signing credentials this workflow depends on don't exist yet, so
writing the workflow file now would create untestable CI configuration. Documented here as the
target shape for when Milestone E's credential-dependent items are unblocked.

## Windows installer (separate document)

See `docs/WINDOWS_READINESS.md` — Windows build status itself is unverified, so an installer
choice is premature until a working Windows build exists to package.
