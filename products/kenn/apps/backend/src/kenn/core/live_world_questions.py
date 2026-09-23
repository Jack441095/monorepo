"""Read-only answers grounded in the Live world model.

Covers questions the fast session snapshot cannot answer: what is on a track,
return, or the master (including rack chains), which tracks send to a return,
a named device parameter's current value, mute/solo state, and Live's scale
setting. Every answer cites the model fingerprint; nothing is inferred when
Live did not report it.
"""

from __future__ import annotations

import re
from typing import Any


NOTE_NAMES = ["C", "C#", "D", "D#", "E", "F", "F#", "G", "G#", "A", "A#", "B"]
_WORD = re.compile(r"[a-z0-9]+")


def _question_kind(lower: str) -> str | None:
    if re.search(r"\bwhich\b.*\bsend(?:s|ing)?\b.*\bto\b", lower) or re.search(r"\bwho\b.*\bsends?\b", lower):
        return "sends_to"
    if re.search(r"\bwhat(?:'s| is)\b.*\b(?:threshold|ratio|attack|release|output|gain|frequency|dry/?wet|drive|makeup|knee)\b", lower):
        return "parameter_value"
    if re.search(r"\b(?:anything|any tracks?|which tracks?)\b.*\b(?:muted|soloed)\b", lower) or re.search(r"\bwhat(?:'s| is)\b.*\b(?:muted|soloed)\b", lower):
        return "mute_solo"
    if re.search(r"\bwhat\s+key\b|\bwhich\s+key\b|\bkey\s+(?:is|of)\s+(?:the\s+)?(?:song|set|track)\b|\bwhat\s+scale\b", lower):
        return "song_key"
    # "What is on track 4?" stays on the existing inventory route; this path
    # adds returns, the master, and tracks named by name (with rack chains).
    if re.search(r"\btrack\s*#?\s*\d+\b", lower):
        return None
    if re.search(r"\bwhat(?:'s| is| are)\b.*\bon\b.*\b(?:track|bus|return|master|channel)\b", lower) or re.search(
        r"\bwhat(?:'s| is)\s+on\s+(?:the\s+)?\S", lower
    ):
        return "chain_contents"
    return None


def _words(text: str) -> set[str]:
    return set(_WORD.findall(text.casefold()))


def _resolve_bus(lower: str, model: dict[str, Any]) -> dict[str, Any] | None:
    """Pick one track, return, or the master named in the question."""
    number = re.search(r"\btrack\s*#?\s*(\d+)\b", lower)
    if number:
        index = int(number.group(1)) - 1
        track = next((t for t in model["tracks"] if t.get("index") == index), None)
        return {"kind": "track", "entity": track} if track else None
    if re.search(r"\bmaster\b|\bmain\s+(?:out|bus)\b", lower):
        if model.get("master"):
            return {"kind": "master", "entity": model["master"]}
        return {"unavailable": "master"}
    asked = _words(lower)
    candidates = [("return", r) for r in model.get("returns", [])] + [("track", t) for t in model["tracks"]]
    scored = []
    for kind, entity in candidates:
        name = str(entity.get("name", ""))
        name_words = _words(re.sub(r"^[a-z]-", "", name.casefold())) - {"track"}
        overlap = len(asked & name_words)
        if overlap:
            scored.append((overlap, -len(name_words), kind, entity))
    if not scored:
        return None
    scored.sort(key=lambda item: (item[0], item[1]), reverse=True)
    best = scored[0]
    if len(scored) > 1 and scored[1][:2] == best[:2]:
        return {"ambiguous": [s[3].get("name") for s in scored if s[:2] == best[:2]]}
    return {"kind": best[2], "entity": best[3]}


def _device_lines(devices: list[dict[str, Any]], depth: int = 0) -> list[str]:
    lines = []
    for device in devices:
        lines.append(("  " * depth) + str(device.get("name", "")))
        for chain in device.get("chains") or []:
            lines.append(("  " * (depth + 1)) + f"chain '{chain.get('name', '')}':")
            lines.extend(_device_lines(chain.get("devices") or [], depth + 2))
    return lines


def _base(kind: str, model: dict[str, Any]) -> dict[str, Any]:
    return {"schema": "kenn.ableton_session_answer.v1", "status": "inspected",
            "intent": {"action": f"inspect_{kind}"}, "changed": False,
            "world_model_fingerprint": model.get("fingerprint"), "world_model_version": model.get("version"),
            "backend": model.get("backend")}


