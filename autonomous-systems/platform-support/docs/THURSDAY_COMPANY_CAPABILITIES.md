# Thursday Company Capabilities

Registered via `register_company_capabilities(adapter, registry, store)`.

| Capability | Risk | Permissions | Output |
|---|---|---|---|
| company.brief.daily | LOW | read | DailyBriefData |
| company.review.weekly | LOW | read | WeeklyReviewData |
| company.goals.list | LOW | read | goal list + honest empty-state note |
| company.tasks.list | LOW | read | task list + honest empty-state note |
| company.risks.list | LOW | read | active risks |
| company.decisions.pending | LOW | read | open decisions |
| company.agents.status | LOW | read | recent agent runs + counts |
| company.approvals.pending | LOW | read | approvals awaiting owner |
| company.approvals.decide | HIGH | read+write | approval record (internal state ONLY) |

## Mandatory separation

`company.approvals.decide` records an owner decision. It never executes the
underlying external action. Execution capabilities must be defined separately,
carry EXTERNAL/DESTRUCTIVE action levels, and consume an *approved* approval
record — this separation is a permanent architecture rule.

## Grounding rules for any NL layer

DailyBriefData / WeeklyReviewData are the only sources of truth. Missing data
must be reported as missing. Confidence vocabulary: measured / observed /
derived / reasoned (never invented numbers).
