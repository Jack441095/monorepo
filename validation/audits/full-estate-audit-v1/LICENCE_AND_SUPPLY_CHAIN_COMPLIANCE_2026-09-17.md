# LICENCE & SUPPLY-CHAIN COMPLIANCE — 2026-09-17

| Component | Licence | Obligation | Satisfied? | Evidence |
|---|---|---|---|---|
| JUCE (SLO 8.0.2) | Dual AGPLv3 / commercial | Commercial licence before closed distribution; notices | NOTICES present; commercial purchase UNVERIFIED | SmartSampleManager/THIRD_PARTY_NOTICES.txt; CMakeLists.txt:90 |
| JUCE (KENN vst3) | Same | Same | NOTICES NOT FOUND (P3 F-17) | vst3-plugin/CMakeLists.txt:34-37 |
| ONNX Runtime | MIT | Notices | Partial (bundled via SLO NOTICES — UNVERIFIED full) | CMakeLists.txt:129-207 |
| PANNs CNN10 model | Research (AudioSet weights; check original licence) | Attribution + redistribution terms | UNVERIFIED — must confirm before bundling .onnx commercially | Models/README.md:1-63 |
| CLAP tarballs (benchmark) | Check per-model | Same | UNVERIFIED | tools/classification_benchmark/ (not opened per cost discipline) |
| umappp v3.3.2 | BSD-2 | Notices | Claimed in NOTICES (spot-check only) | CMakeLists.txt |
| hnswlib v0.8.0 | Apache-2.0 | Notices | Same | CMakeLists.txt |
| TagLib 2.3.1 / dr_libs / libsodium / SQLite | LGPL/MPL/public-domain/ISC | Notices + dynamic-link notes where needed | UNVERIFIED beyond NOTICES file presence | THIRD_PARTY_NOTICES.txt |
| testing-assets sample packs | Per-pack commercial | Redistribution forbidden mostly | NO manifest (P2 F-12) | du 57G; no licence file found at top level |
| Fonts/site assets | Check | Notices | UNVERIFIED | website/public (not audited) |
| GPL/AGPL contamination | — | Must be absent in closed products | No GPL found in spot grep (FULL scan not run — residual risk) | — |

Actions: confirm JUCE commercial tier; confirm PANNs/CLAP redistribution; write testing-assets licence manifest; add KENN-vst3 + DiskSweep NOTICES; gate releases on NOTICES check.
