# Thursday NITE Shadow Adapters

This document details the read-only inspection methods for workspaces.

## 1. Adapter Boundaries
All workspace observation occurs without modifying the monitored directories.
- **Smart Sample Manager**: Observes branch updates, compiler logs, and DAW readiness files.
- **SLO V5-C**: Inspects background extraction checkpoints and CUDA logs.
- **Thursday / KENN**: Monitored for staging test coverage reports and heartbeats.

## 2. Ingestion Semantics
- Adapters verify directory existence and read files using atomic buffered streams.
- Any IO error, directory lockout, or unreadable status is caught gracefully and maps to `UNKNOWN` or `STALE` instead of raising exceptions or stalling the control plane.
- The adapters declare `read_only = True` and write access list `forbidden_writes = ["*"]`.
