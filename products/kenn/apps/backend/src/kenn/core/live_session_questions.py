"""Read-only answers for questions about the current Ableton Live set.

This module deliberately handles only narrow, observable session facts. It
never creates a proposal and never calls a mutation method. Returning ``None``
means the question belongs to KENN's normal chat pipeline.
"""

from __future__ import annotations

from collections import Counter
import re
from typing import Any

from kenn.core.live_action_service import LiveActionService
from kenn.core.live_session_advice import mix_advice_from_session


_TRACK_NUMBER = re.compile(r"\btrack\s*#?\s*(\d+)\b", re.I)
# "What's the current pan on the drum bus?" was answered "'Drum Bus' has: Compressor." and "is the bass muted?" got
# "not sure" (27 Sept 2026): a track's level, pan or mute/solo/arm state is read straight from the set.
_TRACK_STATE_QUESTION = re.compile(
    r"\bwhat(?:'s|s|\s+is)\s+(?:the\s+)?(?:current\s+)?(?P<field>pan|panning|volume|level|fader|color|routing|output\s+routing|input\s+routing)\s+(?:on|of|for)\s+(?P<name>.+?)\s*\??\s*$"
    r"|\bwhat(?:'s|s|\s+is)\s+(?:the\s+)?(?P<name2>.+?)(?:'s|s'|\s+)(?P<field2>pan|panning|volume|level|fader|color|routing|output\s+routing|input\s+routing)\s*\??\s*$"
    r"|\bhow\s+loud\s+is\s+(?P<name3>.+?)\s*\??\s*$"
    r"|^\s*(?:is|are)\s+(?P<name4>.+?)\s+(?P<state>muted|soloed|armed|(?:record[\s-]?)?armed|panned|cent(?:red|ered)|folded|unfolded|collapsed|expanded)\s*\??\s*$"
    r"|^\s*where\s+(?:is|does)\s+(?P<name6>.+?)\s+(?:routed|route(?:\s+to)?|send(?:\s+to)?)\s*\??\s*$"
    # "check the lead vocal volume" as the request itself, not "solo the snare to check its level".
    r"|(?:^|(?:can|could|would)\s+you\s+|\bplease\s+|,\s*)check\s+(?:the\s+)?(?P<name5>(?!its?\b)[^,.?!]+?)\s+(?P<field5>volume|level|pan)\b",
    re.I,
)


