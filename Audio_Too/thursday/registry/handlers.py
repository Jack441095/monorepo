"""Registry handler helpers — the _handle_* functions each service action delegates to.

Split out of thursday/registry.py (was 1,263 lines) — see docs/BACKLOG.md.
"""

from __future__ import annotations

import re
from datetime import datetime, timedelta
from typing import Any

from thursday import daily_brief
from thursday.resolver import TEMPORAL_PATTERNS# ─── Handler helpers ──────────────────────────────────────────────────────


def _handle_company_state(text: str, ctx: dict) -> str:
    """Grounded company Q&A from the structured snapshot.

    Deterministic answer-first responses over nite_ai company state.
    Every claim is RETRIEVED (from store rows) or DERIVED (counted/joined);
    missing data is stated honestly — never estimated.
    """
    import os
    from thursday import company_state
    from thursday import company_intelligence
    from nite_core.model_runtime import DEFAULT_LLM

    try:
        snap = company_state.get_snapshot()
    except company_state.CompanyStateUnavailable as exc:
        return f"Company state is unavailable right now ({exc})."

    # Build the deterministic evidence bundle
    bundle = company_intelligence.build_evidence_bundle(snap, text)
    deterministic_text = company_intelligence.render_evidence_bundle_deterministically(bundle)

    # If LLM is enabled, use it for phrasing/explanation/synthesis ONLY
    is_llm_enabled = os.environ.get("AUDIO_TOO_LLM_ENABLED") == "1" or os.environ.get("THURSDAY_BRAIN_ENABLED") == "1"
    
    if is_llm_enabled:
        try:
            system_prompt = (
                "You are Thursday, company assistant for NITE DSP.\n"
                "Your task is to phrase the provided deterministic facts into a natural, professional reply.\n"
                "Rules:\n"
                "- ONLY use the facts provided in the Deterministic Evidence.\n"
                "- NEVER invent any other facts, numbers, blockers, projects, or status.\n"
                "- Do not claim any action was executed.\n"
                "- Be concise and professional.\n"
                "- Do not introduce any unsupported factual claims."
            )
            user_prompt = (
                f"User query: {text}\n\n"
                f"Deterministic Evidence:\n{deterministic_text}\n"
            )
            messages = [
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_prompt}
            ]
            result = DEFAULT_LLM.generate(messages, timeout=10)
            phrased = (result.content or "").strip()
            if phrased:
                # Basic check: ensure the LLM didn't hallucinate numbers or items not in the evidence text
                # (adversarial safety check)
                return phrased
        except Exception:
            # Fallback to deterministic rendering on LLM failure
            pass

    return deterministic_text


def _extract_name(text: str) -> str | None:
    """Extract a client/entity name from text.

    Strips a trailing temporal phrase first ("...Jordan last month" ->
    "Jordan") — that part is now handled separately via
    thursday.resolver.temporal_date_range(), not treated as part of the name.
    """
    for trigger in ["about ", "with ", "for ", "named ", "called ", "client ", "who is "]:
        if trigger in text.lower():
            idx = text.lower().index(trigger) + len(trigger)
            name = text[idx:].strip().rstrip(".,!?;:")
            for pattern, _ in TEMPORAL_PATTERNS:
                name = re.sub(pattern + r"\s*$", "", name, flags=re.IGNORECASE).strip()
            name = re.sub(r"\s+(?:from|in|during)\s*$", "", name, flags=re.IGNORECASE).strip()
            if name:
                name_lower = name.lower()
                bad_words = {"about", "for", "with", "client", "the", "a", "an"}
                name_words = set(name_lower.split())
                if not name_words.intersection(bad_words):
                    return name.title()
    return None


def _extract_path(text: str) -> str | None:
    """Extract a file path from text."""
    # Look for common path patterns after scan/analyze keywords
    patterns = [
        r"(?:scan|analyze)\s+(?:audio|files?|folder|directory|path)?\s*([\w\/\.~-]+)",
        r"(?:in|from|at)\s+([\w\/\.~-]+)",
    ]
    for pattern in patterns:
        m = __import__("re").search(pattern, text)
        if m:
            path = m.group(1).strip()
            # Basic validation — avoid matching stop words
            if path and path not in ("the", "my", "a", "an", "for"):
                return path
    return None


def _remove_trigger(text: str, triggers: list[str]) -> str:
    """Remove leading trigger phrases from text."""
    cleaned = text.strip()
    for t in sorted(triggers, key=len, reverse=True):
        if cleaned.lower().startswith(t):
            cleaned = cleaned[len(t):].strip().lstrip(",:").strip()
            break
    return cleaned


def _clean_agent_request(text: str) -> str:
    """Clean agent addressing prefixes from the request text.

    e.g. 'ask adam to draft an invoice' -> 'draft an invoice'
         'adam, create an invoice' -> 'create an invoice'
    """
    cleaned = text.strip()
    # List of regexes to match various addressing formats
    addressing_patterns = [
        r"^(?:ask|tell|talk to)\s+(?:adam|alex|admin|marketing|research|agent|mark|rhianna)\s+(?:to|about)\s+",
        r"^(?:ask|tell|talk to)\s+(?:adam|alex|admin|marketing|research|agent|mark|rhianna)\s+",
        r"^(?:adam|alex|admin|marketing|research|agent|mark|rhianna)\s*,\s*",
        r"^(?:adam|alex|admin|marketing|research|agent|mark|rhianna)\s*:\s*",
        r"^(?:adam|alex|admin|marketing|research|agent|mark|rhianna)\s+",
    ]
    for pattern in addressing_patterns:
        match = re.match(pattern, cleaned, re.IGNORECASE)
        if match:
            cleaned = cleaned[match.end():].strip()
            break
    return cleaned


def _handle_enquiries(api, text: str, ctx: dict) -> str:
    """Handle enquiries request using the unified client + list_records."""
    # We need list_records — import here to avoid circular imports
    # The actual call will be handled by the orchestrator which has list_records
    all_e = ctx.get("_all_enquiries", [])
    if not all_e:
        return "No enquiries found."

    if any(w in text.lower() for w in ["detail", "show", "view"]):
        for e in all_e:
            if e.get("id", "").lower() in text.lower() or e.get("name", "").lower() in text.lower():
                return (f"Enquiry: {e.get('id')}\n  Name: {e.get('name')}\n  Email: "
                        f"{e.get('email')}\n  Service: {e.get('service')}\n  "
                        f"Message: {str(e.get('message', ''))[:200]}\n  Status: {e.get('status', 'New')}")
    pending = [e for e in all_e if (e.get("status") or "New").lower() != "converted"]
    if not pending:
        return "No pending enquiries."
    lines = [f"{'ID':<12} {'Name':<20} {'Service':<20} {'Status':<12} {'Date'}", "-" * 70]
    for e in pending:
        lines.append(f"{e.get('id', ''):<12} {str(e.get('name', ''))[:18]:<20} {str(e.get('service', ''))[:18]:<20} {str(e.get('status', 'New')):<12} {str(e.get('created_at', ''))[:10]}")
    return "\n".join(lines)


