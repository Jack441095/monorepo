# SLO Labeling Protocol & Boundaries

## 1. Provenance Authority Levels
To maintain strict data quality control, labels must belong to one of these levels:
- `OWNER_VERIFIED`: Verified directly by the product owner or music technicians (highest authority).
- `MANUALLY_VERIFIED`: Verified by manual audio playback during modeling audits.
- `TRUSTED_PACK_LABEL`: Mapped from clear vendor metadata folder directories (e.g. KSHMR kicks folder).
- `WEAK_FILENAME_LABEL`: Inferred from filename cues.
- `WEAK_FOLDER_LABEL`: Inferred from general folder structures.
- `SYNTHETIC_LABEL`: Programmatically synthesized waveforms.

## 2. Leakage Isolation & Splitting
- **Deduplication**: Exact SHA256 and cosine similarity > 0.995 duplicates are grouped. Only one representative is kept in the active training set.
- **Group-Aware Splitting**: All files sharing the same `source_family` prefix are forced into the same CV split.
- **Gold Standard Freeze**: We freeze the Gold Standard subset of **250 verified clean samples** to evaluate future architectures, strictly preventing any training runs from using these held-out validation samples.
