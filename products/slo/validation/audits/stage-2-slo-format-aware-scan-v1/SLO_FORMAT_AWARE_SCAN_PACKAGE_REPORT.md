# SLO Format-Aware Scan Package Report V1

Status: locally checkpointed implementation package; not merged or pushed.

## Scope

This package closes the documented SLO scan/decode mismatch where
`SampleManagerEngine::addPathToQueue()` admitted only `*.wav` files even
though the product already registered JUCE audio formats and the file picker
advertised additional formats.

The isolated branch is based on SLO `main` at:

```text
c6d0746ac876a0a3af9244907486ffc001b3e718
```

## Implementation

- Directory scans build their wildcard from the file extensions exposed by the
  formats registered with JUCE, then retain a format-manager admission check.
- Non-WAV decoding uses a local JUCE `AudioFormatManager` and
  `AudioFormatReader`, so the scan and decode registries stay aligned.
- WAV decoding retains the existing `dr_wav` validation guard before generic
  decoding. This preserves the established fail-closed behavior for truncated
  RIFF/data chunks that JUCE's tolerant WAV reader may otherwise expose.
- The checked configuration enables WAV, AIFF, FLAC, OGG, and macOS CoreAudio
  readers through `registerBasicFormats()`. MP3 is not claimed: JUCE's
  `JUCE_USE_MP3AUDIOFORMAT` default is disabled in this build.
- Existing cache, embedding, content-hash, and user-state contracts are not
  changed.

## Qualification evidence

Build tree: `/tmp/slo-format-aware-scan-v1-build` (Release, LTO off,
Apple dependency bundling off, plugin auto-install off).

```text
cmake --build /tmp/slo-format-aware-scan-v1-build \
  --target TestFormatAwareScan TestMalformedAudio --parallel 8
```

Result: build succeeded.

```text
/tmp/slo-format-aware-scan-v1-build/TestFormatAwareScan
```

Result: exit 0. Disposable WAV/AIFF/FLAC fixtures were admitted; valid audio
under `.txt` was ignored; malformed `.flac` was rejected; all admitted files
received valid embeddings.

```text
/tmp/slo-format-aware-scan-v1-build/TestMalformedAudio
```

Result: exit 0. The existing garbage, truncated-header, zero-byte, and
lying-data-length WAV cases remained rejected, with no cache poisoning and no
interruption of the valid sibling file.

## Safety boundary

- Both tests use `ScopedIsolatedCacheDb` and unique temporary fixture roots.
- No production cache, owner audio, holdout, secret, model, or customer data
  was modified.
- The shared checkout at `products/slo` was not edited, cleaned, reset, or
  rebuilt in place.
- This package is a local branch checkpoint only; integration remains subject
  to the SLO owner review, broader qualification, and host validation.

## Follow-up before product release

Run the normal SLO qualification and host-validation suites from an approved
release worktree, then verify the shipped picker/format policy against the
actual decoder matrix. Enable and qualify MP3 separately if MP3 remains a
required product format.
