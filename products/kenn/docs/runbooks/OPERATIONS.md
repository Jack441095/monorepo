# KENN Standalone Public Beta Operational Guide

**Version**: `1.0.0-beta`

**Repository**: Standalone KENN Checkout

**Service Root**: `apps/backend/src/kenn/server.py` & `chat/app.py`


---

## 1. Environment & Architecture Overview

KENN runs as a standalone FastAPI service with repository-owned dependencies,
providing:
1. Grounded RAG Mix Advice (`POST /chat`)
2. PCM WAV Signal Fault Analysis (`POST /mix-review`)
3. Feedback & Diagnostic Telemetry (`POST /feedback`)
4. Service Health & Scope Probes (`GET /health`)

No external sibling repositories (`Audio_Too`, NITE DSP, Thursday) or GPU hardware are required.

---

## 2. Environment Variables

| Variable | Default Value | Description |
| :--- | :--- | :--- |
| `KENN_PORT` | `8090` | HTTP listening port |
| `KENN_HOST` | `127.0.0.1` | Listening host address; keep loopback-only for beta |
| `KENN_CHAT_ALLOWED_ORIGINS` | `http://localhost:3000,http://127.0.0.1:3000` | Comma-separated CORS allowed origins |
| `KENN_CHAT_RATE_LIMIT_REQUESTS` | `30` | Max requests per client IP within window |
| `KENN_CHAT_RATE_LIMIT_WINDOW_SECONDS` | `60.0` | Rate limiting fixed-window duration |
| `KENN_CHAT_ENGINE_TIMEOUT_SECONDS` | `30.0` | Maximum time allowed per retrieval question |
| `KENN_INSTANCE_LOCK_PATH` | system temporary directory, per user | Test/operator override for the companion instance-lock file; normally leave unset |

---

## 3. Quickstart & Local Execution

### Local Shell Execution
```bash
# 1. Install dependencies
pip install -r requirements.txt

# 2. Build the supported BM25 index
python3 apps/backend/src/kenn/main.py build

# Optional: enable hybrid semantic retrieval, then rebuild
python3 scripts/fetch_embedding_model.py
python3 apps/backend/src/kenn/main.py build

# 3. Start server
./scripts/start_server.sh
```

Only one KENN companion may run for a local user because AbletonOSC has one
fixed reply port. A second launch exits with status 2 before opening its HTTP
port and reports the current owner's PID/start time. KENN never terminates the
owner automatically. The OS releases lock ownership after normal shutdown,
crash, or termination; a leftover metadata file is safely overwritten by the
next successful owner.

### Docker Execution
```bash
# Build and run container
docker build -t kenn-public-beta .
docker run -p 8090:8090 kenn-public-beta

# Or using Docker Compose:
docker-compose up -d
```

---

## 4. Operational Health Checks & Verification

### Service Health
```bash
curl http://127.0.0.1:8090/api/health
```

### Test Suite Execution
```bash
PYTHONPATH=source:chat python3 -m pytest chat/tests/test_public_api.py apps/backend/src/kenn/tests/ -v
```

### Companion soak

With one companion already running, find its exact PID from the startup line
and run the bounded 24-hour sampler:

```bash
python3 scripts/soak_companion.py --pid <PID> \
  --duration-seconds 86400 --interval-seconds 60 \
  --min-ableton-reconnects 1 --max-ableton-outage-seconds 300 \
  --require-ableton-connected-end --max-thread-growth 8 \
  --output /secure/evidence/kenn-soak.json
```

The report records health latency, Ableton status, RSS, thread count, pending
proposal count, action-receipt count, and bounded Mix Review registry count. It
fails closed if state-count telemetry disappears or exceeds its declared
limit, on any unhealthy/error sample, final or transient RSS growth above 128
MiB, transient thread growth above eight, a missing required reconnect, an
excessive observed outage, or Live remaining offline at the end. During the run, manually close and reopen Live once to exercise the
configured reconnect gate; the harness observes this but never injects a
failure or mutation itself. Counts expose no proposal, receipt, project, or
review content. The report does not qualify musical output.

The receipt is bound to the exact Git revision and soak-harness hash sampled. Release qualification
also rechecks every sample's health/error/runtime-state fields, minute-by-minute
timestamp cadence, RSS and registry limits, reconnect/outage policy, and final
Live state. A stale receipt or a top-level `qualified` claim inconsistent with
the sampled evidence fails closed.

### Privacy-safe support bundle

With the companion running, create an owner-only archive for a support ticket:

```bash
python3 scripts/build_support_bundle.py \
  --output /secure/support/kenn-support.zip
```

For a supervised-pilot evidence bundle, add `--session-id <local-session-id>`
to include only that session's projected receipts. The session ID is sent only
to the loopback companion as a filter and is not persisted in the archive.

The archive contains only allow-listed diagnostics, up to 100 projected
lifecycle events, source revision, and integrity hashes. It never copies raw
logs, audio, prompts, session IDs, track/device/project names, targets, error
text, filesystem paths, or confirmation material. Inspect the archive before
sharing it; this command does not upload anything.

---

## 5. Privacy & Data Handling Controls

- **WAV Uploads**: Uploaded audio files are read into transient memory for signal processing and discarded immediately. No audio files or raw audio waveforms are persisted to disk or used for model training.
- **Feedback Logs**: Feedback entries (`request_id`, rating, comments) are saved to `.runtime/feedback.jsonl`.
