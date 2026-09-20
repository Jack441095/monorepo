# Thursday Lease and Sandbox Model

This document specifies the workspace leases and path containment mechanisms to isolate future specialist writes.

## 1. Lease Receipt Structure
Before a workstream gains local write access, Thursday issues a structured lease receipt:
- `lease_id`: Cryptographically verified ID
- `task_id`: Identifies the executing task
- `worktree`: Path to the dedicated checkout directory
- `allowed_paths`: Sub-folders (e.g. `worktree/staging`) where writes are permitted
- `expires_at`: Epoch timestamp

## 2. Confinement Gates
Lease validation blocks:
- **Path Traversal**: Any presence of `..` or escapes pointing outside the permitted worktree staging directory.
- **Symlink Escapes**: Intercepting attempts to write to symlinks referencing external directories.
- **Stale/Stalled Work**: Rejecting lease checks if the workspace SHA changes or if lease age exceeds limit.
