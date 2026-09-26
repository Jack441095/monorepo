"""Named mix recipes: a mix intention turned into up to three typed, confirmable changes (Stage 3).

Each recipe answers one clear intention ("make room for the kick", "give the vocal some space"), never a bare volume
request: "the hats are too loud" still gets "by how much?". A recipe writes its steps as ordinary commands ("turn
Bass down 1.5 dB", "lower the Drum Bus compressor threshold by 3 dB") and each goes through the same rule parser, unit
conversion and safety checks as a command the producer typed: faders stay at or below 0 dB, device values are
converted from real units, and a step that can't be done exactly makes the whole recipe ask instead. Nothing changes
until Apply, and the recipe undoes in one step.

Levels are read from Live when the recipe is built: a layout-only snapshot has no fader values, and the older recipes
assumed 0.75 when one was missing.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Any, Callable

Built = tuple[list[str], str] | str  # (commands, what the card says) or a question


@dataclass(frozen=True)
class Set:
    tracks: list[dict]
    returns: list[dict]

    def all(self, *words: str) -> list[dict]:
        return [track for track in self.tracks
                if any(re.search(rf"\b{re.escape(word)}\b", str(track.get("name") or "").lower()) for word in words)]

    def find(self, *words: str) -> dict | None:
        """The one track in this role; None when there's none or several (a recipe never guesses between them)."""
        found = self.all(*words)
        return found[0] if len(found) == 1 else None

    def which(self, role: str, *words: str) -> str:
        """The question to ask when a role is missing or matches several tracks."""
        found = self.all(*words)
        if len(found) > 1:
            return f"Which is the {role}: {' or '.join(repr(t['name']) for t in found)}? Name it and I'll go ahead."
        return f"Which track is the {role}? Name it and I'll go ahead."

    def named(self, phrase: str) -> dict | None:
        """The one track a phrase names ("the vox", "hats", "Snare / Clap"), or None."""
        from kenn.core.live_intent import _extract_track_phrase, _find_track

        found = _extract_track_phrase(phrase, self.tracks)
        if not found:
            return None
        track, ambiguous, error = _find_track(found, self.tracks)
        return None if error or ambiguous else track

    def ret(self, word: str) -> str | None:
        return next((str(r["name"]) for r in self.returns if word in str(r.get("name") or "").lower()), None)

    @staticmethod
    def panned(track: dict) -> bool:
        return abs(float(track.get("panning", track.get("pan", 0.0)) or 0.0)) > 0.02

    @staticmethod
    def has(track: dict, device: str) -> bool:
        return any(device.lower() in str(d.get("name") if isinstance(d, dict) else d).lower() for d in track.get("devices") or [])


@dataclass(frozen=True)
class Recipe:
    name: str
    pattern: re.Pattern[str]
    build: Callable[[Set, re.Match[str]], Built]


def _room_for_kick(s: Set, _m: re.Match[str]) -> Built:
    kick, bass = s.find("kick", "bd"), s.find("bass", "sub", "808")
    if not kick:
        return s.which("kick", "kick", "bd")
    if not bass:
        return s.which("bass", "bass", "sub", "808")
    commands = [f"turn {bass['name']} down 1.5 dB"] + ([f"centre {bass['name']}"] if s.panned(bass) else [])
    return commands, f"To make room for '{kick['name']}': turn '{bass['name']}' down 1.5 dB" + (
        " and centre it." if len(commands) == 2 else ".")


def _space(s: Set, m: re.Match[str]) -> Built:
    track = s.named(m.group("what"))
    if not track:
        return "Which track should get the space? Name it and I'll send it to the reverb."
    reverb, delay = s.ret("reverb"), s.ret("delay")
    if not reverb:
        return "I couldn't find a reverb return in this set. Add one and I'll send the track to it."
    vocal = re.search(r"\b(?:vocal|vox|voice)\b", str(track["name"]), re.I)
    commands = [f"send the {track['name']} to the {reverb} at {15 if vocal else 12}%"]
    if vocal and delay:
        commands.append(f"send the {track['name']} to the {delay} at 8%")
    sends = " and ".join(f"{r} at {p}%" for r, p in ([(reverb, 15), (delay, 8)] if len(commands) == 2
                                                    else [(reverb, 15 if vocal else 12)]))
    return commands, f"To give '{track['name']}' some space: send it to {sends}."