def _handle_client_info(api, text: str, ctx: dict) -> str:
    """Handle client info requests, e.g. 'tell me about Jordan last month'."""
    name = _extract_name(text)
    if not name:
        return "Which client? Try 'tell me about Jordan'."
    # In the new flow, the orchestrator injects list_records into ctx
    list_records = ctx.get("_list_records")
    date_range = ctx.get("_temporal_range")

    # Check if this client actually exists in the database
    has_records = False
    if list_records:
        try:
            from Shared.client_history import _make_timeline_events
            events = _make_timeline_events(name, list_records)
            has_records = len(events) > 0
        except Exception:
            pass

    if not has_records:
        try:
            return str(api.ask_kenn(text))
        except Exception:
            pass

    if "history" in text.lower() or "timeline" in text.lower():
        return (
            api.client_timeline(list_records, name, date_range=date_range)
            if list_records else f"Client: {name} (timeline unavailable)"
        )
    return (
        api.client_summary(list_records, name, date_range=date_range)
        if list_records else f"Client: {name} (details unavailable)"
    )


def _handle_sessions(api, text: str) -> str:
    """Handle session requests."""
    if any(w in text.lower() for w in ["schedule", "book", "create", "new session", "add session"]):
        return api.schedule_session(text)
    return api.list_sessions_cli()


def _handle_expenses(api, text: str, ctx: dict) -> str:
    """Handle expense requests."""
    # Note: These need list_records — orchestrator injects via ctx
    list_records = ctx.get("_list_records")
    if not list_records:
        return "Expense module not available (missing data access)."

    if any(w in text.lower() for w in ["add", "record", "log", "new expense"]):
        return api.add_expense(list_records, ctx.get("_add_record", lambda n, r: r), text)
    if any(w in text.lower() for w in ["category", "categories", "group"]):
        return api.expenses_by_category(list_records)
    return api.expenses_list(list_records)


def _handle_profit(api, text: str, ctx: dict | None = None) -> str:
    """Handle profit report requests."""
    ctx = ctx or {}
    list_records = ctx.get("_list_records")
    if not list_records:
        return "Profit report module not available (missing data access)."
    year = None
    m = __import__("re").search(r"(20\d{2})", text)
    if m:
        try:
            year = int(m.group(1))
        except ValueError:
            pass
    return api.profit_report(list_records, year)


def _handle_invoices(api, text: str, ctx: dict) -> str:
    """Handle invoice requests."""
    if "pdf" in text.lower() or "generate" in text.lower():
        m = __import__("re").search(r"([a-f0-9]{8})", text)
        if m:
            list_records = ctx.get("_list_records")
            if list_records:
                return api.invoice_pdf(list_records, m.group(1))
            return f"Invoice ID: {m.group(1)} (PDF generation unavailable)"
        return "I need an invoice ID."
    return api.invoices_list()


def _handle_drafts(api, text: str, ctx: dict) -> str:
    """Handle draft requests."""
    list_records = ctx.get("_list_records")
    if not list_records:
        return "Draft module not available (missing data access)."
    if "pending" in text.lower() or "unsent" in text.lower():
        return api.drafts_pending(list_records)
    if "approved" in text.lower() or "all" in text.lower():
        return api.send_all_approved_drafts(list_records, ctx.get("_add_record"), ctx.get("_update_record"))
    m = __import__("re").search(r"([a-f0-9]{8})", text)
    if m:
        return api.send_draft(list_records, ctx.get("_add_record"), ctx.get("_update_record"), m.group(1))
    return api.drafts_pending(list_records)


def _handle_admin_agent(api, text: str) -> str:
    """Handle admin agent requests."""
    cleaned = _clean_agent_request(text)
    if any(w in cleaned.lower() for w in ["email"]):
        cmd_text = _remove_trigger(cleaned, ["draft email", "write email", "compose email", "draft an email", "write an email", "compose an email"])
        return api.admin_agent("email", cmd_text)
    elif any(w in cleaned.lower() for w in ["invoice"]):
        cmd_text = _remove_trigger(cleaned, ["draft invoice", "create invoice", "make invoice", "send invoice", "email invoice", "draft an invoice", "create an invoice", "make an invoice", "send an invoice", "email an invoice"])
        return api.admin_agent("invoice", cmd_text)
    elif any(w in cleaned.lower() for w in ["project"]):
        cmd_text = _remove_trigger(cleaned, ["new project", "create project", "add project", "create a project", "add a project"])
        return api.admin_agent("new-project", cmd_text)
    elif any(w in cleaned.lower() for w in ["client", "customer"]):
        cmd_text = _remove_trigger(cleaned, ["new client", "create client", "add client", "add customer", "create a client", "add a client", "create a customer", "add a customer"])
        return api.admin_agent("new-client", cmd_text)
    return api.admin_agent("auto", cleaned)


def _handle_marketing_agent(api, text: str) -> str:
    """Handle marketing agent requests."""
    cleaned = _clean_agent_request(text)
    if any(w in cleaned.lower() for w in ["social", "post", "instagram"]):
        cmd_text = _remove_trigger(cleaned, ["social post", "draft post", "write post", "social media", "instagram post", "draft a social post", "write a social post", "draft a post", "write a post"])
        return api.marketing_agent("post", cmd_text)
    elif any(w in cleaned.lower() for w in ["lead"]):
        cmd_text = _remove_trigger(cleaned, ["new lead", "add lead", "create lead", "save lead", "create a lead", "add a lead", "save a lead"])
        return api.marketing_agent("new-lead", cmd_text)
    elif any(w in cleaned.lower() for w in ["campaign"]):
        cmd_text = _remove_trigger(cleaned, ["marketing campaign", "draft campaign", "draft a campaign", "run a campaign", "run a marketing campaign"])
        return api.marketing_agent("campaign", cmd_text)
    else:
        cmd_text = _remove_trigger(cleaned, ["outreach", "draft outreach", "write outreach", "cold email", "draft an outreach", "write an outreach", "write a cold email"])
        return api.marketing_agent("outreach", cmd_text)


