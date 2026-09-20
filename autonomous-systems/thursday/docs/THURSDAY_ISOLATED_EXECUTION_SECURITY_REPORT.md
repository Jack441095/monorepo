# Thursday Isolated Execution Security Report

This document reports on the security controls, environment sanitisation, and shell injection audits for V2-F.

## 1. Sandbox Penetration Verification
Adversarial test scripts ran attacks against the `TaskSandbox` workspace:
- **Symlink Escapes**: Attempted writing outside worktrees via symbolic link traversal was intercepted by `validate_lease_write_attempt`.
- **Environment Leaks**: Fake secrets injected into parent variables were pruned from sandbox env dicts.
- **Process Signals**: Signal operations are confined to processes belonging strictly to the task PGID.

## 2. Command Filtering
Commands containing `sudo`, `rm -rf /`, or `chmod` were intercepted and rejected by command filters.
