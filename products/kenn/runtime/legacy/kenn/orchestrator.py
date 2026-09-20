"""KENN Multi-Agent Orchestrator — central dispatch brain.

Classifies user intent and delegates to specialised sub-agents
(Stem Separation, Mix Review, LTAS Matching, AudioGen, Ableton
Control, Mixing Doctor). Collects results and formats them for
the chat interface.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Any, Callable, Dict, List, Optional

from kenn.core.agent_contracts import AgentRequest, AgentResult


@dataclass
class SubAgent:
    """A specialised sub-agent that KENN can dispatch work to."""

    name: str
    emoji: str
    description: str
    capabilities: List[str]
    keywords: List[str]
    dispatch_fn: Callable[..., Dict[str, Any]]


# ── Intent classification patterns ────────────────────────────────

_STEM_PATTERNS = [
    re.compile(r"\b(separate|split|isolat[ei])\b.*\b(stems?|tracks?|vocals?|drums?|basses?)\b", re.I),
    re.compile(r"\bstems?\s*(separat(e|ion)|split|extract)\b", re.I),
    re.compile(r"\b(extract|pull\s*out)\b.*\b(vocals?|drums?|basses?|instruments?)\b", re.I),
]

_MIX_REVIEW_PATTERNS = [
    re.compile(r"\b(review|analyz[ei]|check|assess|evaluat[ei]|audit)\b.*\b(mix(es)?|masters?|tracks?|songs?)\b", re.I),
    re.compile(r"\b(mix(es)?|masters?)\b.*\b(review|analys[ei]s|feedback|checks?)\b", re.I),
    re.compile(r"\bwhat'?s?\s+wrong\s+with\b.*\b(mix(es)?|masters?|tracks?)\b", re.I),
    re.compile(r"\b(clipping|headroom|dynamics|loudness|phase)\b.*\b(checks?|issues?|problems?)\b", re.I),
]

_LTAS_PATTERNS = [
    re.compile(r"\b(ltas|spectrum|spectral)\b.*\b(match(es)?|analys[ei]|compar[ei])\b", re.I),
    re.compile(r"\b(frequency|eq)\b.*\b(balance|match|target)\b.*\b(reference|commercial|genre)s?\b", re.I),
    re.compile(r"\bmatch\b.*\b(genre|reference|commercial)s?\b", re.I),
]

_AUDIOGEN_PATTERNS = [
    re.compile(
        r"\b(generat[ei]|creat[ei]|make|produc[ei])\s+(?:me\s+)?(?:a|an|the|some|another)\s+"
        r"[^?.]{0,40}\b(loops?|beats?|grooves?|melod(y|ies)|songs?|tracks?)\b",
        re.I,
    ),
    re.compile(r"\b(loops?|beats?|grooves?)\b.*\b(generat|creat|make)\b", re.I),
    re.compile(r"\bbpm\b.*\b(loops?|beats?|grooves?|drill|techno|house)\b", re.I),
]

_ABLETON_PATTERNS = [
    re.compile(r"\b(ableton|session|daw)s?\b.*\b(show|status|state|tracks?|query|get)\b", re.I),
    re.compile(r"\b(set|adjust|change|tweak)\b.*\b(volume|pan|fader|level)s?\b.*\b(tracks?|ableton)?\b", re.I),
    re.compile(r"\btracks?\s*\d+\b.*\b(volume|pan|mute)\b", re.I),
    re.compile(r"\bshow\b.*\b(session|tracks?|projects?)\b", re.I),
    # Mute/solo/record-arm, either word order ("mute track 2" or "track 2
    # mute") -- added 2026-08-06 alongside real write execution for these;
    # pattern 3 above only catches the track-then-verb order.
    re.compile(r"\b(set_mute|unmute|set_solo|unsolo|set_arm|record[\s-]?arm|disarm)\b", re.I),
    re.compile(r"\b(mute|solo)\b.*\btracks?\b", re.I),
    re.compile(r"\btracks?\b.*\b(mute|solo)\b", re.I),
    # Transport (play/stop/tempo) -- added 2026-08-06. Deliberately no bare
    # "N bpm" or bare "tempo" pattern: "is 128 bpm too fast for techno?"
    # and similar genuine questions mention a BPM number without asking to
    # change anything, and _is_question_not_request() alone doesn't catch
    # every such phrasing (that one doesn't start with how/what/why/...).
    # Requiring the explicit set/change verb (matching autonomous_agent.py's
    # own tighter tempo-match requirement) keeps this from misclassifying
    # those into the ableton_controller agent.
    re.compile(r"\b(start_playback|stop_playback|set_tempo)\b", re.I),
    re.compile(r"\b(start|stop)\b.*\b(playback|transport)\b", re.I),
    re.compile(r"\b(set|change)\b.*\btempo\b", re.I),
    # Clip/scene launch -- added 2026-08-06 (D1.2). Requires the explicit
    # launch/fire/play/trigger verb next to clip/scene, not just either
    # word alone (e.g. "play the drum fill" without "clip"/"scene" doesn't
    # match here -- named-clip triggering is a future capability, not yet
    # built; this only covers indexed track/slot or scene-number launches).
    re.compile(r"\b(launch_clip|launch_scene)\b", re.I),
    re.compile(r"\b(launch|fire|play|trigger)\b.*\b(clip|scene)\b", re.I),
    # Macro knob control -- added 2026-08-06 (D1.3). Requires an explicit
    # "macro <N>" reference, not a bare "set" verb (which pattern 2 above
    # already covers for volume/pan/fader/level, but macro knobs are a
    # distinct device-parameter concept those words don't cover).
    re.compile(r"\bset_macro\b", re.I),
    re.compile(r"\bmacro\s*\d+\b", re.I),
    # Scene creation -- added 2026-08-07 (D3.4 building block). Requires
    # an explicit create/add/new verb next to "scene", not bare "scene"
    # alone (e.g. "what's on scene 2?" is a read query).
    re.compile(r"\bcreate_scene\b", re.I),
    re.compile(r"\b(create|add|new)\b.*\bscene\b", re.I),
]

_MIXING_DOCTOR_PATTERNS = [
    re.compile(r"\b(mixing\s*doctors?|health\s*checks?|audit\s*sessions?)\b", re.I),
    re.compile(r"\b(check|scan|monitor)\b.*\b(clipping|phase|masking|issues?)\b", re.I),
]

# Arrangement planning -- added 2026-08-07 (D3.4). Requires an explicit
# bar count next to a structure/arrangement word, matching
# arrangement_planner.parse_arrangement_request()'s own requirement --
# a bare bar-count mention ("this loop is 8 bars long") must not fire.
_ARRANGEMENT_PATTERNS = [
    re.compile(r"\b\d+[\s-]?bars?\b.*\b(structure|arrangement)\b", re.I),
    re.compile(r"\b(build|create|make)\b.*\b\d+[\s-]?bars?\b.*\b(structure|arrangement|section)\b", re.I),
]


def _matches_any(text: str, patterns: list[re.Pattern]) -> bool:
    return any(p.search(text) for p in patterns)


# Live-tested 2026-08-04: every _*_PATTERNS list above matches on loose
# keyword proximity (verb ... noun, anywhere in the sentence), with no
# distinction between "how do I do X" (an informational question, wants an
# explanation) and "do X [for me]" (a direct request to actually run a
# tool). This isn't one or two mistuned patterns -- it's the whole
# approach's blind spot, and it affected every single specialist category:
# "how do I level match a reference track against my mix" (ltas_matcher),
# "How do I check if my mix translates on phone speakers" (mix_reviewer),
# "My master is loud but distorted, what should I check first?"
# (mix_reviewer), "Can Ableton diagnose my ear infection after a loud
# show?" (ableton_controller -- "show" as in concert, not "show me"),
# "Can sample-rate conversion make a Wwise ambience loop click...?"
# (audiogen -- "loop" is the genuine grammatical object of "make", but the
# sentence describes an existing loop's problem, not a request to generate
# one). All five are genuine questions, not requests, and dispatch()
# overriding the whole Q&A pipeline with confidence: "high" for a bad
# classification silently replaces a correct answer with a canned
# specialist-agent response. Every confirmed genuine trigger case (below)
# is an imperative request with no question word, so this is a reliable,
# low-risk guard rather than a narrow patch for one phrasing.
_QUESTION_SHAPE_RE = re.compile(
    r"^\s*(how|what|why|when|where|which|who)\b|^\s*can\s+(?!you\b)"
    r"|\bwhat\s+should\s+i\b|\bwhat\s+do\s+i\b",
    re.I,
)


def _is_question_not_request(query: str) -> bool:
    return bool(_QUESTION_SHAPE_RE.search(query))


# ── Sub-agent dispatch functions ──────────────────────────────────

def _dispatch_stem_separation(**kwargs: Any) -> Dict[str, Any]:
    """Dispatch to the stem separation bridge. Since stem separation
    requires an uploaded file, this returns instructions for the user."""
    return {
        "agent": "stem_separator",
        "status": "awaiting_upload",
        "message": (
            "I'm ready to separate your track into stems (vocals, drums, bass, and other). "
            "Go ahead and upload your audio file using the file picker, and I'll run it through "
            "Demucs to extract each stem for you.\n\n"
            "Once the separation is complete, I'll let you know and you can download each stem individually."
        ),
        "action": "upload_stems",
        "action_label": "Upload Track for Separation",
    }


def _dispatch_mix_review(**kwargs: Any) -> Dict[str, Any]:
    """Dispatch to the mix review pipeline. Requires file upload."""
    return {
        "agent": "mix_reviewer",
        "status": "awaiting_upload",
        "message": (
            "Absolutely — I'll give your mix a thorough analysis. I'll check for clipping, dynamics, "
            "frequency balance, stereo width, loudness, and phase issues.\n\n"
            "Upload your mix file and I'll run it through the full review pipeline. You'll get a "
            "detailed breakdown with specific recommendations for improvement."
        ),
        "action": "upload_mix",
        "action_label": "Upload Mix for Review",
    }


def _dispatch_ltas_match(**kwargs: Any) -> Dict[str, Any]:
    """Dispatch to the LTAS spectrum matcher."""
    from kenn.autonomous_agent import tool_ltas_spectrum_match

    genre = kwargs.get("genre", "pop")
    project_id = kwargs.get("project_id")
    result = tool_ltas_spectrum_match(genre=genre, project_id=project_id)

    if result.get("status") == "no_audio":
        return {
            "agent": "ltas_matcher",
            "status": "needs_input",
            "message": (
                "I can compare your mix's spectral balance against commercial reference curves, "
                "but I need some audio to analyze first. You can either:\n\n"
                "• Upload a mix for review (I'll measure the LTAS automatically)\n"
                "• Tell me which AutoMix project to analyze (e.g. 'match the spectrum for project X')"
            ),
            "result": result,
        }

    eq_recs = result.get("eq_recommendations", [])
    summary_parts = [
        f"I've analyzed your mix against the **{genre}** commercial reference curve "
        f"across {result.get('bands_analyzed', 0)} frequency bands.\n"
    ]
    if eq_recs:
        summary_parts.append("Here are my EQ recommendations:\n")
        for rec in eq_recs[:5]:
            summary_parts.append(f"• {rec}\n")
    else:
        summary_parts.append("Your spectral balance looks solid — no major deviations from the target curve.")

    return {
        "agent": "ltas_matcher",
        "status": "completed",
        "message": "\n".join(summary_parts),
        "result": result,
    }


def _dispatch_audiogen(**kwargs: Any) -> Dict[str, Any]:
    """Dispatch to AudioGen for loop/song generation."""
    import re
    from kenn.ableton_osc_bridge import live_client
    import audiogen_bridge

    query = kwargs.get("query", "")

    # Parse target track index (1-based from user input, converted to 0-based index)
    track_match = re.search(r"\btrack\s*(\d+)\b", query, re.I)
    target_track_idx = int(track_match.group(1)) - 1 if track_match else None

    # Parse tempo
    bpm_match = re.search(r"\b(\d+)\s*bpms?\b", query, re.I)
    bpm = int(bpm_match.group(1)) if bpm_match else 120

    # Parse bar count (default to 4 bars)
    bars_match = re.search(r"\b(\d+)\s*bars?\b", query, re.I)
    bars = int(bars_match.group(1)) if bars_match else 4

    # Infer emotion/profile for generator (using bridge's native helper)
    emotion = audiogen_bridge.infer_emotion(query)

    # Trigger loop generation
    try:
        gen = audiogen_bridge.generate_for_kenn(query, emotion=emotion, bars=bars)
    except Exception as exc:
        return {
            "agent": "audiogen",
            "status": "failed",
            "message": f"AudioGen loop generation failed: {exc}",
            "query": query,
        }

    if not gen.get("ok"):
        return {
            "agent": "audiogen",
            "status": "failed",
            "message": gen.get("error", "AudioGen loop generation failed."),
            "query": query,
        }

    wav_path = gen.get("wav_path", "")
    src = gen.get("src", "")
    portfolio_title = (gen.get("portfolio_entry") or {}).get("title", "AudioGen loop")

    load_message = ""
    load_success = False

    # If target track index is requested, send the OSC clip loading command
    if target_track_idx is not None and wav_path:
        # Load clip via OSC
        try:
            # We assume clip slot 0 for simplicity (first row)
            clip_slot_idx = 0
            success = live_client.load_clip(target_track_idx, clip_slot_idx, wav_path)
            if success:
                load_success = True
                load_message = f" Successfully dispatched OSC command to load the clip onto track {target_track_idx + 1} (slot {clip_slot_idx + 1})."
            else:
                load_message = " Could not send OSC command to load clip onto track; Ableton Live OSC client offline."
        except Exception as exc:
            load_message = f" Failed to dispatch clip to Ableton: {exc}"

    message = (
        f"I've generated a new {bars}-bar loop at {bpm} BPM with the '{emotion}' profile!\n\n"
        f"• **WAV Rendered**: `{wav_path}`\n"
        f"• **Portfolio Entry**: {portfolio_title}\n"
    )
    if load_message:
        message += f"• **Ableton Status**:{load_message}"
    else:
        message += "\n(You can also specify a track to load it into, e.g. *'...and load to track 2'*)."

    return {
        "agent": "audiogen",
        "status": "success" if (target_track_idx is None or load_success) else "connected",
        "message": message,
        "query": query,
        "result": {
            "ok": True,
            "wav_path": wav_path,
            "src": src,
            "target_track_index": target_track_idx,
            "load_success": load_success,
            "emotion": emotion,
            "bars": bars,
            "bpm": bpm,
        }
    }


_ABLETON_WRITE_INTENT_RE = re.compile(
    r"\b(set_volume|volume\s+level|set_pan|pan\s+level|set_parameter|"
    r"device\s+parameter|create_device|create\s+device|sidechain|"
    r"set_mute|unmute|set_solo|unsolo|set_arm|record[\s-]?arm|disarm|"
    r"mute|solo|start_playback|stop_playback|set_tempo|playback|"
    r"transport|launch_clip|launch_scene)\b"
    # Bare "clip"/"scene" alone would false-positive on a read query like
    # "show my ableton session, especially the clip on track 2" -- require
    # the same launch/fire/play/trigger verb the classify()-level pattern
    # above requires, not just the noun.
    r"|\b(?:set|change)\b.*\btempo\b"
    r"|\b(?:launch|fire|play|trigger)\b.*\b(?:clip|scene)\b"
    # Macro control: require "macro N ... to <value>", not a bare mention
    # -- "what does macro 2 do on this synth?" is a genuine question, not
    # a write request, and has no "to <number>" target value in it.
    r"|\bset_macro\b"
    r"|\bmacro\s*\d+\b.*\bto\s+\d"
    r"|\bcreate_scene\b"
    r"|\b(?:create|add|new)\b.*\bscene\b",
    re.I,
)


def _dispatch_ableton(**kwargs: Any) -> Dict[str, Any]:
    """Dispatch to the Ableton OSC controller.

    Found 2026-08-06: this always queried and reported session state, even
    for an explicit write request like "set_volume on track 3 to volume
    0.85" (exactly what Mixing Doctor's clickable fix buttons send as a
    chat message -- see mixing_doctor.py's fix_action strings). The write
    itself never happened; clicking "Fix" silently did nothing. The actual
    parsing + execution + policy-gate logic already existed correctly in
    autonomous_agent.py's KennAutonomousAgent.run_agent_loop() (reachable
    via a completely separate HTTP route, /api/kenn/autonomous-execute),
    so this reuses it directly for write-shaped queries rather than
    duplicating the same regex parsing here.
    """
    query = str(kwargs.get("query", ""))
    if _ABLETON_WRITE_INTENT_RE.search(query):
        from kenn.autonomous_agent import KennAutonomousAgent

        agent_result = KennAutonomousAgent().run_agent_loop(user_prompt=query)
        return {
            "agent": "ableton_controller",
            "status": "executed" if agent_result.get("ok") else "failed",
            "message": agent_result.get("advice", ""),
            "result": agent_result,
        }

    from kenn.autonomous_agent import tool_query_ableton_session

    result = tool_query_ableton_session()
    tracks = result.get("tracks", [])

    if result.get("status") == "connected" and tracks:
        # Item 1 (docs/KENN_WEEKLY_OPTIMIZATION_PLAN_2026-08-08.md): a
        # query naming a specific instrument ("why does the vocal sound
        # buried") used to get the exact same full-session dump as a
        # generic "show my session" -- narrow to the matching tracks when
        # the query names any, fall back to everything otherwise (never
        # the other way around).
        from kenn.core.track_relevance import relevant_tracks

        filtered = relevant_tracks(query, tracks)
        display_tracks = filtered if filtered is not None else tracks

        track_lines = []
        for i, t in enumerate(display_tracks):
            name = t.get("name", f"Track {i}")
            vol = t.get("volume", 0)
            pan = t.get("pan", 0)
            muted = "🔇" if t.get("muted") else "🔊"
            vol_bar = "█" * int(vol * 10) + "░" * (10 - int(vol * 10))
            track_lines.append(f"  {muted} **{name}** — Vol: [{vol_bar}] {vol:.2f} | Pan: {pan:+.2f}")

        if filtered is not None:
            header = (
                f"Here's what I found matching your question "
                f"({len(filtered)} of {len(tracks)} tracks — say "
                "\"show my whole session\" to see the rest):\n\n"
            )
        else:
            header = f"Here's your current Ableton session — {len(tracks)} tracks found:\n\n"

        return {
            "agent": "ableton_controller",
            "status": "connected",
            "message": (
                header
                + "\n".join(track_lines) + "\n\n"
                "I can adjust any track's volume, pan, or device parameters. "
                "Just tell me what you'd like to change."
            ),
            "result": result,
        }

    return {
        "agent": "ableton_controller",
        "status": "disconnected",
        "message": (
            "I tried to connect to Ableton Live but couldn't reach the OSC bridge. "
            "Make sure Ableton is running with LiveOSC enabled on port 11000, "
            "and I'll be able to query and control your session."
        ),
        "result": result,
    }


def _dispatch_arrangement(**kwargs: Any) -> Dict[str, Any]:
    """D3.4 (docs/KENN_FUTURE_PLAN.md Phase 3): suggest a song structure
    from the bar count(s) the user actually specified, then place it as
    real named scenes in the session if DAW writes are allowed.
    Deliberately presents the structure as a starting suggestion, not a
    claimed-correct arrangement -- see arrangement_planner.py's own
    docstring for why. Reuses tool_create_ableton_scene() (already
    gated behind _daw_write_denied()) for each scene rather than adding
    a second write path."""
    from kenn.core.arrangement_planner import (
        describe_structure,
        parse_arrangement_request,
        suggest_song_structure,
    )

    query = str(kwargs.get("query", ""))
    parsed = parse_arrangement_request(query)
    if not parsed:
        return {
            "agent": "arrangement_planner",
            "status": "clarify",
            "message": (
                "Tell me how many bars and I'll suggest a structure -- e.g. "
                '"build a 32-bar verse/chorus structure with a build-up at bar 17".'
            ),
        }

    sections = suggest_song_structure(parsed["total_bars"], parsed["build_up_bar"])
    description = describe_structure(sections)
    suggestion_header = (
        f"Here's a suggested {parsed['total_bars']}-bar structure "
        "(a starting point, not a definitive arrangement -- tell me if you want it different):\n\n"
        f"{description}"
    )

    from kenn.autonomous_agent import tool_create_ableton_scene

    created, errors, denied_message = [], [], ""
    for section in sections:
        result = tool_create_ableton_scene(name=section["name"])
        if result.get("status") == "denied":
            denied_message = result.get("error", "DAW writes are disabled")
            break
        if result.get("status") == "success":
            created.append(section["name"])
        else:
            errors.append(section["name"])

    # G6 (docs/KENN_IMPROVEMENT_PLAN.md): the structure itself (section
    # count, bar counts, build-up placement) is KENN's judgment call, not
    # a measured fact -- true whether or not real scenes got created, so
    # every branch below flags it the same way mix-review EQ suggestions
    # already do.
    if denied_message:
        return {
            "agent": "arrangement_planner",
            "status": "suggested_only",
            "message": f"{suggestion_header}\n\n{denied_message} -- enable DAW control to place these as real scenes.",
            "sections": sections,
            "contains_unvalidated_suggestions": True,
        }
    if created:
        message = f"{suggestion_header}\n\nCreated {len(created)} real scene(s) in your session: {', '.join(created)}."
        if errors:
            message += f" Could not create: {', '.join(errors)}."
        return {
            "agent": "arrangement_planner",
            "status": "created",
            "message": message,
            "sections": sections,
            "contains_unvalidated_suggestions": True,
        }
    return {
        "agent": "arrangement_planner",
        "status": "suggested_only",
        "message": f"{suggestion_header}\n\nCouldn't create real scenes ({', '.join(errors) or 'Ableton not connected'}).",
        "sections": sections,
        "contains_unvalidated_suggestions": True,
    }


def _dispatch_mixing_doctor(**kwargs: Any) -> Dict[str, Any]:
    """Dispatch to the Mixing Doctor for a session health report."""
    from kenn.mixing_doctor import get_mixing_alerts

    alerts = get_mixing_alerts()
    if alerts:
        alert_lines = []
        proposed_actions = []
        for a in alerts:
            label = a.get('track_name') or a.get('fix_label', 'Session')
            alert_lines.append(f"  ⚠️ **{label}** — {a['message']}")
            
            # Categorize the action type
            act_type = "other"
            fix_act = a.get("fix_action", "")
            if "volume" in fix_act:
                act_type = "set_volume"
            elif "pan" in fix_act:
                act_type = "set_pan"
            elif "sidechain" in fix_act:
                act_type = "sidechain"
            elif "create_device" in fix_act or "create device" in fix_act:
                act_type = "create_device"
                
            proposed_actions.append({
                "type": act_type,
                "label": a.get("fix_label", "Fix Issue"),
                "description": a["message"],
                "command": fix_act
            })
            
        return {
            "agent": "mixing_doctor",
            "status": "issues_found",
            "message": (
                f"The Mixing Doctor found **{len(alerts)} issue(s)** in your current session:\n\n"
                + "\n".join(alert_lines) + "\n\n"
                "I can fix any of these automatically — just say the word, or click the Fix buttons "
                "in the alert banner at the top of the chat."
            ),
            "alerts": alerts,
            "proposed_actions": proposed_actions,
        }

    return {
        "agent": "mixing_doctor",
        "status": "healthy",
        "message": (
            "The Mixing Doctor has given your session a clean bill of health! "
            "No clipping, phase issues, or low-end masking detected. "
            "I'm continuously monitoring in the background, so I'll let you know if anything comes up."
        ),
        "alerts": [],
    }


# ── Orchestrator ──────────────────────────────────────────────────

class KennOrchestrator:
    """Central dispatch brain — classifies intent and delegates to sub-agents."""

    def __init__(self) -> None:
        self.agents: Dict[str, SubAgent] = {}
        self._register_defaults()

    def _register_defaults(self) -> None:
        self.register(SubAgent(
            name="stem_separator",
            emoji="🔪",
            description="Splits a mix into individual stems (vocals, drums, bass, other) using Demucs AI",
            capabilities=["Stem separation", "Vocal isolation", "Drum extraction"],
            keywords=["separate", "split", "stems", "isolate", "extract", "vocal", "drums"],
            dispatch_fn=_dispatch_stem_separation,
        ))
        self.register(SubAgent(
            name="mix_reviewer",
            emoji="🎧",
            description="Analyses a mix for clipping, dynamics, frequency balance, stereo width, and phase issues",
            capabilities=["Mix analysis", "Clipping detection", "Loudness check", "Frequency balance"],
            keywords=["review", "analyse", "check", "assess", "mix", "master"],
            dispatch_fn=_dispatch_mix_review,
        ))
        self.register(SubAgent(
            name="ltas_matcher",
            emoji="🎛️",
            description="Compares your mix's spectral balance against commercial genre reference curves",
            capabilities=["LTAS spectrum analysis", "Genre matching", "EQ recommendations"],
            keywords=["spectrum", "ltas", "eq", "frequency", "match", "genre", "curve"],
            dispatch_fn=_dispatch_ltas_match,
        ))
        self.register(SubAgent(
            name="audiogen",
            emoji="🎵",
            description="Generates loops, beats, grooves, and full songs from text prompts using AI",
            capabilities=["Loop generation", "Beat creation", "Full song rendering"],
            keywords=["generate", "create", "loop", "beat", "groove", "melody", "bpm"],
            dispatch_fn=_dispatch_audiogen,
        ))
        self.register(SubAgent(
            name="ableton_controller",
            emoji="🔊",
            description="Queries and controls your Ableton Live session via OSC — volumes, pans, devices",
            capabilities=["Session query", "Volume control", "Pan control", "Device parameters"],
            keywords=["ableton", "session", "tracks", "volume", "pan", "daw", "fader"],
            dispatch_fn=_dispatch_ableton,
        ))
        self.register(SubAgent(
            name="mixing_doctor",
            emoji="🏥",
            description="Monitors your live session for clipping, phase, and masking issues in real-time",
            capabilities=["Clipping detection", "Phase monitoring", "Low-end masking alerts"],
            keywords=["mixing doctor", "health check", "clipping", "phase", "masking"],
            dispatch_fn=_dispatch_mixing_doctor,
        ))
        self.register(SubAgent(
            name="arrangement_planner",
            emoji="🗺️",
            description="Suggests a bar-numbered song structure (verse/chorus/build-up) and can place it as real scenes",
            capabilities=["Structure suggestion", "Real scene placement"],
            keywords=["structure", "arrangement", "verse", "chorus", "build-up", "bars"],
            dispatch_fn=_dispatch_arrangement,
        ))

    def register(self, agent: SubAgent) -> None:
        self.agents[agent.name] = agent

    def list_agents(self) -> List[Dict[str, Any]]:
        return [
            {
                "name": a.name,
                "emoji": a.emoji,
                "description": a.description,
                "capabilities": a.capabilities,
            }
            for a in self.agents.values()
        ]

    def classify(self, query: str) -> Optional[str]:
        """Classify user intent and return the matching sub-agent name, or None."""
        if not query:
            return None
        if _is_question_not_request(query):
            return None

        # Order matters — more specific patterns first
        if _matches_any(query, _MIXING_DOCTOR_PATTERNS):
            return "mixing_doctor"
        if _matches_any(query, _STEM_PATTERNS):
            return "stem_separator"
        if _matches_any(query, _MIX_REVIEW_PATTERNS):
            return "mix_reviewer"
        if _matches_any(query, _LTAS_PATTERNS):
            return "ltas_matcher"
        # Audiogen deliberately NOT classified here (2026-08-04, revised
        # 2026-08-05): _dispatch_audiogen() only handles the "loop" kind
        # (it has no branch for "full_song"/"clarify"), while
        # chat_answer.py's _answer_payload_raw() already calls the real,
        # fully-working chat_routing.audio_generation_payload() a bit
        # further down the same function -- which correctly classifies
        # loop/full-song/clarify requests and queues real render jobs.
        # Classifying "audiogen" here made dispatch() short-circuit before
        # that real path ever ran, breaking full-song requests entirely
        # (caught by test_audio_generation_full_song_queues_background_job).
        # The OSC track-loading that _dispatch_audiogen had (e.g. "...and
        # load it into track 2") was ported into audio_generation_payload's
        # loop branch so that capability isn't lost. The "audiogen" SubAgent
        # registration is left in place for list_agents()/capability
        # listing; it's just not reachable via classify() anymore.
        if _matches_any(query, _ARRANGEMENT_PATTERNS):
            return "arrangement_planner"
        if _matches_any(query, _ABLETON_PATTERNS):
            return "ableton_controller"

        return None

    def dispatch(self, query: str, **kwargs: Any) -> Optional[Dict[str, Any]]:
        """Classify and dispatch to the matching sub-agent. Returns None if no match."""
        agent_name = self.classify(query)
        if not agent_name:
            return None

        agent = self.agents[agent_name]
        request = AgentRequest.create(
            capability=f"kenn.agent.{agent.name}",
            objective=query,
            project_id=str(kwargs.get("project_id") or ""),
            trace_id=str(kwargs.get("correlation_id") or kwargs.get("trace_id") or ""),
            autonomy_level=str(kwargs.get("assistant_mode") or "suggest"),
        )
        result = agent.dispatch_fn(query=query, agent_request=request.to_dict(), **kwargs)
        agent_result = AgentResult.from_dispatch(request, agent=agent.name, payload=result)
        return {
            "orchestrated": True,
            "agent_name": agent.name,
            "agent_emoji": agent.emoji,
            "agent_description": agent.description,
            "agent_envelope": {
                "request": request.to_dict(),
                "result": agent_result.to_dict(),
            },
            **result,
        }


# Module-level singleton
_orchestrator: KennOrchestrator | None = None


def get_orchestrator() -> KennOrchestrator:
    global _orchestrator
    if _orchestrator is None:
        _orchestrator = KennOrchestrator()
    return _orchestrator
