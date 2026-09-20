# SLO / SmartSampleManager Build-Tree Policy

Status: committed build-entry policy for the SLO candidate.

All builds start from `SmartSampleManager/CMakePresets.json`. The supported
tiers are:

| Preset | Purpose | Build behavior |
| --- | --- | --- |
| `ssm-dev` | Fast local development | Debug, no LTO, no plugin install |
| `ssm-qualification` | Executed qualification | Release, shipped-plugin LTO, test LTO off, no plugin install |
| `ssm-release-candidate` | Final release parity | Release, LTO on for product and tests, Apple dependency bundling on, no auto-install |

From `SmartSampleManager`:

```sh
cmake --preset ssm-qualification
cmake --build --preset ssm-qualification --target ssm_qual_full --parallel 8
```

Build trees and FetchContent sources live under the ignored sibling
`_build/` and `_cache/` roots, outside `SmartSampleManager` source files.
Plugin auto-installation is explicitly off in the common preset and must not
be enabled by a default or CI preset. Installation, signing, and notarisation
are separate owner-approved release actions.

Existing legacy build trees remain preserved until separately inventoried and
retired under the copy/compare/qualification/rollback procedure. This policy
does not delete or clean any existing tree.