def _forward(s: Set, m: re.Match[str]) -> Built:
    track = s.named(m.group("what"))
    if not track:
        return "Which track should come forward? Name it and I'll bring it up."
    return [f"turn {track['name']} up 1.5 dB"], f"To bring '{track['name']}' forward: turn it up 1.5 dB."


def _push_back(s: Set, m: re.Match[str]) -> Built:
    track, reverb = s.named(m.group("what")), s.ret("reverb")
    if not track:
        return "Which track should sit further back? Name it and I'll push it back."
    commands = [f"turn {track['name']} down 1.5 dB"] + ([f"send the {track['name']} to the {reverb} at 15%"] if reverb else [])
    return commands, f"To push '{track['name']}' back: turn it down 1.5 dB" + (
        f" and send it to {reverb} at 15%." if reverb else ".")


def _behind(s: Set, m: re.Match[str]) -> Built:
    back, front, reverb = s.named(m.group("what")), s.named(m.group("other")), s.ret("reverb")
    if not back or not front or back is front:
        return "Which track should sit behind which? Name both and I'll push the first one back."
    commands = [f"turn {back['name']} down 2 dB"] + ([f"send the {back['name']} to the {reverb} at 12%"] if reverb else [])
    return commands, f"To sit '{back['name']}' behind '{front['name']}': turn it down 2 dB" + (
        f" and send it to {reverb} at 12%." if reverb else ".")


def _dry_up(s: Set, m: re.Match[str]) -> Built:
    track = s.named(m.group("what"))
    if not track:
        return "Which track should be drier? Name it and I'll take its reverb and delay sends off."
    said = m.group(0) if hasattr(m, "group") else ""
    only_reverb = bool(re.search(r"\b(?:reverb|verb)\b", said, re.I)) and not re.search(r"\bdelay\b", said, re.I)
    returns = [r for r in (s.ret("reverb"), None if only_reverb else s.ret("delay")) if r]
    if not returns:
        return "This set has no reverb or delay returns, so there's nothing to take off."
    return ([f"send the {track['name']} to the {r} at 0%" for r in returns],
            f"To dry up '{track['name']}': turn its {' and '.join(returns)} sends to 0%.")


def _compressor_threshold(words: tuple[str, ...], label: str) -> Callable[[Set, re.Match[str]], Built]:
    def build(s: Set, _m: re.Match[str]) -> Built:
        track = s.find(*words)
        if not track:
            return s.which(label, *words)
        if not s.has(track, "Compressor"):
            return (f"'{track['name']}' has no Compressor to adjust. Want me to add one first? "
                    f"(Say \"put a compressor on the {track['name']}\".)")
        return ([f"lower the {track['name']} compressor threshold by 3 dB"],
                f"On '{track['name']}': lower the Compressor threshold by 3 dB, so it works a little harder.")
    return build


def _mono_low_end(s: Set, _m: re.Match[str]) -> Built:
    low = []
    for words in (("kick", "bd"), ("bass",), ("sub", "808")):
        for track in s.all(*words):  # every low-end track gets centred, so several basses are fine here
            if track not in low:
                low.append(track)
    if not low:
        return "Which tracks carry the low end? Name the kick and bass and I'll centre them."
    panned = [t for t in low if s.panned(t)]
    if len(panned) > 3:
        return (f"{len(panned)} low-end tracks are panned ({', '.join(t['name'] for t in panned)}); a recipe changes at "
                "most three. Which should I centre first?")
    if not panned:
        return f"The low end is already centred ({', '.join(t['name'] for t in low)}). Nothing to change."
    return ([f"centre {t['name']}" for t in panned],
            f"To centre the low end: pan {', '.join(t['name'] for t in panned)} to the middle.")


def _rhythm_section(s: Set, _m: re.Match[str]) -> Built:
    roles = (("kick", ("kick", "bd")), ("snare", ("snare", "clap")), ("bass", ("bass",)))
    for role, words in roles:
        if len(s.all(*words)) > 1:
            return s.which(role, *words)
    parts = [t for t in (s.find(*words) for _role, words in roles) if t]
    if len(parts) < 2:
        return "Which tracks are the rhythm section? Name them and I'll solo them."
    names = [t["name"] for t in parts]
    return [f"solo {n}" for n in names], f"To hear the rhythm section: solo {', '.join(names)}."


