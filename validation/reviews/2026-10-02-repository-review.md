# Nite-DSP repository review — 2 October 2026

This review found three reproducible file-loss paths, block-state defects in the native audio plugins, and missing imports in the extracted KENN AudioGen routes. These findings remain open. The Stripe commerce changes and the requested website/operations cleanup are recorded separately below.

This is a dated evidence report, not a new KENN roadmap. KENN work continues to be tracked in `products/kenn/KENN_PLAN.md`.

## Scope and limits

The review covered the folder `/Volumes/Jack_Gandy_1TB_SSD/Nite-DSP`, with implementation work confined to its main `monorepo`. File inventory, Python syntax parsing, undefined-name screening, searches for risky boundaries, selected manual tracing, local tests, and isolated reproductions were used together.

After excluding assistant run records, runtime folders, backups, workspace scratch files, training transcripts, analysis caches, benchmark output, and generated files, the initial inventory contains **6,777 text files and 1,838,037 lines**. Of these, **3,036 Python files** were syntax-parsed without a parse failure. These are mechanical coverage counts. They do not mean every line received a manual review, and the snapshot predates the implementation changes in this task. Third-party installations, private audio, credentials, and personal session data are outside the review.

Manual review and targeted execution focused on commerce/authentication/webhooks, the website checkout and waitlist routes, NITE Submit file operations, DiskSweep deletion/undo boundaries, KENN backend route extraction and package evaluations, Thursday operations, DSP kernels and their JUCE callers, stem normalization, and native build manifests. The rest of the folder received inventory and search coverage. The complete audio-analysis suite and native SLO build could not be validated in this environment; the exact limitations are below.

All reproductions used synthetic data in temporary directories, CPU tensors, fake service objects, or native kernel calls. No running Ableton session, privileged helper, production service, payment flow, or GPU was exercised. Concurrent user edits were preserved.

## Open findings

Priority definitions: **P1** should be corrected before releasing the affected feature; **P2** is a concrete defect to address during normal maintenance or before enabling a prototype.

### 1. [P1] DiskSweep overwrites trash entries with the same basename

Source: [sidecar/cli.py:88](/Volumes/Jack_Gandy_1TB_SSD/Nite-DSP/monorepo/products/disksweep/sidecar/cli.py:88).

`cmd_trash()` uses a run directory named with second precision and only the source basename for each destination. Selecting `first/cache.dat` and `second/cache.dat` sends both files to the same path. On this platform, the second `shutil.move()` replaces the first file. Both undo entries then reference the same destination, so undo restores the second file into the first source path and cannot restore the other source. Two runs in the same second also share the run directory and `undo.json`.

The isolated reproduction redirected `~/.Trash` to a temporary directory and mocked the Time Machine subprocess. Its result was `duplicate trash destinations: True`, `Restored 1/2 items`, and restored contents `['SECOND', '<missing>']`.

Use a unique run identifier and a collision-free destination for every source, refuse accidental replacement, and persist an undo record without overwriting another run. Add examples for repeated basenames and two calls in the same second.

### 2. [P1] NITE Submit deletes an archive input when its output overlaps that input

Source: [ArchiveEngine.swift:132](/Volumes/Jack_Gandy_1TB_SSD/Nite-DSP/monorepo/products/nite-submit/Sources/NiteSubmitCore/ArchiveEngine.swift:132).

`compress()` verifies that sources exist, removes an existing destination, and only then copies inputs into its staging directory. Calling it with `sources: [original.zip]` and `destinationArchive: original.zip` passes source validation, deletes the original, and throws when staging tries to copy the deleted file. An unrelated existing destination is also lost if a later staging or compressor operation fails.

The temporary Swift reproduction printed `original exists after archive failure: false`. It used the built NiteSubmitCore module and created no user files.

Reject source/output overlap after resolving paths, create and verify the archive at a separate staging destination, and replace the old destination only after successful completion. Cover identical paths, aliases, and a failed compressor with an existing output.

### 3. [P1] NITE Submit replacement moves destroy the old destination before success

Source: [FileOperations.swift:308](/Volumes/Jack_Gandy_1TB_SSD/Nite-DSP/monorepo/products/nite-submit/Sources/NiteSubmitCore/FileOperations.swift:308).

`moveOriginal(..., policy: .replace)` removes the previous destination before moving the new source. If moving fails, the old destination is already gone. The later hash-failure rollback can move the new file back, but does not restore the deleted previous file. The success receipt incorrectly says the earlier copy was removed only after the hash check.

The isolated Swift case created a writable output folder containing a previous file, made the source parent non-writable, and attempted replacement. The move threw a permission error and printed `previous target exists after failed move: false`.