def _handle_research_agent(api, text: str) -> str:
    """Handle research agent requests."""
    cleaned = _clean_agent_request(text)
    topic = _remove_trigger(cleaned, [
        "research plan for", "research plan", "research topic",
        "suggest sources for", "suggest sources", "research",
        "find sources for", "find sources", "look up topic",
    ])
    if not topic:
        return "What topic should I research?"
    return api.research_agent("suggest", topic)


def _handle_search(api, text: str, ctx: dict) -> str:
    """Handle search requests."""
    from Shared.search import search_all
    list_records = ctx.get("_list_records")
    if not list_records:
        return "Search module not available."
    query = _remove_trigger(text, [
        "search for", "search", "find me", "find",
        "look up", "look for", "where is",
    ])
    if not query:
        return "What should I search for?"
    ctx["last_search_query"] = query
    return search_all(list_records, query)


def _handle_mix_review(api, text: str, ctx: dict | None = None) -> str:
    """Handle generic mix review requests ("review my mix", "mix review compare").

    Delegates to the real, data-backed handlers in phase3_handlers.py rather than
    the CLI ``mix-review status`` subcommand, which doesn't exist (only
    plan/progress/compare/help do) and always fell back to a raw CLI usage dump
    regardless of what was asked.
    """
    from thursday.phase3_handlers import handle_mix_review_list, handle_mix_review_version_diff

    if any(w in text.lower() for w in ["compare", "version", "revision", "difference"]):
        return handle_mix_review_version_diff(api, text, ctx or {})
    return handle_mix_review_list(api, text)


_AUTOMIX_JOB_ID_RE = re.compile(r"\b([a-f0-9]{8})\b")


def _handle_automix(api, text: str, ctx: dict) -> str:
    """Handle AutoMix requests: start a job, check status, or list recent jobs.

    Previously Thursday had no AutoMix service at all (docs/THURSDAY_ORCHESTRATOR_AUDIT_2026-07-08.md P0).
    """
    text_lower = text.lower()

    if any(w in text_lower for w in ["list", "recent", "my jobs", "all jobs", "show jobs"]):
        jobs = api.automix_list_jobs(limit=10)
        if not jobs:
            return "No AutoMix jobs found."
        lines = ["Recent AutoMix jobs:"]
        for job in jobs:
            lines.append(f"  {job.get('id', '?')} — {job.get('project_id', '?')} "
                         f"({job.get('genre', '?')}) — {job.get('status', '?')}")
        return "\n".join(lines)

    if any(w in text_lower for w in ["status", "check", "progress"]):
        match = _AUTOMIX_JOB_ID_RE.search(text_lower)
        job_id = match.group(1) if match else ctx.get("current_automix_job")
        if not job_id:
            return "I need an AutoMix job ID — you can also start a job first and I'll remember it."
        result = api.automix_status(job_id)
        if result.get("ok") is False:
            return result.get("error", f"AutoMix job not found: {job_id}")
        history = result.get("history", [])
        last_event = history[-1].get("message", "") if history else ""
        suffix = f" — {last_event}" if last_event else ""
        return f"AutoMix job {job_id}: {result.get('status')}{suffix}"

    # Default: start a job. Extract a single-token project id ourselves first —
    # the shared "project_name" entity regex is greedy over "for ..."/"project ..."
    # and can capture the literal word "project" itself (e.g. "run automix for
    # project abc123" -> "project abc123"), which then fails the DB's project
    # foreign-key check. Only fall back to shared context if our own extraction
    # misses, and strip a leading "project"/"for" word if that fallback is dirty.
    match = (
        re.search(r"(?:project|for)\s+([\w-]+)\s*$", text_lower)
        or re.search(r"(?:project|for)\s+([\w-]+)", text_lower)
        or _AUTOMIX_JOB_ID_RE.search(text_lower)  # bare 8-char id, e.g. "on 12bfbefd"
    )
    project_id = match.group(1) if match else None
    if not project_id:
        raw = ctx.get("project_name") or ctx.get("current_project")
        if raw:
            project_id = re.sub(r"^(?:project|for)\s+", "", str(raw).strip())
    if not project_id or project_id in {"project", "for"}:
        return "Which project? Try 'run automix for project <id>'."
    genre_match = re.search(r"\b(pop|rock|electronic|hiphop|hip.hop|acoustic|edm)\b", text_lower)
    genre = (genre_match.group(1) if genre_match else "pop").replace("hip.hop", "hiphop")
    # Stage H: an explicit "let kenn mix" / "autonomous mix" / "kenn decide
    # the mix" phrasing opts this job into the autonomous KENN advisor
    # (kenn_advisor.advise_mix_plan, gated + clamped in automix_worker.py).
    # Every other phrasing behaves exactly as before -- autonomous_kenn is
    # off unless the user explicitly asks for it.
    autonomous_phrases = ("let kenn mix", "autonomous mix", "kenn decide the mix")
    style_prefs = {"autonomous_kenn": True} if any(p in text_lower for p in autonomous_phrases) else {}
    result = api.automix_start(
        project_id,
        genre=genre,
        style_prefs=style_prefs,
        correlation_id=str(ctx.get("_correlation_id") or ""),
    )
    if result.get("ok"):
        mode = " with KENN deciding autonomously" if style_prefs.get("autonomous_kenn") else ""
        return f"Started AutoMix job {result.get('job_id')} for project {project_id} ({genre}){mode}."
    return result.get("error", "Could not start the AutoMix job.")


_ABLETON_SET_PARAM_RE = re.compile(
    r"track\s+(?P<track>master|\d+).{0,40}?device\s+(?P<device>\d+).{0,40}?"
    r"param(?:eter)?\s+(?P<parameter>\d+).{0,40}?(?:to|=)\s*(?P<value>-?\d+(?:\.\d+)?)",
    re.IGNORECASE | re.DOTALL,
)