def _question_kind(question: str) -> str | None:
    lower = " ".join(str(question or "").casefold().split())
    if not lower:
        return None
    if _TRACK_STATE_QUESTION.search(lower):
        return "track_state"
    if (
        re.search(r"\b(?:what did you change|what have you changed|show(?: me)? (?:the )?history|change history|recent changes)\b", lower)
        or re.search(r"\bundo everything\b", lower)
    ):
        return "change_history"
    if re.search(
        r"\b(?:how does my (?:mix|low[ -]?end) sound|check (?:my low[ -]?end|(?:the )?vocals? for clipping)|any masking issues?|analy[sz]e my (?:session|mix)|mix advice|review my mix)\b",
        lower,
    ):
        return "mix_advice"
    if "ableton" in lower and any(word in lower for word in ("connected", "connection", "online", "status")):
        return "connection"
    if re.search(r"\bhow many\s+(?:live\s+)?tracks?\b", lower):
        return "track_count"
    # Track identity: recognize "what is track 12 named?", "what is the name of track 12?", "track 12 name".
    if _TRACK_NUMBER.search(lower) and (
        re.search(r"\b(?:what|which)\s+(?:is|are)\s+track\b|\bwhat(?:'s|s)\s+track\b", lower)
        or re.search(r"\b(?:name|called)\s+(?:of\s+)?track\b|\btrack\b.*?\b(?:name|named|called)\b", lower)
    ):
        return "track_identity"
    # Metronome and arrangement loop questions: inspect current playback helpers.
    if not re.search(r"\b(?:set|turn|toggle|enable|disable|switch)\b", lower) and (
        re.search(r"\b(?:is\s+(?:the\s+)?(?:metronome|click(?:\s+track)?)|metronome\s+status|click\s+status|is\s+click\s+(?:on|off))\b", lower)
    ):
        return "metronome_state"
    if not re.search(r"\b(?:set|turn|toggle|enable|disable|switch)\b", lower) and (
        re.search(r"\b(?:is\s+(?:the\s+)?(?:(?:arrangement\s+)?loop|looping)\s+(?:on|off|active|enabled)|(?:what|which)(?:'s|\s+is)\s+(?:the\s+)?(?:loop\s+bounds?|loop\s+length|loop\s+start|loop\s+range))\b", lower)
    ):
        return "loop_state"
    if not re.search(r"\b(?:set|turn|change|put|make)\b", lower) and (
        re.search(r"\b(?:what(?:'s|s|\s+is)\s+(?:the\s+)?(?:global\s+|song\s+)?(?:groove(?:\s+amount)?|swing)|how\s+much\s+(?:groove|swing)|groove\s+amount|swing\s+amount)\b", lower)
    ):
        return "groove_state"
    if not re.search(r"\b(?:set|turn|change|put|switch|enable|disable)\b", lower) and (
        re.search(r"\b(?:is\s+(?:arrangement\s+)?record(?:ing)?(?:\s+mode)?\s+(?:on|off|active|enabled)|what(?:'s|s|\s+is)\s+(?:the\s+)?(?:arrangement\s+)?record(?:ing)?(?:\s+mode)?|record\s+mode\s+status)\b", lower)
    ):
        return "record_mode_state"
    if not re.search(r"\b(?:jump|go|skip|add|remove|delete|create)\b", lower) and (
        re.search(r"\b(?:what\s+locators|list\s+(?:the\s+)?(?:locators|markers|cue\s+points)|what\s+markers|what\s+cue\s+points|show\s+(?:the\s+)?(?:locators|markers))\b", lower)
    ):
        return "locators_list"
    # Asking what the tempo is, not any sentence with "tempo" in it ("stretch samples to fit my track's tempo" got
    # "The current tempo is 120 BPM", 26 Sept 2026).
    # Tempo and time-signature changes are Live changes now (27 Sept 2026), so only questions land here.
    # "what bpm is good for house music?" is advice, not this set's tempo.
    advice = re.search(r"\b(?:good|best|right|ideal|should|usually|typical(?:ly)?|normal|common|for\s+(?:a\s+)?[\w-]+\s+(?:music|track|song|beat)s?"
                       r"|genre|house|techno|trance|dnb|drum\s+and\s+bass|dubstep|trap|hip\s*hop|garage|ambient|pop)\b", lower)
    if not advice and not re.search(r"\b(?:set|change|make|put|switch)\b", lower) and (
        re.search(r"\b(?:what|which)(?:'?s|\s+is|\s+are)?\s+(?:the\s+|my\s+|our\s+|this\s+)?(?:current\s+|song'?s?\s+|set'?s?\s+|project'?s?\s+|session'?s?\s+)?"
                 r"(?:tempo|bpm|time\s+signature|meter|key|scale)\b|\bhow\s+fast\s+is\b|^\s*(?:the\s+)?(?:tempo|bpm|time\s+signature|key|scale)\s*\??\s*$"
                 r"|\b(?:tempo|bpm)\s+(?:and|&)\s+(?:the\s+)?(?:time\s+signature|meter|key|scale)\b", lower)
        or re.search(r"\b(?:what\s+key|what's\s+the\s+key|what\s+is\s+the\s+key|what\s+scale|which\s+key)\b", lower)
    ):
        return "tempo_signature"
    if (
        "selected track" in lower
        or ("which track" in lower and "selected" in lower)
        or re.search(r"\bwhat(?:'s| is) selected\b", lower)
    ):
        return "selected_track"
    if (
        "duplicate" in lower
        and "name" in lower
        and re.search(r"\b(?:which|what|any|are there|show|list|find|have|has)\b", lower)
    ):
        return "duplicate_names"
    if re.search(r"\b(?:describe|summari[sz]e)\b.*\b(?:live\s+set|ableton\s+session|session)\b", lower):
        return "overview"
    return None


