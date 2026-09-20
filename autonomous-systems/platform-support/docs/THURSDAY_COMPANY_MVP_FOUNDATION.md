# Thursday Company MVP Foundation

How Thursday will answer "What's happening with NITE DSP today?" using the
platform without losing product ownership:

```
CompanyStore (SQLite) ──► assemble_daily_brief() ──► DailyBriefData
                        ► assemble_weekly_review() ► WeeklyReviewData
                                   │
                     Thursday adapter + personality renders the answer
```

- Priority selection is deterministic and inspectable: overdue → due-today →
  high-priority backlog; blockers and at-risk goals surfaced separately.
  An LLM may phrase the brief later but never chooses priorities.
- Capability contracts reserved for Thursday:
  `company.brief.daily`, `company.review.weekly` (WRITE-free, READ-level;
  presentation/orchestration stays Thursday-owned).
- Write-oriented company capabilities must declare WRITE permission +
  appropriate ActionRisk per nite_ai.approvals before any agent-driven writes.
- Synthetic NITE DSP fixture (SLO release blocker / AI Platform integration /
  website review) proves the flow in tests — no real business data required.