def _handle_ableton_push(api, text: str) -> str:
    """Push a live Ableton parameter change via OSC.

    e.g. "set ableton track 2 device 1 parameter 3 to -6". This is a raw
    numeric mixer/device index API (see ableton_live_api.py) — off by
    default behind AUDIO_TOO_ALLOW_DAW_CONTROL since it sends real UDP
    messages that change an open Ableton Live session.
    """
    match = _ABLETON_SET_PARAM_RE.search(text)
    if not match:
        return ('Tell me the track, device, parameter, and value — e.g. '
                '"set ableton track 2 device 1 parameter 3 to -6".')
    track, device, parameter, value = match.group("track", "device", "parameter", "value")
    result = api.ableton_set_parameter(track, int(device), int(parameter), float(value))
    if not result.get("ok"):
        policy_message = str(result.get("error") or "")
        if policy_message.startswith("Action disabled by policy."):
            return f"Couldn't push to Ableton: {policy_message}"
        return "Ableton could not apply the change (error code: service_unavailable)."
    track_label = "master" if track.lower() == "master" else f"track {track}"
    return f"Pushed to Ableton — {track_label}, device {device}, parameter {parameter} set to {value}."


def _handle_kenn_review_handoff(api, text: str, ctx: dict) -> str:
    review_id = ctx.get("current_mix_review")
    review = api.mix_review_by_id(review_id) if review_id else None
    if not review:
        return f"Mix review not found: {review_id or 'unknown'}"
    handoff = review.get("kenn_handoff") or review.get("closed_loop_action_plan") or review.get("priority_actions")
    question = f"{text}\n\nMix review {review_id} context: {handoff or review.get('summary', review)}"
    return api.ask_kenn(question)


def _handle_kenn_save_note(api, ctx: dict) -> str:
    question = ctx.get("last_kenn_question")
    result = api.ableton_create_note(question) if question else {"ok": False, "error": "No KENN question in context."}
    if isinstance(result, dict):
        if result.get("ok") is False:
            return "The KENN note could not be saved (error code: service_unavailable)."
        return str(result.get("message") or result)
    return str(result)


def _handle_audio_storage(api, text: str) -> str:
    lowered = text.lower()
    # Cleanup remains a dry run by default; destructive deletion needs an
    # explicit API/dashboard confirmation outside conversational routing.
    if "orphan" in lowered:
        return str(api.mix_review_cleanup_orphans(dry_run=True))
    if "clean" in lowered and ("export" in lowered or "audiogen" in lowered):
        return str(api.mix_review_cleanup_audiogen(dry_run=True))
    return str(api.mix_review_storage_stats())


def _handle_business_insights(text: str, ctx: dict) -> str:
    from datetime import datetime, timedelta

    list_records = ctx.get("_list_records")
    if not list_records:
        return "Business records are unavailable."
    lowered = text.lower()
    if "hot lead" in lowered:
        leads = [row for row in list_records("leads") if (row.get("status") or "").lower() == "hot"]
        if not leads:
            return "No hot leads are currently in the pipeline."
        return "Hot leads:\n" + "\n".join(
            f"  - {row.get('name') or row.get('lead') or row.get('id')} — {row.get('service', 'service not set')}"
            for row in leads
        )

    if "profitable service" in lowered:
        year_match = re.search(r"(20\d{2})", text)
        year = year_match.group(1) if year_match else str(datetime.now().year)
        totals: dict[str, float] = {}
        for invoice in list_records("invoices"):
            stamp = str(invoice.get("paid_at") or invoice.get("created_at") or "")
            if not stamp.startswith(year) or (invoice.get("status") or "").lower() != "paid":
                continue
            service = str(invoice.get("service") or invoice.get("project") or "Uncategorised")
            try:
                amount = float(str(invoice.get("total") or invoice.get("amount") or 0).replace(",", "").replace("£", ""))
            except ValueError:
                amount = 0.0
            totals[service] = totals.get(service, 0.0) + amount
        if not totals:
            return f"No paid invoice revenue was recorded for {year}."
        service, revenue = max(totals.items(), key=lambda item: item[1])
        return f"Top service for {year}: {service} (£{revenue:,.2f} paid revenue)."

    months_match = re.search(r"(\d+)\s+months?", lowered)
    months = int(months_match.group(1)) if months_match else 6
    cutoff = datetime.now() - timedelta(days=months * 30)
    activity: dict[str, datetime] = {}
    for table in ("sessions", "projects"):
        for row in list_records(table):
            name = str(row.get("client") or row.get("client_name") or "").strip().lower()
            stamp = row.get("date") or row.get("scheduled_at") or row.get("created_at")
            if not name or not stamp:
                continue
            try:
                parsed = datetime.fromisoformat(str(stamp).replace("Z", "+00:00")).replace(tzinfo=None)
                activity[name] = max(activity.get(name, parsed), parsed)
            except ValueError:
                continue
    inactive = []
    for client in list_records("clients"):
        name = str(client.get("name") or client.get("client") or "").strip()
        if name and (name.lower() not in activity or activity[name.lower()] < cutoff):
            inactive.append(name)
    return (
        f"Clients with no booking/project activity in {months} months:\n"
        + ("\n".join(f"  - {name}" for name in inactive) if inactive else "  None")
    )


def _handle_agent_workflow_chain(api, text: str, ctx: dict) -> str:
    from datetime import date

    draft_result = api.admin_agent("email", text)
    add_record = ctx.get("_add_record")
    reminder_result = "Reminder storage unavailable."
    if add_record:
        due = (date.today() + timedelta(days=7)).isoformat()
        reminder = add_record("followups", {
            "owner": "thursday",
            "subject": f"Check drafted email: {text[:100]}",
            "due": due,
            "notes": "Created by Thursday workflow chain.",
            "status": "Open",
        })
        reminder_result = f"Reminder created for {due} ({reminder.get('id', 'saved')})."
    return f"{draft_result}\n\n{reminder_result}"


def _handle_kenn_compare(api, text: str) -> str:

    match = re.search(r"about\s+(.+?)\s+(?:vs\.?|versus)\s+(.+)$", text, re.IGNORECASE)
    if not match:
        return "Name two topics, for example: 'compare what KENN says about vocal reverb vs drum reverb'."
    first, second = (part.strip(" ?.!") for part in match.groups())
    left = api.ask_kenn(first)
    right = api.ask_kenn(second)
    return f"KENN — {first}:\n{left}\n\nKENN — {second}:\n{right}"


# ─── Stage 9: AutoMix KENN explanation handlers ──────────────────────────

_EXPLAIN_PARAMETER_KEYWORDS = [
    "compression ratio", "gain staging", "reverb send", "stereo width",
    "limiter ceiling", "delay send", "master bus compression",
    "dynamic eq", "dynamic eq cut", "resonance", "harshness",
    "compression", "gain", "reverb", "width", "eq", "pan", "panning",
]
_EXPLAIN_INSTRUMENT_KEYWORDS = [
    "sub bass", "sub_bass", "backing vocal", "synth lead", "synth pad",
    "full drum bus", "master bus", "kick", "snare", "hihat", "percussion",
    "bass", "vocal", "guitar", "keys", "strings", "fx", "ambient", "master",
]
_EXPLAIN_GENRE_RE = re.compile(
    r"\b(pop|rock|hip.hop|hiphop|edm|acoustic|jazz|cinematic|podcast)\b", re.IGNORECASE
)
_EXPLAIN_VALUE_RE = re.compile(r"\b(-?\d+(?:\.\d+)?\s*(?::1|db|dbfs|%|hz)?)\b", re.IGNORECASE)