def _track_state_answer(question: str, tracks: list[dict[str, Any]], *, service: LiveActionService | None = None) -> dict[str, Any]:
    from kenn.core import volume_law
    from kenn.core.live_intent import _extract_track_phrase, _find_track, _find_numbered_track

    match = _TRACK_STATE_QUESTION.search(" ".join(str(question).split()))
    groups = match.groupdict() if match else {}
    phrase = next((groups[key] for key in ("name", "name2", "name3", "name4", "name5", "name6") if groups.get(key)), "")
    field = str(next((groups[key] for key in ("field", "field2", "field5") if groups.get(key)), "")).lower()
    state = str(groups.get("state") or "").lower()
    if groups.get("name3"):
        field = "volume"
    elif groups.get("name6"):
        field = "routing"

    # Inspect master bus mixer when requested. Live's master track lives outside the ordinary song.tracks array.
    lower_phrase = phrase.strip().lower()
    if lower_phrase in {"master", "the master", "master track", "the master track"} or re.search(r"\bmaster\s+(?:volume|fader|level|pan)\b", question, re.I):
        client = getattr(service, "client", None)
        mixer = client.get_bus_mixer("master", -1) if client and hasattr(client, "get_bus_mixer") else {}
        if mixer and mixer.get("success"):
            raw = mixer.get("volume")
            level = volume_law.raw_to_db(float(raw)) if isinstance(raw, (int, float)) and not isinstance(raw, bool) else None
            shown = "-inf dB" if level == float("-inf") else f"{level:.1f} dB" if level is not None else "an unreadable level"
            pan = float(mixer.get("panning") or 0.0)
            where = "centred" if abs(pan) < 0.005 else f"panned {abs(pan) * 100:.0f}% {'left' if pan < 0 else 'right'}"
            if field in {"pan", "panning"} or state in {"panned", "centred", "centered"}:
                return {"answer": f"The master track is {where}.", "track": {"kind": "master", "name": "Master"}, "pan": pan}
            return {"answer": f"The master track is at {shown}.", "track": {"kind": "master", "name": "Master"}, "volume_db": level}

    # Numbered track resolution: musicians frequently address tracks as "track 12" rather than recalling exact names.
    num_match = re.search(r"\btrack\s*#?\s*(\d+)\b", phrase, re.I) or re.search(r"\btrack\s*#?\s*(\d+)\b", question, re.I)
    if num_match:
        track, error = _find_numbered_track(int(num_match.group(1)), tracks)
        ambiguous = []
    else:
        found = _extract_track_phrase(phrase, tracks)
        track, ambiguous, error = _find_track(found, tracks) if found else (None, [], "no track")

    if track is None or ambiguous or error:
        return {"status": "clarification_required", "answer": "Which track do you mean? Nothing changed."}

    name = str(track.get("name"))
    track_idx = track.get("index")
    label = f"Track {track_idx + 1} ('{name}')" if (num_match and isinstance(track_idx, int)) else f"'{name}'"

    if field in {"volume", "level", "fader"} or (not state and not field):
        raw = track.get("volume")
        level = volume_law.raw_to_db(float(raw)) if isinstance(raw, (int, float)) and not isinstance(raw, bool) else None
        if level is None:
            return {"status": "clarification_required", "answer": f"I can't read {label}'s level right now."}
        shown = "-inf dB" if level == float("-inf") else f"{level:.1f} dB"
        return {"answer": f"{label} is at {shown}.", "track": {"index": track.get("index"), "name": name}, "volume_db": level}
    if field in {"pan", "panning"} or state in {"panned", "centred", "centered"}:
        pan = float(track.get("pan") or 0.0)
        where = "centred" if abs(pan) < 0.005 else f"panned {abs(pan) * 100:.0f}% {'left' if pan < 0 else 'right'}"
        return {"answer": f"{label} is {where}.", "track": {"index": track.get("index"), "name": name}, "pan": pan}
    if state in {"folded", "unfolded", "collapsed", "expanded"}:
        client = getattr(service, "client", None)
        is_folded = None
        if client and hasattr(client, "get_track_fold_state") and isinstance(track.get("index"), int):
            is_folded = client.get_track_fold_state(track["index"])
        if is_folded is None:
            is_folded = bool(track.get("fold_state", False))
        fold_word = "folded" if is_folded else "unfolded"
        is_state = is_folded if state in {"folded", "collapsed"} else not is_folded
        return {
            "answer": f"{'Yes' if is_state else 'No'}, {label} is {fold_word}.",
            "track": {"index": track.get("index"), "name": name},
            "folded": is_folded,
        }
    if field == "color":
        client = getattr(service, "client", None)
        color_idx = None
        if client and hasattr(client, "get_track_color_index") and isinstance(track.get("index"), int):
            color_idx = client.get_track_color_index(track["index"])
        if color_idx is None:
            color_idx = track.get("color_index")
        shown_color = f"color palette index {color_idx}" if color_idx is not None else "an unspecified color"
        return {
            "answer": f"{label} is set to {shown_color}.",
            "track": {"index": track.get("index"), "name": name},
            "color_index": color_idx,
        }
    if field in {"routing", "output", "output routing"}:
        out_type = track.get("output_routing_type") or "Master"
        out_ch = track.get("output_routing_channel") or ""
        ch_text = f" via {out_ch}" if out_ch else ""
        return {
            "answer": f"{label} is routed to output '{out_type}'{ch_text}.",
            "track": {"index": track.get("index"), "name": name},
            "output_routing_type": out_type,
            "output_routing_channel": out_ch,
        }
    if field in {"input", "input routing"}:
        in_type = track.get("input_routing_type") or "All Ins"
        in_ch = track.get("input_routing_channel") or ""
        ch_text = f" ({in_ch})" if in_ch else ""
        return {
            "answer": f"{label} receives input from '{in_type}'{ch_text}.",
            "track": {"index": track.get("index"), "name": name},
            "input_routing_type": in_type,
            "input_routing_channel": in_ch,
        }
    key = {"muted": "muted", "soloed": "soloed"}.get(state, "armed")
    on = bool(track.get(key))
    word = {"muted": "muted", "soloed": "soloed"}.get(state, "armed")
    return {"answer": f"{'Yes' if on else 'No'}, {label} is {'' if on else 'not '}{word}.",
            "track": {"index": track.get("index"), "name": name}, key: on}


