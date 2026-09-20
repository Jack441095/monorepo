# PX-D - Cross-Product Intelligence Report

## Status

**PASS WITH LIMITATIONS**

Typed evidence exchange is promising; live audio capability registration is not present in the audited platform state. Product boundaries remain clear when KENN owns engineering interpretation, SLO owns sample intelligence, and Thursday owns company orchestration.

## Current Contract Basis

The AI Platform provides `AgentRequest`, `AgentResult`, `CapabilityDefinition`, permissions, privacy classes, evidence packets, a capability registry, and a local Unix-domain runtime. The observed registered capabilities are nine `company.*` capabilities, including daily brief, company state queries, and approval decision recording.

The platform documentation and tests use `audio.mix.analyze` as a capability example, and a Phase 3 report describes an audio analysis adapter, but no live SLO sample capability registration was found in the current registry audit. `audio.sample.find_similar`, `audio.sample.find_complement`, and `audio.sample.evaluate_fit` remain candidates.

## Required Closeout

### KENN -> SLO

The best candidate is **Find Complement**. KENN provides a measured issue reference, frequency hole or occupancy evidence, transient profile, pitch class, and BPM. SLO returns ranked candidates and keeps sample retrieval and audition product-owned. The handoff should be a reference plus features, not a second KENN sample browser.

The isolated contract probe accepted this evidence-only payload and rejected a payload containing `audio_bytes`.

### SLO -> KENN

SLO can provide a sample reference and feature summary: spectral centroid, crest factor, duration, stereo width, and provenance. KENN evaluates fit against a mix-context reference. Raw private audio stays local unless an explicitly approved local operation needs it.

### THURSDAY -> PRODUCTS

Thursday should call typed product capabilities and summarise results; it should not own DSP semantics or invent audio measurements. Existing company capabilities are the model for company orchestration. A future Thursday request should resolve to a product capability, show its evidence/artifact reference, and hand the user to SLO or KENN for action.

### SHARED CONTRACTS

Reuse the existing `nite_ai` request/result and capability-definition shapes. Candidate IDs should be reviewed and registered by the platform owner rather than creating a parallel contract system. Use additive schema evolution and preserve trace IDs, privacy class, and artifact references.

### PRIVACY

Cross the boundary with metrics, features, references, evidence, and artifact IDs. Reject full projects, project paths, credentials, and raw audio blobs in ordinary inter-product payloads. The probe explicitly enforced that boundary.

## Best Cross-Product Workflow

**KENN identifies a measured kick problem -> SLO finds complementary candidates -> user auditions and chooses -> KENN evaluates the chosen candidate against the same issue -> user decides.**

This workflow has a real user intent and preserves both product boundaries. It remains a prototype until adapter availability, ranking quality, and human usefulness are measured.

## Promotion Decision

Promote the contract and privacy review to an adapter design review. Do not register new audio capabilities or mutate production products from this programme. Drop forced ecosystem dashboards and any workflow that makes Thursday the owner of SLO or KENN semantics.

## Artifact

- [cross_product_contract_probe.py](../experiments/cross_product_contract_probe.py)
- [cross_product_results.json](../experiments/cross_product_results.json)
- [EXPERIMENT_REGISTRY.json](../controller/EXPERIMENT_REGISTRY.json)
