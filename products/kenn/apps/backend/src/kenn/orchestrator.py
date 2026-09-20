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
    re.compile(r"\b(extract|pull\s*out)\b\s+[a-z]+(?:\s+[a-z]+)?\b", re.I),
    re.compile(r"\b(remove|cut)\b\s+(?:the\s+)?(?:vocals?|drums?|bass?|instrument)s?\b", re.I),
]

_MIX_REVIEW_PATTERNS = [
    re.compile(r"\b(review|analyz[ei]|check|assess|evaluat[ei]|audit)\b.*\b(mix(es)?|masters?|tracks?|songs?)\b", re.I),
    re.compile(r"\b(mix(es)?|masters?)\b.*\b(review|analys[ei]s|feedback|checks?)\b", re.I),
    re.compile(r"\bwhat'?s?\s+wrong\s+with\b.*\b(mix(es)?|masters?|tracks?)\b", re.I),
    re.compile(r"\b(clipping|headroom|dynamics|loudness|phase)\b.*\b(checks?|issues?|problems?)\b", re.I),
]

_LTAS_PATTERNS = [
    re.compile(r"\b(ltas|spectrum|spectral)\b.*\b(match(es)?|analys[ei]|compar[ei])\b", re.I),
    re.compile(r"\b(frequency|eq)\b.*\b(balance|match|target)\b.*\b(reference|commercial|genre|pop|rock|hiphop|jazz)s?\b", re.I),
    re.compile(r"\bmatch\b.*\b(genre|reference|commercial|pop|rock|hiphop|jazz)s?\b", re.I),
    re.compile(r"compare.*(?:commercial|genre|reference|pop|rock|hiphop|jazz)", re.I),
    re.compile(r"analy[sz].*?(?:commercial|genre|reference|pop|rock|hiphop|jazz)", re.I),
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
    re.compile(r"\b(set|adjust|change|tweak)\b.*\b(volume|pan|fader|level|send|dry|wet)\b.*\b(tracks?|ableton)?\b", re.I),
    re.compile(r"\btracks?\s*\d+\b.*\b(volume|pan|mute|solo|arm)\b", re.I),
    re.compile(r"\bshow\b.*\b(session|tracks?|projects?)\b", re.I),
    # Mute/solo/record-arm, either word order ("mute track 2" or "track 2
    # mute") -- added 2026-08-06 alongside real write execution for these;
    # pattern 3 above only catches the track-then-verb order.
    re.compile(r"\b(set_mute|unmute|set_solo|unsolo|set_arm|record[\s-]?arm|disarm)\b", re.I),
    re.compile(r"\b(mute|solo)\b.*\btracks?\b", re.I),
    re.compile(r"\btracks?\b.*\b(mute|solo)\b", re.I),
    # Typed Live command gateway actions that are not covered by the older
    # track/transport patterns above.  These are imperative requests only;
    # classify() exits first for information-shaped queries.
    re.compile(
        r"\b(?:add|insert|put|create|make)\b.{0,80}\b(?:eq(?:\s+eight)?|compressor|saturator|auto\s+filter|drum\s+buss|hybrid\s+reverb|echo|"
        r"midi\s+track|audio\s+track|return\s+track|device|macro)\b",
        re.I,
    ),
    re.compile(r"\b(duplicate|rename|revise|update|clear)\b.{0,80}\b(?:clip|notes?|track|scene)\b", re.I),
    re.compile(r"\b(?:set|adjust|change)\b.{0,80}\b(?:send|dry\s*/?\s*wet|parameter|threshold|ratio|attack|release|drive|resonance|eq_band|eq_gain)\b", re.I),
    re.compile(r"\b(?:add|remove|delete)\b.{0,40}\blocator\b", re.I),
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
    # Clip/scene launch -- added 2026-08-07 (D1.2). Requires the explicit
    # launch/fire/play/trigger verb next to clip/scene, not just either
    # word alone (e.g. "play the drum fill" without "clip"/"scene" doesn't
    # match here -- named-clip triggering is a future capability, not yet
    # built; this only covers indexed track/slot or scene-number launches).
    re.compile(r"\b(launch_clip|launch_scene)\b", re.I),
    re.compile(r"\b(launch|fire|play|trigger)\b.*\b(clip|scene)\b", re.I),
    # Macro knob control -- added 2026-08-07 (D1.3). Requires an explicit
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


# Device parameter and EQ band patterns for more granular control queries
_ABLETON_DEVICE_PATTERNS = [
    re.compile(r"\b(set|adjust|change)\b.{0,60}\b(gain|frequency|q|band|send|return)\b", re.I),
    re.compile(r"\b(color|colorize)\b.*\btrack\b", re.I),
    re.compile(r"\b(?:add|insert|put)\b.{0,60}\b(device|effect|instrument)\b", re.I),
    re.compile(r"\b(rename|revise|update)\b.{0,60}\b(track|channel)\b", re.I),
]

_MIXING_DOCTOR_PATTERNS = [
    re.compile(r"\b(mixing\s*doctors?|health\s*checks?|audit\s*sessions?)\b", re.I),
    re.compile(r"\b(check|scan|monitor)\b.*\b(clipping|phase|masking|issues?)\b", re.I),
]

# A broad current-session scan is a distinct read-only composition request.
# Keep it ahead of the generic Mix Review patterns: this should inspect the
# cached Live state and any explicitly supplied realtime evidence, not ask for
# an uploaded/rendered file.
_REALTIME_SESSION_REVIEW_PATTERNS = [
    re.compile(
        r"\b(scan|review|analys[ei]s|audit|check)\b.{0,48}\b(current|live|ableton)\b.{0,24}\b(session|mix)\b",
        re.I,
    ),
    re.compile(
        r"\b(current|live|ableton)\b.{0,24}\b(session|mix)\b.{0,48}\b(scan|review|analys[ei]s|audit|check)\b",
        re.I,
    ),
]

# Arrangement planning -- added 2026-08-07 (D3.4). Requires an explicit
# bar count next to a structure/arrangement word, matching
# arrangement_planner.parse_arrangement_request()'s own requirement --
# a bare bar-count mention ("this loop is 8 bars long") must not fire.
_ARRANGEMENT_PATTERNS = [
    # "32 bars structure" or "structure 32 bars" order
    re.compile(r"\b(structure|arrangement)\b.{0,40}\b\d+[\s-]?bars?\b", re.I),
    re.compile(r"\b\d+[\s-]?bars?\b.{0,40}\b(structure|arrangement)\b", re.I),
    re.compile(r"\b(build|create|make)\b.*\b\d+[\s-]?bars?\b.*\b(structure|arrangement|section)\b", re.I),
]


# Autonomous Producer ReAct Engine patterns — multi-step deliberate mix balancing
_AUTONOMOUS_PRODUCER_PATTERNS = [
    re.compile(r"\b(rebalance|balance)\b.{0,30}\b(mix(es)?|tracks?|session|levels?)\b", re.I),
    re.compile(r"\b(mix(es)?|tracks?|session)\b.{0,30}\b(rebalance|balance)\b", re.I),
    re.compile(r"\b(autonomous|react)\b.{0,30}\b(mix(ing)?|producer|balance|reasoning|agent)\b", re.I),
    re.compile(r"\b(fix|optimize|clean\s*up|polish)\b.{0,30}\b(the\s+)?(mix|balance|session)\b", re.I),
    re.compile(r"\b(solve|resolve|fix|unmask)\b.{0,30}\b(masking|clashes?|frequency\s+conflicts?)\b", re.I),
    re.compile(r"\blevel\b.{0,20}\b(the\s+)?(mix|session|tracks)\b", re.I),
]

_RACK_SYNTHESIZER_PATTERNS = [
    re.compile(r"\b(build|insert|create|add|put|synthesize)\b.{0,40}\b(effect\s*rack|audio\s*rack|audio\s*effect\s*rack)\b", re.I),
    re.compile(r"\b(build|insert|create|add|put)\b.{0,40}\b(neuro\s*reese|ott\s*(drum)?\s*smasher|midside|808\s*saturator|vocal\s*air|tape\s*warmer|glue\s*punch|acid\s*lead|sub\s*monomaker|vocal\s*presence)\b", re.I),
    re.compile(r"\b(neuro\s*reese|ott\s*smasher|midside\s*widener|clean\s*808|vocal\s*air|tape\s*warmer|acid\s*303|sub\s*monomaker)\b.{0,30}\b(rack|strip)\b", re.I),
    re.compile(r"\b(list|show|what)\b.{0,30}\b(available\s+)?(racks|templates)\b", re.I),
]

_NEURAL_MIDI_PATTERNS = [
    re.compile(r"\b(generat|creat|make|write|compose)\b.{0,30}\b(bouncy|driving|sustained|drone)?\s*(bassline|bass\s*line|bass\s*pattern)\b", re.I),
    re.compile(r"\b(bouncy|driving|sustained|drone)\s*(bassline|bass\s*line)\b", re.I),
    re.compile(r"\b(humanize|apply|add|put)\b.{0,30}\b(groove|swing|lofi_swing|boombap|shuffle)\b", re.I),
    re.compile(r"\b(detect|identify|find)\b.{0,30}\b(key|scale)\b.*\b(notes?|chords?|midi)\b", re.I),
]

_SURGICAL_MASKING_PATTERNS = [
    re.compile(r"\b(fix|solve|resolve|carve|unmask)\b.{0,30}\b(masking|clash(es)?|sub\s*and\s*kick|kick\s*and\s*sub|vocal\s*presence|low\s*mid\s*mud)\b", re.I),
    re.compile(r"\b(surgical|acoustic)\b.{0,30}\b(remediation|unmasking|carving|doctor)\b", re.I),
    re.compile(r"\b(clean\s*up|remove)\b.{0,30}\b(mud|rumble|clash(es)?)\b", re.I),
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

    if result.get("status") == "unavailable":
        return None

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

    # Clip loading is intentionally disabled until it has a typed,
    # reversible proposal and verified readback path. Generating audio must
    # never create an implicit Ableton mutation as a side effect.
    if target_track_idx is not None and wav_path:
        load_message = " Automatic Ableton clip loading is disabled until an exact, typed, reversible clip-loading proposal exists."

    message = (
        f"I've generated a new {bars}-bar loop at {bpm} BPM with the '{emotion}' profile!\n\n"
        f"• **WAV Rendered**: `{wav_path}`\n"
        f"• **Portfolio Entry**: {portfolio_title}\n"
    )
    if load_message:
        message += f"• **Ableton Status**:{load_message}"
    else:
        message += "\n(Generated audio is available locally; automatic Ableton loading remains disabled.)"

    return {
        "agent": "audiogen",
        "status": "success",
        "message": message,
        "query": query,
        "result": {
            "ok": True,
            "wav_path": wav_path,
            "src": src,
            "target_track_index": target_track_idx,
            "load_success": load_success,
            "ableton_load_status": "disabled" if target_track_idx is not None else "not_requested",
            "emotion": emotion,
            "bars": bars,
            "bpm": bpm,
        }
    }


_ABLETON_WRITE_INTENT_RE = re.compile(
    r"\b(set_volume|volume\s+level|set_pan|pan\s+level|set_parameter|"
    r"device\s+parameter|create_device|create\s+device|sidechain|"
    r"add|insert|duplicate|rename|revise|update|clear|"
    r"midi\s+track|audio\s+track|return\s+track|eq(?:\s+eight)?|compressor|saturator|auto\s+filter|drum\s+buss|hybrid\s+reverb|echo|"
    r"dry\s*/?\s*wet|send|locator|"
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

    Route write-shaped chat requests through the same canonical command
    gateway used by the HTTP and MCP surfaces.  This keeps ordinary chat in
    sync with the current typed command vocabulary (devices, clips, sends,
    locators, track creation, and MIDI revision) and ensures it receives the
    same proposal/confirmation/readback contract.  The legacy autonomous
    agent remains available for non-Live specialist tools, but is not a
    second Ableton write path.
    """
    query = str(kwargs.get("query", ""))
    from kenn.core.subjective_translator import SubjectiveTranslator
    if _ABLETON_WRITE_INTENT_RE.search(query) or SubjectiveTranslator.can_translate(query):
        from kenn.core.live_command import handle_command

        session_id = str(kwargs.get("session_id") or "orchestrated-live")[:128]
        command_result = handle_command(
            query,
            session_id=session_id,
            # Orchestration is a user-facing command boundary.  Keep the
            # deterministic parser authoritative here; any optional model
            # planning belongs to the typed HTTP/MCP command surfaces.
            allow_llm=False,
        )
        return {
            "agent": "ableton_controller",
            "status": command_result.get("status", "failed"),
            "message": command_result.get("answer", "I could not prepare that Ableton request."),
            "result": command_result,
            "proposal": command_result.get("proposal"),
            "confirmation_token": command_result.get("confirmation_token") or (command_result.get("proposal") or {}).get("confirmation_token", ""),
            "requires_confirmation": bool(
                command_result.get("confirmation_required")
                or command_result.get("status") == "confirmation_required"
            ),
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
    from kenn.mixing_doctor import get_latest_session_state, get_mixing_alerts

    state = get_latest_session_state()
    if not isinstance(state, dict) or state.get("status") not in {"connected", "dispatched"}:
        return {
            "agent": "mixing_doctor",
            "status": "unavailable",
            "message": (
                "I can't scan the current Ableton session yet because the Live connection "
                "is unavailable. I won't infer clipping, masking, phase, or headroom from "
                "missing session data."
            ),
            "alerts": [],
            "proposed_actions": [],
        }
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
                "I can prepare a confirmation-bound change where a supported action exists; "
                "otherwise use the alert's inspection guidance."
            ),
            "alerts": alerts,
            "proposed_actions": proposed_actions,
        }

    return {
        "agent": "mixing_doctor",
        "status": "healthy",
        "message": (
            "The latest Live snapshot has no active structural or instantaneous-meter advisories. "
            "This does not measure audio-rate clipping, masking, phase, LUFS, true peak, or "
            "spectral balance; those require the appropriate Mix Review or meter evidence. "
            "I'm continuously monitoring the available session state."
        ),
        "alerts": [],
    }


def _realtime_knowledge_guidance(query: str, report: Dict[str, Any]) -> list[dict[str, Any]]:
    """Backward-compatible orchestrator wrapper for shared source guidance."""
    from kenn.core.realtime_session_review import realtime_knowledge_guidance
    return realtime_knowledge_guidance(query, report)


def _dispatch_realtime_session_review(**kwargs: Any) -> Dict[str, Any]:
    """Compose the current read-only Live/mix evidence for chat requests."""
    from kenn.core.realtime_session_review import build_realtime_session_review
    from kenn.mixing_doctor import get_latest_session_state, get_mixing_alerts

    session = get_latest_session_state()
    plugin_review = None
    plugin_recommendations = []
    plugin_session_id = str(kwargs.get("plugin_session_id") or "").strip()[:128]
    if plugin_session_id:
        from kenn.plugin_handoff import live_review_summary
        plugin_review = live_review_summary(plugin_session_id)
        plugin_context = plugin_review.get("live_context") if isinstance(plugin_review, dict) else None
        if isinstance(plugin_context, dict):
            from kenn.core.mcp_facade import _realtime_mix_recommendations
            plugin_recommendations = [
                item.payload() for item in _realtime_mix_recommendations(plugin_context)
            ]

    report = build_realtime_session_review(
        session,
        mixing_alerts=get_mixing_alerts(),
        plugin_review=plugin_review,
        plugin_recommendations=plugin_recommendations,
    )
    if not report.get("ok"):
        return {
            "agent": "realtime_session_reviewer",
            "status": "unavailable",
            "message": (
                "I can't scan the current Ableton session because its cached Live state is unavailable. "
                "I won't infer audio problems from missing data."
            ),
            "report": report,
            "sources": [],
        }

    report["knowledge_guidance"] = _realtime_knowledge_guidance(
        str(kwargs.get("query") or ""), report,
    )

    live_session = report.get("live_session") if isinstance(report.get("live_session"), dict) else {}
    mixing_doctor = report.get("mixing_doctor") if isinstance(report.get("mixing_doctor"), dict) else {}
    project_health = report.get("project_health") if isinstance(report.get("project_health"), dict) else {}
    plugin_bus = report.get("plugin_bus") if isinstance(report.get("plugin_bus"), dict) else None
    alert_count = len(mixing_doctor.get("alerts") or [])
    project_count = len(project_health.get("recommendations") or [])
    plugin_count = len(plugin_bus.get("recommendations") or []) if plugin_bus else 0
    message = (
        f"Realtime session review is current: {live_session.get('track_count', 0)} track(s) observed, "
        f"{alert_count} Mixing Doctor advisory/advisories, and {project_count} project-health finding(s)."
    )
    if plugin_bus:
        message += f" The validated plug-in bus contributed {plugin_count} separate advisory finding(s)."
    message += (
        " This is a read-only composition of available evidence; it does not measure audio-rate clipping, "
        "masking, phase, LUFS, true peak, or full spectral balance unless a separately validated audio review "
        "is supplied."
    )

    def recommendation_lines(items: Any, scope: str) -> list[str]:
        lines: list[str] = []
        for item in items if isinstance(items, list) else []:
            if not isinstance(item, dict):
                continue
            title = str(item.get("title") or item.get("type") or "Advisory").strip()[:96]
            detail = str(item.get("message") or item.get("description") or "").strip()[:320]
            action = str(item.get("suggestedAction") or "").strip()[:320]
            if not detail and not action:
                continue
            line = f"- [{scope}] {title}: {detail or action}"
            if detail and action:
                line += f" Next check: {action}"
            lines.append(line)
            if len(lines) >= 3:
                break
        return lines

    advice_sections: list[str] = []
    alert_lines = recommendation_lines(mixing_doctor.get("alerts"), "cached Live")
    if alert_lines:
        advice_sections.append("Mixing Doctor advisories:\n" + "\n".join(alert_lines))
    project_lines = recommendation_lines(project_health.get("recommendations"), "project health")
    if project_lines:
        advice_sections.append("Project-health findings:\n" + "\n".join(project_lines))
    if plugin_bus:
        plugin_lines = recommendation_lines(plugin_bus.get("recommendations"), "plug-in bus")
        if plugin_lines:
            advice_sections.append("Validated plug-in-bus advisories:\n" + "\n".join(plugin_lines))
    if advice_sections:
        message += "\n\n" + "\n\n".join(advice_sections)
    knowledge_lines = [
        f"- [{item['evidence_label']}] {item['source']}: {item['excerpt']}"
        for item in report["knowledge_guidance"]
    ]
    if knowledge_lines:
        message += "\n\nKnowledge-grounded next checks (advisory):\n" + "\n".join(knowledge_lines)
    return {
        "agent": "realtime_session_reviewer",
        "status": "current",
        "message": message,
        "report": report,
        "sources": list(report.get("knowledge_guidance") or []),
    }


def _dispatch_autonomous_producer(**kwargs: Any) -> Dict[str, Any]:
    """Dispatch to the Multi-Step ReAct Autonomous Producer Engine."""
    from kenn.autonomous_agent import KennAutonomousAgent

    query = str(kwargs.get("query", ""))
    session_id = str(kwargs.get("session_id") or "orchestrated-producer")[:128]
    snapshot = kwargs.get("session_snapshot")
    max_iterations = int(kwargs.get("max_iterations", 5))

    agent = KennAutonomousAgent()
    res = agent.react_deliberate(
        objective=query,
        session_id=session_id,
        max_iterations=max_iterations,
        session_snapshot=snapshot,
    )

    proposal = res.get("proposal")
    token = res.get("confirmation_token", "") or (proposal or {}).get("confirmation_token", "")
    requires_conf = bool(res.get("confirmation_required") or res.get("status") == "confirmation_required")

    return {
        "agent": "autonomous_producer",
        "status": res.get("status", "completed" if res.get("ok") else "failed"),
        "message": res.get("answer") or res.get("advice") or "Autonomous deliberation complete.",
        "result": res,
        "proposal": proposal,
        "confirmation_token": token,
        "requires_confirmation": requires_conf,
        "trajectory": res.get("trajectory", []),
    }


def _dispatch_rack_synthesizer(**kwargs: Any) -> Dict[str, Any]:
    """Dispatch to the Dynamic Pro Audio Effect Rack Synthesizer."""
    from kenn.core.rack_builder import list_available_racks, get_rack_template, synthesize_rack_proposal
    from kenn.mixing_doctor import get_latest_session_state

    query = str(kwargs.get("query", "")).lower()
    session_id = str(kwargs.get("session_id", "rack_session"))[:128]

    # Check if user just wants a catalog listing
    if any(kw in query for kw in {"list", "show", "what", "available"}) and "rack" in query:
        racks = list_available_racks()
        rack_bullets = []
        for r in racks:
            rack_bullets.append(f"- **{r['name']}** (`{r['id']}`) — *{r['category'].title()}*: {r['description']} ({r['macro_count']} macros, {r['variation_count']} snapshots)")
        msg = (
            f"🎛️ **KENN Pro Audio Effect Rack Synthesizer Library** ({len(racks)} Racks):\n\n"
            + "\n".join(rack_bullets)
            + "\n\nTo build any rack into your current session, just ask: e.g. *'build a neuro reese rack on track 1'* or *'put an OTT drum smasher on the drum bus'*."
        )
        return {
            "agent": "rack_synthesizer",
            "status": "catalog",
            "message": msg,
            "racks": racks,
        }

    # Identify target rack template
    matched_id = None
    if "neuro" in query and "reese" in query:
        matched_id = "neuro_reese_saturator"
    elif "ott" in query or "smasher" in query:
        matched_id = "ott_drum_smasher"
    elif "midside" in query or "widener" in query or "stereo" in query:
        matched_id = "midside_stereo_widener"
    elif "808" in query:
        matched_id = "clean_808_saturator"
    elif "vocal" in query and "air" in query:
        matched_id = "dynamic_vocal_air"
    elif "vocal" in query and ("presence" in query or "strip" in query):
        matched_id = "vocal_presence_strip"
    elif "tape" in query or "cassette" in query or "lofi" in query:
        matched_id = "lofi_tape_warmer"
    elif "parallel" in query or "glue" in query or "punch" in query:
        matched_id = "parallel_glue_punch"
    elif "acid" in query or "303" in query:
        matched_id = "acid_resonance_lead"
    elif "sub" in query and ("mono" in query or "sculptor" in query or "maker" in query):
        matched_id = "sub_bass_monomaker"
    elif "drum" in query and "crush" in query:
        matched_id = "nyc_drum_crush_rack"
    elif "neuro" in query or "bass" in query:
        matched_id = "neuro_bass_rack"

    if not matched_id:
        matched_id = "neuro_reese_saturator"

    template = get_rack_template(matched_id)
    if not template:
        return {
            "agent": "rack_synthesizer",
            "status": "not_found",
            "message": f"Could not find rack template matching '{matched_id}'. Ask me to 'list available racks' to see options.",
        }

    # Resolve track index and name from session or query
    state = get_latest_session_state() or {"status": "offline", "tracks": []}
    tracks = state.get("tracks", [])

    # Try finding track number in query: e.g. "track 2" or "track 0"
    target_index = 0
    target_name = ""
    trk_match = re.search(r"\btrack\s*(\d+)\b", query, re.I)
    if trk_match:
        target_index = int(trk_match.group(1))
        if target_index < len(tracks):
            target_name = tracks[target_index].get("name", f"Track {target_index}")
    else:
        # Infer target track from rack category using track names
        cat = template.get("category", "")
        for t in tracks:
            tname = str(t.get("name", "")).lower()
            if cat == "bass" and any(k in tname for k in ["bass", "sub", "808", "low"]):
                target_index = t.get("index", 0)
                target_name = t.get("name", f"Track {target_index}")
                break
            elif cat == "drums" and any(k in tname for k in ["drum", "beat", "perc"]):
                target_index = t.get("index", 0)
                target_name = t.get("name", f"Track {target_index}")
                break
            elif cat == "vocals" and any(k in tname for k in ["vox", "vocal", "lead vox"]):
                target_index = t.get("index", 0)
                target_name = t.get("name", f"Track {target_index}")
                break

    if not target_name and tracks:
        target_index = min(target_index, len(tracks) - 1)
        target_name = tracks[target_index].get("name", f"Track {target_index}")
    elif not target_name:
        target_name = f"Track {target_index}"

    res = synthesize_rack_proposal(matched_id, track_index=target_index, track_name=target_name, session_id=session_id)
    if not res.get("ok"):
        return {
            "agent": "rack_synthesizer",
            "status": "failed",
            "message": f"Failed to synthesize rack proposal: {res.get('error')}",
        }

    prop = res["proposal"]
    token = prop["confirmation_token"]

    var_names = [f"`{v['name']}`" for v in prop.get("variations", [])]
    macros = [f"Macro {m['index']+1} ({m['name']} -> {m['target_device']} {m['target_parameter']})" for m in template.get("macros", [])]

    msg = (
        f"🎛️ **Synthesized Audio Effect Rack**: **{template['name']}** for **{target_name}** (Track {target_index})\n\n"
        f"*{template['description']}*\n\n"
        f"• **Chains**: {len(template.get('chains', []))} parallel processing path(s)\n"
        f"• **Macro Knobs**: 8 calibrated parameters pre-bound to target Ableton devices:\n"
        f"  - " + "\n  - ".join(macros[:4]) + "\n  - ...\n"
        f"• **Variation Snapshots**: {len(var_names)} pre-calibrated flavors ({', '.join(var_names)})\n\n"
        f"🛡️ Single-token confirmation gated (`{token}`). Click confirm to build directly into your Live session."
    )

    return {
        "agent": "rack_synthesizer",
        "status": "confirmation_required",
        "message": msg,
        "proposal": prop,
        "confirmation_token": token,
        "requires_confirmation": True,
        "is_rack_synthesis": True,
    }


def _dispatch_neural_midi(**kwargs: Any) -> Dict[str, Any]:
    """Dispatch to the AudioGen Neural MIDI & Groove Generator."""
    from kenn.core.generative_midi import generate_audiogen_bassline, apply_audiogen_groove
    from kenn.mixing_doctor import get_latest_session_state
    from kenn.core.session_world_model import SessionWorldModel

    query = str(kwargs.get("query", ""))
    lower_query = query.lower()
    session_id = str(kwargs.get("session_id", "midi_session"))[:128]
    state = get_latest_session_state() or {"status": "offline", "tracks": []}

    # 1. Harmonic extraction (root & scale)
    harmonics = SessionWorldModel.harmonic_context(state)
    root = harmonics.get("root_note", "C")
    scale = harmonics.get("scale_name", "minor").lower()

    key_match = re.search(r"\b([A-Ga-g][#b]?)\s+(major|minor|dorian|mixolydian|phrygian|lydian)\b", query, re.I)
    if key_match:
        root = key_match.group(1).upper()
        scale = key_match.group(2).lower()

    # 2. Style extraction
    style = "bouncy"
    if "driving" in lower_query:
        style = "driving"
    elif "sustained" in lower_query or "long" in lower_query:
        style = "sustained"
    elif "drone" in lower_query:
        style = "drone"

    # 3. Groove extraction
    groove = "straight"
    if "lofi" in lower_query or "swing" in lower_query:
        groove = "lofi_swing"
    elif "boombap" in lower_query or "boom bap" in lower_query:
        groove = "hiphop_boombap"
    elif "edm" in lower_query or "shuffle" in lower_query:
        groove = "edm_shuffle"

    # 4. Bars extraction
    bars = 2
    bar_match = re.search(r"\b(\d+)\s*bars?\b", lower_query)
    if bar_match:
        bars = int(bar_match.group(1))

    # Generate notes via AudioGen engine
    notes = generate_audiogen_bassline(root=root, scale_name=scale, style=style, bars=bars, groove=groove)

    # Resolve target track (find bass track or first MIDI track)
    tracks = state.get("tracks", [])
    target_index = 0
    target_name = "Bass"
    for t in tracks:
        tname = str(t.get("name", "")).lower()
        if any(k in tname for k in ["bass", "sub", "808"]):
            target_index = t.get("index", 0)
            target_name = t.get("name", f"Track {target_index}")
            break

    # Build MIDI clip proposal
    import hashlib
    token_src = f"{session_id}_{root}_{scale}_{style}_{len(notes)}"
    token = f"midi_prop_{hashlib.sha256(token_src.encode()).hexdigest()[:16]}"

    proposal = {
        "schema": "kenn.ableton_midi_clip_proposal.v1",
        "session_id": session_id,
        "track_index": target_index,
        "track_name": target_name,
        "clip_slot_index": 0,
        "clip_name": f"KENN {root} {scale.title()} {style.title()} Bass",
        "length_beats": float(bars * 4.0),
        "notes": notes,
        "root_note": root,
        "scale_name": scale,
        "quantize_to_scale": True,
        "requires_confirmation": True,
        "confirmation_token": token,
        "is_midi_proposal": True,
    }

    msg = (
        f"🎵 **Generated Neural AudioGen Bassline**: **{root} {scale.title()}** ({style.title()} Style, {bars} Bars)\n\n"
        f"• **Harmonic Lock**: Scaled to `{root} {scale.title()}` with {len(notes)} quantized notes\n"
        f"• **Groove Feel**: Applied `{groove}` micro-timing and dynamic velocity humanization\n"
        f"• **Target**: `{target_name}` (Track {target_index}), Clip Slot 1\n"
        f"• **Tempo**: {state.get('tempo', 120.0)} BPM\n\n"
        f"🛡️ Confirmation token issued (`{token}`). Click confirm to insert directly into Ableton Live."
    )

    return {
        "agent": "neural_midi_generator",
        "status": "confirmation_required",
        "message": msg,
        "proposal": proposal,
        "confirmation_token": token,
        "requires_confirmation": True,
        "is_midi_proposal": True,
    }


def _dispatch_surgical_masking(**kwargs: Any) -> Dict[str, Any]:
    """Dispatch to the Closed-Loop Surgical Masking & Diagnostic Doctor."""
    from kenn.core.session_doctor import SessionDoctor
    from kenn.mixing_doctor import get_latest_session_state
    from kenn.plugin_handoff import live_context_summary

    session_id = str(kwargs.get("session_id", "masking_remedy_session"))[:128]
    state = get_latest_session_state() or {"status": "offline", "tracks": []}
    telemetry = live_context_summary(session_id)

    res = SessionDoctor.formulate_surgical_remediation_proposal(state, meters=telemetry, session_id=session_id)
    if not res.get("ok"):
        return {
            "agent": "surgical_masking_doctor",
            "status": "failed",
            "message": f"Diagnostic analysis failed: {res.get('error', 'Unknown error')}",
        }

    prop = res["proposal"]
    token = prop["confirmation_token"]
    metrics = prop.get("predicted_metrics", {})
    steps = prop.get("steps", [])

    step_lines = []
    for i, s in enumerate(steps[:5], 1):
        act = s.get("action")
        tgt = s.get("track_name", f"Track {s.get('track_index')}")
        reason = s.get("reason", "")
        step_lines.append(f"  {i}. **{act}** on `{tgt}`: {reason}")

    msg = (
        f"🩺 **KENN Closed-Loop Surgical Masking & Acoustic Doctor**\n\n"
        f"{res.get('audit_summary', '')}\n\n"
        f"✦ **Predicted Acoustic Improvements**:\n"
        f"• **Masking Clashes Resolved**: -{metrics.get('masking_reduction_percent', 0.0)}% psychoacoustic competition\n"
        f"• **Dynamic Headroom Reclaimed**: +{metrics.get('headroom_reclaimed_db', 0.0)} dB for summing\n"
        f"• **Mono Phase Correlation**: +{metrics.get('mono_correlation_delta', 0.0):.2f} alignment\n\n"
        f"✦ **Proposed Surgical Recipe** ({len(steps)} actions):\n"
        + "\n".join(step_lines) + "\n\n"
        f"🛡️ Confirmation token issued (`{token}`). All changes strictly $\\le \\pm 3.0\\text{{ dB}}$, master fader protected.\n"
        f"Confirm to apply atomically with 1-click rollback."
    )

    return {
        "agent": "surgical_masking_doctor",
        "status": "confirmation_required",
        "message": msg,
        "proposal": prop,
        "confirmation_token": token,
        "requires_confirmation": True,
        "is_doctor_remediation": True,
    }



# ── Orchestrator ──────────────────────────────────────────────────

class KennOrchestrator:
    """Central dispatch brain — classifies intent and delegates to sub-agents."""

    def __init__(self) -> None:
        self.agents: Dict[str, SubAgent] = {}
        self._register_defaults()

    def _register_defaults(self) -> None:
        self.register(SubAgent(
            name="autonomous_producer",
            emoji="🧠",
            description="Multi-Step ReAct Autonomous Producer Brain — deliberates over SessionWorldModel and Genelec GLM acoustic calibration to balance and optimize the mix",
            capabilities=[
                "Multi-step ReAct deliberation",
                "Session world modeling",
                "Closed-loop acoustic calibration",
                "Masking & frequency territory resolution",
                "Staged safe mix proposals",
            ],
            keywords=["balance mix", "rebalance", "autonomous mix", "producer brain", "fix mix", "level mix", "unmask"],
            dispatch_fn=_dispatch_autonomous_producer,
        ))
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
            description="Monitors available Live state for headroom and bounded mix-health advisories",
            capabilities=["Instantaneous headroom advisories", "Pan-state checks", "Low-end overlap candidates"],
            keywords=["mixing doctor", "health check", "clipping", "phase", "masking"],
            dispatch_fn=_dispatch_mixing_doctor,
        ))
        self.register(SubAgent(
            name="realtime_session_reviewer",
            emoji="📡",
            description="Composes a read-only review of the cached Ableton session and validated realtime mix evidence",
            capabilities=["Current session scan", "Scope-labelled mix evidence", "Read-only session advice"],
            keywords=["scan current session", "realtime session review", "live mix review"],
            dispatch_fn=_dispatch_realtime_session_review,
        ))
        self.register(SubAgent(
            name="arrangement_planner",
            emoji="🗺️",
            description="Suggests a bar-numbered song structure (verse/chorus/build-up) and can place it as real scenes",
            capabilities=["Structure suggestion", "Real scene placement"],
            keywords=["structure", "arrangement", "verse", "chorus", "build-up", "bars"],
            dispatch_fn=_dispatch_arrangement,
        ))
        self.register(SubAgent(
            name="rack_synthesizer",
            emoji="🎛️",
            description="Synthesizes 12 production-grade multi-chain Audio Effect Racks with 8 macro bindings and variation snapshots",
            capabilities=["12 Pro Effect Racks", "Macro Target Binding", "Multi-Chain Splitting", "Variation Snapshots"],
            keywords=["effect rack", "neuro reese", "ott smasher", "midside widener", "clean 808", "vocal air", "lofi tape", "acid lead"],
            dispatch_fn=_dispatch_rack_synthesizer,
        ))
        self.register(SubAgent(
            name="neural_midi_generator",
            emoji="🎹",
            description="Generates harmonic scale-quantized basslines and applies AudioGen groove humanization",
            capabilities=["AudioGen Basslines", "Scale Quantization", "Micro-Timing Grooves", "Swing Humanization"],
            keywords=["bassline", "bass pattern", "groove", "lofi swing", "boombap", "detect scale"],
            dispatch_fn=_dispatch_neural_midi,
        ))
        self.register(SubAgent(
            name="surgical_masking_doctor",
            emoji="🩺",
            description="Diagnoses 40-band ERB psychoacoustic masking and formulates surgical unmasking and mud cleanup proposals",
            capabilities=["40-Band ERB Masking Resolution", "Surgical EQ Carving", "Dynamic Sidechain Ducking", "Mono Sub Clamping"],
            keywords=["fix masking", "unmask", "sub kick clash", "low mid mud", "vocal corridor"],
            dispatch_fn=_dispatch_surgical_masking,
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
        # Broad requests to rebalance a session take the autonomous producer
        # path. Targeted wording (for example "fix the masking in my drop")
        # remains on the surgical masking doctor below.
        broad_masking_request = (
            _matches_any(query, _AUTONOMOUS_PRODUCER_PATTERNS)
            and bool(re.search(r"\b(clashes?|rebalance|balance|session|tracks?)\b", query, re.I))
        )
        if broad_masking_request:
            return "autonomous_producer"
        if _matches_any(query, _SURGICAL_MASKING_PATTERNS):
            return "surgical_masking_doctor"
        if _matches_any(query, _RACK_SYNTHESIZER_PATTERNS):
            return "rack_synthesizer"
        if _matches_any(query, _NEURAL_MIDI_PATTERNS):
            return "neural_midi_generator"
        if _matches_any(query, _AUTONOMOUS_PRODUCER_PATTERNS):
            return "autonomous_producer"
        if _matches_any(query, _REALTIME_SESSION_REVIEW_PATTERNS):
            return "realtime_session_reviewer"
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
        # Device parameter/EQ patterns are more specific, check first
        if _matches_any(query, _ABLETON_DEVICE_PATTERNS):
            return "ableton_controller"
        if _matches_any(query, _ARRANGEMENT_PATTERNS):
            return "arrangement_planner"
        if _matches_any(query, _ABLETON_PATTERNS):
            return "ableton_controller"
        from kenn.core.subjective_translator import SubjectiveTranslator
        if SubjectiveTranslator.can_translate(query):
            return "ableton_controller"

        return None

    def dispatch(self, query: str, **kwargs: Any) -> Optional[Dict[str, Any]]:
        """Classify and dispatch to the matching sub-agent. Returns None if no match."""
        import time as _time

        _t0 = _time.perf_counter()
        agent_name = self.classify(query)
        _classify_ms = (_time.perf_counter() - _t0) * 1000
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
        _t1 = _time.perf_counter()
        result = agent.dispatch_fn(query=query, agent_request=request.to_dict(), **kwargs)
        _dispatch_ms = (_time.perf_counter() - _t1) * 1000
        if result is None:
            return None
        agent_result = AgentResult.from_dispatch(request, agent=agent.name, payload=result)
        result["orchestrator_timing"] = {
            "classify_ms": round(_classify_ms, 1),
            "dispatch_ms": round(_dispatch_ms, 1),
            "agent": agent.name,
        }
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
