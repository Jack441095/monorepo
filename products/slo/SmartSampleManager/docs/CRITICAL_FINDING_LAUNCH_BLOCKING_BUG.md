# Critical Finding: The App Did Not Actually Launch

Phase 7. This corrects prior "PASS" claims across Phase 5.5, 5.6, and 6 for dependency
bundling and the Homebrew dependency guard. Recorded prominently and permanently, not folded
quietly into another document's changelog, because it's the kind of finding future sessions
need to see before trusting any prior "dependency bundling: PASS" claim at face value.

## What happened

Every previous phase's automated Homebrew dependency guard (`scripts/check_homebrew_dependencies.py`)
reported all three release formats as passing with zero forbidden dependency paths. That was
true, and also not sufficient: the guard checked that no reference pointed at a Homebrew path,
but never checked that a non-Homebrew reference actually resolved to a real file. It never
occurred to verify the single most basic thing -- does the app actually launch -- because every
static analysis pass looked clean.

This session, in the course of trying to capture a real product screenshot for the website
(Section 45), the Standalone build was actually launched for the first time since the Phase 5.5
transitive-dependency-bundling fix. It crashed immediately:

```text
dyld[9908]: Library not loaded: @loader_path/libre2.11.dylib
  Referenced from: .../Contents/Frameworks/libonnxruntime.dylib
  Reason: tried: '.../Contents/Frameworks/libre2.11.dylib' (no such file)
```

The bundled file was actually named `libre2.11.0.0.dylib`. The reference and the actual file
never matched. **Every build produced since the Phase 5.5 transitive-dependency fix landed would
have failed to launch on a real customer's machine**, despite passing every automated check that
existed at the time.

## Root cause

`scripts/bundle_apple_deps.py`'s dependency-walking loop resolved a Homebrew symlink (e.g.
`/usr/local/opt/re2/lib/libre2.11.dylib`, pointing into `../Cellar/re2/<version>/lib/libre2.11.0.0.dylib`)
*after* deciding what name to rewrite the reference to, but *before* deciding what name to save
the copied file as. The rewrite used the symlink's short name; the copy used the resolved
Cellar file's long name. Two different filenames for what should have been the same reference.

## The fix

1. `scripts/bundle_apple_deps.py`: resolve the symlink once, up front, and use that single
   resolved name consistently for both the `install_name_tool -change` rewrite and the file
   actually copied into `Frameworks/`.
2. `scripts/check_homebrew_dependencies.py`: added a second, independent check
   (`check_missing_deps`) that resolves every `@loader_path`/`@rpath` reference in every bundled
   Mach-O binary against the actual bundle contents and fails if the target file doesn't exist.
   This is the check that should have existed from the start -- a forbidden-path scan alone was
   never sufficient to prove a bundle actually works.

## Verification this time (not static analysis alone)

1. Full clean rebuild, both `build/` (Debug) and `build-release/` (Release) trees, all three
   formats, synchronous foreground builds (no backgrounding, learned from a prior session's
   false-completion issue).
2. New `check_missing_deps` check run against all 6 resulting bundles (2 trees x 3 formats):
   all pass with zero missing files.
3. **The Standalone binary was actually launched** (`Contents/MacOS/Smart Sample Manager` run
   directly, not just inspected with `otool`). It started, stayed running, and a screenshot was
   captured showing the real, rendered "SMART SAMPLE MAPPER" UI -- saved to
   `nitedsp/website/public/screenshots/main-browser.png` and used on the website's product page.
4. **The AU component was actually validated with Apple's own `auval` tool** against the real
   installed component (`~/Library/Audio/Plug-Ins/Components/`, refreshed by this rebuild's
   `COPY_PLUGIN_AFTER_BUILD`): `auval -v aufx AtSm NDSP` → `AU VALIDATION SUCCEEDED`. This is
   the first time in this project's history that `auval` has actually been run against a real
   build -- previous phases only ever ran the release-manifest/Homebrew-path static checks.
5. Native suite reconfirmed 12/12, zero leaks. Commercial backend reconfirmed 11/11. No
   regression from fixing this.

## What this means for prior phase claims

Every "dependency bundling: PASS" or "Homebrew dependency guard: PASS" statement in
`docs/PHASE_5_5_FINAL_SYNTHESIS.md`, `docs/PHASE_5_6_FINAL_SYNTHESIS.md`,
`docs/PUBLIC_LAUNCH_FINAL_SYNTHESIS.md`, and `docs/PRIVATE_BETA_RC.md` up to this point was
accurate *as a description of the check performed*, and **incomplete as evidence the app actually
worked**. Those documents are not being retroactively rewritten (their record of what was
checked at the time is accurate history) -- this document is the correction layered on top.
`docs/PRIVATE_BETA_RC.md` and `docs/PUBLIC_LAUNCH_CHECKLIST.md` are updated to reference this
finding directly.

## The broader lesson (recorded so it isn't relearned the hard way twice)

A static analysis pass, however thorough, is a hypothesis about runtime behavior -- not a
substitute for exercising the actual behavior at least once. This project has real product code,
real signing/notarization steps, and real customer download flows ahead of it; wherever
practical, prefer "did we actually run it" over "does the analysis look clean," especially for
anything gating a release.