def answer_live_session_question(
    question: str,
    *,
    service: LiveActionService | None = None,
    session_id: str = "",
) -> dict[str, Any] | None:
    """Return one grounded, non-mutating session answer when recognized."""
    kind = _question_kind(question)
    if kind is None:
        from kenn.core.live_world_questions import answer_world_question

        return answer_world_question(question, (service or LiveActionService()).client)

    live = service or LiveActionService()
    if kind == "change_history":
        result = live.describe_recent_changes(limit=10, session_id=session_id)
        return {
            "schema": "kenn.ableton_session_answer.v1",
            "intent": {"action": "inspect_change_history"},
            **result,
            "changed": False,
        }
    # Track count needs only the song-level count/name probe.  A forced full
    # snapshot also asks every track for devices and mixer state; on real Live
    # that can wait on unrelated optional endpoints for hundreds of
    # milliseconds.  Keep the answer fresh without paying for data the
    # question does not use.  Backends without a count-bearing probe fall
    # through to the normal snapshot contract.
    if kind == "track_count":
        probe = getattr(getattr(live, "client", None), "probe_connection", None)
        if callable(probe):
            observation = probe()
            count = observation.get("track_count") if isinstance(observation, dict) else None
            if (
                isinstance(observation, dict)
                and observation.get("status") == "connected"
                and isinstance(count, int)
                and count >= 0
            ):
                return {
                    "schema": "kenn.ableton_session_answer.v1",
                    "status": "inspected",
                    "changed": False,
                    "intent": {"action": "inspect_track_count"},
                    "answer": f"The current Live Set has {count} tracks.",
                    "track_count": count,
                }
    snapshot = live.snapshot(include_mixer=True)
    if snapshot.get("status") != "connected" or not isinstance(snapshot.get("tracks"), list):
        return {
            "schema": "kenn.ableton_session_answer.v1",
            "status": "offline",
            "changed": False,
            "answer": "I cannot read a fresh Ableton Live snapshot from the selected backend right now.",
            "intent": {"action": f"inspect_{kind}"},
        }

    if kind == "mix_advice":
        return {
            "intent": {"action": "inspect_mix_advice"},
            **mix_advice_from_session(service=live, snapshot=snapshot, question=question),
            "changed": False,
        }

    tracks = [item for item in snapshot.get("tracks", []) if isinstance(item, dict)]
    names = [str(item.get("name", "")) for item in tracks]
    payload: dict[str, Any] = {
        "schema": "kenn.ableton_session_answer.v1",
        "status": "inspected",
        "changed": False,
        "intent": {"action": f"inspect_{kind}"},
    }

    if kind == "track_state":
        payload.update(_track_state_answer(question, tracks, service=live))
        return payload
    if kind == "connection":
        backend = str(snapshot.get("backend") or getattr(live.client, "backend_name", "Live backend"))
        payload.update({
            "answer": f"Yes. KENN has a fresh read-only connection to Ableton Live through {backend}.",
            "connected": True,
            "backend": backend,
        })
    elif kind == "track_count":
        payload.update({"answer": f"The current Live Set has {len(tracks)} tracks.", "track_count": len(tracks)})
    elif kind == "track_identity":
        match = _TRACK_NUMBER.search(question)
        number = int(match.group(1)) if match else 0
        if number < 1 or number > len(tracks):
            payload.update({
                "status": "clarification_required",
                "answer": f"Track {number} is not present in the current Live Set, which has {len(tracks)} tracks.",
                "requested_track_number": number,
            })
        else:
            track = tracks[number - 1]
            payload.update({
                "answer": f"Track {number} is '{track.get('name', '')}'.",
                "track": {"number": number, "index": track.get("index"), "name": track.get("name", "")},
            })
    elif kind == "tempo_signature":
        tempo = snapshot.get("tempo")
        numerator = snapshot.get("signature_numerator")
        denominator = snapshot.get("signature_denominator")
        root_note = snapshot.get("root_note")
        scale_name = snapshot.get("scale_name")
        tempo_text = f"{float(tempo):g} BPM" if isinstance(tempo, (int, float)) else "an unavailable tempo"
        signature_text = f"{numerator}/{denominator}" if numerator is not None and denominator is not None else "an unavailable time signature"

        # When Live exposes root note (0-11 pitch class) and scale name, incorporate key into the response.
        pitch_names = ["C", "C#", "D", "D#", "E", "F", "F#", "G", "G#", "A", "A#", "B"]
        scale_text = ""
        if isinstance(root_note, int) and 0 <= root_note < 12 and scale_name:
            scale_text = f" in {pitch_names[root_note]} {scale_name}"

        answer = f"The current tempo is {tempo_text} and the time signature is {signature_text}{scale_text}."
        payload.update({
            "answer": answer,
            "tempo": tempo,
            "signature_numerator": numerator,
            "signature_denominator": denominator,
            "root_note": root_note,
            "scale_name": scale_name,
        })
    elif kind == "metronome_state":
        metronome_on = snapshot.get("metronome")
        if metronome_on is None:
            client = getattr(live, "client", None)
            if client and hasattr(client, "get_metronome"):
                metronome_on = client.get_metronome()
        state_text = "on" if metronome_on else "off"
        answer = f"The metronome (click) is currently {state_text}."
        payload.update({"answer": answer, "metronome": bool(metronome_on)})
    elif kind == "loop_state":
        loop_on = snapshot.get("loop")
        start = snapshot.get("loop_start")
        length = snapshot.get("loop_length")
        if loop_on is None or start is None or length is None:
            client = getattr(live, "client", None)
            if client:
                if loop_on is None and hasattr(client, "get_loop"):
                    loop_on = client.get_loop()
                if (start is None or length is None) and hasattr(client, "get_loop_bounds"):
                    bounds = client.get_loop_bounds()
                    if bounds:
                        start, length = bounds
        state_text = "enabled" if loop_on else "disabled"
        bounds_text = f" (beats {float(start):g} to {float(start) + float(length):g}, length {float(length):g} beats)" if start is not None and length is not None else ""
        answer = f"The arrangement loop is currently {state_text}{bounds_text}."
        payload.update({
            "answer": answer,
            "loop": bool(loop_on),
            "loop_start": float(start) if start is not None else None,
            "loop_length": float(length) if length is not None else None,
        })
    elif kind == "groove_state":
        groove = snapshot.get("groove_amount")
        if groove is None:
            client = getattr(live, "client", None)
            if client and hasattr(client, "get_groove_amount"):
                groove = client.get_groove_amount()
        pct = round(float(groove) * 100) if groove is not None else 0
        answer = f"The global groove amount is currently {pct}%."
        payload.update({"answer": answer, "groove_amount": float(groove) if groove is not None else 0.0})
    elif kind == "record_mode_state":
        rec_mode = snapshot.get("record_mode")
        if rec_mode is None:
            client = getattr(live, "client", None)
            if client and hasattr(client, "get_record_mode"):
                rec_mode = client.get_record_mode()
        state_text = "active (on)" if rec_mode else "inactive (off)"
        answer = f"Arrangement recording is currently {state_text}."
        payload.update({"answer": answer, "record_mode": bool(rec_mode)})
    elif kind == "locators_list":
        cues = snapshot.get("cue_points")
        if cues is None:
            client = getattr(live, "client", None)
            if client and hasattr(client, "get_cue_points"):
                cues = client.get_cue_points()
        cues = cues or []
        if not cues:
            answer = "There are no cue points or locators in the current Live Set."
        else:
            cue_descriptions = [f"'{c.get('name')}' at {float(c.get('time', 0.0)):g} beats" for c in cues]
            answer = f"The Live Set has {len(cues)} locator(s): {', '.join(cue_descriptions)}."
        payload.update({"answer": answer, "cue_points": cues})
    elif kind == "selected_track":
        selected_index = snapshot.get("selected_track_index")
        selected = next((item for item in tracks if item.get("index") == selected_index), None)
        other = snapshot.get("selected_track_kind") if isinstance(snapshot.get("selected_track_kind"), dict) else None
        if selected is None and other and other.get("kind") in {"return", "master"}:
            label = "the master track" if other["kind"] == "master" else f"return track '{other.get('name', '')}'"
            payload.update({
                "answer": f"{label[0].upper()}{label[1:]} is selected.",
                "track": {"kind": other["kind"], "index": other.get("index"), "name": other.get("name", "")},
            })
        elif selected is None:
            payload.update({"status": "unavailable", "answer": "Live did not expose a selected track in the fresh snapshot."})
        else:
            number = tracks.index(selected) + 1
            payload.update({
                "answer": f"Track {number}, '{selected.get('name', '')}', is selected.",
                "track": {"number": number, "index": selected.get("index"), "name": selected.get("name", "")},
            })
    elif kind == "duplicate_names":
        counts = Counter(name for name in names if name)
        duplicates = sorted(name for name, count in counts.items() if count > 1)
        answer = (
            "The duplicated track names are: " + ", ".join(duplicates) + "."
            if duplicates else "There are no duplicate track names in the current Live Set."
        )
        payload.update({"answer": answer, "duplicate_track_names": duplicates})
    else:
        playing = "playing" if snapshot.get("is_playing") else "stopped"
        tempo = snapshot.get("tempo")
        track_summary = ", ".join(f"{index}. {name}" for index, name in enumerate(names, start=1)) or "no tracks"
        tempo_summary = f" at {float(tempo):g} BPM" if isinstance(tempo, (int, float)) else ""
        payload.update({
            "answer": f"The Live Set is {playing}{tempo_summary} with {len(tracks)} tracks: {track_summary}.",
            "track_count": len(tracks),
            "tracks": [
                {"number": number, "index": track.get("index"), "name": track.get("name", "")}
                for number, track in enumerate(tracks, start=1)
            ],
            "tempo": tempo,
            "is_playing": snapshot.get("is_playing"),
        })
    return payload


__all__ = ["answer_live_session_question"]
