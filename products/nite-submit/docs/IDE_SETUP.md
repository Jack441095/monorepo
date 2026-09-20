# IDE / SourceKit-LSP setup (VS Code)

## Symptom seen in V1 preflight

Red diagnostics appeared on nearly every Swift file in this repository even
though `swift build` and `swift run nitesubmit-tests` passed cleanly with zero
errors and zero warnings.

## Root cause

**The VS Code window was rooted at `Audio_Engineering_Company/`, not at
`Nite_Submit/`.**

SourceKit-LSP discovers a Swift package by looking for `Package.swift` in /
above the workspace root. With the company folder open:

- no `Package.swift` is found → no module resolution,
- every file that does `import NiteSubmitCore` or references project types is
  flagged red with cascading "cannot find X in scope" errors.

These are **tooling false positives**, not compiler errors. The command line is
authoritative: `swift build` and the test runner both pass.

## Fix

Pick either:

1. **Preferred:** File ▸ Open Folder… → `…/Audio_Engineering_Company/Nite_Submit`
2. Multi-root workspace: add `Nite_Submit` as a workspace folder alongside the
   company folder (File ▸ Add Folder to Workspace…).

Then let the Swift extension re-index (Command Palette ▸ "Swift: Re-Index" or
reload the window). A repo-level `.vscode/settings.json` ships with sensible
Swift settings for when the folder *is* opened directly.

If diagnostics stay stale after opening the correct root:

```sh
cd Nite_Submit
swift package clean            # or delete .build/
swift build                    # regenerate index/store
# then reload the VS Code window
```

## Note on `swift test`

This machine has Apple **Command Line Tools only** (no full Xcode), so neither
XCTest nor Swift Testing modules are available and `swift test` reports
"no tests found". The canonical test command for this repository is:

```sh
swift run nitesubmit-tests     # 71 checks incl. 203-PDF corpus evaluation
```

Installing full Xcode would allow migrating to XCTest/Swift Testing; until
then the executable harness is intentional, not an oversight.
