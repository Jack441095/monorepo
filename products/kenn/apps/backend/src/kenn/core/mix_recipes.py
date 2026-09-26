"""Named mix recipes: a mix intention turned into up to three typed, confirmable changes (Stage 3).

Each recipe answers one clear intention ("make room for the kick", "give the vocal some space"), never a bare
volume request: "the hats are too loud" still gets "by how much?". Amounts are small and stated in real units on the
proposal card; faders move on Live's fader law and never past 0 dB; nothing changes until Apply, and the whole recipe
undoes in one step like any other. Tracks are found by name in the current set, and a recipe that can't find what it
needs asks rather than guessing.

Levels are read from Live when the recipe is built: a layout-only snapshot has no fader values, and the older recipes
assumed 0.75 when one was missing.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Any, Callable

from kenn.core import volume_law

Step = dict[str, Any]


@dataclass(frozen=True)
class Recipe:
    name: str
    pattern: re.Pattern[str]
    build: Callable[[list[dict], list[dict]], tuple[list[Step], str] | str]


def _find(tracks: list[dict], *words: str, exclude: dict | None = None) -> dict | None:
    for track in tracks:
        name = str(track.get("name") or "").lower()
        if track is not exclude and any(re.search(rf"\b{re.escape(word)}\b", name) for word in words):
            return track
    return None


def _index(track: dict) -> int:
    return int(track.get("index", track.get("track_index", 0)))


def _fader(track: dict, change_db: float) -> Step | None:
    current = volume_law.raw_to_db(float(track.get("volume") or 0.0))
    if current is None or current + change_db > 0.0:
        return None
    return {"action": "set_volume", "track_index": _index(track), "track_name": track["name"],
            "value": volume_law.db_to_raw(current + change_db)}


def _centre(track: dict) -> Step | None:
    pan = float(track.get("panning", track.get("pan", 0.0)) or 0.0)
    if abs(pan) <= 0.02:
        return None
    return {"action": "set_pan", "track_index": _index(track), "track_name": track["name"], "value": 0.0}


def _send(track: dict, returns: list[dict], word: str, amount: float) -> Step | None:
    target = next((r for r in returns if word in str(r.get("name") or "").lower()), None)
    if target is None:
        return None
    return {"action": "set_send", "track_index": _index(track), "track_name": track["name"],
            "return_track_index": int(target.get("index", 0)), "return_track_name": target["name"], "value": amount}


def _room_for_kick(tracks: list[dict], _returns: list[dict]) -> tuple[list[Step], str] | str:
    kick, bass = _find(tracks, "kick", "bd"), _find(tracks, "bass", "sub", "808")
    if not kick or not bass:
        return "Which tracks are the kick and the bass? Name them and I'll make room for the kick."
    steps = [step for step in (_fader(bass, -1.5), _centre(bass)) if step]
    if not steps:
        return f"I couldn't read the level of '{bass['name']}', so nothing changed."
    centred = " and centre it" if len(steps) == 2 else ""
    return steps, f"To make room for '{kick['name']}': turn '{bass['name']}' down 1.5 dB{centred}."


def _vocal_space(tracks: list[dict], returns: list[dict]) -> tuple[list[Step], str] | str:
    vocal = _find(tracks, "vocal", "vox", "vocals")
    if not vocal:
        return "Which track is the vocal? Name it and I'll add some space."
    steps = [step for step in (_send(vocal, returns, "reverb", 0.15), _send(vocal, returns, "delay", 0.08)) if step]
    if not steps:
        return "I couldn't find a reverb or delay return in this set. Add one and I'll send the vocal to it."
    parts = [f"{s['return_track_name']} at {round(s['value'] * 100)}%" for s in steps]
    return steps, f"To give '{vocal['name']}' some space: send it to {' and '.join(parts)}."


def _drums_forward(tracks: list[dict], _returns: list[dict]) -> tuple[list[Step], str] | str:
    drums = _find(tracks, "drum bus", "drums", "drum")
    if not drums:
        return "Which track carries the drums? Name the drum bus and I'll bring it forward."
    step = _fader(drums, 1.5)
    if not step:
        return f"'{drums['name']}' is already at or near 0 dB. Want me to turn the other parts down instead?"
    return [step], f"To bring the drums forward: turn '{drums['name']}' up 1.5 dB."


def _mono_low_end(tracks: list[dict], _returns: list[dict]) -> tuple[list[Step], str] | str:
    low = []
    for words in (("kick", "bd"), ("bass",), ("sub", "808")):
        track = _find(tracks, *words)
        if track and track not in low:
            low.append(track)
    if not low:
        return "Which tracks carry the low end? Name the kick and bass and I'll centre them."
    steps = [step for step in (_centre(track) for track in low) if step][:3]
    if not steps:
        return f"The low end is already centred ({', '.join(t['name'] for t in low)}). Nothing to change."
    return steps, f"To centre the low end: pan {', '.join(s['track_name'] for s in steps)} to the middle."


RECIPES: tuple[Recipe, ...] = (
    Recipe("room_for_kick", re.compile(r"\b(?:make|give|leave)\s+(?:some\s+)?room\s+for\s+the\s+kick\b"
                                       r"|\bkick\s+and\s+(?:the\s+)?bass\s+(?:are\s+)?(?:fighting|clashing|masking)\b", re.I),
           _room_for_kick),
    Recipe("vocal_space", re.compile(r"\b(?:give|add)\s+(?:the\s+)?(?:vocal|vox|vocals)\s+(?:some\s+)?(?:space|ambience|depth)\b"
                                     r"|\b(?:some\s+)?(?:space|ambience|depth)\s+(?:on|to)\s+the\s+(?:vocal|vox|vocals)\b", re.I),
           _vocal_space),
    Recipe("drums_forward", re.compile(r"\bbring\s+the\s+drums?(?:\s+bus)?\s+forward\b", re.I), _drums_forward),
    Recipe("mono_low_end", re.compile(r"\b(?:make|keep|get)\s+the\s+low[\s-]end\s+(?:mono|centred|centered)\b"
                                      r"|\b(?:centre|center|mono)\s+the\s+low[\s-]end\b", re.I),
           _mono_low_end),
)


def match(query: str) -> Recipe | None:
    return next((recipe for recipe in RECIPES if recipe.pattern.search(str(query or ""))), None)


def translate(query: str, service: Any, session_id: str) -> dict[str, Any] | None:
    """A recipe proposal, a question, or None when no recipe matches."""
    from kenn.core.live_recipe import LiveRecipeService

    recipe = match(query)
    if recipe is None:
        return None
    state = service.snapshot()
    tracks = [t for t in state.get("tracks", []) if isinstance(t, dict)]
    returns = [r for r in state.get("return_tracks", []) if isinstance(r, dict)]
    built = recipe.build(tracks, returns)
    if isinstance(built, str):
        return {"status": "clarification_required", "answer": built, "changed": False,
                "intent": {"action": "recipe", "recipe_name": recipe.name, "missing_fields": ["recipe_target"]}}
    steps, summary = built
    result = LiveRecipeService(service).propose_recipe(steps, reason=summary, session_id=session_id)
    if not result.get("ok"):
        return {"status": "failed", "answer": result.get("error", "I couldn't prepare that recipe."), "changed": False}
    return {"status": "proposed", "intent": {"action": "recipe", "recipe_name": recipe.name},
            "proposal": result["proposal"], "confirmation_token": result.get("confirmation_token", ""),
            "requires_confirmation": True, "answer": f"{summary} Nothing changes until you press Apply."}


__all__ = ["RECIPES", "Recipe", "match", "translate"]
