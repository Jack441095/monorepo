# KENN Live Control Audit

Audit date: 2026-09-01. Branch: `develop` (`https://github.com/Jack441095/kenn-standalone.git`).

This document provides a comprehensive, empirical audit of Ableton Live control capabilities inside KENN, evaluating current infrastructure against the target safe conversational control pipeline ("KENN, lower the vocal compressor threshold by 2 dB").

---

## 1. System Overview & Component Classification

Every Ableton Live control component in KENN has been audited and classified against the 8 required categories:

| Component | Classification | Description & Empirical Evidence |
|---|---|---|
| `apps/backend/src/kenn/ableton_osc_bridge.py` (`AbletonOSCClient`) | **Partially working, tested (low-level)** | Python UDP client on port 11000 using JSON-over-UDP. `_send_and_confirm()` waits up to 0.5s for matching response IDs. Supports track fields, device parameters, clip/scene ops, transport, and sidechain configuration. |
| `integrations/ableton-remote-script/KENN_Bridge/` (`KENN_Bridge.py`) | **Partially working, untested (DAW live session)** | Ableton 12 ControlSurface Python script listening on 127.0.0.1:11000. Uses real LOM indexing (`trk.devices[d_idx].parameters[p_idx]`), min/max clamping. `begin_undo_step()` / `end_undo_step()` wrapped only around track volume/pan/mute/solo/arm. |

| `apps/backend/src/kenn/m4l/osc_listener.py` (`AbletonOSCListener`) | **Demo-only, unwired** | Binary OSC parser (UDP 9001) for standard AbletonOSC format. Not instantiated or referenced by any active KENN server route or pipeline. Passive state cache only; no write functionality. |
| `apps/backend/src/kenn/core/autonomous_agent.py` | **Tested but unqualified, unsafe** | Exposes `tool_set_ableton_parameter` and `tool_set_ableton_macro`. Executes LLM-generated JSON tool plans directly against `live_client` without user confirmation or typed proposal contracts. No pre-write value snapshot or parameter undo. |
| `apps/backend/src/kenn/server.py` (`/api/ableton/*` routes) | **Partially working** | Exposes `/api/ableton/osc/volume`, `/pan`, `/mute`, `/solo`, `/arm`, `/undo`, `/transport/play`, `/stop`, `/tempo`, `/clip/launch`, `/scene/launch`. Gated only by global `action_allowed("daw_control")` env flag. No parameter-level get/set routes exposed over HTTP. |
| `apps/backend/src/kenn/core/confirmation.py` & `tool_registry.py` | **Working, tested (unit level), unwired for Ableton** | HMAC-SHA256 signed, time-boxed (TTL 300s) confirmation tokens. `tool_registry.py` defines risk tiers (`LOCAL_MUTATION`), but Ableton parameter writes were explicitly left unregistered in default tables. |
| `apps/backend/src/kenn/core/plugin_actions.py` | **Working, tested (plugin-only)** | Defines `ActionProposal` dataclass (`kenn.action_proposal.v1`) with before/after, reason, risk, verification, and compute-undo payload. Currently hardcoded to `target == "kenn_mix_assistant"` (`target_lufs`), not generalized to Ableton devices. |
| Single-parameter Undo | **Partially working (track-only)** | `/api/ableton/osc/undo` restores previous state for `{volume, pan, muted, soloed, armed}` only. No parameter-level or device-level undo payload exists. |

---

## 2. Gaps Against Mission Goal ("KENN, lower the vocal compressor threshold by 2 dB")

The target workflow requires a 12-step deterministic pipeline:
1. Understand natural-language request ("vocal compressor threshold -2 dB");
2. Identify target track ("Vocal");
3. Identify target device ("Compressor" / "Audio Effect Rack");
4. Identify target parameter ("Threshold");
5. Inspect current value & valid range from Live;
6. Calculate proposed target value;
7. Explain the reason & evidence;
8. Ask for explicit user confirmation with a signed proposal;
9. Apply the change to Live;
10. Read value back from Live to verify;
11. Report success/failure;
12. Store receipt & enable undo.

### Key Technical Gaps

1. **Direct LLM-to-DAW Execution (Bypassed Safety)**: `autonomous_agent.py` translates free-text prompts into direct `live_client.set_device_parameter()` calls without an intermediate `ActionProposal` or user confirmation step.
2. **Missing Typed Action Proposal for Live Control**: `plugin_actions.py` provides the exact required proposal schema (`kenn.action_proposal.v1`), but it is scoped strictly to the VST3 plugin's internal LUFS target.
3. **No Confirmation Token Gate on Live Writes**: `confirmation.py` contains working HMAC confirmation primitives, but `ableton_osc_bridge.py` and `server.py` bypass `tool_registry` gating and rely solely on `action_policy.action_allowed("daw_control")`.
4. **No Read-Back Verification Loop**: Parameter writes return Ableton's immediate echoed status from the write call, but do not execute a secondary verification read query (`get_device_parameters`) to confirm the state persisted.
5. **No Parameter Undo Recording**: Previous parameter values are not snapshotted prior to mutation, preventing exact parameter restoration.
6. **Remote Script Undo Scope**: `KENN_Bridge.py` wraps track volume/pan/mute/solo/arm in `begin_undo_step()`, but does not wrap `set_device_parameter()`.

