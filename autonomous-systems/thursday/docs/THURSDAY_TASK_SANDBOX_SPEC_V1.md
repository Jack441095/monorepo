# Thursday Task Sandbox Specification V1

This document defines the schema and execution rules for isolated task workspaces.

## 1. Sandbox Properties
Every sandbox contains:
- `sandbox_id`: Unique identifier (e.g. `sb-task-123`)
- `task_id`: Identifies the task being executed
- `worktree_path`: Dedicated Git worktree directory
- `temp_path`: Temporary directory inside OS `/tmp`
- `allowed_write_paths`: Confinement allowlist
- `forbidden_paths`: Directories blocked from reading/writing

## 2. Environment Pruning Rules
The sandbox purges variables to prevent secret leaks:
- **Allowed Keys**: `PATH`, `TMPDIR`, `LANG`, `LC_ALL`, `CC`, `CXX`, `MACOSX_DEPLOYMENT_TARGET`
- **Scoped Keys**: `HOME` mapped strictly to the sandbox temporary directory
- **Purged Keys**: Any string matching token, secret, signature, webhook, password, or credential namespaces.