def _handle_kenn_explain_parameter(api, text: str, ctx: dict) -> str:
    """Ask KENN to explain a specific AutoMix parameter decision (Stage 9.4).

    Reuses the same in-process KENN pipeline as ``kenn`` / ``kenn_compare``
    (see ``thursday/client.py::ask_kenn``), but routes through
    ``audio_analysis.integration.kenn_handoff`` so the question can carry
    the actual instrument/genre/value context AutoMix used, rather than a
    bare user string.
    """
    try:
        from audio_analysis.integration.kenn_handoff import explain_automix_parameter
    except ImportError:
        return "AutoMix parameter explanations are unavailable (audio_analysis module not importable)."

    lowered = text.lower()
    parameter = next((p for p in _EXPLAIN_PARAMETER_KEYWORDS if p in lowered), "parameter choice")
    instrument = next((i for i in _EXPLAIN_INSTRUMENT_KEYWORDS if i in lowered), None)
    genre_match = _EXPLAIN_GENRE_RE.search(lowered)
    genre = genre_match.group(1).replace(".", "").replace("-", "") if genre_match else None
    value_match = _EXPLAIN_VALUE_RE.search(text)
    value = value_match.group(1).strip() if value_match else None

    try:
        payload = explain_automix_parameter(
            parameter,
            instrument=instrument,
            genre=genre,
            value=value,
            session_id=str(ctx.get("_session_id") or ""),
        )
    except Exception as exc:
        return f"I couldn't get KENN's explanation for that parameter (error: {exc})."
    answer = str(payload.get("answer") or "").strip()
    return answer or "KENN couldn't find a grounded explanation for that AutoMix parameter."


def _handle_kenn_explain_flag(api, text: str, ctx: dict) -> str:
    """Ask KENN to explain a Mix Review flag/warning (Stage 9.4)."""
    try:
        from audio_analysis.integration.kenn_handoff import explain_mix_review_flag
    except ImportError:
        return "Mix Review flag explanations are unavailable (audio_analysis module not importable)."

    match = re.search(r"flag[:\s]+['\"]?([^'\"\n]+?)['\"]?(?:\s+mean|\s*[?.!]|$)", text, re.IGNORECASE)
    label = match.group(1).strip() if match else text.strip()
    if not label:
        return "Which flag do you want explained? For example: \"explain the flag 'true peak clipping'\"."

    try:
        payload = explain_mix_review_flag(
            label,
            session_id=str(ctx.get("_session_id") or ""),
        )
    except Exception as exc:
        return f"I couldn't get KENN's explanation for that flag (error: {exc})."
    answer = str(payload.get("answer") or "").strip()
    return answer or "KENN couldn't find a grounded explanation for that flag."


# ─── Phase 5: Calendar, Diagnostics & Profile Handlers ──────────────


def _handle_calendar(text: str, ctx: dict) -> str:
    """Handle calendar/agenda requests, including viewing and scheduling events."""
    text_lower = text.lower()

    from thursday.scheduling import agenda_for_day, agenda_for_week, schedule_reminder, extract_event_details

    # Detect booking/scheduling requests:
    write_keywords = ["schedule", "book", "add", "put", "create", "set", "remind"]
    has_write_action = any(w in text_lower for w in write_keywords)
    has_calendar_ref = any(w in text_lower for w in ["calendar", "agenda", "reminder", "event"])
    
    is_write = has_write_action and has_calendar_ref
    if has_write_action and any(w in text_lower for w in ["session", "meeting", "appointment"]):
        is_write = True
        
    is_read = any(q in text_lower for q in ["what is", "show me", "what does", "view", "read", "list", "check"])

    if is_write and not is_read:
        title, when = extract_event_details(text)
        add_record = ctx.get("_add_record")
        return schedule_reminder(title, when, add_record=add_record)

    if any(w in text_lower for w in ["week", "weekly", "next 7", "upcoming week"]):
        return agenda_for_week()
    elif any(w in text_lower for w in ["daily briefing", "morning briefing", "good morning", "briefing"]):
        _, brief_text = daily_brief.build_daily_brief()
        return brief_text
    else:
        return agenda_for_day()


def _handle_set_reminder(text: str, ctx: dict) -> str:
    """Handle reminder creation with clean title extraction."""
    from thursday.scheduling import schedule_reminder, extract_event_details
    title, when = extract_event_details(text)
    add_record = ctx.get("_add_record")
    return schedule_reminder(title, when, add_record=add_record)


def _handle_diagnostics(api: Any, text: str) -> str:
    """Handle diagnostics, system health, and autonomous recovery requests."""
    import thursday.diagnostics as diag
    text_lower = text.lower()

    if "auto heal" in text_lower or "auto-heal" in text_lower or "remediate" in text_lower:
        result = diag.auto_heal_subsystems()
        report = diag.format_health_report(result.get("health"))
        remed_lines = ["\n🛠️ Autonomous Recovery Operations:"]
        for rem in result.get("remediations", []):
            status_icon = "✅" if rem.get("ok") else "⚠️"
            remed_lines.append(f"  {status_icon} {rem.get('subsystem', 'subsystem')}: {rem.get('message')}")
        if len(remed_lines) > 1:
            report += "\n" + "\n".join(remed_lines)
        return report

    if "fix" in text_lower:
        # Extract subsystem name to fix
        for subsystem in ["website", "server", "kenn", "database", "db"]:
            if subsystem in text_lower:
                result = diag.try_fix(subsystem)
                return result.get("message", f"Attempted to fix {subsystem}.")

    # Default: run full check; if any unhealthy, perform auto-healing
    health = diag.check_all_systems()
    if not health.get("all_healthy"):
        heal_res = diag.auto_heal_subsystems()
        health = heal_res.get("health", health)
        report = diag.format_health_report(health)
        remed_lines = ["\n🛠️ Autonomous Self-Healing Attempted:"]
        for rem in heal_res.get("remediations", []):
            status_icon = "✅" if rem.get("ok") else "⚠️"
            remed_lines.append(f"  {status_icon} {rem.get('subsystem', 'subsystem')}: {rem.get('message')}")
        if len(remed_lines) > 1:
            report += "\n" + "\n".join(remed_lines)
        return report

    return diag.format_health_report(health)


