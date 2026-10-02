# Five-question Qwen stream capture — 2 October 2026

Recorded source: `b1d97ad105832105ff43701cd95d66388bdcbbbb`. The
[numeric receipt](KENN_QWEN_SMALL_CURRENT_PATH_2026-10-02.json) records one
small diagnostic run, not C1 qualification or a measured speed improvement.

## Conditions and ownership

Apple M3, 16 GiB unified memory; Ollama **0.34.4**, existing Qwen3 8B
`kenn-brain-qwen3-8b:latest` Q4_K_M. The existing Qwen3 4B planner digest was
frozen but was not exercised. Code, selected model digests, active index
`v-db8c6334cf63` and native fp32 ONNX embedding identities match before/after.
All five questions used loaded embeddings without an embedding error.

The harness explicitly enabled global LLM generation and rewrite and pinned local
Ollama task models. Inherited configuration had generation disabled and no model
selected; this is an experiment configuration, not observed production readiness.
Existing per-task switches, optional critique, evidence/output caps and timeouts
were retained. LLM critique was disabled. Native thinking-off already exists;
the general output cap is 384 tokens, evidence context 1,200 characters, native
keep-alive 30 minutes, socket timeout 20 s and overall stream deadline 60 s.

The benchmark and embedding processes started cold. No selected model was
resident at the initial `/api/ps` observation; the harness neither prewarmed nor
unloaded models. Only the 8B model was resident at the end, with a 4,096-token
context and 5,722,288,946 bytes reported by Ollama for model memory.

The real `tooling/scripts/measure_chat_latency.py` runner executed five existing
public corpus questions on its **stream** surface. The LLM response cache was
disabled and the runner cleared the semantic cache before each question.
Private runtime/session/database/log/output paths were isolated under a temporary
directory before imports. FakeLive recorded **zero writes**. No models, indexes
or dependencies were downloaded, changed or rebuilt; no real Live session was used.

## Results

| Question ID | Total seconds | First delivered token, seconds | Provider active seconds | Verdict |
| --- | ---: | ---: | ---: | --- |
| `bass-processing` | 21.836 | 8.123 | 21.537 | Generated answer accepted |
| `sidechain-release-time` | 15.603 | 6.758 | 15.516 | Generated answer accepted |
| `reverb-send` | 20.111 | 20.104 | 20.002 | Provider `TimeoutError`; template fallback |
| `gain-staging` | 10.123 | 6.775 | 10.015 | Unsupported-measurement prefix rejection |
| `streaming-loudness` | 10.694 | 5.320 | 10.605 | Unsupported-measurement prefix rejection |

All five attempted generation: **two accepted, three rejected**. The runner
reported zero unhandled errors; that count does not erase the handled provider
timeout. The final two rows each record one unsupported measurement and no
completed-answer validation call. Their classification follows the observed
prefix-guard path; raw warning text and generated measurements are not retained.

Median completion time across all five is **15.603 s**; the two accepted answers'
median is **18.720 s**. Median first-delivery time is **6.775 s**. Five observations
do not establish a tail-latency target. First delivery can be a fallback token:
the reverb row's 20.104 s is not model prefill time. Partial generated text can
also precede rejection; a delivered token does not establish a useful final answer.

The provider stream owner occupies **98.6–99.4%** of each runner wall time.
Routing takes less than 0.001 s per row, and no LLM critique call runs. These
observations do not support adding a classifier to accelerate this workload.
The first embedding load/lookup takes 0.079 s; subsequent lookups take less than
0.001 s. Provider usage exists only for the completed accepted rows:
1,144/232 and 1,087/160 prompt/completion tokens. Rejected streams lack terminal
usage; treating them as zero-cost generations would misreport the experiment.

The harness measures active execution of 31 existing owners, including bound
aliases. Generator active time sums execution inside resume/close calls and
excludes suspension in token consumers; elapsed generator spans can overlap
validation. Owner summaries preserve nested inclusive and exclusive times.
Neither measure separates model load, native prefill or decode: production
currently discards those native terminal fields. The normal keep-alive pinger
remains active in a separate thread, outside per-question attribution.

System-wide swap was about 1.04 GB at the start and 1.04 GB at the end; sampled
memory-pressure codes changed from 1 to 2, and reported free-memory percentage
from 67% to 25%. The benchmark process's maximum RSS was 313,081,856 bytes.
These are whole-system snapshots and process high-water readings, not isolated
model peak-memory measurements or evidence of audio dropouts.

## Capture and limits

The temporary instrumenting harness and raw numeric capture remain local. Their
SHA-256 values and the tracked runner/corpus hashes are in the receipt. The
committed receipt aggregates repeated calls by owner and preserves every row,
numeric verdict/count, typed exception, stage total and provenance fingerprint.
It contains no raw answers, query prose, unsupported values, private session data
or machine-specific paths. Capture completion checks verified unchanged source,
models, index and embedding hashes and zero FakeLive writes; `git diff --check`
and JSON parsing validate the evidence artifact.

C1 remains open: at least 30 questions, separate HTTP foreground/background and
stream runs, repeated comparable conditions, full stage/rejection telemetry,
displayed-result timing and controlled Live coexistence are still required.
The measurement and quality gates remain unchanged. Native phase/cache/early-exit
telemetry is the next measurement gap, followed by a controlled same-build
experiment; neither the source audit nor upstream research establishes a speedup.
