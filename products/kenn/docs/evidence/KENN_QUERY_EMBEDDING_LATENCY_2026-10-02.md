# Query embedding latency, 2 Oct 2026

KENN now uses CPU ONNX for retrieval embeddings. On the owner's M3 / 16 GB,
CoreML's partition dispatch cost more than inference for these short queries.
This changes the execution provider only: model weights, tokenizer, pooling,
normalisation, thread settings and the existing index stay the same.

The workload was the first 40 questions from
`tooling/data/citation_eval_queries_v1.json`, used here as questions only. Each
new session had three warm-up queries, followed by 40 individually timed queries.
Sessions ran sequentially in CoreML → CPU → CPU → CoreML order, using the
existing default thread settings. No model download or index rebuild was needed.

| Provider | Session startup | Query p50 | Query p95 |
|---|---:|---:|---:|
| CoreML + CPU, first run | 825 ms | 12.718 ms | 16.584 ms |
| CPU, first run | 43 ms | 1.153 ms | 1.459 ms |
| CPU, second run | 43 ms | 1.141 ms | 1.411 ms |
| CoreML + CPU, second run | 433 ms | 12.426 ms | 13.575 ms |

Across the 40 query vectors, minimum cosine agreement was 0.99999988 and the
largest absolute component difference was 0.00002103. The production
`chat_retrieval.search(..., limit=4)` path then returned identical ordered chunk
IDs for **240/240 questions**, using all 4,642 chunks of index `v-db8c6334cf63`.
This is provider equivalence on this workload, not a new recall or answer-quality gate.

Model identity: `Xenova/all-MiniLM-L6-v2`, 384 dimensions, 256-token limit.
Model SHA-256: `759c3cd2b7fe7e93933ad23c4c9181b7396442a2ed746ec7c1d46192c469c46e`.
Tokenizer SHA-256: `da0e79933b9ed51798a3ae27893d3c5fa4a201126cef75586296df9b4d2c62a0`.
These are the existing fp32 weights. Quantising them would change embedding
identity and needs a separate index qualification.

Raw local receipts are `.runtime/eval/embedding_provider_latency_2026-10-02.json`
and `.runtime/eval/embedding_provider_retrieval_2026-10-02.json`.

The saving is roughly 11 ms per query plus faster session startup. It does not
establish an improvement in model prefill, decoding or end-to-end answer time.
The North Star's Mac answer-latency gate remains open. No Live session was written.

Verification: 59 scoped tests passed across the provider, retrieval startup,
status, mode evaluation, evidence classes, index candidates, sealed holdout,
question-list filtering and weak-retrieval streaming. Restoring CoreML preference
made the new regression test fail; the source was restored byte-for-byte.
The full backend suite returned **3,089 passed, 1 failed, 12 skipped** in 77.86 s.
The remaining failure was the previously recorded order-dependent
`test_live_command::test_llm_plan_gets_one_structural_repair_attempt`; it passed
in isolation (1 passed in 0.12 s). Full log:
`/tmp/kenn-cpu-embedding-suite-2026-10-02.log`.