def _snare_crack(s: Set, _m: re.Match[str]) -> Built:
    snare, reverb = s.find("snare", "clap"), s.ret("reverb")
    if not snare:
        return s.which("snare", "snare", "clap")
    commands = [f"turn {snare['name']} up 1.5 dB"] + ([f"send the {snare['name']} to the {reverb} at 10%"] if reverb else [])
    return commands, f"To make '{snare['name']}' crack: turn it up 1.5 dB" + (
        f" and send it to {reverb} at 10%." if reverb else ".")


def _clear_solos(s: Set, _m: re.Match[str]) -> Built:
    soloed = [t for t in s.tracks if t.get("soloed") or t.get("solo")]
    if not soloed:
        return "Nothing is soloed, so there's nothing to clear."
    if len(soloed) > 3:
        return (f"{len(soloed)} tracks are soloed ({', '.join(t['name'] for t in soloed)}); a recipe changes at most three. "
                "Use Live's solo buttons, or unsolo them a few at a time.")
    names = [t["name"] for t in soloed]
    return [f"unsolo {n}" for n in names], f"To clear the solos: unsolo {', '.join(names)}."


_WHAT = r"(?:the\s+)?(?P<what>[\w/&' -]+?)"
RECIPES: tuple[Recipe, ...] = (
    Recipe("room_for_kick", re.compile(r"\b(?:make|give|leave)\s+(?:some\s+)?room\s+for\s+the\s+kick\b"
                                       r"|\bkick\s+and\s+(?:the\s+)?bass\s+(?:are\s+)?(?:fighting|clashing|masking)\b", re.I),
           _room_for_kick),
    Recipe("space", re.compile(rf"\bgive\s+{_WHAT}\s+some\s+(?:space|ambience|depth)\s*[.!?]?\s*$"
                               r"|\b(?:some\s+)?(?:space|ambience|depth)\s+(?:on|to)\s+the\s+(?P<what2>vocal|vox|vocals)\b", re.I),
           lambda s, m: _space(s, _Alias(m))),
    Recipe("forward", re.compile(rf"\bbring\s+{_WHAT}\s+(?:forward|to\s+the\s+front)\s*[.!?]?\s*$", re.I), _forward),
    Recipe("push_back", re.compile(rf"\b(?:push|sit|move|set)\s+{_WHAT}\s+(?:further\s+)?back(?:\s+in\s+the\s+mix)?\s*[.!?]?\s*$",
                                   re.I), _push_back),
    Recipe("behind", re.compile(rf"\b(?:put|sit|tuck)\s+{_WHAT}\s+behind\s+(?:the\s+)?(?P<other>[\w/&' -]+?)\s*[.!?]?\s*$", re.I),
           _behind),
    Recipe("dry_up", re.compile(rf"\bdry\s+(?:up\s+)?{_WHAT}\s*[.!?]?\s*$|\bmake\s+{_WHAT.replace('what', 'what2')}\s+drier\b"
                                r"|\btake\s+the\s+(?:reverb|verb|effects?)\s+off\s+(?:the\s+)?(?P<what3>[\w/&' -]+?)\s*[.!?]?\s*$", re.I),
           lambda s, m: _dry_up(s, _Alias(m))),
    Recipe("tighten_drum_bus", re.compile(r"\btighten\s+(?:up\s+)?the\s+drum(?:s|\s+bus)?\b", re.I),
           _compressor_threshold(("drum bus", "drums", "drum"), "drum bus")),
    Recipe("vocal_peaks", re.compile(r"\b(?:tame|control|even\s+out)\s+the\s+(?:vocal|vox)(?:'s)?\s*(?:peaks|dynamics)?\b", re.I),
           _compressor_threshold(("vocal", "vox"), "vocal")),
    Recipe("mono_low_end", re.compile(r"\b(?:make|keep|get)\s+the\s+low[\s-]end\s+(?:mono|centred|centered)\b"
                                      r"|\b(?:centre|center|mono)\s+the\s+low[\s-]end\b", re.I),
           _mono_low_end),
    Recipe("rhythm_section", re.compile(r"\b(?:solo|hear)\s+(?:just\s+)?the\s+rhythm\s+section\b", re.I), _rhythm_section),
    Recipe("snare_crack", re.compile(r"\bmake\s+the\s+(?:snare|clap)\s+(?:crack|pop|snap|cut\s+through)\b", re.I), _snare_crack),
    Recipe("clear_solos", re.compile(r"\bunsolo\s+(?:all|everything)\b|\bclear\s+(?:all\s+)?(?:the\s+)?solos\b"
                                     r"|\bturn\s+off\s+(?:all\s+)?(?:the\s+)?solos\b", re.I), _clear_solos),
)


