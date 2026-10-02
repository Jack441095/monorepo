"""Rules that can decide from the set alone, before one track is chosen.

These read ``TRANSPORT_ACTIONS``, ``SONG_ACTIONS``, ``VIEW_ACTIONS`` and the
inspect, clip, locator and send actions out of ``live_command.LLM_PLAN_ACTIONS``:
the questions and changes that belong to the session rather than to a track. They
run ahead of track resolution because a scene launch and a clip-slot stop both
carry a track number without being track changes, and because a return-track send
names its source in a shape none of the track rules read.

Lifted verbatim out of ``live_intent._parse_request_rules``.
"""

from __future__ import annotations

import re
from typing import Any

from kenn.core.live_intent import (
    _ADD_LOCATOR,
    _DEVICE_CONTROL_REFERENCE,
    _DUPLICATE_CLIP,
    _FOCUS_DEVICE,
    _FOCUS_TRACK,
    _FOCUS_TRACK_BARE_NAME,
    _FOCUS_TRACK_NAME,
    _LOCATOR_REQUEST,
    _MUTE_SEND,
    _NUMBERED_SCENE,
    _REMOVE_LOCATOR,
    _RENAME_CLIP,
    _SEND_TRACK_FIRST,
    _SET_SEND,
    _SET_TRACK_SEND,
    _STOP_CLIP_MENTION,
    _STOP_CLIP_SLOT_THEN_TRACK,
    _STOP_CLIP_TRACK_THEN_SLOT,
    _UNSUPPORTED_CLIP_CONTROL,
    _UNSUPPORTED_DEVICE_CONTROL,
    _UNSUPPORTED_MASTER_CONTROL,
    _UNSUPPORTED_RETURN_CONTROL,
    _UNSUPPORTED_SCENE_CONTROL,
    _UNSUPPORTED_SEND_CONTROL,
    _choice_request,
    _extract_track_phrase,
    _find_clip_track,
    _find_numbered_track,
    _find_track,
    _named_device_focus,
    _named_scene,
    _tempo_request,
    _track_to_return_send,
    _time_signature_request,
)


