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
    r"\bwhat(?:'s|s|\s+is)\s+(?:the\s+)?(?:current\s+)?(?P<field>pan|panning|volume|level|fader)\s+(?:on|of|for)\s+(?P<name>.+?)\s*\??\s*$"
    r"|\bwhat(?:'s|s|\s+is)\s+(?:the\s+)?(?P<name2>.+?)(?:'s|s')\s+(?P<field2>pan|panning|volume|level|fader)\s*\??\s*$"
    r"|\bhow\s+loud\s+is\s+(?P<name3>.+?)\s*\??\s*$"
    r"|^\s*(?:is|are)\s+(?P<name4>.+?)\s+(?P<state>muted|soloed|armed|(?:record[\s-]?)?armed|panned|cent(?:red|ered))\s*\??\s*$"
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
    if _TRACK_NUMBER.search(lower) and re.search(r"\b(?:what|which)\s+(?:is|are)\s+track\b|\bwhat(?:'s|s)\s+track\b", lower):
        return "track_identity"
    # Asking what the tempo is, not any sentence with "tempo" in it ("stretch samples to fit my track's tempo" got
    # "The current tempo is 120 BPM", 26 Sept 2026).
    # Tempo changes are Live changes now (set_tempo, 27 Sept 2026); only a time-signature change still lands here.
    # "what bpm is good for house music?" is advice, not this set's tempo.
    advice = re.search(r"\b(?:good|best|right|ideal|should|usually|typical(?:ly)?|normal|common|for\s+(?:a\s+)?[\w-]+\s+(?:music|track|song|beat)s?"
                       r"|genre|house|techno|trance|dnb|drum\s+and\s+bass|dubstep|trap|hip\s*hop|garage|ambient|pop)\b", lower)
    if not advice and (re.search(r"\b(?:set|change|make|put|switch)\b[^.?!]*\b(?:time\s+signature|meter)\b", lower) or re.search(r"\b(?:what|which)(?:'?s|\s+is|\s+are)?\s+(?:the\s+|my\s+|our\s+|this\s+)?(?:current\s+|song'?s?\s+|set'?s?\s+)?"
                 r"(?:tempo|bpm|time\s+signature|meter)\b|\bhow\s+fast\s+is\b|^\s*(?:the\s+)?(?:tempo|bpm|time\s+signature)\s*\??\s*$"
                 r"|\b(?:tempo|bpm)\s+(?:and|&)\s+(?:the\s+)?time\s+signature\b", lower)):
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


def _track_state_answer(question: str, tracks: list[dict[str, Any]]) -> dict[str, Any]:
    from kenn.core import volume_law
    from kenn.core.live_intent import _extract_track_phrase, _find_track

    match = _TRACK_STATE_QUESTION.search(" ".join(str(question).split()))
    groups = match.groupdict() if match else {}
    phrase = next((groups[key] for key in ("name", "name2", "name3", "name4", "name5") if groups.get(key)), "")
    field = str(next((groups[key] for key in ("field", "field2", "field5") if groups.get(key)), "")).lower()
    state = str(groups.get("state") or "").lower()
    if groups.get("name3"):
        field = "volume"
    found = _extract_track_phrase(phrase, tracks)
    track, ambiguous, error = _find_track(found, tracks) if found else (None, [], "no track")
    if track is None or ambiguous or error:
        return {"status": "clarification_required", "answer": "Which track do you mean? Nothing changed."}
    name = str(track.get("name"))
    if field in {"volume", "level", "fader"} or (not state and not field):
        raw = track.get("volume")
        level = volume_law.raw_to_db(float(raw)) if isinstance(raw, (int, float)) and not isinstance(raw, bool) else None
        if level is None:
            return {"status": "clarification_required", "answer": f"I can't read '{name}''s level right now."}
        shown = "-inf dB" if level == float("-inf") else f"{level:.1f} dB"
        return {"answer": f"'{name}' is at {shown}.", "track": {"index": track.get("index"), "name": name}, "volume_db": level}
    if field in {"pan", "panning"} or state in {"panned", "centred", "centered"}:
        pan = float(track.get("pan") or 0.0)
        where = "centred" if abs(pan) < 0.005 else f"panned {abs(pan) * 100:.0f}% {'left' if pan < 0 else 'right'}"
        return {"answer": f"'{name}' is {where}.", "track": {"index": track.get("index"), "name": name}, "pan": pan}
    key = {"muted": "muted", "soloed": "soloed"}.get(state, "armed")
    on = bool(track.get(key))
    word = {"muted": "muted", "soloed": "soloed"}.get(state, "armed")
    return {"answer": f"{'Yes' if on else 'No'}, '{name}' is {'' if on else 'not '}{word}.",
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
        payload.update(_track_state_answer(question, tracks))
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
        tempo_text = f"{float(tempo):g} BPM" if isinstance(tempo, (int, float)) else "an unavailable tempo"
        signature_text = f"{numerator}/{denominator}" if numerator is not None and denominator is not None else "an unavailable time signature"
        answer = f"The current tempo is {tempo_text} and the time signature is {signature_text}."
        if re.search(r"\b(?:set|change|make|put|switch)\b[^.?!]*\b(?:time\s+signature|meter)\b", question, re.I):
            # "set the time signature to 3/4" used to get only the current values, which reads as if KENN had done it.
            answer = f"KENN can't change the time signature yet; set it in Live. {answer}"
        payload.update({
            "answer": answer,
            "tempo": tempo,
            "signature_numerator": numerator,
            "signature_denominator": denominator,
        })
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
