# Contracts

All contracts are frozen dataclasses (KENN precedent) — zero dependencies,
deterministic serialization, JSON Schema derivable for every contract.

## Agent layer
- **AgentRequest** — `request_id`, `trace_id`, dotted `capability_id`
  (e.g. `audio.mix.analyze`), structured `payload` dict, `context_ref`
  (reference, never inline history), BCP-47 `locale`, `priority`,
  `granted_permissions`, `privacy_class`, `metadata`. SECRET payloads rejected.
- **AgentResult** — explicit `status`: SUCCESS / PARTIAL / FAILED / CANCELLED /
  TIMEOUT. Carries structured `result`, optional `evidence` packet, `artifacts`,
  `warnings`, one structured `error`, `execution` metadata. Invariants:
  SUCCESS needs payload/artifacts and forbids errors; terminal failures need an error.
- **ExecutionMetadata** — timing, attempt count, executor/model references.

## Evidence layer (generalised from KENN)
- **EvidenceItem** — name/value/unit + `source` component +
  `confidence_kind` ∈ {measured, classifier, derived, reasoning}; a bare
  confidence float without a kind is invalid. Optional `analysis_version`,
  `captured_at_epoch`, artifact reference.
- **EvidencePacket** — bounded fact bundle with `packet_id`, `source`,
  `limitations`.

## Artifacts
- **ArtifactRef** — id/kind/URI/metadata only. Binary blobs are never embedded.

## Tools
- **ToolDefinition** / **ToolRequest** / **ToolResult** — schemas, timeout,
  retry policy, permissions, risk, latency class, determinism flag.
  ToolResults are structured; raw terminal text is not a contract.

## Capabilities
- **CapabilityDefinition** — stable dotted ID, semver, JSON-Schema input/output,
  permissions, risk, latency class, max privacy class, opaque `provider_id`,
  availability. HIGH/CRITICAL risk requires declared permissions; CRITICAL
  requires the destructive permission.
