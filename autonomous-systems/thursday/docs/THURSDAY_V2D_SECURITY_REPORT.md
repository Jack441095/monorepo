# Thursday V2-D Security Report

This document reports on the security matrix, sandbox restrictions, and prompt injection audits for Thursday V2-D.

## 1. Threat Scenarios Audited
1. **Spoofed Approval / Replay**: Rejecting L2/L3 approvals if plan hash mismatches or if target workspace changes after verification.
2. **Path Traversal / Sandbox Escape**: Specialists modifying directories outside their scope or modifying forbidden targets.
3. **Malicious Task Notes / Injection**: Untrusted data containing instructions like "SYSTEM OVERRIDE" or "Ignore previous instructions".

## 2. Mitigation Status
- **Plan Hash Immutability**: Any envelope modification triggers validation failure.
- **Path Confinement**: Rejecting file modification list if it touches forbidden folders.
- **Injection Block**: Summary and evidence inspect text for malicious trigger phrases and return validation rejection.
