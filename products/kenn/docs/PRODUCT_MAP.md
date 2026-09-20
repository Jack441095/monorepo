# KENN product map

| Area | Canonical location | Purpose |
|---|---|---|
| Python backend | `apps/backend/src/kenn/` | HTTP server, chat/retrieval, Ableton control, audio intelligence and SLO adapter |
| Current editable UX | `apps/frontend/` | Vue 3, TypeScript and Vite application |
| Served/legacy UX | `apps/legacy-web/` | Existing server-served UI code; generated asset folders are excluded |
| VST3/AU | `plugins/kenn-vst3-au/` | JUCE plugin source and build configuration |
| Ableton integration | `integrations/ableton-remote-script/` and `integrations/ableton-osc/` | Remote Script, OSC bridge and vendored source |
| Desktop companion | `apps/desktop/macos/` | macOS companion source |
| Chat service | `packages/chat/` | Standalone chat service and tests |
| Mix Review | `packages/mix-review/` | Local analysis engine, contracts and tests |
| AutoMix | `packages/automix/` | Approval/receipt boundary and associated source |
| Tooling | `tooling/scripts/`, `tooling/benchmarks/`, `tooling/evaluation/` | Build, verification and evaluation code |
| Shared code | `packages/common/` | Shared helpers |
| Documentation | `docs/` | Architecture, guides, plans and reports |

## Workspace structure

```text
products/kenn/
├── apps/
│   ├── backend/
│   ├── frontend/
│   ├── desktop/
│   └── legacy-web/
├── plugins/
├── integrations/
├── packages/
├── tooling/
├── docs/
├── assets/
└── runtime/
    └── legacy/
```

Backend code imports product locations from `kenn.paths`; add new top-level areas there instead of deriving parent-directory counts in feature modules.
