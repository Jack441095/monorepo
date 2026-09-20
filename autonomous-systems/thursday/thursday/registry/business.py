"""Service registry entries: business domain.

Split out of thursday/registry.py (was 1,263 lines) — see docs/BACKLOG.md.
"""

from __future__ import annotations

from typing import Any

from thursday.registry.core import ServiceDef
from thursday.registry.handlers import (
    _handle_admin_agent,
    _handle_business_insights,
    _handle_client_info,
    _handle_drafts,
    _handle_enquiries,
    _handle_expenses,
    _handle_find_customers,
    _handle_invoices,
    _handle_marketing_agent,
    _handle_profit,
    _handle_research_agent,
    _handle_sessions,
)
from thursday.phase3_handlers import (
    handle_dashboard,
    handle_portfolio,
)


def _register_business_services(services: dict, api: Any) -> None:
    services["business_status"] = ServiceDef(
        name="Business Status",
        description="Business health overview with key metrics",
        examples=["how's business", "business health", "status"],
        triggers=["status", "health", "how's business", "how is business", "how are things",
                   "business health", "overview", "dashboard", "stats",
                   "what's the status", "what is the status", "give me the status", "numbers"],
        intents=["business_ops"],
        action=lambda ctx, api, text: api.business_status(),
        post_process=lambda ctx, resp: ctx.update({"last_report": "status"}),
    )

    services["weekly_review"] = ServiceDef(
        name="Weekly Review",
        description="This week's admin and marketing review",
        examples=["weekly review", "this week summary"],
        triggers=["weekly review", "this week summary", "weekly summary"],
        intents=["business_ops"],
        action=lambda ctx, api, text: api.weekly_review(),
        post_process=lambda ctx, resp: ctx.update({"last_report": "weekly"}),
    )

    services["week_ahead"] = ServiceDef(
        name="Week Ahead",
        description="Everything due or scheduled in the next 7 days",
        examples=["what's coming up this week", "week ahead", "next week"],
        triggers=["week ahead", "next week", "weekahead",
                   "what's coming", "whats coming", "what's next", "whats next"],
        intents=["business_ops"],
        action=lambda ctx, api, text: api.week_ahead(),
        post_process=lambda ctx, resp: ctx.update({"last_report": "week_ahead"}),
    )

    services["pipeline"] = ServiceDef(
        name="Pipeline Summary",
        description="Full sales funnel with bottleneck detection",
        examples=["pipeline summary", "sales funnel", "conversion bottlenecks", "who are my leads"],
        # "leads"/"my leads" added 2026-08-03: live-tested "who are my leads"
        # and found it landing on the Client Info service instead -- that
        # service's own triggers (["client", "who is", "tell me about", ...])
        # don't match this text at all either, so it was winning purely on
        # its client_mgmt intent-confidence bonus (score_by_triggers gives 0
        # for a real word-overlap miss). Result: "Which client? Try 'tell me
        # about Jordan'." -- a disambiguation prompt for a plural, "list all
        # of them" question, not a specific-client lookup. No dedicated
        # "list leads by name" handler exists yet (a genuine, separate
        # feature gap), so this routes to the closest existing, actually
        # useful answer -- the funnel counts/bottleneck summary -- rather
        # than a confusing non-sequitur.
        triggers=["pipeline", "funnel", "sales pipeline", "conversion", "bottleneck",
                   "pipeline summary", "leads", "my leads", "who are my leads"],
        intents=["business_ops"],
        action=lambda ctx, api, text: api.pipeline_summary(),
        post_process=lambda ctx, resp: ctx.update({"last_report": "pipeline"}),
    )

    services["reminders"] = ServiceDef(
        name="Reminders",
        description="Due items, overdue items, and stale leads/projects",
        examples=["what's due", "reminders", "follow ups needed"],
        triggers=["reminder", "reminders", "what's due", "whats due",
                   "follow up", "follow up needed", "overdue", "late",
                   "past due", "due soon", "stale"],
        intents=["business_ops"],
        action=lambda ctx, api, text: api.reminders(),
        post_process=lambda ctx, resp: ctx.update({"last_report": "reminders"}),
    )

    services["monthly_report"] = ServiceDef(
        name="Monthly Reports",
        description="Monthly analytics reports",
        examples=["monthly report", "lead sources", "service demand", "invoice aging"],
        triggers=["monthly report", "monthly analytics", "lead source", "lead sources",
                   "service demand", "popular services", "invoice aging",
                   "old invoices", "unpaid invoices", "outstanding invoices",
                   "business report"],
        intents=["business_ops"],
        action=lambda ctx, api, text: api.monthly_report(),
        post_process=lambda ctx, resp: ctx.update({"last_report": "monthly"}),
    )

    services["enquiries"] = ServiceDef(
        name="Enquiries",
        description="Website enquiry management",
        examples=["enquiries", "show enquiry details", "new website enquiries"],
        triggers=["enquiry", "enquiries", "website enquiry", "pending enquiry",
                   "new enquiry", "enquiry details"],
        intents=["business_ops"],
        action=lambda ctx, api, text: _handle_enquiries(api, text, ctx),
        post_process=lambda ctx, resp: ctx.update({"last_report": "enquiries"}),
    )

    services["templates"] = ServiceDef(
        name="Templates",
        description="View email and outreach templates",
        examples=["templates", "show templates", "list templates"],
        triggers=["template", "templates"],
        intents=["business_ops"],
        action=lambda ctx, api, text: api.templates(),
    )

    # ── Client Mgmt ───────────────────────────────────────────────────

    services["client_info"] = ServiceDef(
        name="Client Info",
        description="Client summary, history, and timeline",
        examples=["tell me about Jordan", "client history for Sarah", "who is Test User"],
        triggers=["client", "who is", "tell me about", "about client",
                   "client info", "client details", "client summary",
                   "client history", "client timeline"],
        intents=["client_mgmt"],
        action=lambda ctx, api, text: _handle_client_info(api, text, ctx),
        post_process=lambda ctx, resp: ctx.update({"last_report": "client_info"}),
    )

    services["sessions"] = ServiceDef(
        name="Sessions",
        description="Session list and scheduling",
        examples=["what sessions are coming up", "show my sessions", "schedule a session with Sarah",
                   "book jordan in tomorrow"],
        triggers=["sessions", "session", "session list", "upcoming session",
                   "show session", "my sessions", "list sessions",
                   "sessions coming", "schedule session", "book session",
                   # Informal booking ("book jordan in tomorrow") has no "session"
                   # noun and resolves any pronoun to a name before this scoring
                   # runs, so a bare "book" trigger is needed to catch it —
                   # _handle_sessions already treats "book" as a schedule action.
                   "book"],
        # calendar_scheduling included so an informal "book <name> in <time>" wins
        # the intent-score tie against the generic agenda/calendar view, instead
        # of falling through to a non-actionable "here's your agenda" response.
        intents=["client_mgmt", "calendar_scheduling"],
        action=lambda ctx, api, text: _handle_sessions(api, text),
    )

    # ── Financial ─────────────────────────────────────────────────────

    services["expenses"] = ServiceDef(
        name="Expenses",
        description="Expense tracking and categories",
        examples=["what did I spend money on", "add expense studio rent £500", "expense categories"],
        triggers=["expense", "expenses", "spending", "spent", "spend",
                   "money spent", "where did my money go", "what did i spend",
                   "add expense", "record expense", "log expense"],
        intents=["financial"],
        action=lambda ctx, api, text: _handle_expenses(api, text, ctx),
    )

    services["profit"] = ServiceDef(
        name="Profit Report",
        description="Monthly profit & loss",
        examples=["profit report", "how much profit did I make", "P&L for 2026"],
        triggers=["profit", "profit report", "pnl", "p&l", "how much did i make",
                   "revenue vs expenses", "earnings", "revenue", "income"],
        intents=["financial"],
        action=lambda ctx, api, text: _handle_profit(api, text, ctx),
        post_process=lambda ctx, resp: ctx.update({"last_report": "profit"}),
    )

    services["invoices"] = ServiceDef(
        name="Invoices",
        description="Invoice listing and PDF generation",
        examples=["invoices", "invoice PDF abc12345", "show me invoices"],
        triggers=["invoice", "invoices", "invoice list", "show invoices",
                   "invoice pdf", "generate invoice"],
        intents=["financial"],
        action=lambda ctx, api, text: _handle_invoices(api, text, ctx),
    )

    services["drafts"] = ServiceDef(
        name="Drafts",
        description="Pending drafts, send, approve",
        examples=["pending drafts", "send draft abc12345", "send all approved"],
        triggers=["draft", "drafts", "pending draft", "unsent", "send draft",
                   "send approved", "what drafts", "draft pending"],
        intents=["financial"],
        action=lambda ctx, api, text: _handle_drafts(api, text, ctx),
    )

    # ── Production Q&A (KENN) ─────────────────────────────────────────

    services["admin_agent"] = ServiceDef(
        name="Admin Agent",
        description="Admin tasks: emails, invoices, projects, clients",
        examples=["draft email to Jordan about the mix", "create invoice for Sarah",
                   "new project for Test User"],
        triggers=["draft email", "write email", "compose email",
                   "draft invoice", "create invoice", "make invoice",
                   "send invoice", "email invoice",
                   "new project", "create project", "add project",
                   "new client", "create client", "add client", "add customer",
                   "adam", "ask adam", "tell adam", "talk to adam", "admin", "admin agent"],
        intents=["agent_tasks"],
        action=lambda ctx, api, text: _handle_admin_agent(api, text),
    )

    services["marketing_agent"] = ServiceDef(
        name="Marketing Agent",
        description="Marketing tasks: outreach, social posts, leads, campaigns",
        examples=["write outreach to a new artist", "draft social post about mixing services",
                   "add lead Jordan"],
        triggers=["outreach", "draft outreach", "write outreach", "cold email",
                   "social post", "draft post", "social media", "instagram",
                   "new lead", "add lead", "create lead", "marketing campaign",
                   "marketing", "ask marketing", "marketing agent", "campaigns",
                   "mark", "ask mark", "tell mark", "talk to mark"],
        intents=["agent_tasks"],
        action=lambda ctx, api, text: _handle_marketing_agent(api, text),
    )

    services["find_customers"] = ServiceDef(
        name="Find Potential Customers",
        description="Real web search (Tavily) for prospecting, seeded with NITE Submit's documented target audience",
        examples=["find customers for submit", "look for potential customers",
                   "help me find customers", "find potential customers"],
        # Multi-word triggers score len(words)**2 in score_by_triggers, so
        # these outscore the generic "search"/"research_agent" services'
        # single/double-word triggers ("find", "look for") whenever the
        # word "customer(s)" is actually present -- found live 2026-09-02
        # when "look for potential customers" silently landed on the
        # internal-records "search" service instead (zero results, since
        # there's no internal lead data to search -- this is genuinely a
        # different, real-web-search capability, not a duplicate).
        triggers=["find customers", "find potential customers", "find more customers",
                   "look for customers", "look for potential customers",
                   "get more customers", "get new customers", "new customers",
                   "grow customer base", "customer acquisition", "prospecting",
                   "find prospects", "potential customers"],
        intents=["business_ops"],
        action=lambda ctx, api, text: _handle_find_customers(text),
    )

    services["research_agent"] = ServiceDef(
        name="Research Agent",
        description="Research plans and source suggestions",
        examples=["research compression techniques", "research plan for vocal mixing"],
        triggers=["research", "research plan", "research topic",
                   "suggest sources", "find sources", "look up topic",
                   "research into", "research about", "research for",
                   "techniques for", "guide to", "how does",
                   "ask research", "research agent",
                   "rhianna", "ask rhianna", "tell rhianna", "talk to rhianna"],
        intents=["agent_tasks"],
        action=lambda ctx, api, text: _handle_research_agent(api, text),
    )

    # ── System ────────────────────────────────────────────────────────

    services["portfolio"] = ServiceDef(
        name="Portfolio",
        description="Portfolio audio listing, publishing, and discovery",
        examples=["list portfolio audio", "show portfolio", "publish audio",
                   "discover new audio files", "what's in my portfolio"],
        triggers=["portfolio", "my portfolio", "audio portfolio", "show portfolio",
                   "list audio", "published audio", "portfolio audio",
                   "publish audio", "upload to portfolio", "add to portfolio",
                   "discover audio", "new audio files", "find new audio"],
        intents=["system"],
        action=lambda ctx, api, text: handle_portfolio(api, text),
        post_process=lambda ctx, resp: ctx.update({"last_report": "portfolio"}),
    )

    # ── Phase 5: Calendar & Scheduling ───────────────────────────────

    services["dashboard"] = ServiceDef(
        name="Dashboard & System Health",
        description="Web dashboard health, KENN notes, and subsystem status",
        examples=["dashboard health", "system status", "is everything working",
                   "check dashboard", "show KENN notes", "list improvements",
                   "rebuild KENN index"],
        triggers=["dashboard health", "dashboard status", "system health",
                   "system status", "health check", "check dashboard",
                   "is everything working", "are all systems go",
                   "kenn notes", "kenn index", "rebuild index",
                   "list improvements", "kenn improvements",
                   "web health", "system check", "check all systems",
                   "all systems", "how is the system", "subsystem status",
                   "kenn training notes", "kenn improvement",
                   "approve note", "read note", "show note"],
        intents=["system"],
        action=lambda ctx, api, text: handle_dashboard(api, text),
        post_process=lambda ctx, resp: ctx.update({"last_report": "dashboard"}),
    )

    # ── Phase 4: context-aware knowledge and storage operations ─────

    services["business_insights"] = ServiceDef(
        name="Business Insights",
        description="Answer filtered profitability, client activity, and pipeline questions",
        examples=["what's the most profitable service this year?", "which clients haven't booked in 6 months?"],
        triggers=["most profitable service", "clients haven't booked", "clients have not booked",
                  "only the hot leads", "hot leads only", "pipeline hot leads"],
        intents=["business_ops", "financial", "client_mgmt"],
        action=lambda ctx, api, text: _handle_business_insights(text, ctx),
        post_process=lambda ctx, resp: ctx.update({"last_report": "business_insights"}),
    )

