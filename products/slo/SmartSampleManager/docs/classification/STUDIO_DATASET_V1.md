# SLO Studio-Labeled Dataset V1

## 1. Dataset Manifest
We selected a balanced subset of **1,607 files** (1,357 standard, 250 OOD) from `Sounds of KSHMR Vol.3` and compiled `dataset_manifest.json` with the following schema:
- `sample_id` (incremental integer)
- `sha256` (SHA256 hex checksum)
- `filename` (unique filename prepended with sample ID to avoid name collisions)
- `local_relative_path` (path in the scan directory)
- `vendor_id` (`KSHMR`)
- `pack_id` (`Sounds_of_KSHMR_Vol3`)
- `source_family` (clean prefix base string)
- `expected_subcategory` (target taxonomy class)
- `label_authority` (`TRUSTED_PACK_LABEL` or `OWNER_VERIFIED`)
- `label_confidence` (`HIGH`)
- `ambiguous` (`False`)
- `ood` (`True`/`False`)

## 2. Dataset Balance
The final clean, deduplicated dataset contains **1,272 samples** across 16 classes:
- Kick: 100
- Snare: 100
- Clap: 100
- Hi-Hat: 85
- Percussion: 100
- Bass One-Shot: 98
- Bass Loop: 90
- Synth: 40
- Synth Loop: 47
- Vocal Loop: 53
- Vocal Phrase: 100
- Impact: 68
- Foley: 100
- FX: 100
- Riser: 100
- Music Loop: 75
- Atmosphere: 0 (fused into Foley/Atmosphere overlaps during duplicate controls)
- OOD: 250