Stage the incoming file, preserve the previous destination until verification succeeds, and restore both paths on failure. Test a denied source removal and a verification failure during replacement.

### 4. [P1] The AudioToo Reverb plugin discards delay state at every audio block

Sources: [PluginProcessor.cpp:96](/Volumes/Jack_Gandy_1TB_SSD/Nite-DSP/monorepo/audio-technology/vst3-plugins/AudioToo_Reverb/Source/PluginProcessor.cpp:96), [reverb_full_kernel.cpp:74](/Volumes/Jack_Gandy_1TB_SSD/Nite-DSP/monorepo/audio-technology/audio-analysis/audio_analysis/dsp_engine/native/reverb_full_kernel.cpp:74).

The plugin calls the offline `schroeder_reverb()` kernel independently for each host block. The kernel initializes its delay/filter buffers for that call and skips every comb filter whose delay is at least the current block length. With room size `0.5`, the shortest comb delay is 1,395 samples. At a normal 256-sample block size, every comb is skipped and a fully wet instance outputs silence.

A synthetic impulse at 44.1 kHz produced a peak of `0.1225` when processed as one 8,192-sample call, and a peak of `0.0` when split into 256-sample calls. The offline kernel itself may remain valid for whole-file use; its use as a streaming plugin processor is the defect.

Keep per-instance delay/filter state across `processBlock()` calls, reset it in the appropriate lifecycle method, and verify equivalent output across several block partitions. Thread-local scratch storage is not per-plugin signal state.

### 5. [P1] The AudioToo Limiter resets its envelope and reports latency it does not apply

Sources: [PluginProcessor.cpp:47](/Volumes/Jack_Gandy_1TB_SSD/Nite-DSP/monorepo/audio-technology/vst3-plugins/AudioToo_Limiter/Source/PluginProcessor.cpp:47), [PluginProcessor.cpp:105](/Volumes/Jack_Gandy_1TB_SSD/Nite-DSP/monorepo/audio-technology/vst3-plugins/AudioToo_Limiter/Source/PluginProcessor.cpp:105), [limiter_kernel.cpp:63](/Volumes/Jack_Gandy_1TB_SSD/Nite-DSP/monorepo/audio-technology/audio-analysis/audio_analysis/dsp_engine/native/limiter_kernel.cpp:63).

The plugin invokes an offline forward-window limiter once per channel and host block. Each call clears the maximum-window state, starts `release_state` at `1.0`, and zero-pads the end of that block. A transient at a block boundary therefore loses its release tail and cannot influence preceding samples in another block. The plugin also reports the lookahead as host latency, although the kernel writes processed `x[i]` to output index `i` and has no matching audio delay.

At 44.1 kHz, a 512-sample signal containing a peak at sample 255 gave output sample 256 of `0.062585` as one call and `0.25` as two 256-sample calls. A small impulse at index zero stayed at index zero, while the plugin reports 220 samples for 5 ms lookahead.

Use a streaming limiter with persistent lookahead and release state. Apply a real delay matching the reported latency and update the host when the latency parameter changes. Test boundary transients, release continuity, actual delay, and variable block sizes.

### 6. [P1] Extracted KENN AudioGen handlers reference names absent from their module

Source: [audiogen_handler.py:45](/Volumes/Jack_Gandy_1TB_SSD/Nite-DSP/monorepo/products/kenn/apps/backend/src/kenn/routes/audiogen_handler.py:45). Caller: [server.py:3188](/Volumes/Jack_Gandy_1TB_SSD/Nite-DSP/monorepo/products/kenn/apps/backend/src/kenn/server.py:3188).

The extracted module calls `public_audiogen_status`, `public_audiogen_history`, `public_audiogen_job`, and `public_audiogen_result` without importing or defining them. MIDI proposal/revision paths also reference missing service and conversion names. Those names being imported in `kenn.server` does not make them visible in the extracted module.

Calling the status handler with a fake available bridge returned HTTP `500` and `AudioGen status failed: name 'public_audiogen_status' is not defined`. This happens before any real AudioGen or Live operation. The existing backend suite passed without protecting this available-bridge route.

Import the extracted handlers' dependencies explicitly or pass them as clear arguments. Add route examples with an available fake bridge for status, history, job lookup, generation, and proposal/revision paths.

### 7. [P2] Native plugin CMake manifests still reference moved directories

