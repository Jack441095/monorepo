# Capability Registry

Minimal in-process registries. No database, network service, or plugin discovery.

- `CapabilityRegistry.register(CapabilityDefinition)` — rejects duplicate
  `(capability_id, version)` pairs; latest-version lookup by semver order;
  explicit-version lookup; `versions()`, `enumerate()`, `available()`.
- `ToolRegistry` — same shape for `ToolDefinition`s.

## Ownership / inversion of control

The platform imports **no** product code. Products register providers through
adapters:

```
KENN adapter     → registry.register(CapabilityDefinition(
                     capability_id="audio.mix.analyze",
                     provider_id="kenn.mix_analyzer", ...))
Thursday adapter → registry.register(CapabilityDefinition(
                     capability_id="workflow.email.draft",
                     provider_id="thursday.email_service", ...))
```

Provider IDs are opaque strings; resolution lives product-side. A test
asserts that registering a Thursday-style capability pulls in no `thursday`
or `kenn` modules.
