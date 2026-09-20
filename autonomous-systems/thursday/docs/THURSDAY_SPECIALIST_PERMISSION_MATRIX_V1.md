# Thursday Specialist Permission Matrix V1

This document defines the strict workspace permissions granted to each specialist role.

| Specialist Role | Read Workspace | Write Sandbox | Git Commit | Run Tests | Run Builds | External APIs |
| :--- | :--- | :--- | :--- | :--- | :--- | :--- |
| **DOCUMENTATION** | YES | YES | YES | YES | NO | NO |
| **QA** | YES | YES | YES | YES | YES | NO |
| **ENGINEERING** | YES | YES | YES | YES | YES | NO |
| **RELEASE_ENGINEERING**| YES | YES | YES | YES | YES | NO |
| **RESEARCH** | YES | NO | NO | NO | NO | YES (read-only web search) |
| **MARKETING** | YES | NO | NO | NO | NO | NO (pending real integration) |
| **COMMERCIAL** | YES | NO | NO | NO | NO | NO |
| **SUPPORT** | YES | NO | NO | NO | NO | NO |
| **SECURITY** | YES | NO | NO | NO | NO | NO |
| **DATA** | YES | NO | NO | NO | NO | NO |

- **No Inheritance**: Permissions are role-scoped and do not inherit capabilities from other nodes.
- **Auto-merging**: No specialist is permitted to push directly to shared/release branches under any circumstances.
- **RESEARCH's "External APIs" corrected (2026-09-05)**: this row previously said NO,
  which was stale relative to `thursday/ops/research_ops.py`'s real, wired-up Tavily
  web-search integration (added 2026-09-02, used by the `research_agent`/
  `find_customers` services) — this doc was never reconciled with that work. It's
  scoped strictly to read-only search, never posting/sending/spending.
- **MARKETING has no real external API access yet**: `thursday/specialists.py`'s
  `marketing` manifest requires `external_write` approval for anything that would
  eventually publish/send, but no real external platform (social scheduler, ad
  platform, email tool) is wired up as of this writing — see
  `thursday/mcp_client.py` for the (currently disabled-by-default) generic connection
  point meant to carry that integration once a specific platform is chosen.
  **Verified 2026-09-07** against a real local `mcp` v2.2.0 install and a real stdio
  test server (`tests/fixtures/toy_mcp_server.py`, exercised by
  `tests/test_mcp_client.py::test_real_mcp_server_end_to_end`) — the module was
  originally written against the SDK's legacy v1 API (`ClientSession`/`stdio_client`/
  `sse_client`) and rewritten after finding `pip install mcp` today installs v2, whose
  unified `Client`/`StdioServerParameters` shape is different (and has no top-level
  SSE client at all). Streamable HTTP (`THURSDAY_MCP_SERVER_URL`) is still unverified
  against a real HTTP server — only stdio was tested.
- **Real execution added 2026-09-08** for COMMERCIAL, SUPPORT, DOCUMENTATION, and a
  narrow slice of QA — `thursday/specialists.py::run_grounded_specialist()` gathers
  real evidence from `thursday/ops/finance_ops.py`, `support_ops.py`,
  `documentation_ops.py` + `doc_search_ops.py`, and `qa_ops.py::beta_readiness_check()`
  respectively, then uses the LLM only to phrase a summary of that evidence — never to
  invent it. Reachable via chat through the new `specialist_task` service
  (`registry/system.py`) — "ask the qa specialist ...", "commercial specialist ...", etc.
  **Scope note on QA**: this row's Write Sandbox/Git Commit/Run Tests/Run Builds columns
  describe a broader, code-testing QA role that remains unbuilt (same self-documented
  scaffolding as ENGINEERING/RELEASE_ENGINEERING — see `autonomous_controller.py`'s
  `"EXECUTE (simulated in controller)"` comment). `run_grounded_specialist()`'s "qa" path
  is narrower and read-only: it summarizes the real beta-readiness checklist, it does not
  run tests or touch code.
- **SECURITY and DATA added to this table (2026-09-08), still no real execution**: no
  `security_ops.py` exists anywhere in this repo, and `thursday/ops/macro_analytics.py`
  (the closest thing for "data") only covers Thursday's own macro-execution telemetry,
  not general business/product data. `run_grounded_specialist()` abstains immediately for
  both, with zero LLM calls, rather than answering from nothing — the same discipline
  `support_ops.py` and `marketing_ops.py` already apply to their own real gaps.
