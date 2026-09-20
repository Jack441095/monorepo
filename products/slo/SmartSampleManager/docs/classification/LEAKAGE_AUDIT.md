# SLO Classification V2 Leakage Audit

## 1. Audit Findings
Our leakage audit of the mock real-world dataset surfaced **389 near-duplicate pairs** (cosine similarity > 0.995) across different packs. 

### Causes of Leakage
1. **Deterministic Generator Reuse**: The synthetic generator functions in `generate_real_world_dataset.py` modulated acoustic parameters using modular indices (e.g., `idx % 5` or `idx % 4`). Consequently, files sharing the same modular remainder generated mathematically identical or highly similar waveforms.
2. **Cross-Pack Distribution**: Since files were distributed to packs A, B, C, D sequentially, identical indices fell into different packs (e.g., sample 1 in pack A and sample 5 in pack B are acoustically identical).
3. **Implications**: Stratified CV and pack-held-out evaluations suffer from major data leakage, as exact duplicates of test samples are present in the training set under different names/folders. This artificially inflates performance scorecards.

## 2. Leakage Control Protocol
To establish a trustworthy baseline, we will implement the following controls in `run_research_v2.py`:
1. **Embedding Deduplication**: Remove pairwise duplicates (cosine similarity > 0.99) from the dataset before splitting.
2. **Group-Aware Splitting**: Ensure that any duplicate variants or groups remain strictly in the same fold (train or test), preventing cross-fold contamination.
