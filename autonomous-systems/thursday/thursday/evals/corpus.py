"""Held-out routing corpus assembled from realistic request families."""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class RoutingCase:
    case_id: str
    text: str
    expected_intent: str
    expected_target: str
    critical: bool
    tags: tuple[str, ...]
    previous_intent: str = ""


SEEDS: dict[str, tuple[str, ...]] = {
    "business_ops": (
        "how is business", "give me the business status", "show the sales pipeline",
        "what enquiries are pending", "show this week's business summary",
        "what is coming up next week", "give me the monthly report",
        "where is the sales bottleneck", "show service demand", "which follow ups are overdue",
    ),
    "calendar_scheduling": (
        "what is on my calendar today", "show my agenda", "what does my week look like",
        "remind me to email Jordan tomorrow", "set a reminder to export stems on Friday",
        "schedule a session with Sarah", "book a meeting for next Tuesday",
        "give me my daily briefing", "what is on this afternoon", "set up a client call",
    ),
    "client_mgmt": (
        "tell me about Jordan", "who is Sarah", "show client details for Alex",
        "give me the client history for Morgan", "show the client timeline for Casey",
        "list my sessions", "show upcoming sessions", "client summary for Taylor",
        "show client info for Jamie", "what sessions do I have",
    ),
    "financial": (
        "show invoices", "list pending drafts", "how much revenue did we make",
        "show the profit report", "list expenses", "what did I spend this month",
        "generate invoice pdf", "show unsent drafts", "give me the pnl for 2026",
        "show income and earnings",
    ),
    "production_qa": (
        "how should I compress a vocal", "why is my mix muddy", "how do I sidechain the bass",
        "what limiter ceiling should I use", "how can I make the snare punchy",
        "explain parallel compression", "how should I EQ harsh vocals",
        "why is the low end out of phase", "how do I set reverb pre delay",
        "what causes clipping on the master", "how do I widen a synth safely",
        "what is gain staging", "how should I route a drum bus",
        "why does Ableton have latency", "how do I automate a filter",
    ),
    "audio_generation": (
        "generate a dark eight bar loop", "make a joyful beat", "create a calm song",
        "generate an energetic audio phrase", "make a warm track", "render a full song",
        "show the render queue", "check render status", "cancel render abcdef12",
        "retry render abcdef12",
    ),
    "mix_review_audio_analysis": (
        "analyse my mix", "review this track", "scan audio files", "run a mix review",
        "compare mix versions", "show the revision plan", "analyze my song",
        "scan my project", "analyse file ~/Music/mix.wav", "show review abcdef12",
    ),
    "system_diagnostics": (
        "run diagnostics", "check all systems", "show system health", "fix the website",
        "fix the server", "check each subsystem", "show usage analytics",
        "what do I ask you most", "is everything working", "run a health check",
    ),
    "agent_tasks": (
        "draft email to Jordan", "compose an email for Sarah", "create invoice for Alex",
        "new project for Morgan", "add client Casey", "write outreach for a new artist",
        "draft a social post", "add lead Taylor", "research vocal compression",
        "suggest sources about mastering",
    ),
    "system": (
        "create a snapshot", "backup everything", "archive the business records",
        "export everything", "show available backups", "list snapshots",
        "run daily maintenance", "run weekly maintenance", "start the daily cron",
        "start the weekly cron",
    ),
    "search": (
        "search for Jordan", "find me the Riverside project", "look up invoice abcdef12",
        "where is the mastering template", "find records about Sarah",
        "find projects for Alex", "find clients named Morgan", "find leads from Instagram",
        "look for overdue invoices", "searching for the vocal session",
    ),
    "greeting": (
        "hi", "hey", "hello", "morning", "good morning", "good afternoon",
        "good evening", "howdy", "hiya", "hello Thursday",
    ),
    "help": (
        "help", "commands", "menu", "options", "what can you do",
        "what does Thursday do", "show me what you can do", "what are your capabilities",
        "how do I use Thursday", "tell me what you can help me with",
    ),
    "kenn_voice_mode": (
        "speak with Kenn", "talk to Ken", "switch to Kenn", "send me to Ken",
        "let me talk to Kenn", "Kenn mode", "get Kenn", "switch back to Thursday",
        "talk to Thursday", "Thursday mode",
    ),
    "macro": (
        "start my day", "run my morning routine", "morning briefing", "onboard a new client",
        "register a client", "run a full mix review", "start the mix review pipeline",
        "give me the weekly summary", "run the Friday review", "run my daily routine",
    ),
    "unknown": (
        "how can I improve my website copy",
        "who won the football match", "explain photosynthesis", "book me a flight to Tokyo",
        "what is the capital of Peru", "recommend a dinner recipe", "tell me a history fact",
        "how do I repair a bicycle", "what time is sunset", "write a poem about winter",
        "how does a car engine work", "translate this sentence into French",
        "what is quantum gravity", "recommend a hiking route",
    ),
    "weather": (
        "what is the weather tomorrow", "what's the weather in London",
        "weather forecast for Tokyo", "is it raining right now",
        "how hot is it outside", "will it rain",
    ),
}

