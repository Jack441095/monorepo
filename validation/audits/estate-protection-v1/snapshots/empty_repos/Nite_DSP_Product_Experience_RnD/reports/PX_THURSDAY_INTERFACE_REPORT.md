# PX-G - Thursday Company Interface Report

## Status

**INCONCLUSIVE - CONTINUE R&D**

Thursday has the ingredients for a useful company interface, but the active branch's daily-brief integration test is not green. This track is deliberately read-only because `Audio_Too` has another active writer.

## Required Closeout

### COMPANY INTERFACE

The current architecture has a daily brief composer, scheduling and business adapters, agent receipts, a registry/intent layer, confirmation handling, a menu-bar application, a HUD controller, voice input/output modules, and a shared AI Platform company capability layer. The right product boundary is an orchestrator over structured company state, not a second owner of product DSP semantics.

### MORNING BRIEF

`thursday.daily_brief.compose_daily_brief` gathers business status, today's agenda, week ahead, recent agent receipts, and scheduler state. It degrades each section independently and renders a concise markdown brief. The platform's `company.brief.daily` capability provides the stronger typed direction: facts first, missing state stated honestly, and no invented numbers.

Recommended brief order: important changes, today's obligations, blockers, decisions/approvals, risks, then optional detail. Do not dump all metrics.

### PROACTIVITY

Use four classes:

- Immediate: safety, blocked release, expiring approval, or a user-requested action result.
- Next brief: meaningful overnight changes and due work.
- Weekly review: trends, repeated friction, and non-urgent opportunities.
- Do not surface: low-confidence observations, duplicate telemetry, and work with no decision attached.

The programme did not run a real alert-fatigue study. This remains a human-test item.

### APPROVAL UX

The AI Platform correctly separates `company.approvals.decide` from execution. The capability records an owner decision and never executes an external action. The Thursday package also has signed, expiring confirmation tokens and idempotent action receipts. A production approval card should show action, why, effect, risk, reversibility, evidence, and explicit Approve/Reject controls. High-risk actions must not be casual chat confirmations.

### VOICE

Voice input and output are implemented as optional modules, including local STT paths and a persistent worker attempt. The appropriate near-term role is push-to-talk for brief capture and command, followed by a visual handoff for evidence and approval. Always-listening behavior is not part of this programme.

### RECOMMENDED APPLICATION FORM

A menu-bar entry point with a concise morning brief, command palette for direct requests, and a visual approval/detail surface. A full dashboard can exist as a secondary view, but chat alone should not be the approval or evidence surface.

## Observed Test Gap

The active `Audio_Too` branch's `tests/thursday/test_thursday_daily_brief.py` produced **8 passed, 2 failed** in the read-only run:

- The calendar handler did not return the composed `# Daily Brief` output.
- The test's expected `handlers.daily_brief` patch target was not present.

These failures belong to the active branch and were not changed by this programme.

## Biggest Gap to a Jarvis-Like Experience

The biggest gap is not voice. It is a reliable, prioritised company state model that connects a brief to a decision, owner approval, and evidence without surfacing every subsystem detail.

## Promotion Decision

Continue R&D until the active daily-brief integration is repaired and the morning-brief priority order is tested with the owner. Promote the approval-card contract and typed company capability boundary. Do not expand autonomous execution.

## Artifacts

- [EXPERIMENT_REGISTRY.json](../controller/EXPERIMENT_REGISTRY.json)
- [WORKER_MATRIX.md](../controller/WORKER_MATRIX.md)
- [AI Platform company capability documentation](../../Nite_DSP/Nite_DSP_AI_Platform/docs/THURSDAY_COMPANY_CAPABILITIES.md)
