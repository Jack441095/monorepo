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


def next_step_line(step: dict[str, str] | None, remeasure: str = REMEASURE) -> str:
    if not step:
        return ""
    lead = "Next step you can say" if step["kind"] == "command" else "Next, you could ask KENN"
    return f"{lead}: \"{step['say']}\". {step['why']} {remeasure}"


# Mix Review looks at a whole render, so its findings can't name one track: its next step is always a question.
# Each question was checked to get a practical, cited answer from KENN's notes; families without one get no step.
_MIX_REVIEW_QUESTIONS = (
    ("clipping", "how do I stop my mix clipping on export?"),
    ("true_peak_intersample", "how do I keep my master under -1 dBTP?"),
    ("headroom", "how do I keep my master under -1 dBTP?"),
    ("phase_polarity_mono_compatibility", "how do I check my mix in mono?"),
    ("silence_or_truncation", "why does my export cut off or have silence?"),
    ("calibrated_lufs_bs1770", "how loud should my mix be for streaming?"),
    ("loudness_estimate", "how loud should my mix be for streaming?"),
)
_SEVERITY = {"critical": 0, "high": 1, "medium": 2, "low": 3}


def mix_review_next_step(review: dict[str, Any]) -> dict[str, str] | None:
    flags = [f for f in (review or {}).get("flags") or [] if isinstance(f, dict)]
    order = {family: position for position, (family, _q) in enumerate(_MIX_REVIEW_QUESTIONS)}
    questions = dict(_MIX_REVIEW_QUESTIONS)
    ranked = sorted((f for f in flags if f.get("fault_family") in questions),
                    key=lambda f: (_SEVERITY.get(str(f.get("severity")), 4), order[f["fault_family"]]))
    if not ranked:
        return None
    flag = ranked[0]
    return {"kind": "question", "say": questions[flag["fault_family"]],
            "why": f"Mix Review measured the whole render ({str(flag.get('label') or flag['fault_family']).lower()}), "
                   "so this is about the mix and master rather than one track."}


def with_mix_review_next_step(review: dict[str, Any]) -> dict[str, Any]:
    """A copy of a Mix Review result carrying its next step; the stored review itself is not changed."""
    step = mix_review_next_step(review)
    if not step:
        return review
    annotated = dict(review)
    annotated["next_step"] = step
    annotated["advice"] = [*(annotated.get("advice") or []),
                           next_step_line(step, "To measure again, export and load the new file in Inputs.")]
    return annotated


__all__ = ["REMEASURE", "mix_review_next_step", "next_step", "next_step_line", "with_mix_review_next_step"]
