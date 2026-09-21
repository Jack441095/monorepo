# KENN Public Beta Security and Hardening Notes

**Document Version**: `1.0.0-beta`

**Status**: Verified & Qualified


---

## 1. Input Validation & Abuse Controls

- **Upload Body Size Ceiling**: Enforced strict 50 MB payload ceiling (`MAX_PUBLIC_UPLOAD_BYTES = 50 * 1024 * 1024`). Requests exceeding 50 MB are rejected immediately with `413 Payload Too Large`.
- **Path Traversal Protection**: Filenames submitted via multipart forms or base64 JSON payloads are sanitized using `Path(filename.replace("\\", "/")).name` to strip all directory traversal sequences (`../`, `..\`).
- **File Format & Header Validation**: Only 16-bit and 24-bit PCM WAV formats are decoded. Non-WAV, corrupt, or truncated headers are caught safely and rejected with clean `400 Bad Request` messages without process crashes.
- **Rate Limiting**: Configured fixed-window rate limiter (default 30 requests/minute per client IP) on all public API endpoints (`/chat`, `/mix-review`, `/feedback`).
- **CORS Hardening**: Strict CORS origin configuration via `KENN_CHAT_ALLOWED_ORIGINS` enforcing explicit domain lists.

---

## 2. Output Escaping & Injection Defense

- **XSS & HTML Injection**: All user-controlled text inputs rendered in `UX/index.html` via `UX/app.js` are escaped using HTML entity replacement (`&`, `<`, `>`, `"`, `'`).
- **Prompt Injection Defense**: Input questions seeking system instruction override or DAW execution are routed to honest abstention handlers (`found: false`, `intent: "out_of_scope"`).
- **Stack Trace & Local Path Masking**: Global exception handlers in FastAPI return sanitized JSON error payloads (`{"detail": "..."}`) without leaking internal stack trace tracebacks or absolute server filesystem paths (`/Volumes/...`).

---

## 3. Automated Security Verification

The automated security test suite [chat/tests/test_security_and_abuse.py](file://<LOCAL_VOLUME>/Shenrendao/KENN/chat/tests/test_security_and_abuse.py) continuously verifies all 7 security constraints:
1. Path traversal filename rejection
2. Oversized upload rejection
3. Corrupt header safety
4. XSS script injection escaping
5. Prompt injection abstention
6. Stack trace & path masking
7. Memory-only audio safety

**Verification Status**: PASSED (7/7 tests)
