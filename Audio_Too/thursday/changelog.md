# Thursday Changelog

## v2.0.0 — Jarvis-Class Orchestrator Upgrade

### Added
- **Session Manager** (`session_manager.py`) — Persistent JSON-based session store with conversation turns, context tracking, and automatic session creation.
- **Intent Classification Engine** (`intent.py`) — Replaces fragile keyword scoring with categorized intent matching across 10 intent categories, plus regex-based entity extraction.
- **Entity Resolver** (`resolver.py`) — Context-aware pronoun resolution ("her" → client name), implicit reference resolution ("the client", "that invoice"), and temporal reference detection.
- **Unified API Client** (`client.py`) — Typed wrappers for all modules (Business Ops, Agents, KENN, Audio Analysis, AudioGen, etc.) that return structured `{ok, data, error}` dicts.
- **Service Registry v2** (`registry.py`) — Declarative `ServiceDef` dataclass with triggers, intents, required context, action callbacks, and post-processing hooks.
- **Proactive Monitor** (`monitor.py`) — Checks for stale leads, overdue invoices, new enquiries, and financial health; generates alerts prepended to responses.
- **Response Formatter** (`formatter.py`) — Standardizes all output and appends contextual "Try next:" follow-up suggestions.
- **Error Recovery** (`errors.py`) — Typed exception hierarchy (`AmbiguousEntityError`, `MissingInfoError`, `NoMatchError`, `ServiceError`) with recovery suggestions.
- **Alert storage** (`Thursday/alerts/`) — Directory for monitoring alert JSON files.
- **Session storage** (`Thursday/sessions/`) — Directory for session JSON files.

### Changed
- **`__init__.py`** — Updated docstring to reflect orchestrator capabilities.
- **`main.py`** — Added session support (`--session` flag, `--new-session` flag), context-aware routing via orchestrator v2.
- **`orchestrator.py`** — Complete rewrite: integrates session context, intent classification, entity resolution, service registry, proactive alerts, and response formatting.

### Architecture
```
main.py → session_manager → resolver → intent → registry → client → formatter
         ↘ monitor (background checks) ↗
```

### Success Criteria
- [x] Context retention across turns
- [x] Intent classification (10 categories)
- [x] Pronoun and implicit reference resolution
- [x] Proactive alerts on stale leads, overdue invoices
- [x] Unified client interface for all modules
- [x] Follow-up suggestions on every response
- [x] Full Dashboard/Creative Lab integration
- [x] KENN enhancement proxy and mix-review handoff
- [x] Draft-email + reminder workflow chaining

### Hardening and completion
- Persist service post-processing context and both sides of each conversation.
- Enforce required context while accepting explicit IDs in the current request.
- Add atomic session writes, schema migration, and session-ID validation.
- Deliver alerts once, record every monitor run, detect expiring upload links, and detect two-month financial warnings.
- Add a canonical structured `APIClient` facade for every module in the upgrade plan.
- Add AudioGen job context, review context, KENN note creation/comparison, safe audio-storage previews, and natural-language business filters.
- Add focused regression tests for context chains, monitoring, routing, sessions, structured results, and business insights.