def answer_world_question(question: str, client: Any) -> dict[str, Any] | None:
    lower = " ".join(str(question or "").casefold().split())
    kind = _question_kind(lower)
    if kind is None:
        return None
    from kenn.core.live_world_state import world_state

    model = world_state.current(client)
    if model.get("status") != "connected":
        return {"schema": "kenn.ableton_session_answer.v1", "status": "offline", "changed": False,
                "intent": {"action": f"inspect_{kind}"},
                "answer": "Ableton Live isn't responding, so I can't read the session right now."}
    payload = _base(kind, model)

    if kind == "song_key":
        root, scale = model["song"].get("root_note"), model["song"].get("scale_name")
        if isinstance(root, int) and scale:
            payload["answer"] = (f"Live's scale setting is {NOTE_NAMES[root % 12]} {scale}. "
                                 "That is the set's scale setting, not a key detected from the audio.")
        else:
            payload.update({"status": "unavailable", "answer": "Live did not report a scale setting."})
        return payload

    if kind == "mute_solo":
        muted = [t["name"] for t in model["tracks"] if t.get("muted")] + \
            [r["name"] for r in model.get("returns", []) if r.get("mute")]
        soloed = [t["name"] for t in model["tracks"] if t.get("soloed")] + \
            [r["name"] for r in model.get("returns", []) if r.get("solo")]
        parts = [f"Muted: {', '.join(muted)}." if muted else "Nothing is muted.",
                 f"Soloed: {', '.join(soloed)}." if soloed else "Nothing is soloed."]
        payload.update({"answer": " ".join(parts), "muted": muted, "soloed": soloed})
        return payload

    if kind == "sends_to":
        target = _resolve_bus(lower, {"tracks": [], "returns": model.get("returns", []), "master": None})
        if not model["availability"].get("track_sends"):
            payload.update({"status": "unavailable", "answer": "Live did not report send levels in this read."})
            return payload
        if not target or "entity" not in target:
            names = ", ".join(r["name"] for r in model.get("returns", [])) or "none"
            payload.update({"status": "clarification_required",
                            "answer": f"Which return do you mean? The returns are: {names}."})
            return payload
        ret = target["entity"]
        senders = [
            {"track": t["name"], "value": s["value"]}
            for t in model["tracks"] for s in t.get("sends") or []
            if s.get("return_track_index") == ret["index"] and float(s.get("value") or 0.0) > 0.0
        ]
        payload.update({
            "answer": (f"These tracks send to '{ret['name']}': "
                       + ", ".join(f"{s['track']} ({s['value']:.2f})" for s in senders) + "."
                       if senders else f"No track sends to '{ret['name']}' right now."),
            "return_track": ret["name"], "senders": senders,
        })
        return payload

    target = _resolve_bus(lower, model)
    if target and "unavailable" in target:
        payload.update({"status": "unavailable",
                        "answer": "Live did not report the master track in this read. It needs the updated "
                                  "AbletonOSC (deploy_abletonosc.py --apply --reload)."})
        return payload
    if target and "ambiguous" in target:
        payload.update({"status": "clarification_required",
                        "answer": "Which one do you mean: " + ", ".join(target["ambiguous"]) + "?"})
        return payload
    if not target:
        payload.update({"status": "clarification_required",
                        "answer": "Which track, return, or the master do you mean?"})
        return payload
    entity, entity_kind = target["entity"], target["kind"]

    if kind == "chain_contents":
        tree = entity.get("device_tree")
        if tree is None:
            names = entity.get("devices") or []
            tree = [{"name": d.get("name") if isinstance(d, dict) else d} for d in names]
        label = "the master" if entity_kind == "master" else f"'{entity.get('name')}'"
        lines = _device_lines(tree)
        payload.update({
            "answer": (f"{label[0].upper()}{label[1:]} has: " + "; ".join(line.strip() for line in lines) + "."
                       if lines else f"{label[0].upper()}{label[1:]} has no devices."),
            "target": {"kind": entity_kind, "name": entity.get("name"), "index": entity.get("index")},
            "devices": tree,
        })
        return payload

    # parameter_value
    getter = getattr(client, "get_bus_device_parameters", None)
    devices = entity.get("device_tree") or [{"name": d.get("name") if isinstance(d, dict) else d}
                                            for d in entity.get("devices") or []]
    asked = _words(lower)
    device_index = next((i for i, d in enumerate(devices) if _words(str(d.get("name", ""))) & asked), None)
    if device_index is None and len(devices) == 1:
        device_index = 0
    if device_index is None or not callable(getter):
        payload.update({"status": "clarification_required",
                        "answer": f"Which device on '{entity.get('name')}' do you mean?"})
        return payload
    index = -1 if entity_kind == "master" else int(entity.get("index", -1))
    info = getter(entity_kind, index, device_index)
    if not info.get("success"):
        payload.update({"status": "unavailable", "answer": "Live did not report that device's parameters."})
        return payload
    wanted = [w for w in ("threshold", "ratio", "attack", "release", "output", "gain", "frequency", "drive",
                          "makeup", "knee", "dry") if w in asked or (w == "dry" and "dry/wet" in lower)]
    matches = [p for p in info["parameters"] if wanted and _words(str(p.get("name", ""))) & set(wanted)]
    if not matches:
        payload.update({"status": "clarification_required",
                        "answer": f"I couldn't find that parameter on {info.get('device_name')}."})
        return payload
    shown = "; ".join(f"{p['name']} is {p.get('value_display') or p.get('value')}" for p in matches[:4])
    payload.update({
        "answer": f"On '{entity.get('name')}' → {info.get('device_name')}: {shown}.",
        "target": {"kind": entity_kind, "name": entity.get("name"), "device": info.get("device_name")},
        "parameters": matches[:4],
    })
    return payload


__all__ = ["answer_world_question"]