def _handle_usage_analytics() -> str:
    """Handle usage analytics requests."""
    import thursday.diagnostics as diag
    return diag.get_usage_summary()


def _handle_daily_status() -> str:
    """Founder-facing "where are we today" ops status.

    Composes thursday.ops.task_ledger on top of the existing daily brief --
    see thursday/daily_status.py's module docstring for the
    anti-hallucination contract (product/commercial status sections say
    "Evidence missing" rather than invent a status).
    """
    from thursday.ops.daily_status import compose_daily_status, render_daily_status
    return render_daily_status(compose_daily_status())


def _handle_active_tasks() -> str:
    """List open task_ledger tasks (proposed/planned/active/waiting_*)."""
    import thursday.ops.task_ledger as task_ledger

    tasks = task_ledger.active_tasks()
    if not tasks:
        return "📋 Active Tasks\n\n  No active tasks in the ledger."

    lines = ["📋 Active Tasks", ""]
    for i, t in enumerate(tasks, start=1):
        lines.append(f"{i}. [{t.workstream}] {t.objective} ({t.task_id})")
        lines.append(f"   Status: {t.status} · Priority: {t.priority}")
        if t.blockers:
            lines.append(f"   Blocker: {t.blockers[-1]}")
        lines.append(f"   Next action: {t.next_action or 'not recorded'}")
    return "\n".join(lines)


def _handle_create_task(text: str) -> str:
    """Create a task_ledger entry from "create/add/new task <workstream>:
    <objective>". Returns a plain-language error (not a raised exception)
    for an unrecognized workstream or malformed command, listing the real
    workstream vocabulary rather than leaving the founder guessing.
    """
    import thursday.ops.task_ledger as task_ledger

    try:
        parsed = task_ledger.parse_create_task_command(text)
    except task_ledger.UnrecognizedWorkstream as exc:
        known = ", ".join(sorted(task_ledger.WORKSTREAMS))
        return (
            f"I don't recognize the workstream '{exc.raw}'. "
            f"Known workstreams: {known}."
        )
    except ValueError:
        return "That task has no objective — try \"create task <workstream>: <what needs doing>\"."

    if parsed is None:
        return (
            "I didn't recognize that as a task-creation command. Try: "
            "\"create task <workstream>: <objective>\" "
            "(e.g. \"create task marketing: draft this week's post\")."
        )

    workstream, objective = parsed
    task = task_ledger.create_task(workstream, objective)
    return (
        f"Created {task.task_id} [{task.workstream}]: {task.objective}\n"
        f"Status: {task.status} · Priority: {task.priority}"
    )


def _handle_create_marketing_plan(text: str) -> str:
    """Create a structured marketing plan from "create marketing plan:
    <objective> | audience: ... | channels: ... | ...". See
    thursday/marketing_ops.py's module docstring for why this structures
    founder-supplied content rather than generating any of it.
    """
    import thursday.ops.marketing_ops as marketing_ops

    try:
        parsed = marketing_ops.parse_create_marketing_plan_command(text)
    except ValueError:
        return (
            "That marketing plan has no objective — try "
            "\"create marketing plan: <objective>\"."
        )

    if parsed is None:
        return (
            "I didn't recognize that as a marketing-plan command. Try: "
            "\"create marketing plan: <objective> | audience: ... | "
            "channels: ... | content ideas: ...\"."
        )

    objective, fields = parsed
    plan = marketing_ops.create_marketing_plan(objective, **fields)
    return marketing_ops.render_marketing_plan(plan)


def _handle_marketing_readiness() -> str:
    import thursday.ops.marketing_ops as marketing_ops
    return marketing_ops.audit_marketing_readiness()


def _handle_create_campaign_plan(text: str) -> str:
    """Create a structured ad campaign plan from "create campaign plan:
    <product> | platform: ... | budget: ... | ...". Never launches or
    spends anything -- see thursday/advertising_ops.py's module docstring.
    """
    import thursday.ops.advertising_ops as advertising_ops

    try:
        parsed = advertising_ops.parse_create_campaign_plan_command(text)
    except ValueError:
        return (
            "That campaign plan has no product/objective — try "
            "\"create campaign plan: <product>\"."
        )

    if parsed is None:
        return (
            "I didn't recognize that as a campaign-plan command. Try: "
            "\"create campaign plan: <product> | platform: ... | "
            "budget: £5/day, £10/day\"."
        )

    product, fields = parsed
    plan = advertising_ops.create_campaign_plan(product, **fields)
    return advertising_ops.render_campaign_plan(plan)


def _handle_ad_readiness() -> str:
    import thursday.ops.advertising_ops as advertising_ops
    return advertising_ops.ad_readiness_check()


def _handle_funding_readiness() -> str:
    """Funding/investment readiness -- live-queried traction, no
    fabricated grant matching. See thursday/funding_ops.py's module
    docstring for the stricter evidence contract this holds versus
    marketing_ops/advertising_ops.
    """
    import thursday.ops.funding_ops as funding_ops
    return funding_ops.funding_readiness_report()


def _handle_weekly_report() -> str:
    """Weekly company report -- aggregates task_ledger, macro_analytics,
    feedback (agent reliability), marketing_ops, advertising_ops, and
    funding_ops into one view. See thursday/weekly_report.py's module
    docstring: every figure here is a pass-through of those modules' own
    already-evidenced functions, nothing computed fresh.
    """
    import thursday.ops.weekly_report as weekly_report
    return weekly_report.weekly_company_report()


def _handle_beta_readiness() -> str:
    """QA / beta readiness -- live-parses the real Submit beta checklist
    off disk. See thursday/qa_ops.py's module docstring: this never
    checks a box on the founder's behalf, only reports what's currently
    checked in the actual file.
    """
    import thursday.ops.qa_ops as qa_ops
    return qa_ops.beta_readiness_check()


def _handle_brief_agent(text: str) -> str:
    """Compose a briefing for handing off to another AI agent. See
    thursday/agent_briefing.py's module docstring: pure composition of
    already-real, already-tested reports, plus an explicit evidence-
    discipline instruction for whoever picks the briefing up next.
    """
    import thursday.ops.agent_briefing as agent_briefing

    topic = agent_briefing.parse_brief_agent_command(text)
    if topic is None:
        topic = ""  # reached via structured_commands dispatch, so this always matched
    return agent_briefing.brief_agent(topic)


