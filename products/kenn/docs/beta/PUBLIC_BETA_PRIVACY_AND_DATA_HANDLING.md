# KENN Public Beta Privacy and Data Handling Policy

**Effective Date**: September 1, 2026

**Application**: KENN Public Beta Service (`v1.0.0-beta`)


---

## 1. Transient Audio Data Processing

- **No Permanent Retention**: Uploaded WAV audio files are processed in transient server memory for signal measurement (clipping, headroom, phase, balance, DC offset, loudness) and are discarded immediately after analysis.
- **No Training Use**: Audio files uploaded to KENN Public Beta are **never** used to train AI models or stored in training datasets.
- **Hosted Workflow Transparency**: In hosted beta environments, audio files are transmitted securely over TLS (HTTPS) to the server for processing.

---

## 2. Telemetry and User Feedback

- **Telemetry**: Request IDs (`X-Request-ID`), response latency, error codes, and endpoint usage metrics are logged to aid operational maintenance.
- **Feedback Logs**: Optional user ratings (1-5 stars) and comments submitted via `POST /feedback` are saved in `.runtime/feedback.jsonl` tied to the corresponding `request_id`.
- **No Personal Identifiable Information (PII)**: KENN does not collect names, email addresses, payment information, or account credentials.

---

## 3. Data Retention Summary Matrix

| Data Type | Storage Location | Retention Duration | Purpose |
| :--- | :--- | :--- | :--- |
| **Uploaded Audio (.wav)** | Server RAM only | Transitory (Instant deletion) | Signal diagnostic calculation |
| **Chat Questions** | RAM / Session log | Session duration | Grounded RAG answer generation |
| **Feedback Submissions** | `.runtime/feedback.jsonl` | Persistent (Local runtime DB) | Quality evaluation |
| **Server Logs** | Stdout / Process log | Standard log rotation | Operational monitoring |

---

## 4. User Inquiries & Incident Reporting

For privacy questions or data handling concerns, please contact the KENN release maintainer or file an issue in the repository queue.

