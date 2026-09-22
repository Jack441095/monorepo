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


_TRACK_NUMBER = re.compile(r"\btrack\s*#?\s*(\d+)\b", re.I)


def _question_kind(question: str) -> str | None:
    lower = " ".join(str(question or "").casefold().split())
    if not lower:
        return None
    if (
        re.search(r"\b(?:what did you change|what have you changed|show(?: me)? (?:the )?history|change history|recent changes)\b", lower)
        or re.search(r"\bundo everything\b", lower)
    ):
        return "change_history"
    if "ableton" in lower and any(word in lower for word in ("connected", "connection", "online", "status")):
        return "connection"
    if re.search(r"\bhow many\s+(?:live\s+)?tracks?\b", lower):
        return "track_count"
    if _TRACK_NUMBER.search(lower) and re.search(r"\b(?:what|which)\s+(?:is|are)\s+(?:on\s+)?track\b|\bwhat(?:'s|s)\s+track\b", lower):
        return "track_identity"
    if "tempo" in lower or "time signature" in lower or "meter" in lower:
        return "tempo_signature"
    if "selected track" in lower or ("which track" in lower and "selected" in lower):
        return "selected_track"
    if "duplicate" in lower and ("track" in lower or "name" in lower):
        return "duplicate_names"
    if re.search(r"\b(?:describe|summari[sz]e)\b.*\b(?:live\s+set|ableton\s+session|session)\b", lower):
        return "overview"
    return None


def answer_live_session_question(
    question: str,
    *,
    service: LiveActionService | None = None,
) -> dict[str, Any] | None:
    """Return one grounded, non-mutating session answer when recognized."""
    kind = _question_kind(question)
    if kind is None:
        return None

    live = service or LiveActionService()
    if kind == "change_history":
        result = live.describe_recent_changes(limit=10)
        return {
            "schema": "kenn.ableton_session_answer.v1",
            "intent": {"action": "inspect_change_history"},
            **result,
            "changed": False,
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

    tracks = [item for item in snapshot.get("tracks", []) if isinstance(item, dict)]
    names = [str(item.get("name", "")) for item in tracks]
    payload: dict[str, Any] = {
        "schema": "kenn.ableton_session_answer.v1",
        "status": "inspected",
        "changed": False,
        "intent": {"action": f"inspect_{kind}"},
    }

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
        payload.update({
            "answer": f"The current tempo is {tempo_text} and the time signature is {signature_text}.",
            "tempo": tempo,
            "signature_numerator": numerator,
            "signature_denominator": denominator,
        })
    elif kind == "selected_track":
        selected_index = snapshot.get("selected_track_index")
        selected = next((item for item in tracks if item.get("index") == selected_index), None)
        if selected is None:
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
