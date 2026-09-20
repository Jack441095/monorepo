# KENN Public Beta Scope & Claims Specification

**Version**: 1.0.0-beta

**Date**: September 1, 2026

**Status**: Authoritative Public Beta Scope Document

**Repository**: `KENN` (`Jack441095/kenn-standalone`)


---

## 1. Executive Summary

This document defines the strict, authoritative scope for the **KENN Public Beta Release**.


Historical audit documents in `docs/` (`KENN_LIVE_CONTROL_AUDIT.md`, `KENN_BETA_GAP_MATRIX.md`, `KENN_BETA_ROADMAP.md`) documented experimental features, local DAWs OSC control, C++ VST3 micro-benchmarks, and internal research. **This document supersedes all previous claims for the Public Beta.**

The public beta is strictly a **narrow, web-accessible API and UX service** for text-based mix engineering diagnostics and single-track WAV mix review.

---

## 2. In-Scope Features (Public Beta Included)

1. **Text-Based Mix-Engineering Chat (`POST /chat` & `POST /ask`)**
   * Retrieval-augmented diagnostic Q&A grounded in verified audio engineering knowledge notes.
   * Evidence-backed responses with explicit provenance, source note references, and confidence scoring.
   * Honest abstention state when queries exceed corpus boundaries or lack audio context.

2. **WAV Mix Review (`POST /mix-review`)**
   * Server-side diagnostic analysis of uploaded 16-bit / 24-bit PCM WAV files.
   * Fault diagnosis across 7 primary audio fault families:
     1. Digital Clipping & Inter-Sample True-Peak Overflows
     2. Headroom Deficits & Excessive Density
     3. Silence Truncation & Unexpected Muting
     4. Channel Imbalance (L/R RMS offset $> 1.5\text{ dB}$)
     5. Phase Inversion, Polarity Reversals & Mono Cancellation
     6. DC Offset
     7. Approximate loudness proxy (RMS, crest factor, and sample peak dBFS; not calibrated LUFS or true peak)

3. **Public API Endpoints**
   * `GET /health` — Server health, readiness, and knowledge index version info.
   * `POST /chat` — Public grounded chat interface with strict request validation and rate limiting.
   * `POST /mix-review` — Safe audio file upload and diagnostic review.
   * `POST /feedback` — User feedback collection tied to request ID / analysis receipt ID.

4. **Provenance & Transparency**
   * Analysis versioning and knowledge-base checksums returned in every response payload.
   * Redacted logging and strict user data privacy protection.

---

## 3. Excluded Scope (Explicitly Excluded from Public Beta)

The following features are **STRICTLY EXCLUDED** from the Public Beta. Attempting to invoke or configure these features will return an explicit `{"ok": false, "status": "unavailable", "error": "This feature is excluded from the KENN Public Beta release."}` response:

* 🚫 **AutoMix**: Rendering automatic mixing passes or stem rebalancing.
* 🚫 **Stem Separation**: Demixing audio into stems.
* 🚫 **Audio Generation**: Text-to-audio or music generation.
* 🚫 **Voice Control**: Voice-to-text live audio transcription input.
* 🚫 **Live Ableton OSC Mutation**: Direct network write access to local Ableton Live faders/devices.
* 🚫 **Desktop Companion**: Tray app or desktop window application.
* 🚫 **VST3 / AU Server Features**: DAW plugin host bridge.
* 🚫 **Autonomous General-Purpose Mixing**: Unsupervised multi-track fader automation.
* 🚫 **External Repository Dependencies**: Dependencies on `Audio_Too`, NITE DSP, Thursday, or uncommitted sibling repositories.

---

## 4. Reconciled Contradictions & Audit Corrections

| Historical Audit Claim | Public Beta Status | Correction / Resolution |
| :--- | :--- | :--- |
| *Live OSC parameter mutation active* | **EXCLUDED** | Live Ableton mutation is disabled in public API. `LiveExecutor` is restricted to local offline testing only. |
| *AutoMix rendering via tool registry* | **EXCLUDED** | `run_automix` handler returns clean unavailable status (`status: "unavailable"`). |
| *Stem separation via bridge* | **EXCLUDED** | `run_stem_separation` returns clean unavailable status. |
| *Local-only zero upload processing* | **RECONCILED** | Public hosted beta requires uploading WAV files to the server for analysis; privacy terms state this explicitly. |
| *Multi-agent autonomous mixing* | **EXCLUDED** | Retained strictly as offline research prototype. |

---

## 5. Public Beta Operating Environment

* **Runtime**: Single standalone Python service (`kenn.server` / `chat.app`).
* **Storage**: In-memory knowledge index (`all-MiniLM-L6-v2` ONNX embeddings + BM25 keyword index).
* **Network**: HTTPS with strict CORS header control, rate limiting ($30\text{ req/min}$), and maximum upload size ($50\text{ MB}$).

*Signed off by Lead Engineer & QA Lead.*
