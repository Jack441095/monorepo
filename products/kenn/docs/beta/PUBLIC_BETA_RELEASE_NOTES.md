# KENN Public Beta Release Notes

**Release Version**: `1.0.0-beta`

**Date**: September 2, 2026

**Repository Branch**: `develop`

**Target Audience**: Mix engineers, studio producers, sound designers, and public beta testers


---

## 1. What is KENN Public Beta?

KENN (Kernel Engineering Neural Network) Public Beta is an intelligent, evidence-grounded mix-engineering assistant. It combines:
1. **Source-Grounded Mix Advice Chat**: Answers technical questions about equalization, dynamics, gain staging, vocal processing, stereo imaging, and mastering using verified knowledge notes and vector search.
2. **Deterministic WAV Mix Review**: Analyzes 16-bit and 24-bit PCM WAV tracks for signal defects including digital clipping, low headroom, silence/truncation, channel imbalance, phase/polarity cancellation, DC offset, and approximate loudness.

---

## 2. Public Beta Scope Boundaries

To ensure complete reliability, safety, and deterministic performance, the Public Beta is explicitly scoped:

### INCLUDED in Public Beta:
- ✅ Text-based RAG mix advice chat with source note provenance.
- ✅ Honest abstentions on out-of-scope or ungrounded questions.
- ✅ Single-track 16-bit and 24-bit PCM WAV Mix Review signal analysis (up to 50 MB / 10 minutes).
- ✅ Structured diagnostic reports and action plans.
- ✅ User feedback submission (`POST /feedback`).

### EXCLUDED from Public Beta (Unavailable):
- ❌ AutoMix multi-stem rendering.
- ❌ AI Stem separation.
- ❌ AI Audio generation (AudioGen).
- ❌ Voice control or OSC DAW live control (Ableton Live session mutation).
- ❌ Subjective plugin rankings or taste-based choices.

---

## 3. Tester Guidance & Instructions

1. **Asking Questions**: Type any technical mixing, mastering, or sound design question in the chat bar. KENN will respond with verified source citations and confidence ratings.
2. **Uploading WAV Tracks**: Drag and drop a stereo WAV file into the Mix Review panel, check the consent box, and click **Analyze WAV**. Review the signal metrics, flagged fault families, and suggested corrective actions.
3. **Submitting Feedback**: Use the 1⭐ to 5⭐ rating buttons and comment field in the sidebar to rate answers and diagnostic reports.

---

## 4. Verification & QA Sign-Off Summary

- **Automated Unit & Integration Tests**: 200/200 passing in the current repository-wide suite, with one non-blocking dependency deprecation warning.
- **Mix Review Signal Qualification Benchmark**: 100% detection precision/recall, 0% false positives, 100% corrupted-input recovery, and 3.40 ms mean latency against the documented <100 ms target. The performance gate passes; this remains bounded synthetic evidence.
- **Chat Evaluation Suites**: 100% Pass rate across diagnostic, conversation, and boundary rejection suites.
- **Standalone Build & Vector Index**: Fully verified index `v-93a9b548ec48` built cleanly from source.

**Release Status**: NOT APPROVED — FINAL PUBLIC SIGN-OFF PENDING
