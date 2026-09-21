# C++ migration opportunity matrix

The decision rule is measured total-product value, not “native is faster.” Numerical parity, memory ownership, deployment cost, debugability and realtime safety are first-class gates.

| Candidate | Hot-path evidence | Expected gain | Memory / zero-copy feasibility | Realtime suitability | Complexity / portability | Decision |
|---|---|---:|---|---|---|---|
| Bulk offline audio analysis | Fresh 10 s p50: 440.133 ms Python vs 43.830 ms native; real stem 475.969 vs 8.300 ms | High, 10.04x synthetic and 57.35x real-stem p50 | Existing input reports no copy; result arrays can be native-owned | Worker only | Medium; Accelerate needs portable fallback | **Promote behind opt-in now; make default after gates** |
| Spectral feature kernel | Native p50 3.5751 ms on 10 s synthetic input | High component value | Contiguous float buffers fit well | Worker or carefully bounded native thread | Medium | **Move/retain in C++** |
| Masking kernel | Native p50 6.1818 ms | High component value | Same | Worker; not callback until WCET proven | Medium | **Move/retain in C++** |
| Decode/resample/bulk metrics pipeline | Existing native decoder/smoke receipts and parity tests | High when it avoids Python materialization | Best opportunity is one native pipeline with one boundary crossing | Worker only | Medium-high, codec/platform packaging | **Consolidate in C++ incrementally** |
| Complete Mix Review | Fresh p50: 165.780 vs 146.338 ms | Low, 1.13x | Possible but orchestration remains Python | Offline | Medium | **Reject default promotion; keep optional** |
| Plugin metering/DSP | Already C++/JUCE; kernel at 0.072%–0.112% callback deadline | Required | Preallocated native buffers | Yes, with callback rules | Medium | **Keep C++** |
| OSC/network Live control | No measured CPU bottleneck; latency is transport/Live dominated | Negligible | Serialization/network copies dominate | Never audio callback | High rewrite risk | **Keep Python/service layer** |
| Command parser, proposals, safety policy | 111/111 deterministic corpus; not CPU-bound | Negligible | Poor fit; business logic changes frequently | Not callback | High maintenance cost | **Keep Python** |
| Retrieval/BM25/session memory | Active bottleneck is missing embeddings/manual corpus, not CPU | Unknown and premature | Database/index boundary dominates | Not callback | High product churn | **Keep Python; fix data/evaluation first** |
| JSON schema validation and receipts | Safety/audit path, not measured hot | Negligible | Copy reduction irrelevant | Not callback | High duplication risk | **Keep Python** |
| ONNX embedding/inference runtime | Not currently qualified or measured | Potentially material | C++ tensors can avoid copies if lifecycle is explicit | Worker only | High model/operator/package risk | **Prototype, benchmark, then decide** |
| AudioGen generation | Producer implementation is outside canonical checkout and no E2E latency was measured | Unknown | Model-specific | Worker/process | Very high ownership risk | **Do not migrate from KENN; integrate by contract** |
| SLO library inference/indexing | Production source is outside canonical checkout; no current handoff | Unknown | Potentially good for large libraries | Worker/process | High ownership/deployment risk | **Keep SLO-owned; integrate by versioned manifest** |
| HTTP/frontend orchestration | No evidence of CPU constraint | Low | Not relevant | Not callback | High churn | **Keep TypeScript/Python** |

## Promotion gates for native bulk analysis

1. Golden parity across representative mono/stereo files, silence, denormals, clipping, very short and long assets, 44.1–192 kHz and relevant PCM depths.
2. p95 and p99 improvement on at least two supported Apple machines; investigate the observed synthetic p95 spread.
3. Peak RSS and boundary-copy accounting in the same process, not only separate-process samples.
4. ASan and UBSan clean; TSan clean for any shared state; fuzz malformed inputs/metadata.
5. Wheel/artifact packaging, clean-clone build, license notices, hashes and Python/native fallback tests.
6. No numerical or schema drift in downstream Mix Review, arrangement and recommendation consumers.

## Why several migrations are rejected

Python is not the dominant cost in Live network control, policy, receipts or retrieval configuration. Rewriting those layers would increase implementation surface without improving producer latency or correctness. The 1.13x complete Mix Review result is likewise below a sensible promotion threshold: it adds packaging and failure modes while leaving orchestration and other costs intact.

## Reproducible primary research links

- Apple Accelerate: https://developer.apple.com/documentation/accelerate
- Apple vDSP: https://developer.apple.com/documentation/accelerate/vdsp-library
- nanobind ndarray: https://nanobind.readthedocs.io/en/latest/ndarray.html
- nanobind GIL: https://nanobind.readthedocs.io/en/latest/api_core.html
- JUCE parameter state: https://docs.juce.com/master/classjuce_1_1AudioProcessorValueTreeState.html
- ONNX Runtime C/C++: https://onnxruntime.ai/docs/api/c/c_cpp_api.html
- ONNX Runtime CoreML EP: https://onnxruntime.ai/docs/execution-providers/CoreML-ExecutionProvider.html
- CMake architectures: https://cmake.org/cmake/help/latest/prop_tgt/OSX_ARCHITECTURES.html
- CMake IPO: https://cmake.org/cmake/help/latest/prop_tgt/INTERPROCEDURAL_OPTIMIZATION.html
- Clang sanitizers: https://clang.llvm.org/docs/AddressSanitizer.html, https://clang.llvm.org/docs/UndefinedBehaviorSanitizer.html, https://clang.llvm.org/docs/ThreadSanitizer.html
- ccache: https://ccache.dev/
