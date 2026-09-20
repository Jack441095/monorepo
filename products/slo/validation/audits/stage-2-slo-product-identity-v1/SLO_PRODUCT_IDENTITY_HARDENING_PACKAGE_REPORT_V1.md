# SLO Product Identity Hardening Package Report V1

Date: 2026-08-31  
Package ID: `L-01-PRODUCT-IDENTITY-HARDENING-V1`  
Status: isolated engineering candidate; not a release or beta approval.

## Objective

Make the product name presented to users and hosts match the declared SLO
product contract without renaming internal C++ targets, classes, or source
directories.

## Change

- Changed JUCE's user-visible `PRODUCT_NAME` from `Smart Sample Manager` to
  `SLO`.
- Updated the generated AU/VST3 install-path comments to match the product
  name.
- Updated the macOS About dialog title and body to identify SLO.
- Added a low-cost identity validator and adversarial tests that reject the
  legacy product name on either user-facing surface.

Internal target and symbol names remain unchanged intentionally; this package
does not perform a broad refactor or change source ownership boundaries.

## Direct evidence

```text
python3 -B tools/validate_slo_product_identity.py
VALID SLO product identity: user-visible build and About surfaces use SLO

python3 -B -m unittest -q tools/test_validate_slo_product_identity.py
Ran 3 tests ... OK
```

No audio files, models, protected evaluation data, or generated build trees
were opened or modified by this package.

## Limits

This proves source-level identity consistency only. A fresh CMake configure and
host/DAW launch are still required to prove the generated bundle names and
plugin discovery behavior. Signing, notarisation, clean-machine installation,
and release registration remain open.

## Rollback

Withdraw this isolated package only; do not reset, clean, or alter the shared
SLO checkout or protected Audio_Too paths.