class _Alias:
    """Lets one builder read whichever of what / what2 / what3 the pattern filled in."""

    def __init__(self, match: re.Match[str]):
        self._match = match

    def group(self, name: str | int) -> str:
        if name == 0:
            return self._match.group(0)
        groups = self._match.groupdict()
        return next((groups[k] for k in (name, f"{name}2", f"{name}3") if groups.get(k)), "")


def match(query: str) -> Recipe | None:
    return next((recipe for recipe in RECIPES if recipe.pattern.search(str(query or ""))), None)


def translate(query: str, service: Any, session_id: str) -> dict[str, Any] | None:
    """A recipe proposal, a question, or None when no recipe matches."""
    from kenn.core.live_command import _resolve_natural_recipe_steps
    from kenn.core.live_intent import parse_request
    from kenn.core.live_recipe import LiveRecipeService

    recipe = match(query)
    if recipe is None:
        return None
    state = service.snapshot()
    if not state.get("return_tracks"):
        # The session snapshot never lists returns on real Live (only the fake fills them in), so "give the vocal
        # some space" found no reverb on the demo set's A-Reverb. Read them the way a spoken "send" does.
        try:
            state = {**state, "return_tracks": service.client.get_return_tracks()}
        except Exception:
            pass
    current = Set([t for t in state.get("tracks", []) if isinstance(t, dict)],
                  [r for r in state.get("return_tracks", []) if isinstance(r, dict)])
    built = recipe.build(current, recipe.pattern.search(query))
    if isinstance(built, str):
        return _question(recipe, built)
    commands, summary = built
    entries = []
    for command in commands:
        intent = parse_request(command, state)
        if not intent.get("action") or intent.get("missing_fields"):
            reason = (intent.get("ambiguity") or ["that step isn't one KENN can do exactly"])[0]
            return _question(recipe, f"I can't do that exactly here: {reason} Nothing changed.")
        entries.append({"intent": intent, "segment": command})
    steps, error = _resolve_natural_recipe_steps(service, {"step_intents": entries}, state, session_id=session_id,
                                                  command=query)
    if error:
        return _question(recipe, f"I can't do that exactly here: {error} Nothing changed.")
    result = LiveRecipeService(service).propose_recipe(steps, reason=summary, session_id=session_id)
    if result.get("ok"):
        # A step that's already where the recipe would put it ("dry up" on a dry vocal) is left out; if nothing's left,
        # say so rather than show a card that changes nothing.
        children = result["proposal"].get("steps") or []
        needed = [step for step, child in zip(steps, children) if child.get("before") != child.get("after")]
        if not needed:
            return {"status": "answered", "answer": "That's already how the set is, so there's nothing to change.",
                    "changed": False, "intent": {"action": "recipe", "recipe_name": recipe.name}}
        if len(needed) < len(steps):
            result = LiveRecipeService(service).propose_recipe(needed, reason=summary, session_id=session_id)
    if not result.get("ok"):
        return {"status": "failed", "answer": result.get("error", "I couldn't prepare that recipe."), "changed": False}
    return {"status": "proposed", "intent": {"action": "recipe", "recipe_name": recipe.name},
            "proposal": result["proposal"], "confirmation_token": result.get("confirmation_token", ""),
            "requires_confirmation": True, "answer": f"{summary} Nothing changes until you press Apply."}


def _question(recipe: Recipe, text: str) -> dict[str, Any]:
    return {"status": "clarification_required", "answer": text, "changed": False,
            "intent": {"action": "recipe", "recipe_name": recipe.name, "missing_fields": ["recipe_target"]}}


__all__ = ["RECIPES", "Recipe", "match", "translate"]
