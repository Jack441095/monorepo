"""One next step a tester can say after an audio review.

Findings from a rendered capture are evidence, not instructions, so KENN never changes Live on its own. It ends
the review with one small, reversible step the producer may choose to say. A track command is offered only when
the finding points at one clearly identified track and the command parses to a clean proposal on the current set
(it still goes proposal -> Apply -> readback -> Undo). Anything about the master is a question instead: KENN does
not change the master.
"""

from __future__ import annotations

from typing import Any

REMEASURE = "To measure again after a change, export the same way and ask again."


def _one_track(role_words: tuple[str, ...], snapshot: dict[str, Any]) -> str | None:
    """The only track in these roles (e.g. bass and sub for low end), or None when zero or several could be it."""
    from kenn.core.track_classifier import find_tracks_by_question_role

    tracks = [t for t in (snapshot or {}).get("tracks") or [] if isinstance(t, dict)]
    found = {m.get("track_index"): m.get("track_name") for word in role_words
             for m in find_tracks_by_question_role(f"my {word}", tracks)}
    names = [name for name in found.values() if name]
    return str(names[0]) if len(found) == 1 and names else None


def _parses_cleanly(command: str, snapshot: dict[str, Any]) -> bool:
    from kenn.core.live_intent import parse_request

    parsed = parse_request(command, snapshot)
    return bool(parsed.get("confirmation_required")) and not parsed.get("missing_fields") and not parsed.get("ambiguity")


def _command(say: str, why: str, snapshot: dict[str, Any]) -> dict[str, str] | None:
    return {"kind": "command", "say": say, "why": why} if _parses_cleanly(say, snapshot) else None


def next_step(findings: list[dict[str, Any]], snapshot: dict[str, Any] | None, *, scope: str) -> dict[str, str] | None:
    """The single most useful next step for these findings, or None when there is nothing concrete to offer."""
    snapshot = snapshot if isinstance(snapshot, dict) else {}
    types = {str(f.get("type")) for f in findings if isinstance(f, dict)}
    order = {"low_end": ("low_end", "clipping", "true_peak"), "vocal": ("clipping", "true_peak", "low_end")}.get(
        scope, ("clipping", "low_end", "true_peak"))
    for concern in order:
        if concern == "low_end" and "possible_low_end_excess" in types:
            bass = _one_track(("bass", "sub", "808"), snapshot)
            step = bass and _command(
                f"turn the {bass} down 1 dB",
                f"A small, reversible first test: listen at matched level, and Undo puts {bass} back.", snapshot)
            if step:
                return step
            return {"kind": "question", "say": "how do I balance the kick and bass low end?",
                    "why": "More than one track could be carrying the low end, so KENN won't guess which to change."}
        if concern == "clipping" and "clipping" in types:
            if scope == "vocal":
                vocal = _one_track(("vocal",), snapshot)
                step = vocal and _command(
                    f"turn the {vocal} down 3 dB",
                    "This helps only if the clipping happens in the export, not in the recording itself: "
                    f"lower it, export the vocal again and compare. Undo puts {vocal} back.", snapshot)
                if step:
                    return step
                return {"kind": "question", "say": "how do I fix a clipped vocal recording?",
                        "why": "KENN can't tell which vocal track made this capture, so it won't guess."}
            return {"kind": "question", "say": "how do I stop my mix clipping on export?",
                    "why": "Clipping across the whole mix is fixed at the master, which KENN doesn't change."}
        if concern == "true_peak" and "true_peak_over_ceiling" in types:
            return {"kind": "question", "say": "how do I keep my master under -1 dBTP?",
                    "why": "True peak is set on the master limiter, which KENN doesn't change."}
    return None


def next_step_line(step: dict[str, str] | None) -> str:
    if not step:
        return ""
    lead = "Next step you can say" if step["kind"] == "command" else "Next, you could ask"
    return f"{lead}: \"{step['say']}\". {step['why']} {REMEASURE}"


__all__ = ["REMEASURE", "next_step", "next_step_line"]
