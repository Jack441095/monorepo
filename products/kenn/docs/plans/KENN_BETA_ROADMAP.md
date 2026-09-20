# KENN Beta Roadmap & Implementation Plan

Audit date: 2026-09-01. Branch: `develop` (`https://github.com/Jack441095/kenn-standalone.git`).

This document lays out the phased roadmap and exit criteria required to bring KENN from its current standalone state to a fully qualified, safe internal beta.

---

## 1. Phased Execution Roadmap

The implementation plan is structured into 11 strictly ordered work packages:

```
Package 1: Audit & Document Current State (Completed)
    │
    ▼
Package 2: Isolate Standalone Dependencies & Interfaces
    │
    ▼
Package 3: Knowledge Base Benchmark & Abstention Hardening
    │
    ▼
Package 4: Read-Only Live Context Observer
    │
    ▼
Package 5: Typed Action & Approval Contracts (ActionProposal)
    │
    ▼
Package 6: Single Parameter Mutation Engine (Compressor Threshold)
    │
    ▼
Package 7: Read-Back Verification, Receipts & Undo Engine
    │
    ▼
Package 8: C++ Realtime Core Feature Alignment & Profiling
    │
    ▼
Package 9: Enhanced Knowledge Retrieval & Citation Precision
    │
    ▼
Package 10: Unified Voice & Text Pipeline (Speech-to-Text Handoff)
    │
    ▼
Package 11: Final Beta Qualification & Sign-Off
```

---

## 2. Package Specifications & Exit Criteria

### Package 1: Audit & Document Current State (COMPLETED)
- **Objective**: Complete read-only audit of codebase, C++ core, Live control paths, knowledge base, and evaluation harnesses.
- **Deliverables**:
  - `docs/KENN_CURRENT_STATE_AUDIT.md`
  - `docs/KENN_LIVE_CONTROL_AUDIT.md`
  - `docs/KENN_KNOWLEDGE_BASE_AUDIT.md`
  - `docs/KENN_CPP_ARCHITECTURE_AUDIT.md`
  - `docs/KENN_BETA_GAP_MATRIX.md`
  - `docs/KENN_BETA_ROADMAP.md`
- **Exit Condition**: All 6 reports generated and committed.

---

### Package 2: Isolate Standalone Dependencies & Interfaces
- **Objective**: Ensure KENN has zero mandatory runtime dependencies on `Audio_Too`, `Thursday`, `NITE_DSP`, or external monorepos.
- **Tasks**:
  1. Verify fallback handlers for missing optional routes in `server.py`.
  2. Isolate evaluation scripts: create KENN-native runner for benchmark suite without `audio_analysis` dependency.
  3. Verify standalone build scripts for `plugins/kenn-vst3-au/` and `mix-review/`.
- **Exit Condition**: Full test suite passes without any external path lookup.

---

### Package 3: Knowledge Base Benchmark & Abstention Hardening
- **Objective**: Harden chat engine against ambiguous/out-of-scope queries and validate BM25 retrieval accuracy.
- **Tasks**:
  1. Implement Golden Evaluation Set covering 16 engineering categories.
  2. Harden prompt grounding in `chat_grounding.py` against prompt injection.
  3. Ensure 100% abstention on non-audio or out-of-scope requests.
- **Exit Condition**: 100% pass on abstention test suite; > 0.85 MRR on retrieval benchmarks.

---

### Package 4: Read-Only Live Context Observer
- **Objective**: Build robust session state reader for Ableton Live 12.
- **Tasks**:
  1. Extend `AbletonOSCClient` with structured session state snapshotting.
  2. Implement track, device, and parameter indexing with min/max/unit metadata.
  3. Add connection health monitoring and timestamp versioning.
- **Exit Condition**: Automated unit test mocking Ableton UDP responses returns full session object cleanly.

---

### Package 5: Typed Action & Approval Contracts (`ActionProposal`)
- **Objective**: Create typed proposal contract preventing direct LLM parameter writes.
- **Tasks**:
  1. Generalize `plugin_actions.py` `ActionProposal` (`kenn.action_proposal.v1`) to support Ableton Live devices.
  2. Integrate `confirmation.py` HMAC-SHA256 token generation into action planner.
  3. Register Ableton parameter mutation tool under `LOCAL_MUTATION` risk tier in `tool_registry.py`.
