# KENN Public Beta Support & Operations Runbook

**Target Version**: `1.0.0-beta`

**Audience**: Support Engineers, System Administrators, Operational Maintainers


---

## 1. Incident & Query Classification

| Issue Category | Description | Standard Resolution Procedure |
| :--- | :--- | :--- |
| **Expected Unsupported Input** | User submits MP3, AAC, or 32-bit float WAV | Explain that Public Beta supports 16-bit / 24-bit PCM WAV only. |
| **Honest Abstention** | KENN returns `"found": false` for off-topic query | Confirm query was outside mixing scope; no bug action required. |
| **False Positive / False Negative** | Mix Review flags clean track or misses fault | Inspect metric values in `.runtime/feedback.jsonl` using target `request_id`. |
| **Service Error (500 / 504)** | Server timeout or exception | Inspect server logs via `./scripts/start_server.sh` or `docker logs kenn-public-beta`. |
| **Excluded Feature Request** | User asks for AutoMix / Stem separation | Refer user to `docs/PUBLIC_BETA_SCOPE.md` feature exclusion matrix. |

---

## 2. Server Inspection & Health Procedures

### Checking Active Service Health
```bash
curl http://localhost:8090/health
```

### Reviewing Telemetry & Feedback Logs
```bash
tail -n 50 chat/.runtime/feedback.jsonl
```

### Restarting the Public Beta Service
```bash
# Docker Compose:
docker-compose restart kenn-api

# Local Shell:
pkill -f "python3 apps/backend/src/kenn/server.py" || true
./scripts/start_server.sh &
```
