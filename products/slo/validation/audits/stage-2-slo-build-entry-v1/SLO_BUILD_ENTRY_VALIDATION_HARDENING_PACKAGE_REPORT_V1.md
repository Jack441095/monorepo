# SLO Build-Entry Validation Hardening Package V1

Date: 2026-08-31  
Package ID: `L-02-SLO-BUILD-ENTRY-HARDENING-V1`  
Product: `slo`  
Worktree: `workspace/worktrees/slo/slo-build-entry-v1`  
Base SHA: `2a8d274`

## Objective

Strengthen the lightweight SLO build-entry preflight so unsafe or incomplete
CMake preset changes fail before a potentially expensive build.

## Implemented checks

The validator now requires:

- the canonical sibling `_build` binary-root template;
- the canonical sibling `_cache/fetchcontent` root;
- no base-preset inheritance;
- every supported tier to inherit `ssm-base`;
- no absolute or in-source child `binaryDir`;
- arm64 architecture pinned in the common preset without child overrides;
- the canonical FetchContent root cannot be overridden by a child preset;
- the Debug/Release tier mapping is explicit and enforced;
- matching configure/build preset names; and
- plugin auto-install disabled in the base and every supported tier.

## Verification

```text
python3 -B -m unittest -q tools/test_validate_slo_build_entry.py
python3 -B tools/validate_slo_build_entry.py
git diff --check
```

Results:

- validator tests: `9 passed`;
- current three-tier preset: valid;
- adversarial cases covered: absolute build path, missing base inheritance,
  build/configure target drift, child auto-install override, architecture and
  FetchContent-root overrides, build-type drift, and common architecture drift.

This package intentionally does not claim a successful C++ build, executed
qualification, host validation, signing, licensing, or clean-machine release.

## Deliberately not touched

No C++ source, generated build/cache state, plugin installation, shared SLO
checkout, protected evaluation material, private data, credentials, signing
keys, provider, or release authority was changed.

## Rollback

Revert only the isolated validator/test/report commit. Existing generated
builds and caches remain untouched.

## Next package

Run the declared configure/build/qualification commands from the clean SLO
candidate when the approved environment and resource window are available,
then close host, licensing, signing, installation, support, and rollback gates.
