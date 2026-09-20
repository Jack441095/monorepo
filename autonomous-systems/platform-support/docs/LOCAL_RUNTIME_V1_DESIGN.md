# Local NITE Runtime — V1 Design

DESIGN ONLY — not implemented this phase.

## Recommendation: Unix domain socket, localhost-only (macOS-first)

| Option | Verdict |
|---|---|
| In-process library | simplest, but no crash isolation and one model copy per client |
| Local HTTP | universal debugging, but heavier; loopback TCP still firewall-visible |
| **Unix domain socket** | chosen: local-only by construction, fast, C++/Python/Swift clients all supported, no port collisions |
| localhost service (TCP) | rejected for V1 — broader attack surface |

## Process lifecycle
- Launch on first client request (launchd/agent or lazy spawn), idle shutdown
  after configurable inactivity; explicit version handshake on connect.
- Crash isolation: runtime death never takes down Thursday/KENN/desktop clients;
  clients reconnect and re-handshake.

## API contract (JSON over socket, versioned envelope)
`GET brief.daily / review.weekly / goals / projects / tasks / agents /
approvals / risks / evidence:{id}` · `POST command`, `POST approval.decision`.
All responses are the existing nite_ai contracts serialized to JSON;
`schema_version` in every envelope.

## Auth & privacy
- Socket file permission bits restrict to the owner user; peer-credential
  check (SO_PEERCRED equivalent on macOS) on connect.
- Privacy classes enforced server-side: PRIVATE_AUDIO processing stays local
  (ONNX/local models); routing constraints from `nite_ai.models` apply.

## Model ownership
One model copy inside the runtime; providers registered via ProviderRegistry;
circuit breaker + fallback shared. ONNX session init lock moves into the
runtime (removes per-process duplication seen in audio_too).

## Relationships
Thursday = primary client (company AI + orchestration) · KENN = audio
capability provider/client · Desktop app = UI client of the same contract ·
SLO = optional future external client via stable capabilities only.

## Version compatibility
Handshake carries platform `__version__` + CONTRACT_SCHEMA_VERSION; additive
evolution only; incompatible majors refuse connection with a structured error.

## Not built yet
Deliberately deferred until live adapters have run in real daily use.
