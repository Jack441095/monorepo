# Security and exclusions

This handoff contains source code, tests, configuration examples and documentation. It does not contain:

- `.git` history or unrelated repositories/mirrors;
- real `.env` files or credentials;
- `node_modules`, Python environments or caches;
- compiled build or generated distribution directories;
- ONNX/MLX/other model files or weights;
- training notes, transcripts, PDFs or training/evaluation corpora;
- generated retrieval indexes or embeddings;
- chat/session databases, SLO databases, WAL/SHM files or runtime logs;
- audio, videos, archives or installer packages;
- private evaluation result packets.

The included SLO demo-cache script creates sanitized data locally after extraction. The generated `.runtime/` directory must not be returned or committed.

Generic `/Users/example` and `/Volumes/X` strings remain in security/path-handling tests and third-party AbletonOSC tests; they are synthetic fixtures, not owner paths.
