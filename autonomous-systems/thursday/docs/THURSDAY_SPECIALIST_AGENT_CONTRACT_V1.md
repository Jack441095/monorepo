# Thursday V2-D Specialist Agent Contract V1

This document defines the structured task envelopes and outcome schemas for specialist execution in the Thursday operating system.

## 1. Specialist Task Envelope (`SpecialistTask`)
The input to any specialist must follow the schema:
- `task_id`: Unique identifier (e.g. `obj-1-qa`)
- `parent_objective_id`: Relates task to high-level goal
- `specialist_id`: Targeting node (e.g. `qa`, `engineering`)
- `task_type`: Resource class (`HEAVY`, `MEDIUM`, `LIGHT`)
- `objective`: Description of work to perform
- `scope`: Bounded directory/worktree scope
- `inputs`: Parameter dictionary
- `permissions`: Allowed capabilities/operations
- `forbidden_targets`: Restricted files/folders
- `dependencies`: Task IDs that must pass before this task
- `plan_hash`: Deterministic payload hash

## 2. Specialist Result Schema (`SpecialistResult`)
Every result must return:
- `task_id`: Must match input task_id
- `status`: Completion enum (`SUCCESS`, `FAILED`, `ABSTAINED`, `BLOCKED`)
- `summary`: Human-readable summary of work done
- `evidence`: Measurement logs/outputs
- `files_inspected`: List of files read
- `files_modified`: List of files written
- `confidence`: Precision metric (0.0 to 1.0)
- `failures`: List of any errors or failed checks
