# panns_cnn10_embedding.onnx

Real, trained audio embedding model — replaces the previous `dummy_clap.onnx`,
which was an **untrained** placeholder CNN with randomly-initialized weights
(`generate_dummy_model.py`, still in the repo root for reference/comparison).
Every "similarity" the app computed before this model was noise; this one
produces genuinely acoustically meaningful embeddings (see verification below).

## Model

- **Architecture**: Cnn10, from [qiuqiangkong/audioset_tagging_cnn](https://github.com/qiuqiangkong/audioset_tagging_cnn)
- **Checkpoint**: `Cnn10_mAP=0.380.pth`, from [Zenodo record 3987831](https://zenodo.org/record/3987831)
- **Trained on**: AudioSet (Google), ~5000 hours, 527-class ontology
- **Embedding dimension**: 512 (matches this app's existing hardcoded
  assumption throughout `SampleItem::embedding`, the HNSW index, and the
  SQLite cache schema — no dimension-related changes needed elsewhere)
- **Input**: raw mono waveform, 32kHz, variable length (this app feeds a
  fixed 160,000-sample / 5-second window, padded/truncated, matching the
  existing `loadAndResampleWaveform` pattern)
- **What was exported**: only the 512D embedding output (`fc1` layer). The
  527-way AudioSet classification head was discarded — this app uses the
  embedding for acoustic similarity, not for predicting AudioSet tag labels.

## License (verified against primary sources, not assumed)

- **Code** (qiuqiangkong/audioset_tagging_cnn): MIT
- **Training data** (AudioSet): Google, CC BY 4.0 — explicitly permits
  commercial use. This is the cleanest data-provenance story of every
  candidate evaluated (see `../docs/THIRD_PARTY_LICENSES.md` for the comparison
  against LAION-CLAP and Microsoft CLAP, both of which carry real
  commercial-use complications).
- No separate/restrictive license was found on the Zenodo checkpoint
  hosting page beyond the repo's own MIT license.

## Export

Reproducible via `model_export/export_cnn10.py`. Two verification checks
were run (not just "it exports without error"):

1. **Numerical parity**: ONNX Runtime output vs. the original PyTorch model
   on identical input — max absolute difference `1.19e-6` (float32
   precision-level agreement, i.e. the export is numerically faithful).
2. **Acoustic meaningfulness**: embedded six synthesized test sounds (three
   kick-like percussive low tones, two hihat-like noisy transients, one
   sustained noise texture) and checked pairwise cosine similarity. Kicks
   clustered tightly with each other (0.985–0.993), the sustained texture
   was clearly separated from all percussive sounds (0.59–0.62 vs. 0.93+),
   and kick-vs-hihat (different timbre, same "percussive one-shot" category)
   landed in between (0.93–0.965) — the similarity structure lines up with
   real acoustic intuition, not arbitrary numbers.

## Files

- `panns_cnn10_embedding.onnx` (84KB) — graph definition
- `panns_cnn10_embedding.onnx.data` (24.2MB) — weights, stored as ONNX
  external data (the graph file alone is too small to contain them; both
  files must ship together, next to each other)

## Runtime requirements

Same as the model it replaces: ONNX Runtime (already a project dependency),
CPU inference with optional CoreML acceleration on Apple Silicon (already
wired up in `SampleManagerEngine::init()`). No new runtime dependency.
