"""The per-track scalar ladder: mute, solo, arm, fader level, and pan.

This is ``live_command.TRACK_ACTIONS`` without ``rename_track``: the changes that
read and write the track itself rather than a device sitting on it. It sits after
every device and EQ rule and ahead of the device-parameter rules, because "set the
hats to -3 dB" is the fader and "set the EQ Eight gain on the hats to -3 dB" is a
parameter, and the only thing separating them is which rule is reached first.

Lifted verbatim out of ``live_intent._parse_request_rules``.
"""

from __future__ import annotations

import re
from typing import Any

from kenn.core import volume_law
from kenn.core.live_intent import (
    _COMMA_SECOND_ACTION,
    _NUMBER,
    _RELATIVE_VOLUME_EXCLUDE,
    _SECOND_ACTION,
    _missing_value_question,
    _relative_volume_db,
    _volume_range_message,
)


def resolve_track_values(base: dict[str, Any], track: dict[str, Any], lower: str) -> dict[str, Any] | None:
    """The track-level result, or None when the request names no scalar change."""
    action = None
    mute_off = re.search(
        r"\b(?:un-?mute|un[- ]?silence)\b|\b(?:turn|switch|take)\s+off\s+(?:the\s+)?mute\b|"
        r"\b(?:take|turn|switch)\b.*?\b(?:out\s+of|off)\s+(?:mute|silence)\b|"
        r"\b(?:turn|switch)\s+(?:mute|silence)\s+off\b|"
        # "take the mute off the kick": the noun-first order means off, not on.
        r"\b(?:take|turn|switch|pull|get)\s+(?:the\s+)?(?:mute|silence)\s+off\b|"
        # A mix note writes the bare negation with no verb -- "Lead Vocal off mute", "Kick mute off" -- and the
        # patterns above all require one. Round 9 (2026-09-30) caught "Lead Vocal off solo" being read as solo on:
        # a silent wrong write that still passes readback and is journalled as verified.
        r"\b(?:off|no)\s+(?:the\s+)?(?:mute|silence)\b|\b(?:mute|silence)\s+off\b",
        lower,
    )
    # "kill the FX print", "nuke the hats", "take the kick out of the mix"; not "kill playback".
    mute_slang = (re.search(r"\b(?:kill|nuke)\b|\bout\s+of\s+the\s+mix\b", lower)
                  and not re.search(r"\b(?:playback|song|transport|everything|all)\b", lower))
    if mute_off or re.search(r"\b(?:mute|silence)\b", lower) or mute_slang:
        action = "set_mute"
        base.update({"desired_value": not bool(mute_off), "unit": "boolean"})
    else:
        solo_off = re.search(
            r"\b(?:un-?solo|un[- ]?isolate)\b|\b(?:turn|switch|take)\s+off\s+(?:the\s+)?solo\b|"
            r"\b(?:take|turn|switch)\b.*?\b(?:out\s+of|off)\s+(?:solo|isolation)\b|"
            r"\b(?:turn|switch)\s+solo\s+off\b|"
            r"\b(?:take|turn|switch|pull|get)\s+(?:the\s+)?solo\s+off\b|"
            # Same bare-negation gap as mute: every pattern above wants a verb, so "Lead Vocal off solo" fell
            # through to the positive branch and soloed the track. Reads back fine, so nothing downstream caught it.
            r"\b(?:off|no)\s+(?:the\s+)?(?:solo|isolation)\b|\b(?:solo|isolation)\s+off\b",
            lower,
        )
        # "the vocal on its own", "just the vocal please", "gimme only the bass".
        solo_slang = re.search(r"\bon\s+(?:its|their)\s+own\b|\bhear\b.*\b(?:alone|by\s+itself)\s*[.!]?\s*$|^\s*(?:(?:gimme|give\s+me|let\s+me\s+hear)\s+)?(?:just|only)\s+the\b", lower)
        if solo_off or re.search(r"\b(?:solo|isolate|slo)\b", lower) or solo_slang:
            action = "set_solo"
            base.update({"desired_value": not bool(solo_off), "unit": "boolean"})
        else:
            arm_off = re.search(
                r"\b(?:dis-?arm|un-?arm)\b|\b(?:turn|switch|take)\s+off\s+(?:the\s+)?(?:record[- ]?)?arm\b|"
                r"\b(?:take|turn|switch)\b.*?\b(?:out\s+of|off)\s+(?:arm|record[- ]?enable|record[- ]?ready|record(?:ing)?)\b|"
                r"\b(?:turn|switch)\s+(?:record[- ]?arm|arm)\s+off\b",
                lower,
            )
            arm_on = re.search(r"\b(?:arm|record[- ]?enable|record[- ]?ready)\b", lower)
            if arm_off or arm_on:
                action = "set_arm"
                base.update({"desired_value": not bool(arm_off), "unit": "boolean"})
    if action is None:
        volume_match = re.search(r"(?:volume|level)\s+(?:(?:to|at)\s+)?" + _NUMBER + r"\s*(db)?", lower)
        if volume_match is None:
            # Accept the common command ordering "set the volume on track 4
            # to -6 dB" and "set track 4 volume at -6 dB" while still
            # requiring an explicit absolute value.
            volume_match = re.search(r"(?:volume|level).*?\b(?:to|at)\s+" + _NUMBER + r"\s*(db)?", lower)
        if volume_match is None:
            # "Bring Bass Synth to -9 dB" is a common absolute level request
            # even when the word volume is omitted. Keep this narrow: a dB
            # target is required, and arbitrary parameter changes still use
            # the device-specific path below.
            volume_match = re.search(r"\bbring\b.*?\b(?:to|at)\s+" + _NUMBER + r"\s*db\b", lower)
        if volume_match is None and not _RELATIVE_VOLUME_EXCLUDE.search(lower):
            # "Put the kick at minus 12 dB", "set the snare to -10 dB": the same
            # narrow shape (explicit dB target) with no device, send or pan words.
            volume_match = re.search(r"\b(?:put|set|sit|pull|push|drop|turn|tuck|lower|raise|take|move|nudge|get)\b.*?\b(?:to|at)\s+" + _NUMBER + r"\s*db\b", lower)
            if volume_match is None:
                volume_match = re.search(r"^\s*[a-z][\w\s/'-]*?\s+at\s+" + _NUMBER + r"\s*db\s*[.!?]?\s*$", lower)
        pan_match = re.search(
            r"pan\b.*?\b(?:track|trk|channel|chan|ch)\s*#?\s*\d+\s+"
            + _NUMBER
            + r"\s*(%|percent)?\s*(left|right)?",
            lower,
        ) or re.search(r"pan\b.*?" + _NUMBER + r"\s*(%|percent)?\s*(left|right)?", lower)
        pan_side_first_match = re.search(
            r"\b(?:move|put|place)\b.*?\b(left|right)\b\s*(?:by\s*)?" + _NUMBER + r"\s*(%|percent)?",
            lower,
        )
        pan_amount_first_match = re.search(
            r"\b(?:move|put|place)\b.*?" + _NUMBER + r"\s*(%|percent)?\s*(left|right)\b",
            lower,
        )
        pan_hard_match = re.search(
            r"\bpan\b.*?\b(?:hard|fully|all\s+the\s+way)\s+(left|right)\b",
            lower,
        )
        pan_free = not re.search(r"\b(?:db|hz|khz|send|sends|eq|band|reverb|delay|echo|compressor|threshold|volume|level)\b", lower)
        if pan_hard_match is None and pan_free:
            # "synth hard right", "stick the Drum Bus hard left".
            pan_hard_match = re.search(r"\b(?:hard|fully|all\s+the\s+way)\s+(left|right)\s*[.!]?\s*$", lower)
        if pan_free and not (pan_match or pan_side_first_match or pan_amount_first_match):
            # "hats left 20", "roll track 2 20 percent to the left": a bare number is a percentage.
            pan_side_first_match = re.search(r"\b(left|right)\s+" + _NUMBER + r"\s*(%|percent)?\s*[.!]?\s*$", lower)
            if pan_side_first_match is None:
                # "hats 20 left", "snare 0.5 left": typed quickly with no verb at all.
                pan_amount_first_match = re.search(r"^\s*[a-z][\w /'&-]*?\s+" + _NUMBER + r"\s*(%|percent)?\s*(left|right)\s*[.!]?\s*$",
                                                   lower)
            if pan_side_first_match is None and pan_amount_first_match is None:
                pan_amount_first_match = re.search(
                    r"\b(?:roll|shift|nudge|stick|move|put|place|throw|park|sit)\b.*?" + _NUMBER
                    + r"\s*(%|percent)\s*(?:to\s+the\s+)?(left|right)\b", lower)
        # "Pan the Synth center" / "Centre the Synth": the one pan target with
        # no number or side. Frequency wording is excluded so "centre
        # frequency" never becomes a pan request.
        pan_center_match = (
            re.search(r"\bpan\b.*?\b(?:to\s+(?:the\s+)?)?(?:cent(?:er|re)(?:d)?|middle)\b", lower)
            or re.match(r"\s*(?:please\s+)?(?:re)?cent(?:er|re)\s+(?:the\s+)?\S", lower)
        ) if not re.search(r"\b(?:freq(?:uency)?|hz|khz|eq|band)\b", lower) else None
        relative_db = None if (volume_match or pan_match or pan_side_first_match or pan_amount_first_match
                                   or pan_hard_match or pan_center_match) else _relative_volume_db(lower)
        if volume_match:
            # Live's fader law (volume_law), not 10^(dB/20): raw 0.85 is 0 dB.
            db = float(volume_match.group(1))
            target = volume_law.db_to_raw(db) if db <= 0.0 else None
            if target is None:
                base.update(action="set_volume")
                base["missing_fields"].append("valid_volume")
                base["ambiguity"].append(_volume_range_message(db))
                return base
            base.update({"desired_value": target, "unit": "normalized", "requested_unit": "dB", "absolute_value": db})
            action = "set_volume"
        elif relative_db is not None:
            # The track's current level in dB (Live's fader law) plus the
            # change; the proposal's stale-state check still guards against
            # Live changing before Apply.
            current = track.get("volume")
            if isinstance(current, bool) or not isinstance(current, (int, float)) or not current > 0:
                base["missing_fields"].append("current_volume")
                base["ambiguity"].append("The current track volume is not in the Live snapshot, so a relative dB change cannot be computed.")
                return base
            current_db = volume_law.raw_to_db(float(current))
            target_db = None if current_db is None else current_db + relative_db
            target = volume_law.db_to_raw(target_db) if target_db is not None and target_db <= 0.0 else None
            if target is None:
                base.update(action="set_volume")
                base["missing_fields"].append("valid_volume")
                if current_db is not None and target_db is not None and target_db > 0.0:
                    # Say where the track is and how much room is left, not just "no".
                    room = max(0.0, -current_db)
                    base["ambiguity"].append(
                        f"'{track.get('name')}' is at {current_db:.1f} dB, so up {relative_db:g} dB would take it above "
                        f"0 dB, which KENN doesn't set." + (f" Up to {room:.1f} dB is fine." if room >= 0.1 else ""))
                else:
                    base["ambiguity"].append(_volume_range_message(target_db))
                return base
            base.update({"desired_value": target, "unit": "normalized", "requested_unit": "dB",
                         "requested_relative_db": relative_db})
            action = "set_volume"
        elif pan_center_match and not (pan_hard_match or pan_match or pan_side_first_match or pan_amount_first_match):
            base.update({"desired_value": 0.0, "unit": "normalized", "requested_unit": "normalized"})
            action = "set_pan"
        elif pan_hard_match or pan_match or pan_side_first_match or pan_amount_first_match:
            if pan_hard_match:
                side = pan_hard_match.group(1)
                amount = -1.0 if side == "left" else 1.0
                unit = None
            elif pan_match:
                amount = float(pan_match.group(1))
                unit = pan_match.group(2)
                side = pan_match.group(3)
            elif pan_side_first_match:
                side = pan_side_first_match.group(1)
                amount = float(pan_side_first_match.group(2))
                unit = pan_side_first_match.group(3)
            else:
                amount = float(pan_amount_first_match.group(1))
                unit = pan_amount_first_match.group(2)
                side = pan_amount_first_match.group(3)
            if not side:
                # "pan the synth left 30%" matched the amount with no side and used to pan right. Take the side from
                # anywhere in the request; both sides named is a question.
                sides = set(re.findall(r"\b(left|right)\b", lower))
                if len(sides) > 1:
                    base["ambiguity"].append("That names both left and right. Which side, and how far?")
                    base["missing_fields"].append("pan_side")
                    return base
                side = next(iter(sides), None)
                signed = amount < 0 or re.search(r"\+\s*\d", lower)  # "-0.4" is left and "+0.4" right, as in Live
                if side is None and not pan_hard_match and amount > 0 and not signed:
                    # "pan the synth 20%" names no side; it used to go right. Ask rather than guess.
                    base["ambiguity"].append(f"Which side? For example \"pan {track.get('name') or 'it'} {abs(amount):g}"
                                             f"{'%' if unit else ''} left\".")
                    base["missing_fields"].append("pan_side")
                    return base
            if side == "left":
                amount = -abs(amount)
            elif side == "right":
                amount = abs(amount)
            if unit is None and side and abs(amount) > 1.0:
                unit = "%"  # "hats left 20" and "pan the hats 20 left" mean 20%; the pan_side hint below says "20 left"
            normalized = amount / 100.0 if unit else amount
            if not -1.0 <= normalized <= 1.0:
                base["ambiguity"].append("Pan value is outside the supported -1.0 to 1.0 range; no clamping was applied.")
                base["missing_fields"].append("valid_pan_value")
                return base
            base.update({"desired_value": normalized, "unit": "normalized", "requested_unit": "%" if unit else "normalized"})
            action = "set_pan"

    if action is None and track:
        # A recognisable request missing one value: ask exactly for it instead of the generic reply.
        name = str(track.get("name") or "the track")
        question = _missing_value_question(lower, name)
        if question:
            base.update(action=question[0])
            base["missing_fields"].append(question[1])
            base["ambiguity"].append(question[2])
            return base
    if action and (_SECOND_ACTION.search(lower) or _COMMA_SECOND_ACTION.search(lower)):
        # "solo the bass and turn it up 2 dB": proposing only the first part
        # would silently drop the rest. Supported two-step requests are
        # handled by parse_natural_recipe before this parser runs.
        base["missing_fields"].append("single_action")
        base["ambiguity"].append("This asks for more than one change. Say them one at a time, or join them with \"then\".")
        return base
    if action:
        base.update({"mode": "assist", "action": action, "confirmation_required": True, "confidence": 0.95})
        return base


__all__ = ["resolve_track_values"]