def resolve_session_rules(
    base: dict[str, Any],
    text: str,
    numeric_text: str,
    tracks: list[dict[str, Any]],
    session_snapshot: dict[str, Any] | None,
) -> dict[str, Any] | None:
    """The set-level result for this request, or None to fall through."""
    lower = numeric_text.lower()
    snapshot = session_snapshot or {}
    duplicate_clip_match = _DUPLICATE_CLIP.fullmatch(numeric_text)
    rename_clip_match = _RENAME_CLIP.fullmatch(numeric_text)
    if any(cue in lower for cue in ("list my tracks", "what tracks", "which tracks", "show my tracks", "show the tracks")) or re.search(
            r"^\s*(?:list|show(?:\s+me)?)\s+(?:all\s+)?(?:of\s+)?(?:the|my)\s+tracks\b", lower):
        base.update({"action": "inspect_tracks", "confidence": 0.99})
        return base
    focus_device_match = _FOCUS_DEVICE.match(text)
    if focus_device_match:
        track_number = int(focus_device_match.group("track_number"))
        focus_track, focus_error = _find_numbered_track(track_number, tracks)
        if focus_error or focus_track is None:
            base["missing_fields"].append("track")
            base["ambiguity"].append(focus_error or f"Track {track_number} is not present in the current Live snapshot.")
            return base
        device_phrase = " ".join(focus_device_match.group("device").strip(" '\"").split())
        devices = [item for item in (focus_track.get("devices") or []) if isinstance(item, dict)]
        matches = [
            item for item in devices
            if str(item.get("name", "")).strip().casefold() == device_phrase.casefold()
        ]
        if len(matches) != 1:
            base["missing_fields"].append("device")
            base["ambiguity"].append(
                f"Device {device_phrase!r} is not an exact, unique device on track {track_number}."
            )
            return base
        device = matches[0]
        base.update({
            "mode": "assist",
            "action": "focus_device",
            "track_reference": {"kind": "user_track_number", "number": track_number},
            "track": {"index": focus_track.get("index"), "name": str(focus_track.get("name", ""))},
            "device": {"index": int(device.get("index", devices.index(device))), "name": str(device.get("name", ""))},
            "confirmation_required": True,
            "confidence": 0.98,
        })
        return base
    named_device = _named_device_focus(text, tracks)
    if named_device is not None:
        focus_track, device = named_device
        base.update({
            "mode": "assist",
            "action": "focus_device",
            "track": {"index": focus_track.get("index"), "name": str(focus_track.get("name", ""))},
            "device": {"index": int(device.get("index", 0)), "name": str(device.get("name", ""))},
            "confirmation_required": True,
            "confidence": 0.95,
        })
        return base
    focus_match = _FOCUS_TRACK.search(lower)
    if focus_match:
        track_number = int(focus_match.group(1))
        focus_track, focus_error = _find_numbered_track(track_number, tracks)
        if focus_error or focus_track is None:
            base["missing_fields"].append("track")
            base["ambiguity"].append(focus_error or f"Track {track_number} is not present in the current Live snapshot.")
            return base
        base.update({
            "mode": "assist",
            "action": "focus_track",
            "track": {"index": focus_track.get("index"), "name": str(focus_track.get("name", ""))},
            "confirmation_required": True,
            "confidence": 0.98,
        })
        return base
    focus_named_match = _FOCUS_TRACK_NAME.match(text)
    if focus_named_match is None:
        # "Select the Drum Bus" / "Focus the bass.": the word "track" left out.
        # Only when the words name exactly one track, so "focus on the low end"
        # keeps its old route.
        bare = _FOCUS_TRACK_BARE_NAME.match(text)
        if bare:
            candidate, _bare_candidates, bare_error = _find_track(" ".join(bare.group("name").split()).strip(" '\""), tracks)
            said = set(re.findall(r"[a-z0-9]+", bare.group("name").casefold())) - {"track", "channel", "the"}
            named = set(re.findall(r"[a-z0-9]+", str((candidate or {}).get("name", "")).casefold()))
            if not bare_error and candidate is not None and said and said <= named:
                focus_named_match = bare
    if focus_named_match:
        requested_track_name = " ".join(
            str(focus_named_match.groupdict().get("name") or focus_named_match.groupdict().get("show_name") or "").split()
        ).strip(" '\"")
        focus_track, _candidates, focus_error = _find_track(requested_track_name, tracks)
        if focus_error or focus_track is None:
            base["missing_fields"].append("track")
            base["ambiguity"].append(focus_error or "The requested track is not present in the current Live snapshot.")
            return base
        base.update({
            "mode": "assist",
            "action": "focus_track",
            "track": {"index": focus_track.get("index"), "name": str(focus_track.get("name", ""))},
            "confirmation_required": True,
            "confidence": 0.98,
        })
        return base
    signature = _time_signature_request(text)
    if signature is not None:
        base.update(signature)
        return base
    tempo = _tempo_request(text, snapshot)
    if tempo is not None:
        base.update(tempo)
        return base
    # Scene launch phrasing ("play scene 2") must be checked before the
    # generic transport play/stop match below, since both contain the bare
    # word "play"/"stop" and scene requests are otherwise unrelated to
    # transport state.
    scene_match = _NUMBERED_SCENE.search(lower)
    if scene_match is None and (named := _named_scene(lower, snapshot)) is not None:
        # "launch the Chorus scene", "fire scene Drop": the scene's own name from the set, whole words only.
        base.update({"mode": "assist", "action": "launch_scene",
                     "scene": {"index": named.get("index"), "name": str(named.get("name", ""))},
                     "confirmation_required": True, "confidence": 0.95})
        return base
    if scene_match:
        scene_number = int(scene_match.group(1))
        scenes = [s for s in (snapshot.get("scenes") if isinstance(snapshot, dict) else []) or [] if isinstance(s, dict)]
        if scene_number < 1 or scene_number > len(scenes):
            base["missing_fields"].append("scene")
            base["ambiguity"].append(f"Scene {scene_number} is not present in the current Live snapshot.")
            return base
        scene = scenes[scene_number - 1]
        base.update({
            "mode": "assist",
            "action": "launch_scene",
            "scene": {"index": scene.get("index"), "name": str(scene.get("name", ""))},
            "confirmation_required": True,
            "confidence": 0.97,
        })
        return base
    if _LOCATOR_REQUEST.search(lower):
        remove_locator = _REMOVE_LOCATOR.match(text)
        locator_match = remove_locator or _ADD_LOCATOR.match(text)
        locator_name = " ".join(str(locator_match.group("name") or "").split()).strip() if locator_match else ""
        if locator_match is None:
            base["ambiguity"].append(
                "Add or remove a named locator at the stopped current playhead, e.g. 'add a locator named Verse at the current position'."
            )
            return base
        if not locator_name:
            base["missing_fields"].append("locator_name")
            base["ambiguity"].append("Give the locator a non-empty name so KENN can verify the exact marker.")
            return base
        base.update({
            "mode": "assist",
            "action": "remove_locator" if remove_locator else "add_locator",
            "locator_name": locator_name,
            "unit": "beats",
            "confirmation_required": True,
            "confidence": 0.98,
        })
        return base
    if duplicate_clip_match:
        source_slot = int(duplicate_clip_match.group("source_slot"))
        target_slot = int(duplicate_clip_match.group("target_slot"))
        source_track, source_ambiguous, source_error = _find_clip_track(duplicate_clip_match.group("source"), tracks)
        target_track, target_ambiguous, target_error = _find_clip_track(duplicate_clip_match.group("target"), tracks)
        base.update({"mode": "assist", "action": "duplicate_clip", "confirmation_required": True, "confidence": 0.97})
        if source_slot < 1:
            base["missing_fields"].append("source_clip_slot")
            base["ambiguity"].append("Source clip slot numbers start at 1.")
        if target_slot < 1:
            base["missing_fields"].append("target_clip_slot")
            base["ambiguity"].append("Target clip slot numbers start at 1.")
        if source_track is None:
            base["missing_fields"].append("source_track")
            base["ambiguity"].append(source_error or ("The source track is ambiguous." if source_ambiguous else "The source track was not found."))
        else:
            base["source_track"] = {"index": source_track.get("index"), "name": str(source_track.get("name", ""))}
        if target_track is None:
            base["missing_fields"].append("target_track")
            base["ambiguity"].append(target_error or ("The target track is ambiguous." if target_ambiguous else "The target track was not found."))
        else:
            base["target_track"] = {"index": target_track.get("index"), "name": str(target_track.get("name", ""))}
        if source_slot >= 1:
            base["source_clip_slot"] = {"index": source_slot - 1}
        if target_slot >= 1:
            base["target_clip_slot"] = {"index": target_slot - 1}
        if source_track is not None and target_track is not None and source_slot == target_slot and source_track.get("index") == target_track.get("index"):
            base["ambiguity"].append("Source and target clip slots must be different.")
        return base
    if rename_clip_match:
        slot = int(rename_clip_match.group("slot"))
        requested_name = " ".join(rename_clip_match.group("name").split()).strip()
        track, ambiguous, error = _find_clip_track(rename_clip_match.group("track"), tracks)
        base.update({"mode": "assist", "action": "rename_clip", "confirmation_required": True, "confidence": 0.97})
        if slot < 1:
            base["missing_fields"].append("clip_slot")
            base["ambiguity"].append("Clip slot numbers start at 1.")
        if not requested_name:
            base["missing_fields"].append("clip_name")
            base["ambiguity"].append("Give the clip a non-empty name.")
        if track is None:
            base["missing_fields"].append("track")
            base["ambiguity"].append(error or ("The track is ambiguous." if ambiguous else "The track was not found."))
        else:
            base["track"] = {"index": track.get("index"), "name": str(track.get("name", ""))}
        if slot >= 1:
            base["clip_slot"] = {"index": slot - 1}
        base["desired_value"] = requested_name
        base["unit"] = "string"
        return base
    # Clip-slot stop phrasing ("stop clip slot 2 on track 3") must also be
    # checked before the generic transport stop match below, and it requires
    # an explicit slot number rather than guessing which of a track's clips
    # is currently playing.
    if _STOP_CLIP_MENTION.search(lower):
        slot_track_match = _STOP_CLIP_SLOT_THEN_TRACK.search(lower)
        track_slot_match = _STOP_CLIP_TRACK_THEN_SLOT.search(lower)
        if slot_track_match:
            clip_slot_number, track_number = int(slot_track_match.group(1)), int(slot_track_match.group(2))
        elif track_slot_match:
            track_number, clip_slot_number = int(track_slot_match.group(1)), int(track_slot_match.group(2))
        else:
            base["missing_fields"].append("clip_slot")
            base["ambiguity"].append(
                "Specify the exact clip slot and track to stop, e.g. 'stop clip slot 1 on track 3'."
            )
            return base
        stop_track, stop_track_error = _find_numbered_track(track_number, tracks)
        if stop_track_error or stop_track is None:
            base["missing_fields"].append("track")
            base["ambiguity"].append(stop_track_error or f"Track {track_number} is not present in the current Live snapshot.")
            return base
        base.update({
            "mode": "assist",
            "action": "stop_clip",
            "track": {"index": stop_track.get("index"), "name": str(stop_track.get("name", ""))},
            "clip_slot": {"index": clip_slot_number - 1},
            "confirmation_required": True,
            "confidence": 0.95,
        })
        return base
    # "set the <return name> send on track N to <value>". The exact return
    # track (name -> index, ambiguity/unknown) is resolved later, against a
    # fresh snapshot, by LiveActionService.propose_send_action -- this only
    # extracts what the user asked for.
    mute_send_match = _MUTE_SEND.search(lower)
    send_match = (mute_send_match or _SET_SEND.search(lower) or _SEND_TRACK_FIRST.search(lower)
                  or _SET_TRACK_SEND.search(lower) or _track_to_return_send(lower, session_snapshot))
    if send_match:
        track_number_text = send_match.group("track_number")
        if track_number_text:
            send_track, send_track_error = _find_numbered_track(int(track_number_text), tracks)
        else:
            requested_track_name = str(send_match.group("track_name") or "").strip()
            send_track, _candidates, send_track_error = _find_track(requested_track_name, tracks)
        if send_track_error or send_track is None:
            base["missing_fields"].append("track")
            base["ambiguity"].append(send_track_error or "The requested track is not present in the current Live snapshot.")
            return base
        if mute_send_match:
            send_value = 0.0
        else:
            try:
                send_value = float(send_match.group("value"))
                if send_match.group("percent"):
                    send_value /= 100.0
            except (TypeError, ValueError):
                send_value = None
        if send_value is None or not (0.0 <= send_value <= 1.0):
            base["missing_fields"].append("desired_value")
            base["ambiguity"].append("Send level must be 0–100% or a normalized value between 0.0 and 1.0, e.g. 'set the reverb send on track 4 to 25%'.")
            return base
        base.update({
            "mode": "assist",
            "action": "set_send",
            "track": {"index": send_track.get("index"), "name": str(send_track.get("name", ""))},
            "return_track_name": send_match.group("return_name").strip(),
            "desired_value": send_value,
            "unit": "normalized",
            "confirmation_required": True,
            "confidence": 0.9,
        })
        return base
    if "send" in lower and (
        re.search(r"\b(?:mute|turn\s+off|zero)\b", lower)
        or _UNSUPPORTED_SEND_CONTROL.search(lower)
    ):
        base["missing_fields"].append("send_value")
        base["ambiguity"].append(
            "Specify the return, source track, and an absolute send value, e.g. "
            "'set the reverb send on Vocal to 20%'."
        )
        return base
    if _UNSUPPORTED_RETURN_CONTROL.search(lower):
        base["missing_fields"].append("return_track_action")
        base["ambiguity"].append(
            "Return-track mute, solo, arm, and enable controls are not in the qualified action set; "
            "no regular-track action was inferred."
        )
        return base
    if _UNSUPPORTED_CLIP_CONTROL.search(lower):
        base["missing_fields"].append("clip_action")
        base["ambiguity"].append(
            "Clip mute, solo, arm, and enable controls are not in the qualified action set; "
            "no track-level action was inferred."
        )
        return base
    if _UNSUPPORTED_SCENE_CONTROL.search(lower):
        base["missing_fields"].append("scene_action")
        base["ambiguity"].append(
            "Scene mute, solo, arm, and enable controls are not in the qualified action set; "
            "no track-level action was inferred."
        )
        return base
    if _UNSUPPORTED_MASTER_CONTROL.search(lower):
        base["missing_fields"].append("master_track_action")
        base["ambiguity"].append(
            "Master-track mute, solo, arm, and enable controls are not in the qualified action set; "
            "no regular-track action was inferred."
        )
        return base
    mentioned_devices = [
        str(device.get("name") or "").strip()
        for track in tracks
        for device in (track.get("devices") if isinstance(track.get("devices"), list) else [])
        if isinstance(device, dict) and str(device.get("name") or "").strip()
    ]
    # Words inside a track's own name aren't a device reference: "mute the FX Print" is the track called FX Print,
    # and it used to be refused as "device mute" because of the "fx".
    without_track_names = lower
    for track in tracks:
        name = str(track.get("name") or "").strip().lower()
        if name:
            without_track_names = re.sub(rf"(?<!\w){re.escape(name)}(?!\w)", " ", without_track_names)
    # "turn auto release on" is a qualified chooser, not the device's own on/off switch the guard below is for.
    choice_asked = any(_choice_request(lower, name) for name in set(mentioned_devices))
    if _UNSUPPORTED_DEVICE_CONTROL.search(lower) and not choice_asked and (
        _DEVICE_CONTROL_REFERENCE.search(without_track_names)
        or any(
            re.search(rf"(?<!\w){re.escape(name)}(?!\w)", text, re.I)
            for name in mentioned_devices
        )
    ):
        base["missing_fields"].append("device_action")
        base["ambiguity"].append(
            "KENN can't switch devices on or off yet. The device's on/off switch in Live does it (top left of the "
            "device). Nothing changed.")
        return base
    transport_word = re.search(r"^\s*(?:play|stop|start|pause)\s+(?:the\s+)?(?P<what>.+?)\s*[.!?]?\s*$", lower)
    if transport_word and not re.search(r"\b(?:song|set|session|track|playback|playing|beat|it|music|everything)\b",
                                        transport_word.group("what")) and _extract_track_phrase(transport_word.group("what"), tracks):
        # "play the drums", "stop the bass": Live's transport plays and stops the whole set, never one track. Starting
        # or stopping everything isn't what was asked, so ask which is meant.
        what = transport_word.group("what")
        base["missing_fields"].append("transport_target")
        base["ambiguity"].append(f"Play and stop run the whole set, not one track. Did you mean to solo or mute {what}, "
                                 "or start/stop the whole set? Nothing changed.")
        return base
    # "Play" is Live's transport unless someone is playing notes: "every note I play", "play a sample across the
    # keyboard" were Play proposals (26 Sept 2026), and so was "the hats play 1/16 notes" (27 Sept).
    if re.search(r"(?<!\bi\s)(?<!\bwe\s)(?<!\byou\s)(?<!\bthey\s)\bplay\b(?!\s+(?:a|an|some|each|every|any|one|two|notes?|"
                 r"chords?|samples?|sounds?|keys?|melod(?:y|ies)|parts?|live|along|over|through|across|around|with|"
                 r"\d+\s*/\s*\d+|whole|half|quarter|eighth|sixteenth|8ths?|16ths?|32nds?|triplets?|off-?beats?|straight)\b)"
                 r"|\b(?:start playback|start\s+(?:the\s+)?(?:song|set|playback|playing)|hit\s+play)\b"
                 r"|^\s*(?:let'?s\s+(?:hear\s+it|jam)|can\s+we\s+start|let'?s\s+go)\s*[.!?]?\s*$", lower):
        scene_named = next((sc for sc in ((snapshot or {}).get("scenes") or []) if isinstance(sc, dict)
                            and str(sc.get("name", "")).strip()
                            and re.search(rf"\bplay\s+(?:the\s+)?{re.escape(str(sc['name']).strip().casefold())}\s*[.!?]?\s*$", lower)),
                           None)
        if scene_named is not None:
            # "play the chorus" in a set with a Chorus scene: launch it, or press Play? Ask rather than guess.
            name = str(scene_named["name"]).strip()
            base["missing_fields"].append("transport_target")
            base["ambiguity"].append(f"Launch the '{name}' scene, or start playback from the playhead? Say \"launch the "
                                     f"{name} scene\" or \"press play\". Nothing changed.")
            return base
        base.update({"mode": "assist", "action": "transport_play", "confirmation_required": True, "confidence": 0.99})
        return base
    if re.search(r"\b(stop playback|stop the session|stop)\b|^\s*pause(?:\s+(?:it|playback|the\s+song))?\s*[.!]?\s*$", lower):
        base.update({"mode": "assist", "action": "transport_stop", "confirmation_required": True, "confidence": 0.99})
        return base


__all__ = ["resolve_session_rules"]
