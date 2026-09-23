# A1 — UI-path test harness: evidence (2026-09-23)

Why this exists: earlier the 10/10 demo script gate passed while the UI's
Apply button was broken for every numeric proposal, because the gate called
`/api/ableton/command` directly and never went through the chat route or the
browser. A1 makes the real UI path testable, with or without Live.

## What was built

| Piece | Path | Notes |
|---|---|---|
| Fixture recorder | `tooling/scripts/record_fake_live_fixture.py` | Read-only capture of the open Live set (tracks, returns, devices, every parameter with its display string, sends). Normalises pan/selection to the demo reset state unless `--as-is`. |
| Recorded fixture | `apps/backend/src/kenn/core/fake_live_fixtures/investor_demo.json` | Recorded from the real `KENN_Live12_Demo_RESET` set: 8 tracks, Drum Bus / Lead Vocal Compressor, Bass EQ Eight (84 params), returns A-Reverb and B-Delay. |
| Fake Live backend | `apps/backend/src/kenn/core/fake_live.py` | `KENN_LIVE_BACKEND=fake` only, never a fallback. Stateful writes, readback, display strings, device insert/remove with reindexing, fail-closed for unknown devices. Every snapshot and capability report says `fake`. |
| Fake companion launcher | `tooling/scripts/run_fake_live_companion.py` | Port 8091, isolated lock, receipt journal, chats, DB, shadow log and session file in a temp dir, so it can run beside the real companion. |
| Chat-route gate | `tooling/scripts/demo_script_gate.py --route ask` | Sends the 13 prompts through `/kenn/api/ask`, validates the gateway result embedded in chat replies, paces at 2.1 s to respect the chat route's 30/min budget. |
| Preflight honesty | `tooling/scripts/demo_preflight.py` | Against a fake backend it prints "FAKE Live backend: not demo evidence" instead of "ready for demo". |
| Playwright E2E | `apps/frontend/playwright.config.ts`, `apps/frontend/e2e/*.e2e.ts` | Installed Google Chrome (`channel: 'chrome'`), no browser download; starts or reuses the fake companion. `npm run test:e2e`. |

## Results

- **Fake Live, preflight:** 11/11, including set + exact undo, labelled "FAKE Live backend: not demo evidence".
- **Fake Live, gate:** command route 1/1 and chat route 1/1.
- **Playwright (fake Live), 5/5 in 3.7 s:**
  - session questions answer from the snapshot;
  - Apply → "Readback Verified" → receipt Undo → "Restored to Original State";
  - Dismiss → "No Changes Made" and empty session history;
  - chat "Undo that." reverts and marks the earlier card "Reverted" with no Undo button;
  - delete and master-maximum refused with no Apply button.
- **Real Live, chat route gate: 10/10** consecutive runs, 130 prompts, slowest 597.6 ms (budget 650 ms). The first attempt stopped at run 3 on KENN's 30/min chat-route rate limit; the gate now paces per route.
- **Suites:** backend 1,425 passed (5 skipped) at A1 completion; frontend unit 21/21; production build ok.

## Limits

- The fake approximates Live's display strings from recorded formats; KENN verifies writes by raw value, so this does not weaken readback checks.
- The analysis steps (12–13) need the rendered demo WAVs under `.runtime/`, so CI without them must skip those checks. The Playwright specs do not depend on them.
- The chat route's slowest step (597.6 ms) is close to the 650 ms budget; watch it in I1.
