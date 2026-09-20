"""Service registry entries: system domain.

Split out of thursday/registry.py (was 1,263 lines) — see docs/BACKLOG.md.
"""

from __future__ import annotations

from typing import Any

from thursday.registry.core import ServiceDef
from thursday.registry.handlers import (
    _handle_active_tasks,
    _handle_ad_readiness,
    _handle_agent_reliability,
    _handle_agent_workflow_chain,
    _handle_beta_readiness,
    _handle_brief_agent,
    _handle_calculator,
    _handle_calendar,
    _handle_create_campaign_plan,
    _handle_deployment_health,
    _handle_create_marketing_plan,
    _handle_create_task,
    _handle_current_time,
    _handle_daily_status,
    _handle_date_query,
    _handle_diagnostics,
    _handle_draft_beta_invite,
    _handle_faq,
    _handle_funding_readiness,
    _handle_known_issues,
    _handle_launch_tracker,
    _handle_macro_stats,
    _handle_marketing_readiness,
    _handle_pricing,
    _handle_reindex_docs,
    _handle_release_hygiene,
    _handle_search,
    _handle_search_docs,
    _handle_specialist_task,
    _handle_weekly_report,
    _handle_set_default_location,
    _handle_set_reminder,
    _handle_timer,
    _handle_unit_conversion,
    _handle_usage_analytics,
    _handle_user_profile,
    _handle_company_state,
    _handle_weather,
)