- **Exit Condition**: Action planner returns signed `ActionProposal` payload requiring explicit token verification prior to execution.

---

### Package 6: Single Parameter Mutation Engine ("KENN, lower vocal compressor threshold by 2 dB")
- **Objective**: Implement safe end-to-end single parameter modification.
- **Tasks**:
  1. Implement intent parser mapping natural language ("lower vocal compressor threshold by 2 dB") to target track/device/parameter indices.
  2. Calculate proposed value clamped strictly to parameter min/max.
  3. Require explicit HMAC token verification before calling `live_client.set_device_parameter()`.
- **Exit Condition**: End-to-end test executing proposal → confirmation → set parameter successfully.

---

### Package 7: Read-Back Verification, Receipts & Undo Engine
- **Objective**: Guarantee execution accuracy and full reversibility.
- **Tasks**:
  1. Snapshot `current_value` prior to applying mutation.
  2. Execute immediate read-back query (`get_device_parameters`) after write to verify final parameter value.
  3. Emit structured execution receipt (`kenn.execution_receipt.v1`).
  4. Implement 1-step undo operation restoring exact prior parameter value.
- **Exit Condition**: Reversing an applied parameter change restores original parameter value with read-back proof.

---

### Package 8: C++ Realtime Core Feature Alignment & Profiling
- **Objective**: Align C++ real-time analysis core (`AudioTooRealtimeCore.h`) with Mix Review evidence schema and perform profiling.
- **Tasks**:
  1. Create numerical correctness tests comparing C++ analysis against reference NumPy calculations.
  2. Profile CPU, memory, and latency overhead under stress.
  3. Harmonize field names between plugin JSON handoff and `mix-review` evidence reports.
- **Exit Condition**: Zero TSan data races; numerical parity verified within 1e-4 tolerance.

---

### Package 9: Enhanced Knowledge Retrieval & Citation Precision
- **Objective**: Support full citation transparency in chat answers.
- **Tasks**:
  1. Add source note title and relative file link to every citation payload.
  2. Verify citation ground-truth mapping against retrieved note text.
- **Exit Condition**: 100% of generated citations match retrieved source documents.

---

### Package 10: Unified Voice & Text Pipeline
- **Objective**: Ensure voice commands pass through the exact same safe action pipeline.
- **Tasks**:
  1. Map Speech-to-Text (STT) transcriptions directly into natural-language intent parser.
  2. Enforce identical proposal, confirmation, execution, read-back, and undo steps.
- **Exit Condition**: Voice input payload produces identical `ActionProposal` and confirmation requirement as typed text.

---

### Package 11: Final Beta Qualification & Definition of Done
- **Objective**: Final readiness review and formal qualification.
- **Definition of Done Checklist**:
  - [ ] Standalone repository builds without external dependencies.
  - [ ] Default Live control does not require `Audio_Too` checkout.
  - [ ] Read-only Live inspection functional.
  - [ ] End-to-end single parameter control ("lower vocal compressor threshold by 2 dB") verified.
  - [ ] 100% of parameter writes require signed confirmation tokens.
  - [ ] Range, unit, and track identity validated.
  - [ ] Read-back verification confirms DAW state.
  - [ ] Structured receipts generated for every change.
  - [ ] Single-step parameter Undo tested and functional.
  - [ ] Adversarial test suite passing with zero unauthorized mutations.
  - [ ] Knowledge base retrieval & citation precision benchmarked.
  - [ ] C++ core numerical correctness and thread safety verified.
  - [ ] Voice and text pipelines share unified contract.
  - [ ] Operational tester guide, support runbook, and rollback plan updated.

---

## 3. Risk Mitigation & Safety Summary

| Risk | Mitigation Strategy |
|---|---|
| Unintended DAW Parameter Corruption | Strict min/max clamping, read-back verification, mandatory user confirmation. |
| Hallucinated Action Parameters | Parameters fetched exclusively from Live LOM (`get_device_parameters`), not LLM memory. |
| Stale Session Context | Expiring proposal timestamps (TTL 300s) and Live session versioning. |
| Malicious / Adversarial Injection | XML data wrapping, strict request schema validation, HMAC token signing. |

