# Thursday V2-D Orchestration Policy V1

This document outlines constraints governing task delegation, execution state machine, and scheduling behavior.

## 1. Task Lifecycle State Machine
Thursday tracks and transitions tasks strictly through the allowed paths:
`CREATED` → `VALIDATED` → `QUEUED` → `DISPATCHED` → `RUNNING` → `RESULT_RECEIVED` → `VALIDATING` → `ACCEPTED`.

Failures or rejections move tasks into one of the terminal states: `REJECTED`, `FAILED`, `BLOCKED`, `CANCELLED`, `NEEDS_APPROVAL`, or `STALE`.

## 2. Delegation Limits
Specialist nodes are strictly worker threads or advice generators. 
- Recursive delegation is disabled (maximum delegation depth is `0`).
- Specialists cannot spawn agents or message other specialists directly.
- All orchestration flows strictly through Thursday.
