"""Service registry entries: studio domain.

Split out of thursday/registry.py (was 1,263 lines) — see docs/BACKLOG.md.
"""

from __future__ import annotations

from typing import Any

from thursday.registry.core import ServiceDef
from thursday.registry.handlers import (
    _extract_path,
    _handle_ableton_push,
    _handle_audio_storage,
    _handle_automix,
    _handle_kenn_compare,
    _handle_kenn_explain_flag,
    _handle_kenn_explain_parameter,
    _handle_kenn_review_handoff,
    _handle_kenn_save_note,
    _handle_mix_review,
)
from thursday.phase3_handlers import (
    handle_audiogen_job,
    handle_audiogen_render,
    handle_audiogen_status,
    handle_creative_lab,
    handle_creative_lab_repairs,
    handle_mix_review_detail,
    handle_mix_review_list,
    handle_mix_review_rack,
    handle_mix_review_references,
    handle_mix_review_timeline,
    handle_mix_review_version_diff,
)


def _register_studio_services(services: dict, api: Any) -> None:
    services["kenn"] = ServiceDef(
        name="KENN Knowledge Base",
        description="Audio production, mixing, and mastering advice",
        examples=["how do I sidechain in Ableton", "what's the best way to EQ vocals",
                   "mastering limiter settings"],
        triggers=[],  # Uses intent matching instead
        intents=["production_qa"],
        action=lambda ctx, api, text: api.ask_kenn(
            text,
            fast=bool(ctx.get("_voice_mode", False)),
            history=ctx.get("_kenn_history"),
            session_id=str(ctx.get("_session_id") or ""),
        ),
    )

    # ── Audio Generation ──────────────────────────────────────────────

    services["audiogen"] = ServiceDef(
        name="AudioGen",
        description="Generate audio loops, songs, and emotion-based renders",
        examples=["generate a joyful loop", "make a beat", "render a song"],
        triggers=["generate loop", "make a loop", "generate phrase", "create a beat",
                   "generate audio", "make a song", "render song",
                   "audiogen", "render queue", "render status"],
        intents=["audio_generation"],
        action=lambda ctx, api, text: api.audiogen_generate(text),
        post_process=lambda ctx, resp: ctx.update({"last_report": "audiogen"}),
    )

    # ── Mix Review / Audio Analysis ───────────────────────────────────

    services["audio_analysis"] = ServiceDef(
        name="Audio Analysis",
        description="Audio file scanning, analysis, and mix diagnostics",
        examples=["scan audio files", "analyze my mix", "analyse my track for issues"],
        triggers=["analyze audio", "scan audio", "audio analysis", "scan my files",
                   "analyse mix", "analyze my song", "analyse my track",
                   "audio scan", "scan my project", "analyse a track",
                   "scan folder", "scan directory", "analyse file",
                   "audio file analysis", "track analysis", "song analysis"],
        intents=["mix_review_audio_analysis"],
        action=lambda ctx, api, text: api.audio_scan(_extract_path(text)),
        post_process=lambda ctx, resp: ctx.update({
            "current_audio_scan": resp if "Audio directory" not in resp else None,
            "last_report": "audio_scan",
        }),
    )

    services["mix_review"] = ServiceDef(
        name="Mix Review",
        description="Mix review plans, progress, and version comparison",
        examples=["mix review plan", "revision plan", "mix review compare"],
        triggers=["mix review", "revision plan", "mix review compare",
                   "check my mix", "mix analysis", "analyze my mix"],
        intents=["mix_review_audio_analysis"],
        action=lambda ctx, api, text: _handle_mix_review(api, text, ctx),
        post_process=lambda ctx, resp: ctx.update({"last_report": "mix_review"}),
    )

    services["automix"] = ServiceDef(
        name="AutoMix",
        description="Start, check, and list automated mixdown jobs",
        examples=["run automix for project abc123", "automix status", "list my automix jobs"],
        triggers=["automix", "auto mix", "automated mix", "auto-mix",
                   "run automix", "start automix", "automix status",
                   "automix job", "automix jobs",
                   "let kenn mix", "autonomous mix", "kenn decide the mix"],
        intents=["mix_review_audio_analysis"],
        action=lambda ctx, api, text: _handle_automix(api, text, ctx),
        post_process=lambda ctx, resp: ctx.update({"last_report": "automix"}),
    )

    # ── Agent Tasks ───────────────────────────────────────────────────

    services["audiogen_status"] = ServiceDef(
        name="AudioGen Status",
        description="AudioGen system status, available emotions, render queue",
        examples=["is AudioGen working", "audiogen status", "what emotions can I use on AudioGen",
                   "check the render queue"],
        triggers=["audiogen status", "audiogen health", "is audiogen working",
                   "audiogen queue", "render queue", "check render queue",
                   "what emotions", "show emotions", "audiogen emotions",
                   "audiogen render history", "render history",
                   "audiogen history", "audiogen system"],
        intents=["audio_generation"],
        action=lambda ctx, api, text: handle_audiogen_status(api, text),
        post_process=lambda ctx, resp: ctx.update({"last_report": "audiogen_status"}),
    )

    services["audiogen_render"] = ServiceDef(
        name="AudioGen Full Song Render",
        description="Queue a full song render in AudioGen with emotion control",
        examples=["render a joyful full song", "queue a sad song render", "render 4 bars of piano",
                   "create a full song with happy emotion"],
        triggers=["render full song", "render song", "queue render", "full song render",
                   "full song",
                   "create a full song", "write a song", "make a song",
                   "audiogen render", "render a song with",
                   "automix", "auto-mix", "mixdown"],
        intents=["audio_generation"],
        action=lambda ctx, api, text: handle_audiogen_render(api, text, ctx),
        post_process=lambda ctx, resp: ctx.update({
            "last_report": "audiogen_render",
            "current_audiogen_job": resp.get("job", {}).get("id") if isinstance(resp, dict) else None,
        }),
    )

    services["audiogen_job"] = ServiceDef(
        name="AudioGen Job Control",
        description="Check, cancel, or retry AudioGen render jobs",
        examples=["check render job status", "cancel my render", "retry failed render",
                   "what's the status of my render", "stop the render"],
        triggers=["render job", "job status", "cancel render", "retry render",
                   "stop render", "check render", "render status",
                   "audiogen job", "cancel that render", "retry that render"],
        intents=["audio_generation"],
        requires_context=["current_audiogen_job"],
        action=lambda ctx, api, text: handle_audiogen_job(api, text, ctx),
        post_process=lambda ctx, resp: ctx.update({"last_report": "audiogen_job"}),
    )

    # ── Phase 3: Mix Review Advanced ──────────────────────────────────

    services["mix_review_list"] = ServiceDef(
        name="List Mix Reviews",
        description="List and browse recent mix reviews",
        examples=["show my mix reviews", "list recent reviews", "what reviews do I have",
                   "browse mix reviews"],
        triggers=["list reviews", "all reviews", "show reviews", "list mix reviews",
                   "my reviews", "recent reviews", "browse reviews",
                   "show all reviews", "mix reviews list", "latest reviews", "latest mix reviews"],
        intents=["mix_review_audio_analysis"],
        action=lambda ctx, api, text: handle_mix_review_list(api, text),
        post_process=lambda ctx, resp: ctx.update({"last_report": "mix_review_list"}),
    )

    services["mix_review_detail"] = ServiceDef(
        name="Mix Review Detail",
        description="Fetch a specific mix review by ID",
        examples=["show review abc12345", "get mix review details", "review report",
                   "what does review abc123 say"],
        triggers=["review detail", "show review", "get review", "review report",
                   "review html", "open review", "fetch review",
                   "review status for", "review by id"],
        intents=["mix_review_audio_analysis"],
        action=lambda ctx, api, text: handle_mix_review_detail(api, text),
        post_process=lambda ctx, resp: ctx.update({
            "last_report": "mix_review_detail",
            "current_mix_review": next((r.get("id") for r in ([resp] if isinstance(resp, dict) else []) if isinstance(r, dict)), None),
        }),
    )

    services["mix_review_timeline"] = ServiceDef(
        name="Mix Review Timeline",
        description="Version timeline for a specific track",
        examples=["show timeline for my track", "version history of mix", "track timeline"],
        triggers=["track timeline", "version history", "version timeline",
                   "mix timeline", "track versions", "song timeline",
                   "revisions for", "revision history",
                   "show timeline for", "timeline for", "history for"],
        intents=["mix_review_audio_analysis"],
        action=lambda ctx, api, text: handle_mix_review_timeline(api, text),
        post_process=lambda ctx, resp: ctx.update({"last_report": "mix_review_timeline"}),
    )

    services["mix_review_version_diff"] = ServiceDef(
        name="Mix Version Comparison",
        description="Compare two versions of a mix review",
        examples=["compare two reviews", "version diff", "what changed between versions"],
        triggers=["compare reviews", "version diff", "compare versions", "version comparison",
                   "diff between", "what changed", "compare mix", "revision diff"],
        intents=["mix_review_audio_analysis"],
        action=lambda ctx, api, text: handle_mix_review_version_diff(api, text, ctx),
        post_process=lambda ctx, resp: ctx.update({"last_report": "mix_review_diff"}),
    )

    services["mix_review_correction_rack"] = ServiceDef(
        name="Ableton Correction Rack",
        description="Generate an Ableton correction rack from a mix review",
        examples=["generate correction rack for review abc123", "ableton repair rack",
                   "make a correction rack", "generate ableton rack for mix review"],
        triggers=["correction rack", "repair rack", "ableton rack", "correction chain",
                   "generate rack", "ableton correction", "repair template"],
        intents=["mix_review_audio_analysis"],
        action=lambda ctx, api, text: handle_mix_review_rack(api, text),
        post_process=lambda ctx, resp: ctx.update({"last_report": "correction_rack"}),
    )

    services["mix_review_references"] = ServiceDef(
        name="Reference Tracks",
        description="List saved reference tracks for mix comparison",
        examples=["show my reference tracks", "list references", "reference tracks",
                   "upload a reference track"],
        triggers=["reference tracks", "show references", "list references",
                   "my references", "saved references", "reference list",
                   "upload reference", "add reference"],
        intents=["mix_review_audio_analysis"],
        action=lambda ctx, api, text: handle_mix_review_references(api, text),
        post_process=lambda ctx, resp: ctx.update({"last_report": "references"}),
    )

    # ── Phase 3: Creative Lab ─────────────────────────────────────────

    services["creative_lab"] = ServiceDef(
        name="Creative Lab",
        description="Creative Lab snapshot, session events, and feedback",
        examples=["creative lab snapshot", "show creative lab", "creative lab status",
                   "record creative lab session"],
        triggers=["creative lab", "creative lab snapshot", "creative lab status",
                   "creative lab session", "creative lab feedback",
                   "lab snapshot", "lab status"],
        intents=["system"],
        action=lambda ctx, api, text: handle_creative_lab(api, text),
        post_process=lambda ctx, resp: ctx.update({"last_report": "creative_lab"}),
    )

    services["creative_lab_repairs"] = ServiceDef(
        name="Creative Lab Repairs",
        description="Repair recommendations, promotion, and training export",
        examples=["show repair recommendations", "promote repair", "run repair recommendation",
                   "export repair training data"],
        triggers=["repair recommendation", "repair suggestions", "repair training",
                   "promote repair", "run repair", "export repairs",
                   "creative lab repair", "repair artifacts", "create repair artifacts",
                   "repair recommendations", "show repair", "pending repair"],
        intents=["system"],
        action=lambda ctx, api, text: handle_creative_lab_repairs(api, text),
        post_process=lambda ctx, resp: ctx.update({"last_report": "creative_lab_repairs"}),
    )

    # ── Phase 3: Portfolio ────────────────────────────────────────────

    services["kenn_review_handoff"] = ServiceDef(
        name="KENN Mix Review Handoff",
        description="Ask KENN for actions based on the current mix review",
        examples=["based on my last mix review, what should I fix first?"],
        triggers=["based on my last mix review", "based on that review", "ask kenn about the review",
                  "what should i fix first", "kenn handoff"],
        intents=["mix_review_audio_analysis"],
        requires_context=["current_mix_review"],
        action=lambda ctx, api, text: _handle_kenn_review_handoff(api, text, ctx),
        post_process=lambda ctx, resp: ctx.update({"last_report": "kenn_review_handoff"}),
    )

    services["kenn_save_note"] = ServiceDef(
        name="Save KENN Note",
        description="Create a draft training note from the last KENN question",
        examples=["save that as a note"],
        triggers=["save that as a note", "save as a note", "create note from that"],
        intents=[],
        requires_context=["last_kenn_question"],
        action=lambda ctx, api, text: _handle_kenn_save_note(api, ctx),
        post_process=lambda ctx, resp: ctx.update({"last_report": "kenn_note"}),
    )

    services["audio_storage"] = ServiceDef(
        name="Audio Storage & Cleanup",
        description="Review audio storage and safely preview cleanup operations",
        examples=["how much storage are reviews using?", "clean up orphaned uploads"],
        triggers=["storage are reviews using", "review storage", "audio storage", "storage stats",
                  "clean up old audio exports", "cleanup audio exports", "orphaned uploads",
                  "clean up orphaned uploads"],
        intents=["mix_review_audio_analysis", "system"],
        action=lambda ctx, api, text: _handle_audio_storage(api, text),
        post_process=lambda ctx, resp: ctx.update({"last_report": "audio_storage"}),
    )

    services["kenn_compare"] = ServiceDef(
        name="KENN Comparison",
        description="Compare KENN guidance for two production topics",
        examples=["compare what KENN says about reverb for vocals vs drums"],
        triggers=["compare what kenn says", "ask kenn to compare", "kenn compare"],
        intents=["production_qa"],
        action=lambda ctx, api, text: _handle_kenn_compare(api, text),
        post_process=lambda ctx, resp: ctx.update({"last_report": "kenn_compare"}),
    )

    services["kenn_explain_parameter"] = ServiceDef(
        name="KENN AutoMix Parameter Explanation",
        description="Ask KENN why AutoMix chose a specific mix parameter (gain, compression ratio, reverb send, width)",
        examples=["why is the compression ratio 3.5:1 on the vocal bus",
                   "explain the vocal reverb send", "why is the kick gain staged that way",
                   "explain the stereo width on the synth pad"],
        triggers=["why is the compression ratio", "explain the compression", "explain the gain",
                   "why is the gain", "explain the reverb", "why is the reverb",
                   "explain the stereo width", "why is the stereo width", "explain the pan",
                   "why is the limiter ceiling", "explain the limiter", "explain that parameter",
                   "explain this parameter", "kenn explain parameter"],
        intents=["production_qa", "mix_review_audio_analysis"],
        action=lambda ctx, api, text: _handle_kenn_explain_parameter(api, text, ctx),
        post_process=lambda ctx, resp: ctx.update({"last_report": "kenn_explain_parameter"}),
    )

    services["kenn_explain_flag"] = ServiceDef(
        name="KENN Mix Review Flag Explanation",
        description="Ask KENN what a specific Mix Review flag/warning means and how to fix it",
        examples=["explain the true peak clipping flag", "what does the mono compatibility flag mean",
                   "why did i get a stereo correlation warning"],
        triggers=["explain the flag", "explain that flag", "explain this flag", "what does the flag mean",
                   "what does that warning mean", "why did i get that flag", "kenn explain flag"],
        intents=["production_qa", "mix_review_audio_analysis"],
        action=lambda ctx, api, text: _handle_kenn_explain_flag(api, text, ctx),
        post_process=lambda ctx, resp: ctx.update({"last_report": "kenn_explain_flag"}),
    )

    services["ableton_push"] = ServiceDef(
        name="Ableton Live Push",
        description="Push a live device parameter change to Ableton Live via OSC",
        examples=["set ableton track 2 device 1 parameter 3 to -6",
                   "push to ableton track master device 0 parameter 1 to 0.5"],
        triggers=["set ableton", "push to ableton", "push that to ableton",
                   "ableton track", "send to ableton", "push repair to ableton"],
        intents=["mix_review_audio_analysis", "system"],
        action=lambda ctx, api, text: _handle_ableton_push(api, text),
        post_process=lambda ctx, resp: ctx.update({"last_report": "ableton_push"}),
    )
