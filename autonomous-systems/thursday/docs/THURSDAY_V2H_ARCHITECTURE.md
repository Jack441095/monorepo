# Thursday V2-H Architecture — Controlled Autonomous Engineering Loop

Branch: `thursday/v2h-autonomous-engineering` · Baseline: `d4f5934`

V2-H closes the loop from *observation* to *integrated, reconciled change*
while keeping every trust-sensitive decision deterministic and gated.

## Loop stages

```
OBSERVE   → OpportunityDetector.scan()          deterministic provenance
DECIDE    → value gate + risk classification     NO_ACTION is a first-class outcome
PROPOSE   → seal_proposal()                      frozen, hashed work proposal
PLAN      → seal_execution_plan()                task DAG, mutation boundaries
ROUTE     → SpecialistRegistry.route_task()
SCHEDULE  → heavy-task budget (limit = 2)
EXECUTE   → isolated sandbox task                V2-F isolation
COLLECT   → EvidenceCollector.collect()          machine receipts only
QA        → IndependentQA.validate()             independent veto authority
SECURITY  → SecurityReviewer.review()            independent veto authority
APPROVE   → WAITING_FOR_APPROVAL                 durable first-class state
APPLY     → SharedExecutor (V2-G)                token verify+consume, TOCTOU, lease
POST-QA   → PostIntegrationValidator             independent of pre-integration QA
RECONCILE → StateReconciler                      Thursday-owned derived state only
BRIEF     → OwnerBriefGenerator                  no unsupported claims
```

## Modules

| Module | Responsibility |
|---|---|
| `engineering_contracts.py` | Frozen, hashed data types: proposals, plans, evidence, lineage |
| `opportunity_detector.py` | Deterministic scan; anti-busywork policy; provenance required |
| `autonomous_controller.py` | Top-level coordinator; delegates, never duplicates |
| `independent_qa.py` | Adversarial falsification; test-integrity violations; veto |
| `security_reviewer.py` | Hard veto on policy-critical changes; cannot be overruled |
| `evidence_collector.py` | Machine-verified evidence; secret rejection; scope-drift detection |
| `post_integration_validator.py` | Independent post-merge QA; triggers FAILED_SAFE on failure |
| `state_reconciler.py` | Closed-loop dependency reasoning; never auto-executes unblocked work |
| `owner_brief_generator.py` | Approval packets and status briefs sourced only from verified facts |
| `diagnostic_store.py` | Bounded failure diagnostics (age/count/size pruned) |

## Safety invariants preserved

* LLMs never control permissions, approval verification, SHA verification,
  lease ownership, integration eligibility, security veto, or rollback.
* All trust-sensitive fields are deterministic and hashed at seal time.
* Lineage is append-only; closing twice does not change state.
* Foreign projects are structurally out of scope (`StateReconciler.FOREIGN_PROJECT_PREFIXES`).
* Shared mutation still requires the full V2-G chain: IntegrationPlan,
  ApprovalToken (single-use, digest+SHA bound), exclusive lease, TOCTOU
  re-checks, post-integration QA, deterministic rollback.
