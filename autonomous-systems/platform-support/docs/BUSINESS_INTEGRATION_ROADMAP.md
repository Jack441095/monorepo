# Business Integration Roadmap (DESIGN ONLY — no writes implemented)

All write connectors require the approval pipeline: ApprovalRequest →
owner decision (company.approvals.decide) → separate execution capability.
Read connectors still register as capabilities with explicit privacy classes.

| Connector | Read (Phase 5+) | Write (later, approval-gated) | Risk on write |
|---|---|---|---|
| Local Git | branch/sha/dirty/test snapshots → EngineeringStatus | none ever from platform | n/a |
| GitHub | repo status, CI results, releases | issues/comments later; merges need approval | HIGH |
| Gmail | important inbox, unanswered threads | draft always; send requires approval | HIGH/EXTERNAL |
| Calendar | today's meetings, deadlines | create/move/cancel with approval | MEDIUM/EXTERNAL |
| Website analytics | traffic/conversion summaries | none | n/a |
| Commerce/sales | order/revenue reads | none | n/a |
| Finance/invoices | invoice status reads | prepare drafts; sending requires approval | CRITICAL |

Rules: financial truth lives in accounting systems; the LLM never invents
records; every connector degrades gracefully when offline; each connector is
an adapter behind the capability registry — no product or vendor SDK in core.