---

## 3. Safe 5-Layer Live Control Architecture Specification

To satisfy safety and explainability requirements, KENN's Live control architecture must be structured into 5 isolated layers:

```
[ Natural Language Request ]
            │
            ▼
┌───────────────────────────┐
│ 1. Live Context Observer  │ ◄── Reads session state, tracks, devices, params, ranges
└─────────────┬─────────────┘
              │ Verified Live State
              ▼
┌───────────────────────────┐
│ 2. Intent & Action Planner│ ──► Generates typed ActionProposal (NO DAW Execution)
└─────────────┬─────────────┘
              │ Proposal Payload
              ▼
┌───────────────────────────┐
│ 3. Safety & Policy Layer  │ ──► Validates range/unit/target, issues HMAC token, prompts User
└─────────────┬─────────────┘
              │ Confirmed Token
              ▼
┌───────────────────────────┐
│ 4. Live Executor          │ ──► Applies write via UDP, performs readback verification
└─────────────┬─────────────┘
              │ Verification Result
              ▼
┌───────────────────────────┐
│ 5. Receipt & Undo Engine  │ ──► Records execution receipt, stores undo payload
└───────────────────────────┘
```

### Layer 1: Live Context Observer
- **Role**: Periodically or on-demand queries Live session state (`query_session_state`, `get_device_parameters`).
- **Data Model**: Stable identifiers for tracks, devices, parameter indices, names, min/max bounds, units, current values, and session version timestamps.
- **Health**: Monitored via ping response and UDP timeout checks.

### Layer 2: Intent and Action Planner
- **Role**: Converts natural-language requests and observer state into a strongly-typed `ActionProposal` instance.
- **Contract**:
  - `action_id`: UUIDv4
  - `schema`: `"kenn.action_proposal.v1"`
  - `operation`: `"set_device_parameter"`
  - `target_track`: Track name & index
  - `target_device`: Device name & index
  - `target_parameter`: Parameter name & index
  - `current_value`: Snapshotted value
  - `proposed_value`: Calculated value
  - `unit`: e.g. `"dB"`, `"Hz"`, `"%"`, `""`
  - `valid_range`: `[min_val, max_val]`
  - `reason`: Grounded explanation
  - `confidence`: `"high"` | `"medium"` | `"low"`
  - `expiry_timestamp`: Time-to-live deadline
  - `requires_confirmation`: `True`

### Layer 3: Safety & Policy Layer
- **Role**: Gating mechanism preventing unauthorized or malformed execution.
- **Rules**:
  - Rejects ambiguous track/device matching (must be unambiguous or abstain).
  - Validates proposed values strictly against `valid_range`.
  - Rejects expired or stale proposals (timestamp check vs Live context version).
  - Requires valid HMAC signature token generated by `confirmation.py`.
  - Enforces `LOCAL_MUTATION` risk tier policy.

### Layer 4: Live Executor
- **Role**: Executes approved parameter changes safely via `AbletonOSCClient`.
- **Flow**:
  1. Validates confirmation token against proposal ID and request context.
  2. Issues `set_device_parameter(track_idx, device_idx, param_idx, proposed_value)`.
  3. Performs immediate read-back query (`get_device_parameters`).
  4. Compares read-back value against `proposed_value` within float tolerance (1e-3).

### Layer 5: Receipt and Undo Engine
- **Role**: Records audit trails and provides exact 1-step reversal.
- **Receipt Payload**: Includes proposal details, timestamp, execution status, read-back verification delta, and `undo_payload`.
- **Undo Execution**: Re-applies `current_value` captured prior to mutation via the same verified executor pipeline.

---

## 4. Operational Boundaries for First Internal Beta

The initial internal beta release must restrict Live control scope to:
- **Allowed Operations**: Single-parameter modification (`set_device_parameter`) on existing Audio Effect / VST devices.
- **Prohibited Operations**:
  - Track / device deletion or creation.
  - Record arming or transport state modification during active recording.
  - Destructive project file saving or overwriting.
  - Multi-track or bulk parameter automation batches.
  - Arbitrary unverified text-to-code execution.

---

## 5. Verification & Qualification Criteria

Before marking Live control as Beta-Ready:
- [ ] End-to-end automated test covering "propose → confirm → apply → read-back → verify → undo" loop.
- [ ] Adversarial tests covering ambiguous track names, out-of-bounds parameter values, expired confirmation tokens, and sudden UDP disconnects.
- [ ] Manual verification in Ableton Live 12 suite with standard devices (Compressor, EQ Eight, Utility, Limiter).
