# Adapter Mapping (design notes — read-only, no product code changed)

Validation of the Phase-1 contracts against the current Thursday and KENN
types. Lossy mappings are stated explicitly.

## Thursday → shared contracts

| Thursday type/field | Shared contract | Mapping |
|---|---|---|
| `ServiceDef.name` | `CapabilityDefinition.capability_id` | rename + must be dotted-lowercase; some names need normalisation |
| `ServiceDef.version` | `.version` | direct |
| `ServiceDef.description/examples/triggers` | description only | examples/triggers are routing heuristics — **product-specific**, stay in Thursday |
| `ServiceDef.permissions: PermissionScope` | `permissions: tuple[Permission,...]` | rename; scope values map 1:1-ish |
| `ServiceDef.risk: ActionRisk(READ_ONLY…DESTRUCTIVE)` | `ActionRisk(LOW/MEDIUM/HIGH/CRITICAL)` | derived mapping needed (LOCAL_MUTATION→HIGH, DESTRUCTIVE→CRITICAL) — **lossless if mapped centrally** |
| `ServiceDef.action/post_process: Callable` | not representable in core | stays product-side; platform stores opaque `provider_id` |
| `Capability.to_capability()` JSON input schema | `input_schema` | direct |
| `thursday.client` results (prose-oriented) | `AgentResult.result` dict | **needs extension work** — Thursday returns human-formatted text today |
| action receipts / confirmation flow | out of scope Phase 1 | future execution-state layer |

## KENN → shared contracts

| KENN type/field | Shared contract | Mapping |
|---|---|---|
| `core.agent_contracts.AgentRequest` | `AgentRequest` | near-direct; add trace_id/locale/priority |
| `core.agent_contracts.AgentResult` | `AgentResult` | near-direct |
| `SubAgent(name, emoji, keywords, dispatch_fn)` | `CapabilityDefinition(provider_id=...)` | emoji/keywords are UI/routing — **product-specific** |
| `core.evidence.EvidenceFact/EvidencePacket` | `EvidenceItem/EvidencePacket` | direct with additions (analysis_version, confidence_kind); KENN's string confidence ("measured") becomes enum — small migration |
| `MARKER = "KENN_EVIDENCE_PACKET_V1:"` chat transport | structured transport later | **not representable** in core; keep until chat transport migrates |
| `tool_registry.py` tools | `ToolDefinition/ToolRegistry` | mostly direct |
| `mix_guardrails`, `chat_*`, persona | out of scope | stay KENN-owned |

## Verdict
No field forced product-specific logic into the shared core. The two known
gaps for a future phase: (1) Thursday's prose-oriented service results need a
structured-result wrapper; (2) KENN's evidence-in-chat-history marker needs a
structured transport before deprecation.