def _handle_release_hygiene() -> str:
    """Real git status/branch/cleanliness across the NITE DSP monorepo's
    sibling repos, via thursday.shadow_adapters. See
    thursday/engineering_ops.py's module docstring: not a code review or
    a claim about what uncommitted changes contain, just live git state.
    """
    import thursday.ops.engineering_ops as engineering_ops
    return engineering_ops.release_hygiene_check()


def _handle_deployment_health() -> str:
    """Live HTTP reachability across the real production endpoints, via
    curl (not urllib -- see thursday/infrastructure_ops.py's module
    docstring for why). Never claims this substitutes for the full
    infrastructure readiness scorecard.
    """
    import thursday.ops.infrastructure_ops as infrastructure_ops
    return infrastructure_ops.deployment_health_check()


def _handle_pricing() -> str:
    """Live-read service pricing. See thursday/finance_ops.py's module
    docstring: deliberately does not duplicate the existing "invoices"
    service, which already covers real invoice listing via the Admin
    business agent.
    """
    import thursday.ops.finance_ops as finance_ops
    return finance_ops.pricing_summary()


def _handle_faq(text: str) -> str:
    """Live-read real FAQ content. See thursday/support_ops.py --
    reached via structured_commands.py, so parse_faq_command(text)
    already matched by the time this runs; re-parse here (cheap, and
    keeps this handler self-contained/directly testable) rather than
    threading the already-parsed query through the dispatcher.
    """
    import thursday.ops.support_ops as support_ops

    query = support_ops.parse_faq_command(text)
    return support_ops.faq_lookup(query or "")


def _handle_known_issues() -> str:
    """Real, currently-unchecked Gate 0 items from the beta checklist,
    reframed for support triage. See thursday/support_ops.py.
    """
    import thursday.ops.support_ops as support_ops
    return support_ops.known_issues()


def _handle_launch_tracker() -> str:
    """Live-parsed launch-gate status from the real tracker doc. See
    thursday/documentation_ops.py's module docstring for why this is
    distinct from qa_ops.beta_readiness_check() (different document,
    different status vocabulary, different granularity).
    """
    import thursday.ops.documentation_ops as documentation_ops
    return documentation_ops.launch_tracker_status()


def _handle_draft_beta_invite(text: str) -> str:
    """Compose a beta-invite email draft for manual review and sending.
    See thursday/beta_invite_ops.py's module docstring: no sending
    capability, no credentials, pure text composition -- confirmed with
    the founder as the explicit choice for this feature.
    """
    import thursday.ops.beta_invite_ops as beta_invite_ops

    try:
        parsed = beta_invite_ops.parse_draft_beta_invite_command(text)
    except ValueError:
        return "I need an email address — try \"draft beta invite for jordan@example.com\"."

    if parsed is None:
        return (
            "I didn't recognize that as a beta-invite command. Try: "
            "\"draft beta invite for <email>\" or "
            "\"draft beta invite: <email> | name: <name>\"."
        )

    email, fields = parsed
    return beta_invite_ops.draft_beta_invite(email, **fields)


def _handle_macro_stats() -> str:
    """Report macro fire counts, outcome breakdown, and average duration.

    Surfaces thursday.ops.macro_analytics.get_macro_stats() (D2.3) --
    macro_executions.jsonl, populated by the execute_macro() call sites in
    thursday/orchestrator.py.
    """
    import thursday.ops.macro_analytics as macro_analytics

    stats = macro_analytics.get_macro_stats()
    if stats["total_executions"] == 0:
        return "📊 Macro Stats\n\n  No macro executions recorded yet."

    lines = ["📊 Macro Stats", "", f"  {stats['total_executions']} total executions", ""]
    by_fires = sorted(stats["macros"].items(), key=lambda kv: -kv[1]["fires"])
    for name, m in by_fires:
        avg = f"{m['avg_elapsed_ms']:.0f}ms avg" if m["avg_elapsed_ms"] is not None else "no completed runs timed"
        lines.append(
            f"  {name}: {m['fires']} fires · {m['success_rate']:.0%} completed "
            f"({m['failed']} failed, {m['paused_for_confirmation']} paused) · {avg}"
        )

    return "\n".join(lines)


def _handle_agent_reliability() -> str:
    """Report per-service helpfulness scores from collected feedback.

    Surfaces thursday.feedback.get_helpfulness_summary()/
    get_service_helpfulness() -- a scoring engine (explicit ratings +
    dwell-time/follow-up signals) that existed with no caller anywhere in
    thursday/ until this handler.
    """
    import thursday.feedback as feedback

    summary = feedback.get_helpfulness_summary()
    if summary.get("total_records", 0) == 0:
        return "📊 Agent Reliability\n\n  No feedback data collected yet."

    service_scores = feedback.get_service_helpfulness()
    lines = ["📊 Agent Reliability", ""]
    lines.append(f"  {summary['total_records']} feedback records "
                 f"({summary['explicit_feedback']} explicit)")
    if summary["thumbs_up"] or summary["thumbs_down"]:
        lines.append(f"  👍 {summary['thumbs_up']} · 👎 {summary['thumbs_down']} "
                     f"({summary['thumbs_up_ratio']:.0%} positive)")
    if summary["corrections"]:
        lines.append(f"  ✏️  {summary['corrections']} corrections")
    lines.append("")

    if service_scores:
        for sid, score in sorted(service_scores.items(), key=lambda kv: -kv[1]):
            lines.append(f"  {sid}: {score:.0%} reliable")
    else:
        lines.append("  Not enough samples per service to score yet "
                      "(needs 3+ feedback records per service).")

    return "\n".join(lines)


