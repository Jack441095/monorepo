# QC-04 Format-Support Correction — "WAV-only" Is Stale (2026-09-18, branch slo/class-opt-v1)

## Verdict
The "WAV-only scanning" gap asserted in four docs is **CONTRADICTED (AIFF/FLAC) /
UNVERIFIED (MP3/OGG)** against current code. No decode work is needed for AIFF/FLAC.
What remains is a **disclosure + verification** task, not an engineering gap.

## Evidence (all Grade B — code read, not runtime-proven this pass)
- Discovery: `Source/SampleManagerEngine.cpp:2171-2210` (`addPathToQueue`) enumerates
  `*` and admits via `formatManager.findFormatForFileExtension(...)` — JUCE registry,
  not a `*.wav` glob. Skips counted honestly (`scanSkippedNonAudio`). [B]
- Registry: `SampleManagerEngine.cpp:430` `formatManager.registerBasicFormats()`. [B]
- Decode: embedding path first applies a dr_wav WAV guard, then decodes through JUCE
  `AudioFormatReader` (`SampleManagerEngine.cpp:5946-5985`: "supports every format
  enabled by registerBasicFormats()... handling the source bit depth/format conversion
  for WAV, AIFF, FLAC, OGG, and other registered readers"). dr_wav is WAV-validation,
  not the decode path. [B]
- Tests: `Source/test_format_aware_scan_main.cpp:94-175` admits WAV/AIFF/FLAC, rejects
  text/malformed-FLAC/symlinks; checks AIFF+FLAC BPM/key metadata before fallback. [B]
- UI: reference-search chooser advertises `*.wav;*.mp3;*.aif;*.aiff;*.flac;*.ogg`
  (`Source/PluginEditor.cpp:2082`). Drag/drop path: `PluginEditor.cpp:18` checks
  `.wav`/`.mp3` only — narrower than scan admission (see gap 3 below).

## Corrected support table
| Format | Discovery | Decode | Test cover | Status |
|---|---|---|---|---|
| WAV | yes | JUCE + dr_wav guard | extensive | SUPPORTED |
| AIFF | yes | JUCE reader | format-aware test | SUPPORTED (docs were wrong) |
| FLAC | yes | JUCE reader | format-aware test | SUPPORTED (docs were wrong) |
| OGG | yes | JUCE reader | none found | LIKELY, UNVERIFIED at runtime |
| MP3 | yes | JUCE reader (flag-dependent) | none found | ADVERTISED in chooser, UNVERIFIED at runtime |

## Docs to correct (owner pass — not edited here)
- `SLO_SCAN_INDEX_PIPELINE_REPORT_V1.md` ("Not supported — same reason") → CONTRADICTED.
- `SLO_CURRENT_WORKING_STATE_AUDIT_V1.md:75`, `SLO_V1_WORKING_PRODUCT_DEFINITION.md:29`,
  `SLO_PRIVATE_BETA_READINESS_V2.md:30,38` ("WAV-only ... real gap") → STALE; the
  "genuine scoped engineering task" was either completed since or never needed for
  AIFF/FLAC. Recommend a strikethrough amendment, not silent edit (audit trail).

## Remaining gaps (real, small)
1. **MP3/OGG runtime proof**: add one MP3 + one OGG fixture to the format-aware test
   (S effort). Until then, keep them as "admitted, unverified" — do not advertise.
2. **User disclosure**: README + empty-state list no formats at all. One-line disclosure
   ("Scans WAV, AIFF, FLAC…; MP3/OGG admitted, verifying") closes the honesty gap.
3. **Drag/drop filter** (`PluginEditor.cpp:18`, wav/mp3 only) is narrower than scan
   admission — either widen or document why. One-line change, needs UI test.
4. TagLib usage (`#include <taglib/wavfile.h`, `SampleManagerEngine.cpp:11`) for metadata
   may still be WAV-leaning — metadata fallback for non-WAV relies on the generic
   BPM/key path the format-aware test covers; no action unless a metadata bug surfaces.

## Kill / close criterion
Close the "WAV-only" blocker as INVALID (AIFF/FLAC) + DOWNGRADE MP3/OGG to a P2
verification task (one fixture each). No decoder rewrite is on the table.
