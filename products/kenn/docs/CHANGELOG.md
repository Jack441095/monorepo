# Changelog

All notable changes to the KENN repository will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.0.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

---

## [1.1.0-pilot] - 2026-09-14

### Added
- **AbletonOSC Transport Keep-Alive Watchdog & Circuit Breaker (`apps/backend/src/kenn/ableton_osc_bridge.py`)**:
  - Implemented explicit DAW connection lifecycle state machine (`connected`, `degraded`, `disconnected`, `reconnecting`).
  - Added `ping(timeout=0.5) -> bool` with lightweight query heartbeat.
  - Added background watchdog thread (`start_watchdog`, `stop_watchdog`) running every 2.5s.
  - Implemented fast-fail circuit breaker (`enable_circuit_breaker=True`) preventing UI and query threads from blocking on dead UDP sockets when Ableton Live is backgrounded or closed.
  - Added diagnostic endpoints to server: `GET /api/ableton/ping` and `GET /api/ableton/watchdog`.
- **32-Bit Float WAV & Extensible Container Support (`mix-review/core/local_engine.py`)**:
  - Implemented robust RIFF/WAVE container parser (`_parse_wav`) supporting standard 16-bit/24-bit PCM, 32-bit float (`WAVE_FORMAT_IEEE_FLOAT`), 32-bit integer PCM, and `WAVE_FORMAT_EXTENSIBLE` (0xFFFE).
  - Vectorized NumPy `<f4` decoding with a fallback pure-Python standard-library `array("f")` path verified with 100% bit-exact parity.
  - Enabled native ingestion of 32-bit float mixdowns exported by modern DAWs (Ableton Live default export format).
- **32-Bit Float WAV & Extensible Container Support Across All Engines**:
  - `mix-review/core/local_engine.py`: Implemented robust RIFF/WAVE container parser (`_parse_wav`) supporting standard 16-bit/24-bit PCM, 32-bit float (`WAVE_FORMAT_IEEE_FLOAT`), 32-bit integer PCM, and `WAVE_FORMAT_EXTENSIBLE` (0xFFFE). Vectorized NumPy `<f4` decoding with fallback pure-Python standard-library `array("f")` path.
  - `apps/backend/src/kenn/core/audio_analysis.py`: Updated `_decode` to natively parse 32-bit float audio renders for spectral analysis, pink noise baseline comparison, and LTAS spectral difference calculations.
  - `apps/backend/src/kenn/core/local_mix_review_service.py`: Verified multi-track reference audio comparison with 32-bit float inputs.
  - End-to-end integration test `test_mix_reference_endpoint_handles_32_bit_float_wavs` in `apps/backend/src/kenn/tests/test_server_smoke.py`.
- **Modular Route Package Architecture (`apps/backend/src/kenn/routes/`)**:
  - Created modular routing package `apps/backend/src/kenn/routes/ableton_routes.py` with typed handlers for ping, watchdog, and capabilities endpoints.
  - Decomposed route handlers out of `apps/backend/src/kenn/server.py` monolith with 100% backward-compatible HTTP semantics.
- **Native Apple Silicon C++ VST3/AU Plug-in Build (`plugins/kenn-vst3-au/`)**:
  - Updated `plugins/kenn-vst3-au/CMakeLists.txt` with configurable host-native architecture detection and optional `KENN_BUILD_UNIVERSAL` flag.
  - Built on macOS Apple Silicon `arm64` using AppleClang 21.0, compiling VST3, AU, and all test targets.
  - Executed all 9 CTest test suites with 100% pass rate.

### Fixed
- **JUCE C++ VST3 Thread-Safety Vulnerability (`plugins/kenn-vst3-au/Source/PluginEditor.cpp`)**:
  - Fixed 9 background worker thread dispatches (`juce::Thread::launch`) that dereferenced `juce::Component::SafePointer` off the Message Thread.
  - Fixed background worker thread dispatches (`juce::Thread::launch`) that dereferenced `juce::Component::SafePointer` off the Message Thread.
  - Processor captured safely by reference; all UI state updates dispatched via `juce::MessageManager::callAsync`.
- **Review Packet Cryptographic Provenance**:
  - Regenerated `docs/ABLETON_ASSISTANT_HUMAN_REVIEW_PACKET_2026-09-08.json` using `scripts/build_human_review_packet.py`.
  - Resolved `human_review` gate integrity check, advancing qualification state from `FAIL` to `PENDING`.
- **Clean Working Tree Hygiene**:
  - Restored uncommitted modifications to `docs/PUBLIC_BETA_READINESS_REPORT.md` to clear dirty git working tree flags blocking reproducible packaging.
- **Rate Limit Buckets Isolation in Integration Tests**:
  - Added `reset_rate_limit_buckets` fixture in `apps/backend/src/kenn/tests/test_server_smoke.py` preventing test-order rate limit saturation on local client IP.

### Qualification
- **Pilot Readiness Qualification Gate**:
  - Executed `scripts/qualify_internal_beta.py --profile pilot --run-suite`.
  - Result: **4 passed, 0 pending, 0 failed** (100% of required gates passed).
  - Automated test suite expanded from 1,205 to **1,207 tests passed, 0 failed** in 135.94s.
  - Automated test suite expanded from 1,205 to **1,214 tests passed, 0 failed** in 93.99s.
  - C++ VST3 plug-in suite: **9 passed, 0 failed** out of 9 tests in 26.79s.

---

## [1.0.0-beta] - 2026-09-01

### Added
- **Public Beta Scope Document**: Established official scope boundaries and feature exclusion matrix in `docs/PUBLIC_BETA_SCOPE.md`.
- **Standalone Public API (`chat/app.py`)**:
  - `GET /health`: Health, service version (`1.0.0-beta`), schema version (`kenn.public_api.v1`), and privacy statement.
  - `POST /chat`: Strict schema validation, rate limiting, request ID tracking (`X-Request-ID`), RAG retrieval provenance.
  - `POST /mix-review`: PCM WAV file upload ($\le 50\text{ MB}$, $\le 600\text{ s}$) executing KENN-owned `local_engine.py`.
  - `POST /feedback`: User rating and comments submission endpoint.
- **Honest Public UX (`UX/index.html`, `UX/app.js`)**:
  - Redesigned interface removing AutoMix, stem separation, AudioGen, and DAW control widgets.
  - Added upload consent checkbox and feedback capture widget.
- **Mix Review Signal Analysis Qualification**:
  - Evaluated on 7 fault families; achieved 100% Precision, 100% Recall, 0% FPR, 68ms mean latency, 100% corrupted input recovery (`docs/MIX_REVIEW_BENCHMARK_REPORT.md`).
- **Chat & Knowledge Base Qualification**:
  - Evaluated on held-out evaluation suites (`chat/eval_runner.py`); achieved 100% pass rate across diagnostic, conversation, and boundary rejection suites (`docs/CHAT_BENCHMARK_REPORT.md`).
- **Standalone Containerization & CI**:
  - Created `Dockerfile`, `docker-compose.yml`, `scripts/start_server.sh`, and `scripts/ci_verification.sh`.
- **Security & Privacy Hardening**:
  - Added input validation, path traversal defense, script escaping, rate limiting, and 7-stage security test suite (`chat/tests/test_security_and_abuse.py`).

### Fixed
- Fixed `_run_automix` and `_run_stem_separation` tool registry gating bug in `apps/backend/src/kenn/core/tool_registry_defaults.py`.
- Resolved all test suite errors across core, tools, and API layers (131/131 tests passing).

### Excluded
- AutoMix, stem separation, audio generation, voice control, Ableton Live session mutation, and external repository dependencies.