CRITICAL_INTENTS = {
    "agent_tasks", "audio_generation", "client_mgmt", "financial",
    "kenn_voice_mode", "mix_review_audio_analysis", "production_qa", "system",
}

SPECIAL_CASES = (
    # Common keyboard/voice-recognition errors exercise canonical normalization.
    ("typo-business", "how is buisness", "business_ops", "orchestrator", "", "typo"),
    ("typo-calendar", "show my calender", "calendar_scheduling", "orchestrator", "", "typo"),
    ("typo-invoice", "show invioce abcdef12", "financial", "orchestrator", "", "typo"),
    ("typo-review", "run a mix reveiw", "mix_review_audio_analysis", "orchestrator", "", "typo"),
    ("typo-analysis", "analise my mix", "mix_review_audio_analysis", "orchestrator", "", "typo"),
    ("typo-diagnostics", "run diagnotics", "system_diagnostics", "orchestrator", "", "typo"),
    ("typo-research", "reserch mastering", "agent_tasks", "orchestrator", "", "typo"),
    ("typo-ableton", "why is Ableon clipping", "production_qa", "kenn_stream", "", "typo"),
    ("typo-sidechain", "how do I sidechian bass", "production_qa", "kenn_stream", "", "typo"),
    ("typo-compression", "explain compresion", "production_qa", "kenn_stream", "", "typo"),
    # Overlapping nouns should defer to the explicit operation phrase.
    ("ambiguous-invoice-review", "review my invoice", "financial", "orchestrator", "", "ambiguous"),
    ("ambiguous-generate-invoice", "generate an invoice", "financial", "orchestrator", "", "ambiguous"),
    ("ambiguous-render-mix", "render my mix for delivery", "production_qa", "kenn_stream", "", "ambiguous"),
    ("ambiguous-research-vocal", "find sources for vocal compression", "agent_tasks", "orchestrator", "", "ambiguous"),
    ("ambiguous-schedule-review", "schedule an invoice review", "calendar_scheduling", "orchestrator", "", "ambiguous"),
    ("ambiguous-business-analysis", "analyse my business pipeline", "business_ops", "orchestrator", "", "ambiguous"),
    # Compound requests must never enter the direct KENN streaming path.
    ("compound-business-finance", "how is business and show invoices", "business_ops", "orchestrator", "", "compound"),
    ("compound-finance-client", "show invoices and tell me about Jordan", "financial", "orchestrator", "", "compound"),
    ("compound-generation-reminder", "generate a beat and remind me tomorrow", "audio_generation", "orchestrator", "", "compound"),
    ("compound-review-snapshot", "review my mix and create a snapshot", "mix_review_audio_analysis", "orchestrator", "", "compound"),
    ("compound-search-pipeline", "search for Jordan and show the pipeline", "search", "orchestrator", "", "compound"),
    ("compound-diagnostics-backups", "run diagnostics and list snapshots", "system_diagnostics", "orchestrator", "", "compound"),
    # Explicit follow-up openers inherit only the current session's prior intent.
    ("followup-production-why", "why does that matter?", "production_qa", "kenn_stream", "production_qa", "followup"),
    ("followup-production-more", "tell me more", "production_qa", "kenn_stream", "production_qa", "followup"),
    ("followup-production-next", "what should I do next?", "production_qa", "kenn_stream", "production_qa", "followup"),
    ("followup-finance-month", "and what about last month?", "financial", "orchestrator", "financial", "followup"),
    ("followup-client-more", "tell me more", "client_mgmt", "orchestrator", "client_mgmt", "followup"),
    ("followup-calendar-next", "what about next week?", "calendar_scheduling", "orchestrator", "calendar_scheduling", "followup"),
)