Sources: [vst3-plugins/CMakeLists.txt:34](/Volumes/Jack_Gandy_1TB_SSD/Nite-DSP/monorepo/audio-technology/vst3-plugins/CMakeLists.txt:34), [vst3-plugins/CMakeLists.txt:45](/Volumes/Jack_Gandy_1TB_SSD/Nite-DSP/monorepo/audio-technology/vst3-plugins/CMakeLists.txt:45), [AudioToo_Reverb/CMakeLists.txt:8](/Volumes/Jack_Gandy_1TB_SSD/Nite-DSP/monorepo/audio-technology/vst3-plugins/AudioToo_Reverb/CMakeLists.txt:8).

The root manifest points to `../audio_analysis/.../reverb_full_kernel.cpp`, although the package is now under `../audio-analysis/`. It also adds a `SmartSampleManager` subdirectory that is absent; the product lives under `products/slo/SmartSampleManager`. The standalone Reverb manifest requires an absent local `JUCE` directory and repeats the old kernel path. Direct existence checks confirmed these missing paths without fetching or installing plugins.

Update the declared source paths and choose one supported JUCE acquisition/build entry point. Add a configure-only check with plugin installation disabled. The separate SLO toolchain failure below is not evidence of a SLO source defect.

### 8. [P2] DiskSweep's privileged helper destination check permits path traversal

Source: [helper.cpp:18](/Volumes/Jack_Gandy_1TB_SSD/Nite-DSP/monorepo/products/disksweep/privileged-helper/helper.cpp:18).

`DstInsideTrash()` checks a textual prefix and slash. It accepts a destination shaped like `~/.Trash/Disksweep/../../escaped-file`, although normalization resolves it outside the allowed directory. The helper later creates directories and renames using that unnormalized destination. Symlinked path components require the same consideration.

A predicate-only C++ program included the helper source with its `main` renamed. It printed `traversal accepted: 1` and `normalized path remains in trash: 0`. The helper's move loop was never called, installed, or run with privileges. This is a latent defect in the prototype, not a claim about a deployed privileged service.

Before enabling the helper, resolve destinations beneath a trusted trash root, reject traversal and symlink escapes, and use an authenticated helper interface. Exercise containment checks independently of privileged filesystem operations.

### 9. [P2] DiskSweep's GUI reports successful deletion without invoking the sidecar

Source: [ScanStore.swift:87](/Volumes/Jack_Gandy_1TB_SSD/Nite-DSP/monorepo/products/disksweep/ui/ScanStore.swift:87).

`trash()` computes selected rows, creates an unused picks path and encoded object, then immediately clears `undoLog`, reports that the items moved, and rescans. It never writes the picks file or starts the sidecar. Clicking the GUI action therefore leaves files in place and offers no valid undo receipt despite claiming success.

This was confirmed by tracing the full method; no deletion was attempted. Wire the selected rows to the guarded sidecar flow, wait for its result, and report the actual moved/skipped counts and returned undo log. Test failure as well as successful completion.

### 10. [P2] Stem separation divides by zero for valid silent and antiphase audio

Source: [separator.py:83](/Volumes/Jack_Gandy_1TB_SSD/Nite-DSP/monorepo/audio-technology/stem-separation/stem_separation/core/separator.py:83).

Normalization divides by the standard deviation of the mono average. Silence, constant DC, and an exact stereo antiphase signal all have zero mono standard deviation. The normalized tensor consequently contains NaN or infinity before inference; denormalization cannot repair that model input.

A CPU-only reproduction supplied synthetic float WAV files and a mocked Demucs model. All three inputs produced `finite model input: False`, while `separate()` still returned four output paths. No model download or GPU was used.

Handle zero-energy/constant signals explicitly and use a normalization scale that does not collapse for non-silent stereo antiphase material. Verify finite model input and finite output for silence, DC, one-sample clips, and antiphase stereo.

### 11. [P2] Thursday document search includes installed dependency licenses as business evidence

Source: [doc_search_ops.py:425](/Volumes/Jack_Gandy_1TB_SSD/Nite-DSP/monorepo/autonomous-systems/thursday/thursday/ops/doc_search_ops.py:425).

Keyword search recursively walks each product directory for Markdown without pruning `.venv`, installed dependencies, runtime data, or backups. Those files compete with authoritative business documents under per-root caps. The baseline corpus tests returned `librosa` and `narwhals` package license files among the top hits for customer price questions; they also failed to cite the expected service SOPs.

Exclude non-source/runtime/vendor directories before ranking and resolve the authoritative SOP roots after the repository move. Test that a planted vendor license cannot enter a customer-facing result. The other Thursday version/analytics failures listed below also need separate attention.

## Verification and existing failures

These results describe the audit runs on this checkout. Passing a suite does not clear the uncovered defects above. Tests used fake service boundaries where available; skipped tests and collection failures remain explicit.