def _register_system_services(services: dict, api: Any) -> None:
    services["snapshot"] = ServiceDef(
        name="Business Snapshot",
        description="Full business archive with all records",
        examples=["create snapshot", "backup everything", "export business"],
        triggers=["snapshot", "backup", "archive", "export everything"],
        intents=["system"],
        action=lambda ctx, api, text: api.snapshot(),
    )

    services["list_snapshots"] = ServiceDef(
        name="List Snapshots",
        description="List available backup archives",
        examples=["list snapshots", "available backups", "show snapshots"],
        triggers=["snapshots", "available backup", "show snapshot"],
        intents=["system"],
        action=lambda ctx, api, text: api.list_snapshots(),
    )

    services["daily_maintenance"] = ServiceDef(
        name="Daily Maintenance",
        description="Run daily cron tasks",
        examples=["run daily tasks", "daily maintenance"],
        triggers=["daily maintenance", "cron daily", "run daily", "daily cron"],
        intents=["system"],
        action=lambda ctx, api, text: api.daily_maintenance(),
    )

    services["weekly_maintenance"] = ServiceDef(
        name="Weekly Maintenance",
        description="Run weekly cron tasks",
        examples=["run weekly tasks", "weekly maintenance"],
        triggers=["weekly maintenance", "cron weekly", "run weekly", "weekly cron"],
        intents=["system"],
        action=lambda ctx, api, text: api.weekly_maintenance(),
    )

    # ── Search ────────────────────────────────────────────────────────

    services["search"] = ServiceDef(
        name="Search",
        description="Full-text search across all records",
        examples=["search for Jordan", "find mixing projects", "look up invoices"],
        triggers=["search", "find", "look up", "find me", "where is",
                   "search for", "find records", "find projects", "find clients",
                   "find leads", "find invoices", "look for",
                   "lookup", "show me", "searching"],
        intents=["search"],
        action=lambda ctx, api, text: _handle_search(api, text, ctx),
    )

    services["search_docs"] = ServiceDef(
        name="Search Docs (Semantic)",
        description="Local semantic search over docs/'s real markdown files (audits, plans, launch checklists, truth sheets) — no network call",
        examples=["search docs: paddle KYC", "what do the docs say about the estate audit",
                   "what does the estate say about revenue"],
        # Multi-word triggers score len(words)**2 in score_by_triggers, so
        # these outscore "search"'s single-word triggers (internal DB
        # records, an unrelated data source) and "research_agent"'s
        # "research"/"look up topic" (subagent delegation, unrelated)
        # whenever the query is clearly about the docs corpus itself --
        # same mechanism verified live for find_customers, 2026-09-02.
        triggers=["search docs", "search the docs", "what do the docs say",
                   "what does the doc say", "search the estate", "what does the estate say",
                   "what have we said about", "search documentation",
                   "look through the docs", "check the docs for", "docs say about"],
        intents=["system"],
        action=lambda ctx, api, text: _handle_search_docs(text),
    )

    services["reindex_docs"] = ServiceDef(
        name="Reindex Docs",
        description="Rebuild the local semantic search index over docs/ (on-demand, not automatic)",
        examples=["reindex docs", "rebuild doc index"],
        triggers=["reindex docs", "rebuild doc index", "reindex the docs",
                   "update doc search index", "rebuild the doc index"],
        intents=["system"],
        action=lambda ctx, api, text: _handle_reindex_docs(text),
    )

    # ── Phase 3: AudioGen Advanced ────────────────────────────────────

    services["calendar_agenda"] = ServiceDef(
        name="Calendar & Agenda",
        description="Daily and weekly agenda with scheduled reminders",
        examples=["what's on my calendar today", "show my agenda", "what does my week look like",
                   "daily briefing", "remind me to email jordan on friday"],
        triggers=["calendar", "agenda", "schedule", "my day",
                   "what's on", "whats on", "daily briefing",
                   "what does my day look like", "what does my week look like",
                   "week ahead", "add to calendar", "add to my calendar",
                   "put on my calendar", "schedule to calendar",
                   "create calendar event", "add event"],
        intents=["calendar_scheduling"],
        action=lambda ctx, api, text: _handle_calendar(text, ctx),
        post_process=lambda ctx, resp: ctx.update({"last_report": "calendar"}),
    )

    services["reminder_set"] = ServiceDef(
        name="Set Reminder",
        description="Create a reminder with natural language date/time",
        examples=["remind me to send Jordan the stems on Friday at 3pm",
                   "set a reminder for tomorrow morning"],
        triggers=["remind", "reminder", "set a reminder", "set reminder",
                   "remind me", "create a reminder"],
        intents=["calendar_scheduling"],
        action=lambda ctx, api, text: _handle_set_reminder(text, ctx),
    )

    # ── Phase 5: Diagnostics & System Health ─────────────────────────

    services["system_health"] = ServiceDef(
        name="System Health & Diagnostics",
        description="Check all subsystems, diagnose errors, and attempt recovery",
        examples=["check all systems", "system health", "diagnostics",
                   "fix the website", "what's wrong with the server"],
        triggers=["check all systems", "system health", "health check",
                   "diagnostics", "fix the", "what's wrong",
                   "is everything working", "check everything",
                   "system check"],
        intents=["system_diagnostics"],
        action=lambda ctx, api, text: _handle_diagnostics(api, text),
    )

    services["usage_analytics"] = ServiceDef(
        name="Usage Analytics",
        description="View Thursday usage statistics and patterns",
        examples=["usage analytics", "what do I ask you most", "my usage stats"],
        triggers=["usage analytics", "usage stats", "usage data",
                   "what do i ask you", "analytics"],
        intents=["system_diagnostics"],
        action=lambda ctx, api, text: _handle_usage_analytics(),
    )

    services["agent_reliability"] = ServiceDef(
        name="Agent Reliability",
        description="Per-service helpfulness scores from collected feedback",
        examples=["agent reliability", "which agents are most reliable",
                   "how reliable is admin"],
        triggers=["agent reliability", "reliability score", "reliability report",
                   "which agent is most reliable", "how reliable"],
        intents=["system_diagnostics"],
        action=lambda ctx, api, text: _handle_agent_reliability(),
    )

    services["macro_stats"] = ServiceDef(
        name="Macro Stats",
        description="Macro fire counts, outcome breakdown, and average duration",
        examples=["macro stats", "macro analytics", "which macros fail most"],
        triggers=["macro stats", "macro analytics", "macro report",
                   "how are my macros doing", "which macros fail"],
        intents=["system_diagnostics"],
        action=lambda ctx, api, text: _handle_macro_stats(),
    )

    services["daily_status"] = ServiceDef(
        name="Daily Status",
        description="Founder-facing 'where are we today' operations status",
        examples=["where are we today", "daily status", "what should i focus on"],
        triggers=["daily status", "where are we today", "what should i focus on",
                   "ops status", "company status", "thursday what's happening",
                   "thursday whats happening"],
        intents=["business_ops"],
        action=lambda ctx, api, text: _handle_daily_status(),
    )

    services["active_tasks"] = ServiceDef(
        name="Active Tasks",
        description="List open tasks from the task ledger",
        examples=["active tasks", "what tasks are active", "list my tasks"],
        triggers=["active tasks", "what tasks are active", "list active tasks",
                   "show my tasks", "list my tasks", "current tasks"],
        intents=["business_ops"],
        action=lambda ctx, api, text: _handle_active_tasks(),
    )

    services["create_task"] = ServiceDef(
        name="Create Task",
        description="Add a task to the task ledger",
        examples=["create task marketing: draft this week's post",
                   "add task for advertising - prepare campaign brief"],
        triggers=["create task", "add task", "new task"],
        intents=["business_ops"],
        action=lambda ctx, api, text: _handle_create_task(text),
    )

    services["create_marketing_plan"] = ServiceDef(
        name="Create Marketing Plan",
        description="Structure and track a marketing plan (approval-gated before publish)",
        examples=["create marketing plan: prepare this week's Submit content"],
        triggers=["create marketing plan", "new marketing plan", "add marketing plan"],
        intents=["business_ops"],
        action=lambda ctx, api, text: _handle_create_marketing_plan(text),
    )

    services["marketing_readiness"] = ServiceDef(
        name="Marketing Readiness Audit",
        description="Deterministic audit of tracked marketing plans and tasks",
        examples=["marketing readiness", "audit marketing readiness"],
        triggers=["marketing readiness", "audit marketing", "marketing audit"],
        intents=["business_ops"],
        action=lambda ctx, api, text: _handle_marketing_readiness(),
    )

    services["create_campaign_plan"] = ServiceDef(
        name="Create Ad Campaign Plan",
        description="Structure and track an ad campaign plan (never launches or spends)",
        examples=["create campaign plan: Submit | platform: google search"],
        triggers=["create campaign plan", "new campaign plan", "create ad campaign plan"],
        intents=["business_ops"],
        action=lambda ctx, api, text: _handle_create_campaign_plan(text),
    )

    services["ad_readiness"] = ServiceDef(
        name="Ad Readiness Check",
        description="Readiness checklist before any paid advertising",
        examples=["ad readiness", "are we ready for ads", "ad readiness check"],
        triggers=["ad readiness", "advertising readiness", "ready for ads",
                   "ready to advertise"],
        intents=["business_ops"],
        action=lambda ctx, api, text: _handle_ad_readiness(),
    )

    services["funding_readiness"] = ServiceDef(
        name="Funding Readiness Report",
        description="Live-queried investment/funding readiness (no fabricated grant matching)",
        examples=["funding readiness", "are we ready for investment",
                   "funding readiness report"],
        triggers=["funding readiness", "investment readiness",
                   "ready for investment", "ready to fundraise",
                   "funding report"],
        intents=["business_ops"],
        action=lambda ctx, api, text: _handle_funding_readiness(),
    )

    services["weekly_company_report"] = ServiceDef(
        name="Weekly Company Report",
        description="Aggregate report: tasks, macros, agent reliability, "
                     "marketing/advertising/funding readiness",
        examples=["weekly company report", "make me a weekly company report"],
        triggers=["weekly company report", "company report", "full company report"],
        intents=["business_ops"],
        action=lambda ctx, api, text: _handle_weekly_report(),
    )

    services["beta_readiness"] = ServiceDef(
        name="Beta Readiness Check",
        description="Live-parsed Submit beta launch checklist status",
        examples=["beta readiness", "is submit ready for beta",
                   "what's blocking the beta"],
        triggers=["beta readiness", "submit beta status",
                   "what's blocking the beta", "whats blocking the beta",
                   "beta checklist"],
        intents=["business_ops"],
        action=lambda ctx, api, text: _handle_beta_readiness(),
    )

    services["brief_agent"] = ServiceDef(
        name="Brief Another Agent",
        description="Compose a handoff briefing for another AI agent (Codex, Gemini, etc.)",
        examples=["brief another agent on funding", "brief codex on the beta",
                   "brief another agent"],
        triggers=["brief another agent", "brief an agent", "brief codex", "brief gemini"],
        intents=["business_ops"],
        action=lambda ctx, api, text: _handle_brief_agent(text),
    )

    services["release_hygiene"] = ServiceDef(
        name="Release Hygiene Check",
        description="Real git status/branch/cleanliness across the NITE DSP monorepo",
        examples=["release hygiene", "engineering status", "are the repos clean"],
        triggers=["release hygiene", "engineering status", "repo hygiene",
                   "are the repos clean", "branch hygiene"],
        intents=["business_ops"],
        action=lambda ctx, api, text: _handle_release_hygiene(),
    )

    services["deployment_health"] = ServiceDef(
        name="Deployment Health Check",
        description="Live HTTP reachability across real production endpoints",
        examples=["deployment health", "is the site up", "is the website up"],
        triggers=["deployment health", "is the site up", "is the website up",
                   "is the api up", "infrastructure health"],
        intents=["business_ops"],
        action=lambda ctx, api, text: _handle_deployment_health(),
    )

    services["specialist_task"] = ServiceDef(
        name="Specialist Task",
        description=(
            "Ask a named specialist (commercial, support, documentation, qa, "
            "security, data) an open-ended question, grounded in real evidence "
            "where a real data source exists"
        ),
        examples=["ask the qa specialist for a readiness summary",
                   "documentation specialist: how's the launch tracker looking",
                   "ask the security specialist about our licensing"],
        triggers=["commercial specialist", "support specialist", "documentation specialist",
                   "docs specialist", "qa specialist", "quality specialist",
                   "readiness specialist", "security specialist", "data specialist",
                   "analytics specialist", "pricing specialist", "billing specialist"],
        intents=["business_ops"],
        action=lambda ctx, api, text: _handle_specialist_task(text),
    )

    services["pricing"] = ServiceDef(
        name="Pricing Summary",
        description="Live-read Audio_Too service price list",
        examples=["pricing", "pricing summary", "what do we charge"],
        triggers=["pricing summary", "our pricing", "what do we charge",
                   "service pricing"],
        intents=["business_ops"],
        action=lambda ctx, api, text: _handle_pricing(),
    )

    services["faq"] = ServiceDef(
        name="FAQ",
        description="Live-read real FAQ content, optionally filtered by topic",
        examples=["faq", "faq about pricing", "faqs on stems"],
        triggers=["faq", "faqs"],
        intents=["business_ops"],
        action=lambda ctx, api, text: _handle_faq(text),
    )

    services["known_issues"] = ServiceDef(
        name="Known Issues",
        description="Real, currently-open Gate 0 blockers from the beta checklist",
        examples=["known issues", "what's blocking support", "current known issues"],
        triggers=["known issues", "current known issues", "known bugs"],
        intents=["business_ops"],
        action=lambda ctx, api, text: _handle_known_issues(),
    )

    services["launch_tracker"] = ServiceDef(
        name="Launch Tracker Status",
        description="Live-parsed launch-gate status from the real tracker doc",
        examples=["launch tracker", "launch tracker status", "launch gates"],
        triggers=["launch tracker", "launch gates", "launch status"],
        intents=["business_ops"],
        action=lambda ctx, api, text: _handle_launch_tracker(),
    )

    services["draft_beta_invite"] = ServiceDef(
        name="Draft Beta Invite",
        description="Compose a beta-invite email draft for manual review and sending (never sends)",
        examples=["draft beta invite for jordan@example.com",
                   "draft beta invite: jordan@example.com | name: Jordan"],
        triggers=["draft beta invite", "draft beta email"],
        intents=["business_ops"],
        action=lambda ctx, api, text: _handle_draft_beta_invite(text),
    )

    # ── Phase 5: User Profile ────────────────────────────────────────

    services["user_profile_prefs"] = ServiceDef(
        name="User Profile & Preferences",
        description="View or update user preferences",
        examples=["update my preferences", "set auto speak on", "show my profile",
                   "create shortcut jj for Jordan", "my profile"],
        triggers=["my profile", "profile", "preferences", "update preference",
                   "set preference", "my preferences",
                   "shortcut", "create shortcut"],
        intents=["system"],
        action=lambda ctx, api, text: _handle_user_profile(text, ctx),
    )

    # ── Phase 3: Dashboard / System Health ────────────────────────────

    # ── Siri-style utility tools (2026-08-07) ─────────────────────────

    services["calculator"] = ServiceDef(
        name="Calculator",
        description="Arithmetic: addition, subtraction, multiplication, division, percentages",
        examples=["what's 47 times 12", "calculate 15% of 200", "square root of 144"],
        triggers=["calculate", "compute", "square root of", "percent of",
                  "plus", "minus", "times", "multiplied by", "divided by"],
        intents=["calculator"],
        action=lambda ctx, api, text: _handle_calculator(text),
    )

    services["unit_conversion"] = ServiceDef(
        name="Unit Conversion",
        description="Convert between units of length, mass, volume, and temperature",
        examples=["convert 5 km to miles", "how many miles in 5 km", "30 celsius to fahrenheit"],
        triggers=["convert", "how many", "celsius to fahrenheit", "fahrenheit to celsius",
                  "km to miles", "miles to km", "kg to lbs", "lbs to kg"],
        intents=["unit_conversion"],
        action=lambda ctx, api, text: _handle_unit_conversion(text),
    )

    services["timer"] = ServiceDef(
        name="Timer",
        description="Set, check, or cancel a countdown timer",
        examples=["set a timer for 10 minutes", "how much time is left", "cancel my timer"],
        triggers=["timer", "set a timer", "start a timer", "countdown",
                  "cancel timer", "cancel my timer", "how much time is left"],
        intents=["timer"],
        action=lambda ctx, api, text: _handle_timer(text),
    )

    services["weather"] = ServiceDef(
        name="Weather",
        description="Current weather conditions for a place",
        examples=["what's the weather in London", "weather forecast for Tokyo"],
        triggers=["weather", "forecast", "is it raining", "how hot is it", "how cold is it"],
        intents=["weather"],
        action=lambda ctx, api, text: _handle_weather(text),
    )

    services["company_state"] = ServiceDef(
        name="Company State",
        description="Grounded answers from structured NITE DSP company state: "
        "blocked/overdue work, pending approvals, agent failures, active risks",
        examples=["what's blocked", "what needs my approval", "which agents failed",
                  "what's overdue", "are we on track", "company overview"],
        triggers=[
            "what's blocked", "what is blocked", "blocking", "stuck",
            "overdue", "needs my approval", "pending approvals",
            "which agents failed", "agent status", "agents still working",
            "at risk", "on track", "company state", "company overview",
            "company status",
        ],
        intents=["company_state"],
        action=lambda ctx, api, text: _handle_company_state(text, ctx),
    )

    services["set_default_location"] = ServiceDef(
        name="Set Default Location",
        description="Save a default location for weather and location-aware queries",
        examples=["my location is London", "set my location to Tokyo"],
        triggers=["my location is", "set my location"],
        intents=["set_default_location"],
        action=lambda ctx, api, text: _handle_set_default_location(text),
    )

    services["current_time"] = ServiceDef(
        name="Current Time",
        description="Current time, locally or for a named place",
        examples=["what time is it", "what time is it in Tokyo"],
        triggers=["what time is it", "current time", "time is it"],
        intents=["current_time"],
        action=lambda ctx, api, text: _handle_current_time(text),
    )

    services["date_query"] = ServiceDef(
        name="Date Math",
        description="Today's date, or date arithmetic (in N days, until a weekday)",
        examples=["what's the date", "what day is it in 10 days", "how many days until friday"],
        triggers=["what's the date", "what is the date", "what day is it",
                  "how many days until", "how many days till"],
        intents=["date_query"],
        action=lambda ctx, api, text: _handle_date_query(text),
    )

    services["agent_workflow_chain"] = ServiceDef(
        name="Agent Workflow Chain",
        description="Chain drafting and reminder creation in one request",
        examples=["draft an email to Jordan and remind me to check next week"],
        triggers=["and remind me", "save as draft and remind", "draft an email and remind",
                  "draft email and remind"],
        intents=["agent_tasks"],
        action=lambda ctx, api, text: _handle_agent_workflow_chain(api, text, ctx),
        post_process=lambda ctx, resp: ctx.update({"last_report": "agent_workflow"}),
    )

