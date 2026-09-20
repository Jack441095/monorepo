# SLO Scanner Memory Optimization Recommendations

The classification baseline benchmark revealed significant memory retention:
- **Baseline Memory (Idle)**: ~14.28 MB
- **Peak Scanning Memory**: ~2439.41 MB
- **Retained Memory (Post Scan)**: ~1359.55 MB

This memory footprint is independent of the classification head. The following steps are recommended to address memory footprint in the scanning engine:

## 1. Scoped Memory Drivers
1. **ONNX Runtime Arenas**: By default, ONNX Runtime allocates memory pools for execution (arenas) and does not release them to the OS immediately. We should configure `Ort::SessionOptions` to disable memory arenas or release allocations periodically.
2. **Audio Decoders**: `SampleManagerEngine` decodes full audio files into memory buffers for processing. Ensure that decoded buffers are actively deleted or freed once the feature/embedding generation step finishes, rather than holding them in memory inside `SampleItem` queues.
3. **SQLite Page Cache**: SQLite database transactions hold onto page caches for optimization. We can limit page memory limits using `PRAGMA cache_size = 2000;` (limiting cache to ~2MB) or call `sqlite3_db_release_memory()` periodically.
4. **Thread Concurrency**: Multiple files are processed in parallel. Limiting the thread pool size can reduce peak memory overhead by bounding concurrent allocations.