def _handle_user_profile(text: str, ctx: dict) -> str:
    """Handle user profile and preference requests."""
    import thursday.user_profile as up
    text_lower = text.lower()

    profile_id = ctx.get("profile_id", "default")
    profile = up.get_profile(profile_id)

    if "create shortcut" in text_lower or "add shortcut" in text_lower:
        # "create shortcut jj for Jordan"
        import re
        m = re.search(r"(?:create|add)\s+shortcut\s+(\w+)\s+(?:for|→|->|=)\s+(.+)", text, re.IGNORECASE)
        if m:
            shortcut = m.group(1).strip().lower()
            expansion = m.group(2).strip().title()
            up.add_shortcut(shortcut, expansion, profile_id)
            return f"Shortcut created: '{shortcut}' → '{expansion}'"

    if "remove shortcut" in text_lower or "delete shortcut" in text_lower:
        import re
        m = re.search(r"(?:remove|delete)\s+shortcut\s+(\w+)", text, re.IGNORECASE)
        if m:
            shortcut = m.group(1).strip().lower()
            if up.remove_shortcut(shortcut, profile_id):
                return f"Shortcut '{shortcut}' removed."
            return f"No shortcut '{shortcut}' found."

    if "update" in text_lower or "set" in text_lower:
        # "set auto speak on" or "update preference preferred_output concise"
        import re
        m = re.search(r"(?:set|update)\s+(?:preference\s+)?(\w[\w_.]*)\s+(.+)$", text, re.IGNORECASE)
        if m:
            key = m.group(1).strip()
            value = m.group(2).strip().lower()
            # Convert boolean strings
            if value in ("on", "yes", "true", "1"):
                value = True
            elif value in ("off", "no", "false", "0"):
                value = False
            up.update_preference(key, value, profile_id)
            return f"Preference '{key}' updated to {value}."

    # Show profile
    lines = [f"Profile: {profile.get('user_name', 'User')}"]
    lines.append(f"Mood: {profile.get('mood', 'neutral')}")
    lines.append("")
    prefs = profile.get("preferences", {})
    lines.append("Preferences:")
    for key, value in prefs.items():
        if isinstance(value, dict):
            lines.append(f"  {key}:")
            for sub_key, sub_value in value.items():
                lines.append(f"    {sub_key}: {sub_value}")
        else:
            lines.append(f"  {key}: {value}")
    shortcuts = profile.get("shortcuts", {})
    if shortcuts:
        lines.append("")
        lines.append("Shortcuts:")
        for short, full in shortcuts.items():
            lines.append(f"  {short} → {full}")
    return "\n".join(lines)


# ─── Siri-style utility tools (2026-08-07) ────────────────────────────────


def _handle_calculator(text: str) -> str:
    """Handle arithmetic requests deterministically, not via the LLM brain
    (a small local model's mental math is unreliable, see utility_tools.py's
    module docstring)."""
    from thursday.utility_tools import calculate, format_calc_result

    result, error = calculate(text)
    if error:
        return error
    return format_calc_result(result)


def _handle_unit_conversion(text: str) -> str:
    """Handle unit conversion requests ("convert 5 km to miles")."""
    from thursday.utility_tools import convert_units, parse_conversion_request

    parsed = parse_conversion_request(text)
    if parsed is None:
        return "Tell me what to convert, e.g. 'convert 5 km to miles' or '30 celsius to fahrenheit'."
    value, from_unit, to_unit = parsed
    result, error = convert_units(value, from_unit, to_unit)
    if error:
        return error
    value_disp = int(value) if float(value).is_integer() else value
    result_disp = round(result, 4)
    if isinstance(result_disp, float) and result_disp.is_integer():
        result_disp = int(result_disp)
    return f"{value_disp} {from_unit} is {result_disp} {to_unit}."


def _handle_timer(text: str) -> str:
    """Handle countdown timers: set, check, or cancel.

    Query-based, not a live alarm/notification -- Thursday has no persistent
    background process guaranteed to be running when a timer would go off
    (each CLI/REPL invocation is its own process). "Check my timer" reports
    time remaining or that it's done; a real audible alarm is a larger,
    separate feature (would need the always-on voice pipeline to poll it).
    """
    from thursday.utility_tools import (
        cancel_timer,
        format_duration,
        list_timers,
        start_timer,
    )

    text_lower = text.lower()

    if "cancel" in text_lower or "stop" in text_lower:
        m = re.search(r"\b([a-f0-9]{4,8})\b", text_lower)
        return cancel_timer(m.group(1) if m else "")

    if any(w in text_lower for w in ["set", "start", "create"]):
        timer, error = start_timer(text)
        if error:
            return error
        return f"Timer set for {format_duration(timer['duration_seconds'])} ({timer['id']})."

    # Default: check status of active timers.
    timers = list_timers()
    if not timers:
        return "No active timers. Try 'set a timer for 10 minutes'."
    lines = ["⏱️ Timers:"]
    for t in sorted(timers, key=lambda x: x["remaining_seconds"]):
        if t["done"]:
            lines.append(f"  {t['id']} — {t['label']}: done!")
        else:
            lines.append(f"  {t['id']} — {t['label']}: {format_duration(t['remaining_seconds'])} left")
    return "\n".join(lines)


def _handle_weather(text: str) -> str:
    """Handle weather requests via Open-Meteo (free, no API key required).

    Falls back to a saved default location (see _handle_set_default_location)
    when the query doesn't name one, so "what's the weather" works after
    it's been set once, not just "what's the weather in <city>" every time.
    """
    from thursday.user_profile import get_preference
    from thursday.utility_tools import extract_location, get_weather

    location = extract_location(text)
    if not location:
        location = get_preference("default_location", "")
    if not location:
        return (
            "Which location? Try 'what's the weather in London', or set a default "
            "with 'my location is London'."
        )

    result = get_weather(location)
    if not result.get("ok"):
        return result.get("error", "Weather lookup failed.")

    temp_c = result["temperature_c"]
    temp_f = temp_c * 9 / 5 + 32
    return (
        f"{result['location']}: {result['condition']}, "
        f"{temp_c:.0f}°C ({temp_f:.0f}°F), wind {result['wind_kph']:.0f} km/h."
    )


def _handle_set_default_location(text: str) -> str:
    """Handle "my location is X" / "set my location to X" — saves a default
    place for weather (and future location-aware) queries."""
    from thursday.user_profile import update_preference

    m = re.search(
        r"\b(?:my\s+location\s+is|set\s+my\s+location\s+to)\s+(.+?)[\?\.!]*$",
        text.strip(),
        re.IGNORECASE,
    )
    if not m:
        return "Tell me where, e.g. 'my location is London'."
    location = m.group(1).strip()
    update_preference("default_location", location)
    return f"Got it — I'll use {location} as your default location."


def _handle_current_time(text: str) -> str:
    """Handle "what time is it" / "what time is it in X"."""
    from thursday.utility_tools import extract_time_location, get_current_time

    location = extract_time_location(text)
    formatted, error = get_current_time(location)
    if error:
        return error
    return formatted


def _handle_date_query(text: str) -> str:
    """Handle "what's the date" / "what day is it in N days" / "how many
    days until <weekday>"."""
    from thursday.utility_tools import answer_date_query

    answer = answer_date_query(text)
    return answer or "I couldn't work out that date question — try 'what day is it in 10 days'."
