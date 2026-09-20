# SLO Build-Entry Package Report V1

Status: committed build-entry policy; no product behavior or shared checkout
changed.

This package makes SLO’s supported build path explicit and easy to find. It
defines development, qualification, and release-candidate tiers, keeps build
and dependency state outside `SmartSampleManager`, and enforces disabled plugin
auto-installation in every preset. Legacy trees remain preserved and are not
retired by this package.

## Direct checks

```text
python3 -B tools/validate_slo_build_entry.py
python3 -B -m unittest tools/test_validate_slo_build_entry.py
cmake --list-presets
```

The qualification preset maps to the same safety properties used by the fresh
M-06A run: Release arm64 build, plugin LTO enabled, test LTO disabled, Apple
dependency bundling off for engineering qualification, and no auto-install.
The release-candidate preset is intentionally stricter but still does not
install plugins automatically.

Rollback is to stop using these additive presets and retain the prior explicit
command; no generated tree or active worktree is deleted.
