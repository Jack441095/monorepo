# SLO Format-Aware Scan Qualification Refresh Receipt V1

Date: 2026-08-30

## Source and scope

- Branch: `engineering/slo-format-aware-scan-v1`
- Source SHA: `6d0d8ff`
- Scope: refresh the existing format-aware scan package evidence; no source
  or product checkout outside this isolated worktree was changed.
- Build tree: `/tmp/slo-format-aware-scan-v1-build`

## Commands

```sh
cmake --build /tmp/slo-format-aware-scan-v1-build \
  --target TestFormatAwareScan TestMalformedAudio --parallel 8
/tmp/slo-format-aware-scan-v1-build/TestFormatAwareScan
/tmp/slo-format-aware-scan-v1-build/TestMalformedAudio
```

## Result

All commands exited successfully.

`TestFormatAwareScan` passed its disposable WAV/AIFF/FLAC admission and
malformed-FLAC rejection checks, ignored an unsupported extension, and
completed embeddings for admitted fixtures.

`TestMalformedAudio` passed its garbage, truncated-header, zero-byte, and
lying-data-length WAV rejection checks; the valid sibling remained processable
and the cache was not poisoned.

The ONNX runtime emitted CoreML partition-assignment warnings during these
tests. They are runtime provider diagnostics, not test failures; the tests
returned success. They should remain visible in any future performance or
provider qualification rather than being treated as proof of CoreML parity.

## Decision

The format-aware scan package remains technically qualified for its declared
WAV/AIFF/FLAC scope in isolated synthetic fixtures. This does not qualify MP3,
live DAW behavior, clean-machine packaging, signing/notarisation, or a public
release. Those remain separate owner-gated exits.
