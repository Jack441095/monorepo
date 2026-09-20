# Versioning

- Package: `nite_ai` **0.1.0** — early development, not a stable public API.
- `CONTRACT_SCHEMA_VERSION = "1.0.0"` — carried by schema-bearing payloads
  (e.g. `EvidencePacket.schema_version`, `EvaluationSuite.schema_version`).
- Capability/tool versions are semver strings, validated at registration;
  registries resolve "latest" by semver order and support pinned lookups.

## Compatibility philosophy

**Additive evolution.** New fields must be optional with defaults. Removing or
renaming a field, changing a field's type, or tightening validation is a
breaking change → bump the major contract schema version and coordinate with
all registered providers before release.

## Rules of thumb

1. Contracts serialize deterministically (sorted keys, enums as values).
2. Machine IDs (`capability_id`, `tool_id`, error codes) never change meaning
   silently; descriptions may change freely.
3. JSON Schemas are derived from the dataclasses, so schema drift is caught by
   the test suite rather than by documentation decay.
