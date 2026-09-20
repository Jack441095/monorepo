# NITE DSP AI Platform (`nite_ai`)

Shared typed contracts and platform primitives for NITE DSP AI systems.
Phase 1 foundation — **no orchestrator, no runtime behaviour yet**.

## What this is

- Typed agent / evidence / artifact / tool / capability contracts (frozen dataclasses)
- Structured error taxonomy + bounded retry policy contracts
- Permission / risk / privacy machine contracts
- Minimal in-process capability & tool registries (inversion of control)
- Evaluation and telemetry/trace schemas

## What this is NOT

- Not an orchestrator or agent runtime
- Not a model-routing or LLM-provider implementation
- Not a memory, context, prompt, or audio-analysis engine
- Not an HTTP service, IPC mechanism, or plugin host
- **Not a dependency of SLO.** SLO (SmartSampleManager) does not depend on
  this platform today and must not be coupled to it.

## Phase 1 scope

Implements backlog items AI-I01 (typed contracts) and the contract halves of
AI-I03 (error/permission/retry), AI-I04 (capability registry foundations),
and AI-I05 (evaluation/telemetry schemas). See
`Nite_DSP/architecture/NITE_DSP_AI_PLATFORM_IMPLEMENTATION_BACKLOG.md`.

## Install (dev)

```bash
python3 -m venv .venv && . .venv/bin/activate
pip install -e '.[dev]'
```

## Run tests

```bash
pytest
```

No network, no LLM APIs, no audio files, no database, no DAW required.

## Package structure

```
nite_ai/
  contracts/        AgentRequest/AgentResult, EvidencePacket, ArtifactRef,
                    ToolDefinition/ToolResult, CapabilityDefinition
  capabilities/     in-process CapabilityRegistry / ToolRegistry
  models/           model contracts, ProviderRegistry, deterministic
                    privacy-enforcing ModelRouter with bounded fallback,
                    deterministic mock providers
  adapters.py       ProductAdapter IoC glue (platform never imports products)
  context.py        typed context refs + budget selection
  working_memory.py task lifecycle + scratch/decision records
  approvals.py      approval requests, action levels, reversibility
  domain.py         company domain schemas (goals/projects/tasks/briefs)
  evaluation.py     evaluation case/suite/result schemas
  evaluation_runner.py  deterministic suite runner with JSON export
  errors.py         ErrorCategory, AgentError, RetryPolicy, ValidationError
  permissions.py    Permission, ActionRisk, PrivacyClass
  telemetry.py      TraceContext, TaskEvent (metadata-only)
tests/
docs/               CONTRACTS, CAPABILITY_REGISTRY, ADAPTER_MAPPING,
                    VERSIONING, PHASE2_MODEL_RUNTIME_AUDIT
```

## Product boundaries

| Product | Relationship |
|---|---|
| Thursday | Registers general/workflow capabilities via a future adapter; owns its orchestrator |
| KENN | Registers audio/mix capabilities via a future adapter; owns mix intelligence |
| SLO | External product boundary — zero coupling today |

The platform never imports product source; products register through adapters.
Parent architecture: `Nite_DSP/architecture/NITE_DSP_AI_PLATFORM_ARCHITECTURE_V1.md`.
