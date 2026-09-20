# KENN AbletonOSC Vendor Metadata

This directory contains the AbletonOSC Remote Script used by KENN's local
Ableton Live integration.

- Upstream: https://github.com/ideoforms/AbletonOSC
- KENN pin: `88b08476a2d24406dce54ef5f45d516c9affbf72`
- Pin source: the upstream `insert_device` extension in PR #173
- Installed runtime: `scripts/install_abletonosc.py`

The package is vendored for reproducible local setup. Preserve the upstream
license and attribution in `LICENSE.md`. Do not add KENN application logic to
this directory; transport policy and confirmation safety belong in
`apps/backend/src/kenn/`.
