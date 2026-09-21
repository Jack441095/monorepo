# Ableton Assistant Support Runbook

## No Live connection

First inspect `KENN_LIVE_BACKEND` and `GET /api/ableton/capabilities`.

For `control-deck-mcp`, report `offline`, confirm Live is open, confirm `Control
Deck` is selected after restart, and run the configured
`KENN_LIVE_MCP_COMMAND` directly to expose its startup error. Confirm
`KENN_LIVE_MCP_CWD` still points at the built Control Deck checkout. Do not
change the backend to OSC as a workaround: an explicitly selected MCP backend
fails closed. KENN's Control Deck adapter is read-only until real-Live
qualification is recorded, even though the upstream provider advertises write
tools.

For `osc`, report `offline`/`dispatched`, confirm Live is open, confirm
`AbletonOSC` is selected after restart, check UDP 127.0.0.1:11000 and response
port 11001, and retry a read-only snapshot. A second post-hardening companion
launch exits with status 2 and the active owner's PID before serving HTTP; stop
only that exact KENN instance before retrying. For older builds that report
`Address already in use` for UDP 11001, use `lsof -nP -iUDP:11001` to identify
the exact owner. Never kill an unidentified process or broadly match process
names. Do not claim a write succeeded.

## Stale or ambiguous proposal

Ask the user to refresh the snapshot and create a new proposal. Do not edit the token, index, name, or value to “make it fit.” Duplicate track/device names require clarification.

## Readback failure

Treat the result as unverified. Inspect Live manually, do not retry automatically, and preserve the receipt/error. If a batch partially ran, confirm rollback before any further action.

## Audio analysis issue

Retain the input hash and error, validate that the file is mono/stereo 16/24-bit PCM WAV, and report abstention for short/silent/corrupt input. Do not substitute RMS for LUFS or sample peak for true peak.

Escalate with KENN version, command, sanitized request, input hash, Live version, session/set hash, receipt ID, and logs. Redact audio, tokens, paths, and personal data.

## Support diagnostics

For a ticket, query the loopback-only redacted payload:

```bash
curl http://127.0.0.1:8090/api/support/diagnostics
```

It reports capability and environment summaries without raw Live state, source
audio, project content, personal paths, or confirmation tokens. Attach the
payload together with a sanitized request ID; use the separate read-only Live
probe for session-specific evidence.

Create a shareable local archive with
`python3 scripts/build_support_bundle.py --output /secure/support/kenn-support.zip`.
This performs an additional allow-list projection and excludes raw logs,
session IDs, targets, names, paths, prompts, errors, audio, and confirmation
material. It writes mode 0600 and does not upload the archive.
