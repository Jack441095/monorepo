# Third-party licences used by KENN

KENN is a closed commercial product: only permissive licences (MIT, BSD, ISC,
Apache-2.0, Unlicense, MPL-2.0 for test-only tooling) are allowed. GPL, AGPL,
BSL, PolyForm and non-commercial code or model weights are not. Record every
new dependency here when it is added.

| Dependency | Licence | Used for | Added |
|---|---|---|---|
| pyloudnorm | MIT | ITU-R BS.1770 loudness (LUFS, LRA windows) | 2026-09-23 (E2) |
| librosa | ISC | Chroma key estimate, beat-tracked tempo | 2026-09-23 (E2) |
| scipy | BSD-3-Clause | 4x oversampled true peak | 2026-09-23 (E2) |
| numpy | BSD-3-Clause | Numeric arrays | pre-existing |
| soundfile | BSD-3-Clause | WAV decoding for measurements | pre-existing |
| @playwright/test | Apache-2.0 | UI end-to-end tests (dev only; system Chrome, no bundled browser) | 2026-09-23 (A1) |
| AbletonOSC (vendored fork) | MIT | Live Remote Script transport | pre-existing |

Deliberately avoided: Essentia (AGPL-3.0), aubio (GPL-3.0), libkeyfinder
(GPL-3.0), madmom models (CC BY-NC-SA), pedalboard (GPL-3.0), MusicGen /
audiocraft weights (CC-BY-NC-4.0), Qwen2.5-3B (research licence), and
GPL/AGPL/BSL Ableton tools. BlackHole is GPL-3.0 and must never be bundled.