| Area | Result | Scope or limitation |
| --- | --- | --- |
| KENN backend | 3,413 passed; 12 skipped; 7 warnings | Documented backend suite with fake Live/test fixtures, 104.52 s. |
| NITE Submit | 475/475 checks passed | Swift test executable and deterministic PDF corpus, scratch build directory. Separate file-loss reproductions still fail. |
| DiskSweep | 31 passed | Existing Python suite, 0.94 s. Separate collision reproduction still loses one file. |
| Platform support | 136 passed | Standalone platform-support tests. |
| Audio-analysis scoped DSP | 151 passed; 2 skipped | Streaming DSP, true-peak fast path, stereo correlation, stem classification, batched FFT onset tests; 15.73 s. |
| KENN chat/automix/mix-review packages | 136 passed; 2 failed | Both failures are chat evaluation receipts; 17.35 s. |
| Thursday standalone | 493 passed; 7 failed; 1 skipped | Existing corpus, advisory, version, pricing, and analytics failures; 27.96 s. |
| Audio-analysis full suite | 26 collection errors; 1 skipped | Missing import roots and one stale fixture path prevent a full run. |
| KENN frontend | Blocked before test collection | Installed native binding does not satisfy the running Node architecture; missing `@rolldown/binding-darwin-x64`. |
| SLO offline native configure | Blocked at compiler detection | x86_64 configure attempted to load an arm64-only CommandLineTools `libxcrun`. Plugin installation was disabled and dependency fetching was disconnected. |
| Isolated native DSP probes | Reproduced findings 4 and 5 | Locally compiled kernels, synthetic impulse/transient signals, no host/plugin installation. |
| Isolated file/route/stem probes | Reproduced findings 1, 2, 3, 6, 8, 10 | Temporary files, fake bridge/model, and destination predicate only. |

The two existing KENN package failures are:

- `products/kenn/packages/chat/tests/test_eval_chat_coverage.py::test_full_chat_coverage_receipt_passes`
- `products/kenn/packages/chat/tests/test_eval_runner.py::test_full_evaluation_receipt_passes`

The seven Thursday baseline failures are:

- `tests/test_doc_search_corpus_eval.py::test_corpus_eval_30_questions_cited`
- `tests/test_doc_search_corpus_eval.py::test_router_top1_cites_authoritative_source`
- `tests/test_thursday_advisory_ops.py::test_data_availability_is_honest_without_db_url`
- `tests/test_thursday_advisory_ops.py::test_business_brief_uses_live_facts`
- `tests/test_thursday_beta_invite_ops.py::test_read_truth_sheet_field_reads_real_version`
- `tests/test_thursday_website_ops.py::test_pricing_check_compares_website_vs_truth_sheet`
- `tests/test_thursday_website_ops.py::test_traffic_status_reports_pageviews_and_custom_events`

The full audio-analysis collection attempt could not import modules including `db`, `scripts`, `studio`, `mix_features`, `kenn`, `mix_report_tokens`, `reference_track_comparison`, and `agents`. It also tried to load the moved `audio-technology/scripts/eval/automix_listening_benchmark.py`. The narrower DSP run used the available canonical and compatibility package roots and passed; it does not substitute for the blocked full suite.

Audit logs remain local at `/tmp/nite-dsp-kenn-tests.log`, `/tmp/nite-dsp-submit-tests.log`, `/tmp/nite-dsp-disksweep-tests.log`, `/tmp/nite-dsp-platform-support-tests.log`, `/tmp/nite-dsp-audit-dsp-tests.log`, `/tmp/nite-dsp-audit-packages-tests.log`, `/tmp/nite-dsp-thursday-tests.log`, `/tmp/nite-dsp-analysis-tests.log`, `/tmp/nite-dsp-kenn-frontend-test.log`, and `/tmp/nite-dsp-slo-configure.log`. They are temporary evidence files and are not part of a release artifact.

## Changes completed during this task

<!-- Root agent: replace this placeholder with final Stripe, website, operations and hosting assessment results, scoped verification, migration/configuration requirements, and an exact changed-file manifest. -->

## Release implications

Fix the three file-loss findings before releasing the affected DiskSweep or NITE Submit operations. Verify the native plugins using a real streaming state implementation before treating their offline kernel tests as plugin acceptance. Restore explicit dependencies in the AudioGen routes and add available-bridge tests. Resolve the recorded failing/blocked suites for the affected release instead of interpreting the broad passing counts as a release sign-off.

The remaining findings are recorded without changing those product implementations in this commerce/website cleanup task.