def _variants(seed: str, intent: str) -> tuple[tuple[str, str], ...]:
    if intent in {"greeting", "help"}:
        return (
            (seed, "typed"),
            (seed.upper(), "case_variation"),
            (f"{seed}!", "punctuation"),
            (f"{seed}?", "voice_transcript"),
        )
    return (
        (seed, "typed"),
        (f"please {seed}", "polite"),
        (f"Thursday, {seed}", "addressed"),
        (f"um {seed} please", "voice_transcript"),
    )


def held_out_cases() -> list[RoutingCase]:
    cases = []
    for intent, seeds in SEEDS.items():
        for seed_index, seed in enumerate(seeds, 1):
            for variant_index, (text, variant_tag) in enumerate(_variants(seed, intent), 1):
                cases.append(
                    RoutingCase(
                        case_id=f"{intent}-{seed_index:02d}-{variant_index}",
                        text=text,
                        expected_intent=intent,
                        expected_target=(
                            "kenn_stream" if intent == "production_qa" else "orchestrator"
                        ),
                        critical=intent in CRITICAL_INTENTS,
                        tags=(intent, variant_tag, "held_out"),
                    )
                )
    for case_id, text, intent, target, previous_intent, tag in SPECIAL_CASES:
        cases.append(
            RoutingCase(
                case_id=case_id,
                text=text,
                expected_intent=intent,
                expected_target=target,
                critical=intent in CRITICAL_INTENTS,
                tags=(intent, tag, "held_out"),
                previous_intent=previous_intent,
            )
        )
    return cases


def release_holdout_cases() -> list[RoutingCase]:
    """Unseen release phrasings, kept separate from the tuned development set."""
    cases = []
    for intent, seeds in SEEDS.items():
        for seed_index, seed in enumerate(seeds, 1):
            if intent in {"greeting", "help"}:
                variants = (
                    (f"{seed}!!", "punctuation_holdout"),
                    (f"{seed}...", "voice_pause_holdout"),
                    (f"{seed}?!", "punctuation_holdout"),
                )
            else:
                variants = (
                    (f"could you {seed}?", "polite_holdout"),
                    (f"can you {seed}?", "voice_holdout"),
                    (f"I need you to {seed}", "direct_holdout"),
                )
            for variant_index, (text, tag) in enumerate(variants, 1):
                cases.append(
                    RoutingCase(
                        case_id=f"release-{intent}-{seed_index:02d}-{variant_index}",
                        text=text,
                        expected_intent=intent,
                        expected_target=(
                            "kenn_stream" if intent == "production_qa" else "orchestrator"
                        ),
                        critical=intent in CRITICAL_INTENTS,
                        tags=(intent, tag, "release_holdout"),
                    )
                )
    return cases


def final_release_holdout_cases() -> list[RoutingCase]:
    """Final untouched release split, distinct from both development rounds."""
    cases = []
    for intent, seeds in SEEDS.items():
        for seed_index, seed in enumerate(seeds, 1):
            if intent in {"greeting", "help"}:
                variants = (
                    (f"{seed}!!!", "punctuation_final"),
                    (f"{seed}.?!", "voice_pause_final"),
                    (f"{seed}??", "punctuation_final"),
                )
            else:
                variants = (
                    (f"would you {seed}?", "polite_final"),
                    (f"when you can, {seed}", "voice_final"),
                    (f"hey Thursday, {seed}", "addressed_final"),
                )
            for variant_index, (text, tag) in enumerate(variants, 1):
                cases.append(
                    RoutingCase(
                        case_id=f"final-{intent}-{seed_index:02d}-{variant_index}",
                        text=text,
                        expected_intent=intent,
                        expected_target=(
                            "kenn_stream" if intent == "production_qa" else "orchestrator"
                        ),
                        critical=intent in CRITICAL_INTENTS,
                        tags=(intent, tag, "final_release_holdout"),
                    )
                )
    return cases
