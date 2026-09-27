"""Deterministic natural-language intent and slot extraction for Ableton Live.

The output is deliberately a plan-shaped dictionary.  It never performs a
write, and it refuses to choose an index when a target is missing or when
names are duplicated.  Device and parameter names come from the supplied Live
snapshot; the parser does not invent them from model knowledge.
"""

from __future__ import annotations

import re
from typing import Any

from kenn.core import volume_law
from kenn.core.device_units import display_to_raw, find_profile, normalize_unit


_NUMBER = r"(-?(?:\d+(?:\.\d+)?|\.\d+))"
_DESTRUCTIVE = re.compile(r"\b(delete|remove|overwrite|replace|destroy|erase)\b", re.I)
_UNBOUNDED_EXECUTION = re.compile(
    r"(?:\b(?:run|execute)\b.{0,80}\b(?:python|javascript|shell|script|code|osc\s+messages?)\b"
    r"|\b(?:python|javascript|shell|script|code|osc\s+messages?)\b.{0,80}\b(?:run|execute)\b)",
    re.I,
)
_SAFETY_BYPASS = re.compile(
    r"(?:\b(?:ignore|bypass|circumvent|disable|skip)\b.{0,80}"
    r"\b(?:confirmation|guardrails?|policy|system\s+instructions?|developer\s+instructions?)\b"
    r"|\b(?:confirmation|guardrails?|policy|system\s+instructions?|developer\s+instructions?)\b.{0,80}"
    r"\b(?:ignore|bypass|circumvent|disable|skip)\b)",
    re.I,
)
# A number with a unit after it is a value, not a track: "move the synth track 5 dB louder" turned up track 5 (Bass).
_NUMERIC_TRACK = re.compile(r"\b(?:track|trk|channel|chan|ch)\s*#?\s*(\d+)\b"
                            r"(?!\.\d|\s*(?:dbs?|decibels?|%|percent|hz|khz|ms|:1)\b|\s*%)", re.I)
_NUMBERED_SCENE = re.compile(r"\b(?:play|launch|fire|trigger)\b.*?\bscene\s*#?\s*(\d+)\b", re.I)
_LOCATOR_REQUEST = re.compile(
    r"\b(?:add|create|set|drop|place|put|remove|delete)\b.{0,80}\b(?:locator|cue\s+point|marker)\b"
    r"|\b(?:locator|cue\s+point|marker)\b.{0,80}\b(?:add|create|set|remove|delete)\b",
    re.I,
)
_ADD_LOCATOR = re.compile(
    r"^\s*(?:add|create|set|drop|place|put)\s+(?:a\s+)?(?:locator|cue\s+point|marker)\b"
    r"(?:\s+(?:called|named|label(?:ed|led)?|with\s+name)\s+['\"]?(?P<name>[^'\"]+?)['\"]?)?"
    r"(?:\s+(?:(?:at|on)\s+(?:the\s+)?(?:current\s+position|cursor|playhead|song\s+position)|(?:right\s+)?here|now))?"
    r"\s*[.!]?\s*$",
    re.I,
)
_REMOVE_LOCATOR = re.compile(
    r"^\s*(?:remove|delete)\s+(?:the\s+)?(?:locator|cue\s+point|marker)\b"
    r"(?:\s+(?:called|named|label(?:ed|led)?|with\s+name)\s+['\"]?(?P<name>[^'\"]+?)['\"]?)?"
    r"(?:\s+(?:(?:at|on)\s+(?:the\s+)?(?:current\s+position|cursor|playhead|song\s+position)|(?:right\s+)?here|now))?"
    r"\s*[.!]?\s*$",
    re.I,
)
_CREATE_MIDI_TRACK = re.compile(
    r"^\s*(?:(?:create|add|make|spin\s+up|set\s+up|give\s+me|(?:i\s+)?need|i'?d\s+like)\s+(?:an?\s+|another\s+)?(?:new\s+|fresh\s+|empty\s+|blank\s+)?|new\s+)midi\s+track\b"
    r"(?:\s+(?:called|named|with\s+name)\s+['\"]?(?P<name>[^'\"]+?)['\"]?|\s+for\s+(?:the\s+)?[\w'-]+(?:\s+[\w'-]+)?)?\s*[.!]?\s*$",
    re.I,
)
_CREATE_AUDIO_TRACK = re.compile(
    r"^\s*(?:(?:create|add|make|spin\s+up|set\s+up|give\s+me|(?:i\s+)?need|i'?d\s+like)\s+(?:an?\s+|another\s+)?(?:new\s+|fresh\s+|empty\s+|blank\s+)?|new\s+)audio\s+track\b"
    r"(?:\s+(?:called|named|with\s+name)\s+['\"]?(?P<name>[^'\"]+?)['\"]?|\s+for\s+(?:the\s+)?[\w'-]+(?:\s+[\w'-]+)?)?\s*[.!]?\s*$",
    re.I,
)
_CREATE_RETURN_TRACK = re.compile(
    r"^\s*(?:(?:create|add|make|spin\s+up|set\s+up|give\s+me|(?:i\s+)?need|i'?d\s+like)\s+(?:an?\s+|another\s+)?(?:new\s+|fresh\s+|empty\s+|blank\s+)?|new\s+)return(?:\s+(?:track|channel))?\b"
    r"(?:\s+(?:called|named|with\s+name)\s+['\"]?(?P<name>[^'\"]+?)['\"]?)?\s*[.!]?\s*$",
    re.I,
)
_GAIN_STAGE = re.compile(
    r"^\s*(?:auto\s+)?gain\s*stage(?:\s+(?:all|session)\s+tracks?)?"
    r"(?:\s+(?:to|at)\s+(?P<db>-?\d+(?:\.\d+)?)\s*(?:db|dbfs)?)?\s*$"
    r"|^\s*(?:level|balance)\s+all\s+tracks(?:\s+(?:for\s+mixing|to\s+(?P<level_db>-?\d+(?:\.\d+)?)\s*(?:db|dbfs)?))?\s*$",
    re.I,
)
_GROUP_TRACKS = re.compile(
    r"^\s*(?:auto\s+)?(?:group|organize|bus)\s+(?:all\s+)?tracks?(?:\s+(?:by\s+instrument|into\s+buses|for\s+mixing))?\s*$"
    r"|^\s*(?:create|add|make)\s+(?:a\s+)?(?P<group_type>drums?|vocals?|vox|bass|synths?|guitars?|fx)\s+(?:bus|group)\b"
    r"(?:\s+(?:for\s+tracks?\s+(?P<track_refs>[\d,\s\sand]+))?)?\s*$",
    re.I,
)
_FOCUS_TRACK = re.compile(
    r"(?:\b(?:select|focus|follow|go\s+to|jump\s+to|take\s+me\s+to)\b.*?|\b(?:show|open)\b(?:\s+me)?\s+(?:the\s+)?)(?:track|trk|channel|chan|ch)\s*#?\s*(\d+)\b",
    re.I,
)
_FOCUS_TRACK_NAME = re.compile(
    r"^\s*(?:select|focus|follow)\s+(?:the\s+)?(?P<name>.+?)\s+"
    r"(?:track|trk|channel|chan|ch)\s*$"
    r"|^\s*(?:show|open)\s+(?:me\s+)?(?:the\s+)?(?:track|trk|channel|chan|ch)\s+"
    r"(?P<show_name>.+?)\s*$",
    re.I,
)
_FOCUS_TRACK_BARE_NAME = re.compile(
    r"^\s*(?:select|focus(?:\s+on)?|follow|highlight|go\s+to|jump\s+to|move\s+to|take\s+me\s+to|show\s+me)\s+(?:the\s+)?(?P<name>[^.!?]+?)\s*[.!]?\s*$", re.I)
_ORDINAL_TRACK = re.compile(
    r"\b(?P<ordinal>first|second|third|fourth|fifth|sixth|seventh|eighth|ninth|tenth|last)\s+"
    r"(?:visible\s+)?(?:track|trk|channel|chan|ch)\b",
    re.I,
)
_ORDINAL_TRACK_VALUES = {
    "first": 1, "second": 2, "third": 3, "fourth": 4, "fifth": 5,
    "sixth": 6, "seventh": 7, "eighth": 8, "ninth": 9, "tenth": 10,
}
_SPOKEN_TRACK_NUMBER = re.compile(
    r"\b(?:track|trk|channel|chan|ch)\s+(?P<number>zero|one|two|three|four|five|six|seven|eight|nine|ten)\b",
    re.I,
)
_FOCUS_DEVICE = re.compile(
    r"^\s*\b(?:select|focus|follow)\b\s+(?:the\s+)?(?:device\s+|plugin\s+)?(?P<device>.+?)\s+"
    r"\b(?:on|in)\b\s+(?:the\s+)?(?:track|trk|channel|chan|ch)\s*#?\s*(?P<track_number>\d+)\s*[.!]?\s*$",
    re.I,
)
_STOP_CLIP_MENTION = re.compile(r"\bstop\b.*?\bclip\b", re.I)
_STOP_CLIP_SLOT_THEN_TRACK = re.compile(
    r"\bstop\b.*?\bclip\b.*?\bslot\s*#?\s*(\d+).*?\b(?:track|trk|channel|chan|ch)\s*#?\s*(\d+)\b", re.I
)
_STOP_CLIP_TRACK_THEN_SLOT = re.compile(
    r"\bstop\b.*?\bclip\b.*?\b(?:track|trk|channel|chan|ch)\s*#?\s*(\d+)\b.*?\bslot\s*#?\s*(\d+)", re.I
)
_DUPLICATE_CLIP = re.compile(
    r"^\s*(?:duplicate|copy)\s+(?:the\s+)?clip\s+(?:on|from)\s+"
    r"(?P<source>.+?)\s+(?:clip\s+)?slot\s*#?\s*(?P<source_slot>\d+)\s+"
    r"(?:to|into)\s+(?P<target>.+?)\s+(?:clip\s+)?slot\s*#?\s*(?P<target_slot>\d+)\s*[.!?]?\s*$",
    re.I,
)
_RENAME_CLIP = re.compile(
    r"^\s*(?:rename|name)\s+(?:the\s+)?clip\s+(?:on|from)\s+"
    r"(?P<track>.+?)\s+(?:clip\s+)?slot\s*#?\s*(?P<slot>\d+)\s+"
    r"(?:to|as|called|named)\s+['\"]?(?P<name>[^'\"]+?)['\"]?\s*[.!?]?\s*$",
    re.I,
)
# One deliberately narrow, explicit phrasing for send control: "set [the]
# <return name> send on track N to <value-or-percent>". The return track's exact
# identity (name -> index, ambiguity/unknown handling) is resolved later by
# LiveActionService.propose_send_action against a fresh snapshot, not here
# -- this layer only extracts what the user asked for, matching the same
# division of labor already used for track/device names elsewhere in this
# file. Broader phrasing (relative "turn down", omitted "the", etc.) is
# deliberately not attempted yet. Percentages are converted to the normalized
# 0.0-1.0 value used by Live; no relative delta is inferred.
_SET_SEND = re.compile(
    r"\bset\s+(?:the\s+)?(?P<return_name>[\w' -]+?)\s+send\b.*?\bon\s+"
    r"(?:(?:track|trk|channel|chan|ch)\s*#?\s*(?P<track_number>\d+)\b|(?:the\s+)?(?P<track_name>[\w' -]+?))"
    r"\s+\bto\s+(?P<value>-?(?:\d+(?:\.\d+)?|\.\d+))\s*(?P<percent>%|percent\b)?",
    re.I,
)
# Track-first orders: "send the lead vocal to A-Reverb at 25%", "set the synth
# send to B-Delay at 10%". Same named groups as _SET_SEND (track_number never
# participates here).
_SEND_TAIL = (r"to\s+(?:the\s+)?(?P<return_name>[\w' -]+?)\s+(?:at|to)\s+(?P<value>-?(?:\d+(?:\.\d+)?|\.\d+))"
              r"\s*(?P<percent>%|percent\b)?(?P<track_number>(?!))?")
# "send the lead vocal to A-Reverb at 25%" (the verb is "send")
_SEND_TRACK_FIRST = re.compile(r"\bsend\s+(?:the\s+)?(?P<track_name>[\w' /-]+?)\s+" + _SEND_TAIL, re.I)
# "set the synth send to B-Delay at 10%" ("set" needs the word "send", so EQ and
# device "set ... to ... at ..." commands never match)
_SET_TRACK_SEND = re.compile(r"\bset\s+(?:the\s+)?(?P<track_name>[\w' /-]+?)(?:'s)?\s+send\s+" + _SEND_TAIL, re.I)
# "synth to the delay at 20 percent": no word "send", so only accepted when the
# destination names exactly one return track in the set (see _track_to_return_send).
_TRACK_TO_RETURN = re.compile(
    r"^\s*(?:(?:set|put|bring|route)\s+)?(?:the\s+)?(?P<track_name>[\w' /-]+?)\s+" + _SEND_TAIL + r"\s*[.!]?\s*$", re.I)


def _track_to_return_send(lower: str, snapshot: Any) -> re.Match | None:
    match = _TRACK_TO_RETURN.search(lower)
    if not match:
        return None
    wanted = set(re.findall(r"[a-z0-9]+", match.group("return_name").casefold())) - {"the", "return", "track", "bus"}
    returns = [r for r in ((snapshot or {}).get("return_tracks") or []) if isinstance(r, dict)]
    hits = [r for r in returns if wanted and wanted <= set(re.findall(r"[a-z0-9]+", str(r.get("name", "")).casefold()))]
    return match if len(hits) == 1 else None


_MUTE_SEND = re.compile(
    r"\b(?:mute|turn\s+off|zero)\s+(?:the\s+)?(?P<return_name>[\w' -]+?)\s+send\b.*?\bon\s+"
    r"(?:(?:track|trk|channel|chan|ch)\s*#?\s*(?P<track_number>\d+)\b|(?:the\s+)?(?P<track_name>[\w' -]+?))\s*$",
    re.I,
)
_UNSUPPORTED_SEND_CONTROL = re.compile(
    r"\b(?:unmute|enable|disable|turn\s+on|solo|unsolo|arm|disarm|lower|reduce|decrease|raise|increase|boost)\b"
    r".{0,80}\bsend\b|\bsend\b.{0,80}"
    r"\b(?:unmute|enable|disable|turn\s+on|solo|unsolo|arm|disarm|lower|reduce|decrease|raise|increase|boost)\b",
    re.I,
)
_UNSUPPORTED_DEVICE_CONTROL = re.compile(
    r"\b(?:mute|unmute|enable|disable|bypass|solo|unsolo|arm|disarm|turn\s+(?:on|off))\b|\bturn\b.*\b(?:on|off)\s*[.!?]*\s*$",
    re.I,
)


def _display_unit_error(*, device_name: str, parameter_name: str, value: float, unit: str, relative: bool) -> str | None:
    """Return a fail-closed explanation for an unsupported display request."""
    normalized = normalize_unit(unit)
    if normalized not in {"ms", "ratio"}:
        return None
    if find_profile(device_name, parameter_name, normalized) is None:
        return (
            f"I can't set {device_name} {parameter_name} to {value:g}{' ms' if normalized == 'ms' else ':1'} yet: that "
            "control hasn't been measured in Live, so I can't be sure which setting gives that value. Nothing changed."
        )
    _, error = display_to_raw(
        device_name=device_name,
        parameter_name=parameter_name,
        value=value,
        unit=normalized,
        relative=relative,
    )
    return error


def _device_setup_parameter(match: re.Match[str], device_name: str | None) -> tuple[str, str]:
    parameter = str(match.group("parameter") or "").strip().casefold()
    if parameter == "threshold" or device_name == "Compressor":
        return "Threshold", "dB"
    return ("Dry/Wet" if device_name == "Hybrid Reverb" else "Dry Wet"), "%"


_DEVICE_CONTROL_REFERENCE = re.compile(
    r"\b(?:device|plugin|plug-in|effect|fx|eq(?:\s*8|\s+eight)?|compressor|reverb|echo|filter|saturator|drum\s+buss)\b",
    re.I,
)
_UNSUPPORTED_RETURN_CONTROL = re.compile(
    r"\b(?:mute|unmute|enable|disable|solo|unsolo|arm|disarm|turn\s+(?:on|off))\b"
    r".{0,80}\breturn(?:\s+track)?\b|\breturn(?:\s+track)?\b.{0,80}"
    r"\b(?:mute|unmute|enable|disable|solo|unsolo|arm|disarm|turn\s+(?:on|off))\b",
    re.I,
)
_UNSUPPORTED_CLIP_CONTROL = re.compile(
    r"\b(?:mute|unmute|enable|disable|solo|unsolo|arm|disarm|turn\s+(?:on|off))\b"
    r".{0,80}\bclip\b|\bclip\b.{0,80}"
    r"\b(?:mute|unmute|enable|disable|solo|unsolo|arm|disarm|turn\s+(?:on|off))\b",
    re.I,
)
_UNSUPPORTED_SCENE_CONTROL = re.compile(
    r"\b(?:mute|unmute|enable|disable|solo|unsolo|arm|disarm|turn\s+(?:on|off))\b"
    r".{0,80}\bscene\b|\bscene\b.{0,80}"
    r"\b(?:mute|unmute|enable|disable|solo|unsolo|arm|disarm|turn\s+(?:on|off))\b",
    re.I,
)
_UNSUPPORTED_MASTER_CONTROL = re.compile(
    r"\b(?:mute|unmute|enable|disable|solo|unsolo|arm|disarm|turn\s+(?:on|off))\b"
    r".{0,80}\bmaster(?:\s+track)?\b|\bmaster(?:\s+track)?\b.{0,80}"
    r"\b(?:mute|unmute|enable|disable|solo|unsolo|arm|disarm|turn\s+(?:on|off))\b",
    re.I,
)
_UNSAFE_MASTER_LEVEL = re.compile(
    r"\b(?:set|raise|increase|boost|max(?:imize)?|turn\s+up)\b.{0,80}"
    r"\b(?:master|main)(?:\s+track)?\b.{0,40}\b(?:volume|level|fader)\b"
    r"|\b(?:master|main)(?:\s+track)?\b.{0,40}\b(?:volume|level|fader)\b.{0,80}"
    r"\b(?:maximum|max|full|raise|increase|boost|turn\s+up)\b",
    re.I,
)
# Master level without the word volume ("master to max", "crank the master",
# "push the master fader all the way up"): master/main near a maximising word.
_UNSAFE_MASTER_MAX = re.compile(
    r"\b(?:master|main)(?:\s+(?:track|bus|fader|channel))?\b.{0,60}"
    r"\b(?:max(?:imum|imise|imize)?|full|all\s+the\s+way|as\s+loud|crank(?:ed)?)\b"
    r"|\b(?:max(?:imum|imise|imize)?|crank)\b.{0,60}\b(?:master|main)(?:\s+(?:track|bus|fader|channel))?\b",
    re.I,
)
# Safety words checked with a one-letter typo allowance ("delte", "mastr"), so
# a slip of the keyboard cannot turn a refusal into something else.
_SAFETY_WORDS = ("delete", "remove", "erase", "overwrite", "replace", "destroy", "master")


def _within_one_edit(word: str, target: str) -> bool:
    """A missing letter or two swapped neighbours: the common keyboard slips.

    Substitutions and extra letters are not allowed, so real words such as
    "remote" or "removed" never read as "remove".
    """
    if len(word) == len(target) - 1:
        return any(target[:i] + target[i + 1:] == word for i in range(len(target)))
    if len(word) == len(target) and word != target:
        return any(word == target[:i] + target[i + 1] + target[i] + target[i + 2:] for i in range(len(target) - 1))
    return False


def _safety_normalised(text: str) -> str:
    """The text with near-miss safety words (4+ letters, one edit) spelt correctly."""
    def fix(match: re.Match) -> str:
        word = match.group(0)
        lower = word.casefold()
        if len(lower) < 4 or lower in _SAFETY_WORDS:
            return word
        return next((target for target in _SAFETY_WORDS if _within_one_edit(lower, target)), word)
    return re.sub(r"[A-Za-z]+", fix, text)


# The full stop that ends a typed sentence isn't part of the name ("rename the kick to Big Kick." gave "Big Kick.").
_RENAME_TRACK = re.compile(
    r"\b(?:rename|name)\b.*?\b(?:to|as)\s+['\"]?([^'\"]+?)['\"]?\s*[.!]?\s*$",
    re.I,
)
_INSERT_DEVICE_ALIASES = (
    ("Glue Compressor", r"glue\s+compressor"),
    ("Multiband Dynamics", r"multi-?band(?:\s+(?:dynamics|compressor))?"),
    ("Roar", r"roar"),
    ("Auto Filter", r"auto\s+filter|filter"),
    ("Drum Buss", r"drum\s+buss"),
    ("Saturator", r"saturator"),
    ("EQ Eight", r"eq(?:ualizer)?(?:\s+eight)?|eq\s*8"),
    ("Hybrid Reverb", r"hybrid\s+reverb|reverb"),
    ("Echo", r"echo|delay"),
    ("Compressor", r"compressor"),
)
# NOTE: order matters here -- "glue compressor" must be checked before the
# bare "compressor" alternative so a request naming the specific device isn't
# shadowed by the generic one; _insert_device_name below relies on
# _INSERT_DEVICE_ALIASES iteration order for the same reason.
_ADD_DEVICE = re.compile(
    r"\b(?:stick|drop|throw|slap|pop|chuck)\s+(?:a|an|another)\s+(?:new\s+)?(?:glue\s+compressor|multi-?band(?:\s+(?:dynamics|compressor))?|roar|auto\s+filter|filter|drum\s+buss|saturator|eq(?:ualizer)?(?:\s+eight)?|eq\s*8|hybrid\s+reverb|reverb|echo|delay|compressor)\b"
    r"|\b(?:add|append|insert|put|load)\b.*\b(?:glue\s+compressor|multi-?band(?:\s+(?:dynamics|compressor))?|roar|auto\s+filter|filter|drum\s+buss|saturator|eq(?:ualizer)?(?:\s+eight)?|eq\s*8|hybrid\s+reverb|reverb|echo|delay|compressor)\b"
    r"|\b(?:glue\s+compressor|multi-?band(?:\s+(?:dynamics|compressor))?|roar|auto\s+filter|drum\s+buss|saturator|eq(?:ualizer)?(?:\s+eight)?|eq\s*8|hybrid\s+reverb|reverb|echo|delay|compressor)\b.*\b(?:add|append|insert|put|load)\b",
    re.I,
)
_DEVICE_SETUP = re.compile(
    r"\b(?:add|append|insert|put|load)\s+(?:an?\s+)?"
    r"(?P<device>hybrid\s+reverb|reverb|echo|delay|compressor)\s+"
    r"(?:to|on)\s+(?P<track>.+?)\s+"
    r"(?:at|with|set\s+(?:the\s+)?)\s*"
    r"(?P<value>-?(?:\d+(?:\.\d+)?|\.\d+))\s*(?P<unit>%|percent|db|decibels?)\s+"
    r"(?P<parameter>dry\s*[/ ]?\s*wet|threshold)\b",
    re.I,
)
_DEVICE_SETUP_TRAILING = re.compile(
    r"\b(?:add|append|insert|put|load)\s+(?:an?\s+)?"
    r"(?P<device>hybrid\s+reverb|reverb|echo|delay|compressor)\s+"
    r"(?:to|on)\s+(?P<track>.+?)\s+and\s+set\s+(?:the\s+)?"
    r"(?P<parameter>dry\s*[/ ]?\s*wet|threshold)\s+(?:to|at)\s+"
    r"(?P<value>-?(?:\d+(?:\.\d+)?|\.\d+))\s*(?P<unit>%|percent|db|decibels?)(?:\b|$)",
    re.I,
)
_INSPECT_DEVICE_PARAMETERS = re.compile(r"\b(?:show|list|inspect|display|what(?:\s+are|\s+is)?)\b.*\b(?:parameters|settings|controls)\b", re.I)
_EQ_GAIN_VERB_INNER = (
    r"reduce|lower|decrease|cut|attenuate|back\s+off|turn\s+down"
    r"|boost|increase|raise|lift|add|apply|push\s+up|turn\s+up|bring\s+up"
)
_EQ_BOOST_WORD = re.compile(
    r"\b(?:boost|increase|raise|lift|apply|push\s+up|turn\s+up|bring\s+up)\b",
    re.I,
)
_EQ_HZ_UNIT = r"(?:hz|hertz)"
_EQ_DB_UNIT = r"(?:d?b|decibels?)"
_EQ_BAND_GAIN = re.compile(
    r"\b(?:" + _EQ_GAIN_VERB_INNER + r")\b.*?"
    r"\b(?:amplitude|level|gain|volume)\b.*?\bby\s+" + _NUMBER
    + r"\s*" + _EQ_DB_UNIT + r"\b.*?\b(?:at|around)\s+" + _NUMBER + r"\s*" + _EQ_HZ_UNIT + r"\b"
    + r"(?:.*?\bband\s*(\d+)\s*([ab])\b)?",
    re.I,
)
_EQ_BAND_GAIN_FREQ_FIRST = re.compile(
    r"\b(?:" + _EQ_GAIN_VERB_INNER + r")\b.*?"
    + _NUMBER + r"\s*" + _EQ_HZ_UNIT + r"\b.*?\bby\s+" + _NUMBER + r"\s*" + _EQ_DB_UNIT + r"\b",
    re.I,
)
_EQ_BAND_COMPACT_GAIN = re.compile(
    r"\b(?:" + _EQ_GAIN_VERB_INNER + r")\b\s*" + _NUMBER
    + r"\s*" + _EQ_DB_UNIT + r"\b\s*(?:at|around)\s*" + _NUMBER
    + r"\s*(khz|kilohertz|hz|hertz)\b",
    re.I,
)
_EQ_BAND_SHORT_GAIN = re.compile(
    r"\b(?:" + _EQ_GAIN_VERB_INNER + r")\b.*?"
    r"\bband\s*(\d+)\s*([ab])\b.*?\bby\s+" + _NUMBER + r"\s*" + _EQ_DB_UNIT + r"\b"
    r".*?\b(?:at|around)\s+" + _NUMBER + r"\s*" + _EQ_HZ_UNIT + r"\b",
    re.I,
)
_EQ_BAND_ONLY_GAIN = re.compile(
    r"\b(?:" + _EQ_GAIN_VERB_INNER + r")\b.*?"
    r"\beq(?:ualizer)?(?:\s+eight)?\b.*?\bband\s*(\d+)\s*([ab])?\b.*?"
    r"\bby\s+" + _NUMBER + r"\s*" + _EQ_DB_UNIT + r"\b",
    re.I,
)
_EQ_BAND_UNTYPED_SETTING = re.compile(
    r"\b(?:change|set|adjust|modify)\b.*?"
    r"\b(?:eq(?:ualizer)?(?:\s+eight)?\s+)?band\s*(\d+)\s*([ab])?\b.*?"
    r"\b(?:setting|value)\s+(?:of|to)\s*" + _NUMBER,
    re.I,
)
_EQ_BAND_ABSOLUTE_GAIN = re.compile(
    r"\b(?:set|change|adjust|modify)\b.*?"
    r"\b(?:eq(?:ualizer)?(?:\s+eight)?|eq\s*8)\b.*?"
    r"(?:\bband\s*)?(\d+)\s*(?:gain\s*)?([ab])\s*"
    r"(?:\bgain\b\s*)?(?:to|at)\s*" + _NUMBER + r"\s*" + _EQ_DB_UNIT + r"\b",
    re.I,
)
_EQ_BAND_TUNING_GAIN = re.compile(
    r"\b(?:set|move|retune|tune|change)\b.*?"
    r"\b(?:eq(?:ualizer)?(?:\s+eight)?|eq\s*8)\b.*?"
    r"\bband\s*(\d+)\s*([ab])\b.*?"
    r"\b(?:to|at)\s+" + _NUMBER + r"\s*" + _EQ_HZ_UNIT + r"\b.*?"
    r"\b(?:" + _EQ_GAIN_VERB_INNER + r")\b.*?"
    r"\b(?:gain|amplitude|level)\b.*?\bby\s+" + _NUMBER + r"\s*" + _EQ_DB_UNIT + r"\b",
    re.I,
)
_EQ_BAND_TUNING_GAIN_ABSOLUTE = re.compile(
    r"\b(?:set|move|retune|tune|change|adjust)\b.*?"
    r"\b(?:eq(?:ualizer)?(?:\s+eight)?|eq\s*8)\b.*?"
    r"\bband\s*(\d+)\s*([ab])\b.*?"
    r"\b(?:frequency|freq)\b\s*(?:to|at|=)?\s*" + _NUMBER + r"\s*" + _EQ_HZ_UNIT + r"\b.*?"
    r"\b(?:and\s+)?(?:set\s+)?(?:gain|amplitude|level)\b\s*(?:to|at|=)\s*"
    + _NUMBER + r"\s*" + _EQ_DB_UNIT + r"\b",
    re.I,
)
_EQ_DEVICE_REFERENCE = re.compile(
    r"\b(?:eq(?:ualizer)?(?:\s+eight)?|eq\s*8)\s+device\s*#?\s*(\d+)\b",
    re.I,
)
_DEVICE_PARAMETER_ACTION = re.compile(
    r"\b(lower|reduce|decrease|raise|increase|boost|back\s+off|set|change|adjust)\b",
    re.I,
)
_RECIPE_SEPARATOR = re.compile(
    r"\s*(?:;|\b(?:and\s+then|then)\b|\band\s+(?=(?:set|add|append|insert|put|load|mute|silence|solo|isolate|arm|disarm|pan|rename|name|play|stop|show|list|inspect)\b))\s*",
    re.I,
)
_RECIPE_TRACK_ACTIONS = frozenset({"set_volume", "set_pan", "set_mute", "set_solo", "set_arm", "rename_track"})
_RECIPE_TRANSPORT_ACTIONS = frozenset({"transport_play", "transport_stop"})
_RECIPE_DEVICE_ACTIONS = frozenset({"set_device_parameter"})
_RECIPE_SEND_ACTIONS = frozenset({"set_send"})
_SOLO_ANALYSIS_WORKFLOW = re.compile(
    r"\b(?:solo|isolate)\b.{0,100}\b(?:check|analy[sz]e|inspect|listen\s+to)\b.{0,80}"
    r"\b(?:low\s*end|mix|audio|spectrum|clipping|masking)\b",
    re.I,
)
_CREATE_RETURN_SEND_WORKFLOW = re.compile(
    r"\b(?:create|add|make)\b.{0,80}\breturn(?:\s+track)?\b.{0,120}\b(?:send|route)\b",
    re.I,
)
_INSERT_EQ_TUNE_WORKFLOW = re.compile(
    r"\b(?:add|append|insert|put|load)\b.{0,60}\beq(?:\s+eight|\s*8)?\b.{0,120}"
    r"\b(?:boost|cut|reduce|raise|set)\b.{0,80}\b(?:hz|khz|hertz|kilohertz)\b",
    re.I,
)
_INSERT_EQ_TUNE_VALUES = re.compile(
    r"\b(?P<verb>boost|increase|raise|lift|cut|reduce|lower|decrease|attenuate)\b.*?"
    r"(?P<gain>-?(?:\d+(?:\.\d+)?|\.\d+))\s*(?:db|decibels?)\b.*?"
    r"\b(?:at|around)\s*(?P<frequency>\d+(?:\.\d+)?|\.\d+)\s*"
    r"(?P<frequency_unit>khz|kilohertz|hz|hertz)\b",
    re.I,
)
_GROUP_RENAME_WORKFLOW = re.compile(
    r"\b(?:balance|group|organize|bus)\b.{0,100}\b(?:drums?|vocals?|vox|bass|synths?|guitars?|fx)\b"
    r".{0,100}\b(?:call|name|rename)\b",
    re.I,
)

_SPOKEN_NUMBER_VALUES = {
    "zero": 0, "one": 1, "two": 2, "three": 3, "four": 4,
    "five": 5, "six": 6, "seven": 7, "eight": 8, "nine": 9,
    "ten": 10, "eleven": 11, "twelve": 12, "thirteen": 13,
    "fourteen": 14, "fifteen": 15, "sixteen": 16, "seventeen": 17,
    "eighteen": 18, "nineteen": 19, "twenty": 20, "thirty": 30,
    "forty": 40, "fifty": 50, "sixty": 60, "seventy": 70,
    "eighty": 80, "ninety": 90,
}
_SPOKEN_NUMBER_WORD = "(?:" + "|".join(_SPOKEN_NUMBER_VALUES) + ")"
_SPOKEN_NUMBER_CONTEXT = re.compile(
    r"(?P<sign>\b(?:minus|negative)\s+)?(?P<first>\b(?:" + "|".join(_SPOKEN_NUMBER_VALUES) + r")\b)"
    r"(?:\s+(?P<hundred>hundred))?"
    r"(?:\s+(?P<second>\b(?:" + "|".join(_SPOKEN_NUMBER_VALUES) + r")\b))?"
    r"(?=\s*(?:dbs?|decibels?|hz|hertz|khz|kilohertz|%|percent\b|ms|milliseconds?\b|:1|left\b|right\b))",
    re.I,
)
_SPOKEN_SIGNED_DIGIT = re.compile(
    r"\b(?P<sign>minus|negative)\s+(?P<number>-?(?:\d+(?:\.\d+)?|\.\d+))",
    re.I,
)


_COUPLE_OF_DB = re.compile(r"\b(?:a\s+)?couple\s+(?:of\s+)?(?=(?:dbs?|decibels?)\b)", re.I)

# Relative volume ("hats down 2 dB", "take 4 dB off the kick", "vox up 1.5 dB").
# Device, EQ, send and pan wording is excluded: those have their own parsers.
_RELATIVE_VOLUME_EXCLUDE = re.compile(
    r"\b(?:hz|khz|eq|band|threshold|ratio|attack|release|knee|makeup|send|sends|reverb|delay|echo|"
    r"compressor|comp|gain|output|pan|left|right|width|dry|wet|drive|q)\b", re.I)
_RELATIVE_VOLUME_AMOUNT = re.compile(r"(?<![\w.])([+-]?\d+(?:\.\d+)?)\s*(?:dbs?|decibels?)\b", re.I)
_RELATIVE_VOLUME_DOWN = re.compile(
    r"\b(?:down|back|lower|drop|cut|reduce|decrease|quieter|softer|pull|tuck|trim|duck|off)\b", re.I)
_RELATIVE_VOLUME_UP = re.compile(r"\b(?:up|raise|boost|louder|hotter|push|bump|increase|lift|add)\b", re.I)


def _volume_range_message(db: float | None) -> str:
    if db is not None and db > 0.0:
        return "That would take the track above 0 dB, which KENN doesn't set."
    low = volume_law.law().min_db
    return f"KENN sets track volume between {low:g} dB and 0 dB; mute the track to silence it."


def _relative_volume_db(lower: str) -> float | None:
    """A signed dB change for a relative level request, or None when not clearly one.

    Needs an explicit dB amount and exactly one direction (or "by" with a
    signed amount). "to"/"at" means an absolute level, handled elsewhere;
    no direction ("kick -6 dB") or both directions stays ambiguous.
    """
    if _RELATIVE_VOLUME_EXCLUDE.search(lower):
        return None
    amount = _RELATIVE_VOLUME_AMOUNT.search(lower)
    if amount is None or re.search(r"\b(?:to|at)\s+[+-]?\d", lower):
        return None
    value = float(amount.group(1))
    down, up = bool(_RELATIVE_VOLUME_DOWN.search(lower)), bool(_RELATIVE_VOLUME_UP.search(lower))
    if down and not up:
        return -abs(value)
    if up and not down:
        return abs(value)  # "up -3 dB" is caught after parsing and asked about
    if not up and not down and re.search(r"\bby\s+[+-]\d", lower):
        return value
    return None


_TRACK_NICKNAMES = (
    (re.compile(r"\b(?:high|hi)[\s-]*hats?\b|\bhihats?\b", re.I), "hi hats"),
    (re.compile(r"\b(?:vox|vocals|voc)\b", re.I), "vocal"),
    (re.compile(r"\bdrums\b", re.I), "drum"),
    (re.compile(r"\bdrumbuss?\b", re.I), "drum bus"),
)
# The words _TRACK_NICKNAMES accepts, as plain words.
_NICKNAME_WORDS = frozenset({"high", "hi", "hat", "hats", "hihat", "hihats", "vox", "vocals", "voc", "drums", "drumbus",
                             "drumbuss"})
_GENERIC_TRACK_WORDS = {"track", "bus", "group", "the", "and", "audio", "midi", "return", "main", "channel"}
# Words that name a *particular* track. "the Lead Vocal" must not resolve to a
# "Backing Vocal" track just because both contain "vocal".
_TRACK_QUALIFIERS = {
    "lead", "backing", "main", "harmony", "harmonies", "double", "doubles", "bgv", "bgvs", "adlib", "adlibs",
    "sub", "top", "bottom", "room", "overhead", "overheads", "kick", "snare", "synth", "pad", "bass", "acoustic",
    "electric", "rhythm", "clean", "dirty", "low", "string", "strings", "piano", "keys", "guitar", "fx", "print",
    "chorus", "verse", "drum", "vocal", "hi", "clap",
}
_SECOND_ACTION = re.compile(
    r"\b(?:and|then|also|plus)\s+(?:then\s+)?(?:turn|mute|unmute|solo|unsolo|pan|bring|set|push|pull|drop|raise|"
    r"lower|boost|cut|tuck|arm|disarm|rename|add|insert|put|play|stop|start|make|take|nudge|bump|park|center|centre)\b",
    re.I,
)
_VAGUE_EFFECT = re.compile(r"\b(?:some|more|less|a\s+bit\s+of|a\s+little|a\s+touch\s+of|a\s+splash\s+of)\s+(?:reverb|verb|delay|echo)\b", re.I)


def _nickname_track_name(text: str, tracks: list[dict[str, Any]]) -> str:
    """The one track a nickname points at ("hats" -> Hi-Hats, "vox" -> Lead Vocal), or ""."""
    def normalize(value: str) -> str:
        return " ".join(re.sub(r"[-/_&]+", " ", value.casefold()).split())

    spoken = normalize(text)
    for pattern, replacement in _TRACK_NICKNAMES:
        spoken = pattern.sub(replacement, spoken)
    # Capitalised words (not sentence-initial) are name-like qualifiers too.
    capitalised = {w.casefold() for i, w in enumerate(re.findall(r"[A-Za-z]+", text)) if i and w[:1].isupper()}
    tokens = spoken.split()
    matched = []
    for track in tracks:
        name = str(track.get("name", "")).strip()
        normalized = normalize(name)
        name_words = set(normalized.split())
        words = {w for w in name_words if len(w) >= 3 and w not in _GENERIC_TRACK_WORDS}
        words |= {w[:-1] for w in words if w.endswith("s") and len(w) > 3}  # "hats" also answers to "hat"
        if not name or not words:
            continue

        def fits(position: int) -> bool:
            # Reject when the word before names a different track ("Lead" Vocal vs Backing Vocal).
            previous = tokens[position - 1] if position > 0 else ""
            return not previous or previous in name_words or not (previous in _TRACK_QUALIFIERS or previous in capitalised)

        hit = any(
            fits(i) for i, token in enumerate(tokens)
            if token in words or (token.endswith("s") and token[:-1] in words)
        )
        if hit or re.search(rf"\b{re.escape(normalized)}\b", spoken):
            matched.append(name)
    # Two tracks sharing a nickname is ambiguous: KENN asks rather than picks.
    return matched[0] if len(matched) == 1 else ""


def _eq_gain_signed(matched_text: str, magnitude: float) -> float:
    """Apply boost/cut direction to an EQ gain magnitude.

    Boost-family verbs (boost, increase, raise, ...) yield a positive change;
    everything else keeps the historical cut convention (negative). The match
    is scoped to the already-matched EQ clause so unrelated words elsewhere
    in the request cannot flip the sign.
    """
    magnitude = abs(float(magnitude))
    if _EQ_BOOST_WORD.search(matched_text or ""):
        return magnitude
    return -magnitude


def _insert_eq_tune_values(text: str) -> dict[str, Any] | None:
    """Extract one exact new-EQ band assignment without choosing a band."""
    if not _INSERT_EQ_TUNE_WORKFLOW.search(text):
        return None
    values = _INSERT_EQ_TUNE_VALUES.search(text)
    if values is None:
        return None
    band = re.search(r"\bband\s*(\d+)\s*([ab])\b", text, re.I)
    frequency = float(values.group("frequency"))
    if values.group("frequency_unit").casefold() in {"khz", "kilohertz"}:
        frequency *= 1000.0
    return {
        "gain_db": _eq_gain_signed(values.group(0), float(values.group("gain"))),
        "frequency_hz": frequency,
        "eq_band": f"{int(band.group(1))}{band.group(2).upper()}" if band else "",
    }


def _spoken_hundred_value(first: int, hundred: str | None, second: int) -> int:
    if hundred:
        return first * 100 + second
    if first >= 20 and 0 <= second < 10:
        return first + second
    return first


def _normalize_spoken_numbers(text: str) -> str:
    """Convert bounded spoken numbers only where a numeric unit follows.

    The context requirement avoids rewriting ordinary track/device names such
    as ``Studio One`` while allowing natural commands like ``minus nine dB``
    and ``fifteen percent left`` to use the same numeric parsers as digit
    forms. Compound tens such as ``twenty five`` are supported.
    """
    def replace(match: re.Match[str]) -> str:
        first = _SPOKEN_NUMBER_VALUES[match.group("first").lower()]
        second_text = match.group("second")
        second = _SPOKEN_NUMBER_VALUES[second_text.lower()] if second_text else 0
        value = _spoken_hundred_value(first, match.group("hundred"), second)
        if match.group("sign"):
            value = -value
        return str(value)

    signed_digits = _SPOKEN_SIGNED_DIGIT.sub(lambda match: "-" + match.group("number"), text)
    # "a couple of dB" is a studio idiom for 2 dB; "a touch" or "a bit" stay vague.
    signed_digits = _COUPLE_OF_DB.sub("2 ", signed_digits)
    return _SPOKEN_NUMBER_CONTEXT.sub(replace, signed_digits)


def _insert_device_name(text: str) -> str | None:
    for canonical, pattern in _INSERT_DEVICE_ALIASES:
        if re.search(rf"\b(?:{pattern})\b", text, re.I):
            return canonical
    return None


def _device_setup_name(value: str) -> str | None:
    normalized = " ".join(str(value or "").casefold().split())
    if normalized in {"reverb", "hybrid reverb"}:
        return "Hybrid Reverb"
    if normalized in {"echo", "delay"}:
        return "Echo"
    if normalized == "compressor":
        return "Compressor"
    return None


def _track_entries(snapshot: dict[str, Any]) -> list[dict[str, Any]]:
    tracks = snapshot.get("tracks") if isinstance(snapshot, dict) else []
    return [track for track in tracks or [] if isinstance(track, dict)]


def _find_track(phrase: str, tracks: list[dict[str, Any]]) -> tuple[dict[str, Any] | None, list[dict[str, Any]], str | None]:
    normalized = " ".join(phrase.lower().split())
    exact = [track for track in tracks if str(track.get("name", "")).strip().lower() == normalized]
    if len(exact) == 1:
        return exact[0], [], None
    if len(exact) > 1:
        return None, exact, "duplicate track name"
    contained = [track for track in tracks if str(track.get("name", "")).strip() and str(track.get("name", "")).strip().lower() in normalized]
    if len(contained) == 1:
        return contained[0], [], None
    if len(contained) > 1:
        return None, contained, "ambiguous track name"
    # Nicknames ("vocal" -> Lead Vocal, "hats" -> Hi-Hats), with the same guard
    # against a qualifier that names a different track.
    nickname = _nickname_track_name(phrase, tracks)
    if nickname:
        return next(t for t in tracks if str(t.get("name", "")).strip() == nickname), [], None
    return None, [], "track not found in the current Live snapshot"


def _extract_track_phrase(text: str, tracks: list[dict[str, Any]]) -> str:
    lowered = text.lower()
    names = sorted((str(track.get("name", "")) for track in tracks if track.get("name")), key=len, reverse=True)
    for name in names:
        if name.lower() in lowered:
            return name
    nickname = _nickname_track_name(text, tracks)
    if nickname:
        return nickname
    match = re.search(r"(?:track|channel|chan|ch|vocal|bass|kick|guitar|drum\s+bus)\s+([\w][\w -]{0,50})", lowered)
    return match.group(1).strip() if match else ""


def _find_numbered_track(number: int, tracks: list[dict[str, Any]]) -> tuple[dict[str, Any] | None, str | None]:
    """Resolve the user-facing one-based track number against the snapshot.

    Ableton's internal bridge indices are zero-based, while a musician saying
    "track 4" normally means the fourth visible track.  The result records
    both meanings so the proposal can show the exact Live identity before any
    write is possible.
    """
    if number < 1 or number > len(tracks):
        return None, f"Track {number} is not present in the current Live snapshot."
    track = tracks[number - 1]
    if not isinstance(track, dict):
        return None, f"Track {number} is not readable in the current Live snapshot."
    return track, None


def _find_clip_track(phrase: str, tracks: list[dict[str, Any]]) -> tuple[dict[str, Any] | None, list[dict[str, Any]], str | None]:
    """Resolve one duplication endpoint as a numbered or named track."""
    clean = " ".join(str(phrase or "").strip(" ' \"").split())
    numbered = re.fullmatch(r"(?:track|trk|channel|chan|ch)\s*#?\s*(\d+)", clean, re.I)
    if numbered:
        track, error = _find_numbered_track(int(numbered.group(1)), tracks)
        return track, [], error
    return _find_track(clean, tracks)


def _generic_device_parameter_match(text: str, device_name: str) -> dict[str, str] | None:
    """Extract a parameter name after an exact device name.

    The deterministic parser deliberately does not maintain a hard-coded list
    of Live parameters: different devices expose different controls.  The
    command gateway resolves this name against a fresh parameter inspection
    before it can create a proposal.
    """
    device_match = re.search(re.escape(device_name), text, re.I)
    if device_match is None or _DEVICE_PARAMETER_ACTION.search(text[:device_match.start()]) is None:
        return None
    # "compressor lookahead on the drum bus to 10 ms": the track is where, not which control; left in, the control
    # came out as "On The Drum Bus".
    tail = re.sub(r"\s+on\s+(?:the\s+)?[\w/&' -]+?(?=\s+(?:to|by)\s)", "", text[device_match.end():], count=1, flags=re.I)
    match = re.search(
        r"\s+(?:the\s+)?(?P<parameter>[a-z0-9][a-z0-9]*(?:[ /_-]+[a-z0-9][a-z0-9]*){0,3}?)"
        r"\s+(?P<verb>to|by)\s+" + _NUMBER + r"\s*(?P<unit>db|dbs|decibels?|hz|hertz|khz|kilohertz|%|percent|ms|milliseconds?|:1)?(?=\s|$|on\b)",
        tail,
        re.I,
    )
    if match:
        return {
            "parameter": match.group("parameter"),
            "verb": match.group("verb"),
            "value": match.group(3),
            "unit": match.group("unit") or "",
        }

    # Also accept the common form "reduce Device Parameter on Track by X"
    # where the track phrase sits between the parameter and numeric value.
    match = re.search(
        r"\s+(?:the\s+)?(?P<parameter>[a-z0-9][a-z0-9]*(?:[ /_-]+[a-z0-9][a-z0-9]*){0,3}?)"
        r"\s+on\s+.+?\s+(?P<verb>to|by)\s+" + _NUMBER + r"\s*(?P<unit>db|dbs|decibels?|hz|hertz|khz|kilohertz|%|percent|ms|milliseconds?|:1)?(?=\s|$)",
        tail,
        re.I,
    )
    if match:
        return {
            "parameter": match.group("parameter"),
            "verb": match.group("verb"),
            "value": match.group(3),
            "unit": match.group("unit") or "",
        }

    # Finally accept "set Parameter [control] on Device to X", useful for
    # named controls whose device is naturally mentioned second.
    prefix = text[:device_match.start()]
    prefix_match = re.search(
        r"\b(?:set|change|adjust)\s+(?:the\s+)?(?P<parameter>[a-z0-9][a-z0-9]*(?:[ /_-]+[a-z0-9][a-z0-9]*){0,3}?)"
        r"(?:\s+control)?\s+on\s*$",
        prefix,
        re.I,
    )
    suffix_match = re.search(
        r"\s+(?P<verb>to|by)\s+" + _NUMBER + r"\s*(?P<unit>db|dbs|decibels?|hz|hertz|khz|kilohertz|%|percent|ms|milliseconds?|:1)?(?=\s|$)",
        tail,
        re.I,
    )
    if prefix_match and suffix_match:
        return {
            "parameter": prefix_match.group("parameter"),
            "verb": suffix_match.group("verb"),
            "value": suffix_match.group(2),
            "unit": suffix_match.group("unit") or "",
        }
    return None


def split_recipe_request(text: str) -> list[str]:
    """Split only explicit, bounded recipe separators.

    The look-ahead on the bare ``and`` form deliberately avoids splitting
    compound EQ language such as ``frequency ... and gain ...``. A caller
    should treat an empty or one-item result as an ordinary single command.
    """
    parts = [part.strip(" ,") for part in _RECIPE_SEPARATOR.split(text) if part.strip(" ,")]
    return parts if len(parts) > 1 else []


_AND_SPLIT = re.compile(r"\s*,?\s+and\s+(?!then\b)", re.I)
_SHARED_TAIL = re.compile(r"^\s*(?P<verb>turn|bring|push|pull|drop|set|put|pan)\s+(?P<a>(?:the\s+)?[\w/'-]+(?:\s+[\w/'-]+)?)"
                          r"\s+and\s+(?P<b>(?:the\s+)?[\w/'-]+(?:\s+[\w/'-]+)?)\s+(?P<tail>(?:up|down|to|by|at|left|right|"
                          r"hard|back)\b.+)$", re.I)
_LEADING_VERB = re.compile(r"^\s*(?P<verb>(?:un)?mute|(?:un)?solo|pan|arm|disarm|kill|nuke|rename)\b", re.I)


def _clean_intent(segment: str, snapshot: dict[str, Any]) -> dict[str, Any] | None:
    intent = parse_request(segment, snapshot)
    ok = intent.get("action") and not intent.get("missing_fields") and not intent.get("ambiguity") \
        and intent.get("mode") != "refuse"
    return intent if ok else None


def _split_plain_and(text: str, snapshot: dict[str, Any]) -> list[str]:
    """Two changes joined by a plain "and", accepted only when both halves are clear.

    "mute the hats and the snare" repeats the verb; "solo the bass and turn it up
    2 dB" resolves "it" to the first track. If either half would not parse on
    its own, return nothing and let the single-command path ask as before.
    """
    text = text.strip().rstrip(".!")
    # "turn the kick and snare down 2 dB" changed only the Kick (27 Sept 2026): the amount belongs to both.
    shared = _SHARED_TAIL.match(text)
    if shared:
        names = [shared.group("a"), shared.group("b")]
        distributed = [f"{shared.group('verb')} {name} {shared.group('tail')}" for name in names]
        # Both halves read as Live changes: keep both, so a half that can't be done is reported as that step
        # ("Step 2: 'Lead Vocal' is at 0.0 dB...") rather than quietly dropped while the other half goes ahead.
        if all(parse_request(part, snapshot).get("action") for part in distributed):
            return distributed
    parts = _AND_SPLIT.split(text)
    verb = _LEADING_VERB.match(parts[0]) if parts else None
    if len(parts) == 2 and "," in parts[0] and verb:
        # "mute the kick, the snare and the hats" dropped the snare: a list, each name taking the verb.
        head, *listed = [part.strip() for part in parts[0].split(",") if part.strip()]
        items = [head] + [f"{verb.group('verb')} {name}" for name in listed + [parts[1].strip()]
                          if re.match(r"^(?:the\s+)?[\w/'-]+(?:\s+[\w/'-]+)?$", name, re.I)]
        if len(items) == len(listed) + 2 and all(_clean_intent(item, snapshot) is not None for item in items):
            return items
    if len(parts) != 2:
        return []
    first, second = parts[0].strip(), parts[1].strip()
    first_intent = _clean_intent(first, snapshot)
    if first_intent is None:
        # "pan the kick left and the bass right": neither says how far, but both are clearly pans; keep both so the
        # recipe asks about each step instead of reading one pan that names both sides.
        verb = _LEADING_VERB.match(first)
        if verb and verb.group("verb").lower() == "pan":
            second_full = second if _LEADING_VERB.match(second) else f"pan {second}"
            if parse_request(first, snapshot).get("action") == "set_pan" \
                    and parse_request(second_full, snapshot).get("action") == "set_pan":
                return [first, second_full]
        return []
    verb = _LEADING_VERB.match(first)
    if verb and verb.group("verb").lower() == "rename" and re.match(r"^(?:the\s+)?[\w/'-]+(?:\s+[\w/'-]+)?\s+to\s+\S", second, re.I):
        second = f"rename {second}"  # "rename the synth to Pads and the bass to Sub" named the Synth "Pads and the bass to Sub"
    elif verb and (re.match(r"^(?:the\s+)?[\w/'-]+(?:\s+[\w/'-]+)?$", second, re.I)
                 or (verb.group("verb").lower() == "pan"
                     and re.match(r"^(?:the\s+)?[\w/'-]+(?:\s+[\w/'-]+)?\s+(?:\d+\s*%?\s*)?(?:hard\s+)?(?:left|right)\b", second, re.I))):
        second = f"{verb.group('verb')} {second}"  # "... and the snare", "pan the kick left and the bass right"
    track_name = str((first_intent.get("track") or {}).get("name") or "")
    if track_name:
        second = re.sub(r"\b(?:it|that)\b", f"the {track_name}", second, count=1)
    if _clean_intent(second, snapshot) is None:
        return []
    return [first, second]


def parse_natural_recipe(query: str, session_snapshot: dict[str, Any] | None) -> dict[str, Any] | None:
    """Parse a small natural-language recipe into typed, non-executable steps.

    Existing track/transport actions are typed immediately. A generic
    existing-device parameter action is retained as a parsed intent for the
    live-side sparse-index and unit resolver. Device insertion and EQ band
    actions are rejected rather than guessed inside a recipe.
    """
    # Same tidy-up as single commands: "Can you solo the drum bus and the vocal at the same time?" didn't split, and
    # the single-command parse then soloed only the Drum Bus.
    text = _rewrite_common_phrasings(" ".join(str(query or "").strip().split()))
    guarded_workflows = (
        (
            _SOLO_ANALYSIS_WORKFLOW,
            "Solo-and-analyze requires a fresh post-solo capture plus verified restoration of the prior solo state; "
            "that capture workflow is not qualified yet, so nothing changed.",
        ),
        (
            _CREATE_RETURN_SEND_WORKFLOW,
            "Create-return-and-send is not one exact-undo recipe yet: return deletion, inserted-device identity, and "
            "the requested send display-unit mapping must all be qualified first. Nothing changed.",
        ),
        (
            _GROUP_RENAME_WORKFLOW,
            "Group-and-rename is not qualified because Live group-member routing and exact group deletion are not "
            "verified through KENN yet. Nothing changed.",
        ),
    )
    for pattern, reason in guarded_workflows:
        if pattern.search(text):
            return {
                "schema": "kenn.ableton_recipe_intent.v1",
                "action": "recipe",
                "mode": "assist",
                "segments": [text],
                "steps": [],
                "step_intents": [],
                "missing_fields": [],
                "ambiguity": [reason],
                "confirmation_required": False,
                "confidence": 1.0,
            }
    # Insert-and-configure phrases contain an ``and set`` separator but map
    # to one qualified, rollback-capable atomic proposal.  Let parse_request
    # handle that primitive instead of splitting it into an unsafe recipe.
    if _DEVICE_SETUP.search(text) or _DEVICE_SETUP_TRAILING.search(text) or _insert_eq_tune_values(text):
        return None
    segments = split_recipe_request(text) or _split_plain_and(text, session_snapshot or {})
    if not segments:
        return None
    if len(segments) > 3:
        return {
            "schema": "kenn.ableton_recipe_intent.v1",
            "action": "recipe",
            "mode": "assist",
            "segments": segments[:3],
            "steps": [],
            "missing_fields": [],
            "ambiguity": ["A natural-language recipe is limited to three reversible steps."],
            "confirmation_required": False,
            "confidence": 1.0,
        }
    snapshot = session_snapshot or {}
    steps: list[dict[str, Any]] = []
    step_intents: list[dict[str, Any]] = []
    problems: list[str] = []
    for position, segment in enumerate(segments, start=1):
        intent = parse_request(segment, snapshot)
        if intent.get("mode") == "refuse":
            problems.append(f"Step {position}: {intent.get('error', 'the request is outside the safety boundary')}")
            continue
        if intent.get("missing_fields") or intent.get("ambiguity"):
            details = "; ".join(intent.get("ambiguity") or intent.get("missing_fields") or [])
            problems.append(f"Step {position}: {details or 'the target is ambiguous'}")
            continue
        action = intent.get("action")
        if action in _RECIPE_TRACK_ACTIONS:
            track = intent.get("track") or {}
            steps.append({
                "action": action,
                "track_index": track.get("index"),
                "track_name": track.get("name", ""),
                "value": intent.get("desired_value"),
            })
            step_intents.append({"segment": segment, "intent": intent})
        elif action in _RECIPE_TRANSPORT_ACTIONS:
            steps.append({"action": action})
            step_intents.append({"segment": segment, "intent": intent})
        elif action in _RECIPE_DEVICE_ACTIONS or action in _RECIPE_SEND_ACTIONS:
            # The parser can identify the exact device and user-facing value,
            # but only the live-side parameter inspection can resolve the
            # sparse parameter index and any evidence-backed unit conversion.
            step_intents.append({"segment": segment, "intent": intent})
        else:
            problems.append(
                f"Step {position}: natural recipes currently support track controls, play/stop, send levels, and exact "
                "existing-device parameter changes; device insertion and EQ band changes must be proposed separately."
            )
    if not problems and len(steps) == len(step_intents) and len({repr(sorted(step.items())) for step in steps}) == 1:
        return None  # "mute the snare and clap" is one track here (Snare / Clap), not two steps doing the same thing
    return {
        "schema": "kenn.ableton_recipe_intent.v1",
        "action": "recipe",
        "mode": "assist",
        "segments": segments,
        "steps": steps if not problems else [],
        "step_intents": step_intents if not problems else [],
        "missing_fields": [],
        "ambiguity": problems,
        "confirmation_required": bool(steps) and not problems,
        "confidence": 0.95 if not problems else 0.9,
    }


def _bool_value(text: str, positive: str) -> bool:
    return positive not in text.lower().split()


_ORDINALS = {"first": 1, "second": 2, "third": 3, "fourth": 4, "fifth": 5, "sixth": 6, "seventh": 7,
             "eighth": 8, "ninth": 9, "tenth": 10}
_ORDINAL_CHANNEL = re.compile(
    r"\b(?:the\s+)?(" + "|".join(_ORDINALS) + r")\s+(?:visible\s+)?(?:track|trk|channel|chan|ch)\b", re.I)
_ORDINAL_SCENE = re.compile(r"\b(?:the\s+)?(" + "|".join(_ORDINALS) + r")\s+scene\b", re.I)
_CORRECTION_LEAD = re.compile(r"^\s*(?:no\s+wait|no|wait|sorry|actually|oops)\s*[,.!:;-]\s*", re.I)
_CORRECTION_TAIL = re.compile(r",?\s+(?:not|instead\s+of)\s+the\s+[\w\s/'-]+?\s*[.!]?\s*$", re.I)
# "set Vocal volume to minus six—actually pan it twenty percent right": a new instruction after the correction replaces
# the first one, and its "it" is the track named before. Only a following verb counts; "solo the vocal, actually the
# synth" is handled by the correction rules in live_command.
_MID_CORRECTION = re.compile(
    r"^(?P<before>.+?)\s*(?:\u2014|\u2013|--|,|;|\.)\s*(?:actually|no\s+wait|scratch\s+that)\s*,?\s+"
    r"(?P<after>(?:pan|set|mute|unmute|solo|unsolo|turn|make|bring|arm|disarm|put|send|add|rename|cent(?:er|re))\b.+)$", re.I)
# "mute track 2, actually track 3" used to mute track 2: a bare new target after the correction replaces the old one.
_MID_CORRECTION_TARGET = re.compile(
    r"^(?P<before>.+?)\s*(?:\u2014|\u2013|--|,|;|\.|\s)\s*(?:actually|no\s+wait|i\s+mean|sorry)\s*,?\s+"
    r"(?P<target>(?:the\s+)?(?:track\s+\w+|[a-z][\w/'-]*(?:\s+[a-z][\w/'-]*){0,2}))\s*[.!]?\s*$", re.I)
# "Mute the kick. No wait, the snare." and "mute the kick no wait the snare" muted the Kick (27 Sept 2026); only a comma
# after the first request used to count.
# "rather than solo the kick, mute the snare" muted the Kick (27 Sept 2026): only the second clause is the request.
_INSTEAD_OF = re.compile(r"^\s*(?:instead\s+of|rather\s+than)\s+(?P<before>[^,;]+?)\s*[,;]\s*(?P<after>.+)$", re.I)
_INSTEAD_OBJECT = re.compile(r"^\s*(?:\w+ing|set|turn|bring|make|put|pan|mute|solo|arm)\s+(?P<obj>.+?)"
                             r"(?:\s+(?:to|by|at|up|down)\b.*)?$", re.I)
_CORRECTED_OBJECT = re.compile(r"^\s*(?:set|turn|bring|make|put|get|pan|mute|solo)\s+(?P<obj>.+?)"
                               r"(?:\s+(?:volume|level|fader|pan))?(?:\s+(?:to|by|at|up|down)\b.*)?$", re.I)
_CALL_TRACK = re.compile(r"^\s*call\s+(track\s+\d+)\s+['\"]?(.+?)['\"]?\s*[.!]?\s*$", re.I)
_TERSE_LEVEL = re.compile(
    r"^\s*(?!(?:set|put|bring|turn|send|pan|make|move|drop|push|pull|get|take|mute|solo|arm|rename|call)\b)"
    r"(?P<name>[\w/'&-]+(?:\s+[\w/'&-]+){0,3}?)\s+(?:to|at)\s+(?P<amount>(?:minus\s+|[-+])?\d+(?:\.\d+)?)\s*dbs?\s*[.!]?\s*$",
    re.I)
_TERSE_LEVEL_EXCLUDE = re.compile(r"\b(?:send|sends|reverb|delay|echo|eq|band|gain|threshold|makeup|output|input)\b", re.I)

# Everyday phrasings found by the 505-phrasing check (tooling/data/natural_holdout_candidates.jsonl). Each one is
# anchored to the whole request and rewritten into a form the rules already parse; the track name still has to
# resolve, so "synth off" works and "metronome off" still asks.
_NAME = r"(?P<name>(?:the\s+)?[\w/'&-]+(?:\s+[\w/'&-]+){0,3}?)"
_POLITE_TAIL = re.compile(r"\s*,?\s+(?:please|pls|plz|thanks|thank\s+you|cheers|mate|for\s+(?:now|a\s+(?:moment|sec(?:ond)?|minute|while))"
                          r"|real\s+quick|right\s+now)\s*[.!?]*\s*$", re.I)
# "bring the kick down to -16, it's too loud": the clause after the comma says why, not what.
_STATE_REASON_TAIL = re.compile(r"\s*[,;]\s*(?:it'?s|it\s+is|they'?re|they\s+are|it\s+sounds|that'?s)\s+(?:too|a\s+bit|way|really|"
                                r"kinda|kind\s+of|very|so|quite|pretty)\b[^,;]*$", re.I)
# "The kick is too loud, can you bring it down to -16?": "it" is the track the first clause named.
_PROBLEM_THEN_IT = re.compile(rf"^\s*{_NAME}(?:\s+track)?\s+(?:is|sounds|feels|seems|'s)\s+(?:way\s+|a\s+bit\s+|a\s+little\s+|"
                              r"really\s+|kind\s+of\s+|kinda\s+|pretty\s+|just\s+|still\s+)*too\s+\w+\s*[,.;!]+\s*(?P<rest>.+)$", re.I)
# "The transport is stopped, can you start it?": "it" is the transport, and starting it is Play.
_TRANSPORT_IT = re.compile(r"\btransport\b.*\b(?P<verb>start|play|run|stop|halt)\s+it\b", re.I)
# "the FX Print track should be called FX Send, can you rename it?"
_SHOULD_BE_CALLED = re.compile(rf"^\s*(?:i\s+think\s+)?{_NAME}(?:\s+track)?\s+should\s+be\s+(?:called|named)\s+"
                               r"['\"]?(?P<new>[^,'\"?!.]+?)['\"]?\s*(?:[,.?!].*)?$", re.I)
# "move the drum bus to the left a little": a pan without an amount, so KENN asks how far.
_MOVE_TO_SIDE = re.compile(rf"^\s*(?:move|shift|nudge|push|slide)\s+{_NAME}\s+(?:over\s+)?(?:to\s+)?(?:the\s+)?"
                           r"(?P<side>left|right)(?:\s+(?:a\s+(?:little|bit|touch)|slightly))?\s*[.!?]?\s*$", re.I)
# "I need the drum bus muted", "make sure the snare is centered", "I want the vocal back to center".
_WANTED_STATE = re.compile(rf"^\s*(?:make\s+sure|i\s+(?:need|want|would\s+like|'d\s+like)|let'?s\s+(?:have|get))\s+{_NAME}"
                           r"(?:\s+tracks?)?\s+(?:(?:is|are|'s)\s+|(?:to\s+be|should\s+be)\s+)?(?P<neg>n't\s+|not\s+|un)?"
                           r"(?P<state>muted|soloed|(?:record[\s-]?)?armed|cent(?:red|ered)|back\s+(?:to|in)\s+(?:the\s+)?"
                           r"(?:centre|center|middle))\s*[.!?]?\s*$", re.I)
# "lower the bass a bit": a level change with no amount, so KENN asks how much.
_VAGUE_LEVEL_VERB = re.compile(rf"^\s*(?P<verb>lower|drop|reduce|decrease|raise|boost|increase|lift)\s+{_NAME}(?:\s+track)?"
                               r"(?P<vague>\s+(?:a\s+(?:bit|little(?:\s+bit)?|touch|tad|hair)|slightly))?\s*[.!?]?\s*$", re.I)
# Dictated requests stack fillers in front ("um yeah so can you ..."), so the lead repeats.
_POLITE_LEAD = re.compile(r"^\s*(?:(?:um+|uh+|erm|er|hmm+|yeah|yep|so|well|alright|yo|hey|ok|okay|right|please"
                          r"|just(?=\s+(?!the\b|my\b|that\b|this\b)\w)"  # but "just the kick" means solo it
                          r"|let'?s(?=\s+(?!go\b|jam\b|hear\b|have\b|get\b))|let\s+us(?=\s+(?!go\b|jam\b|hear\b))"
                          r"|(?:can|could|would|will)\s+(?:you|u)(?:\s+please)?"
                          r"|(?:is|would)\s+it\s+(?:be\s+)?possible\s+(?:for\s+you\s+)?to"
                          r"|i\s+(?:want|need|would\s+like|'d\s+like)\s+(?:you\s+)?to)\s*[,!]?\s+)+(?=\w)", re.I)
# ", can you do that?", "for clarity", "so I can adjust it": asides after the request. Left in, they ended up in new
# track names ("Synth Lead, can you do that?").
_TRAILING_ASIDE = re.compile(r"\s*,?\s+(?:can\s+you\s+(?:do\s+that|help(?:\s+me)?(?:\s+with\s+that)?)|is\s+that\s+possible|"
                             r"if\s+(?:you\s+can|possible)|for\s+clarity|for\s+me|at\s+the\s+same\s+time|together|simultaneously|so\s+(?:that\s+)?i\s+can\s+[^,]+|thanks?(?:\s+you)?)"
                             r"\s*[?.!]*\s*$", re.I)
# "how do I solo the vocal?" asks how, it doesn't ask KENN to do it; KENN's notes answer it.
_HOW_TO_QUESTION = re.compile(r"^\s*(?:how\s+(?:do|can|would|should)\s+i|is\s+there\s+a\s+way\s+to|what(?:'s|\s+is)\s+the\s+"
                              r"(?:best\s+)?way\s+to)\b", re.I)
_A_DB = re.compile(r"\b(?:(?P<half>half\s+a)|an?)\s+(?:db|decibel)\b", re.I)
_SIGNED_CHANGE = re.compile(rf"^\s*{_NAME}\s+(?P<sign>[+-])\s*(?P<amount>\d+(?:\.\d+)?)\s*(?:dbs?)?\s+relative\s*[.!]?\s*$"
                            rf"|^\s*{_NAME.replace('name', 'name2')}\s+\+\s*(?P<amount2>\d+(?:\.\d+)?)\s*dbs?\s*[.!]?\s*$", re.I)
_UNITLESS_CHANGE = re.compile(rf"^\s*{_NAME}\s+(?P<direction>up|down)\s+(?P<amount>\d+(?:\.\d+)?)\s*[.!]?\s*$"
                              rf"|^\s*(?P<verb>lower|raise|drop|cut|boost|reduce|up)\s+{_NAME.replace('name', 'name2')}\s+(?:by\s+)?"
                              r"(?P<amount2>\d+(?:\.\d+)?)\s*[.!]?\s*$", re.I)
_HARD_PAN_ON = re.compile(rf"^\s*(?:hard|fully)\s+(?P<side>left|right)\s+(?:on|for)\s+{_NAME}\s*[.!]?\s*$", re.I)
_VOL_ON = re.compile(rf"^\s*set\s+(?:the\s+)?(?:vol|volume|level)\s+(?:to\s+)?(?P<amount>(?:minus\s+|-)\d+(?:\.\d+)?)\s*(?:dbs?)?\s+"
                     rf"(?:on|for)\s+{_NAME}\s*[.!]?\s*$", re.I)
# "drum bus comp thres -12", "comp lead vocal thres -12", "voc comp thres down 2"
_TERSE_THRESHOLD = re.compile(
    rf"^\s*(?:(?:set|change)\s+)?(?:(?:the\s+)?{_NAME}\s+(?:comp|compressor)|(?:comp|compressor)\s+{_NAME.replace('name', 'name2')})\s+"
    r"(?:thres|thresh|threshold)\s+(?:(?P<direction>up|down)\s+(?P<change>\d+(?:\.\d+)?)|(?:to\s+)?(?P<amount>-?\d+(?:\.\d+)?))"
    r"\s*(?:dbs?)?\s*[.!]?\s*$", re.I)
# A negative bare number on a fader is a dB level ("fx print at -15", "kick fader to minus 10"); a bare "kick to -9"
# without "at" or "fader" still asks, as before.
_UNITLESS_LEVEL = re.compile(rf"^\s*{_NAME}\s+(?:fader\s+(?:to|at)|at|fader)\s+(?P<amount>(?:minus\s+|-)\d+(?:\.\d+)?)"
                             r"\s*(?:dbs?)?\s*[.!]?\s*$", re.I)
_BARE_PAN = re.compile(rf"^\s*{_NAME}\s+(?P<amount>\d+(?:\.\d+)?)\s*(?:%|percent)\s+(?:to\s+the\s+)?(?P<side>left|right)"
                       r"\s*[.!]?\s*$", re.I)
_LR_PAN = re.compile(rf"^\s*{_NAME}\s+(?P<side>[lr])\s*(?P<amount>\d{{1,3}})\s*[.!]?\s*$", re.I)
_CENTRE_PAN = re.compile(rf"^\s*(?:put\s+)?{_NAME}\s+(?:in\s+the\s+middle|dead\s+cent(?:er|re)|(?:back\s+)?to\s+the\s+"
                         r"(?:cent(?:er|re)|middle))\s*[.!]?\s*$|^\s*re-?(?P<verb>cent(?:er|re))\b", re.I)
_MUTE_IDIOM = re.compile(rf"^\s*(?:(?:turn|switch|shut|cut)\s+{_NAME}\s+(?:off|out)|{_NAME.replace('name', 'name2')}\s+off"
                         rf"|lose\s+{_NAME.replace('name', 'name3')})\s*[.!]?\s*$", re.I)
_UNMUTE_IDIOM = re.compile(rf"^\s*(?:turn|switch|bring|put)\s+{_NAME}\s+back\s+(?:on|in)\s*[.!]?\s*$", re.I)
_NOT_A_TRACK_NAME = re.compile(r"\b(?:it|that|this|them|everything|all|solo|arm|record|mute|metronome|click|loop|"
                               r"playback|transport|song|master|plugin|device|effect|fx)\s*$|^(?:the\s+)?(?:it|that|this)\b"
                               r"|\b(?:pan|comp|compressor|ratio|attack|release|tempo|bpm|pitch|transpose|key|swing)\b", re.I)
# A negative bare number as a fader target is dB (Live shows faders in dB): "set hats to -6", "turn the kick down to
# -16", "make the clap -12". A verb is required, so a bare "kick to -9" still asks, and positive numbers still ask.
_NEGATIVE = r"(?P<amount>(?:minus\s+|-)\d+(?:\.\d+)?)\s*(?:dbs?)?(?:\s+again)?\s*[.!?]?\s*$"
_VERB_LEVEL = re.compile(rf"^\s*(?:set|put|bring|turn|drop|pull|push|get|take)\s+{_NAME}(?:\s+(?:down|up|back))?\s+(?:to|at)\s+"
                         + _NEGATIVE + rf"|^\s*make\s+{_NAME.replace('name', 'name2')}\s+(?:(?:to|at)\s+)?"
                         + _NEGATIVE.replace("amount", "amount2"), re.I)
_PAN_NEUTRAL = re.compile(rf"^\s*(?:set|put|bring|move)\s+{_NAME}\s+(?:to\s+pan\s+(?:neutral|cent(?:er|re)|middle)|(?:back\s+)?in(?:to)?\s+"
                          r"the\s+(?:cent(?:er|re)|middle)|(?:back\s+)?to\s+(?:the\s+)?(?:cent(?:er|re)|middle))\s*[.!?]?\s*$", re.I)
_SEND_LETTER_AFTER = re.compile(rf"^\s*(?:set\s+)?{_NAME}(?:'s)?\s+send\s+(?P<ret>[ab])\s+(?:to|at)\s+(?P<value>\d+(?:\.\d+)?)\s*"
                                r"(?:%|percent)\s*[.!?]?\s*$", re.I)
_LOCATOR_NOUN = r"(?:loc|locator|marker|mark|cue(?:\s+point)?)"
_LOCATOR_POSITION = (r"(?:\s+(?:(?:right\s+)?here|now|at\s+now|at\s+(?:the\s+|this\s+|current\s+|the\s+current\s+)?"
                     r"(?:head|playhead|spot|point|position|cursor|song\s+position|time)(?:\s+position)?)){0,2}")
_LOCATOR_SAID = re.compile(
    rf"^\s*(?:add|create|set|drop|place|put)\s+(?:a\s+)?(?:new\s+)?{_LOCATOR_NOUN}{_LOCATOR_POSITION}\s*,?\s+"
    r"(?:called|named|name\s+it|with\s+(?:the\s+)?name|label(?:l?ed)?|for)\s+['\"\u2018\u2019]?(?P<locator>[^'\"\u2018\u2019]+?)['\"\u2018\u2019]?"
    + _LOCATOR_POSITION + r"\s*[.!]?\s*$"
    r"|^\s*(?:mark\s+(?:this\s+(?:point|spot|time|position|bit|moment)|now|here)\s+as|marker\s+(?:now|here)\s+(?:for|called))\s+"
    r"['\"\u2018\u2019]?(?P<locator2>[^'\"\u2018\u2019]+?)"
    r"['\"\u2018\u2019]?(?:\s+with\s+a\s+(?:locator|marker))?\s*[.!]?\s*$", re.I)
_CALL_TRACK_THE = re.compile(rf"^\s*call\s+{_NAME}\s+track\s+(?:the\s+)?(?P<new>[\w' -]+?)\s*[.!]?\s*$", re.I)
_MAKE_CALLED = re.compile(rf"^\s*make\s+(?!(?:an?|new|another)\b|(?:midi|audio|return)\b){_NAME}(?:\s+track)?\s+(?:be\s+)?(?:called|named)\s+['\"]?(?P<new>[\w' -]+?)['\"]?\s*[.!]?\s*$",
                          re.I)
_MAKE_SURE_STATE = re.compile(rf"^\s*make\s+sure\s+{_NAME}(?:\s+tracks?)?\s+(?:is|are|'s)\s*(?P<neg>n't\s+|not\s+|un)?"
                              r"(?P<state>muted|soloed|(?:record[\s-]?)?armed)\s*[.!?]?\s*$", re.I)
_PAN_ZERO = re.compile(rf"^\s*(?:set\s+)?(?:the\s+)?pan\s+(?:on|of|for)\s+{_NAME}\s+to\s+(?:zero|0)\s*[.!?]?\s*$"
                       rf"|^\s*pan\s+{_NAME.replace('name', 'name2')}\s+to\s+(?:zero|0)\s*[.!?]?\s*$", re.I)
# "i want the drums bus to be -10 dB" names the level it wants; the polite-lead rule only strips "i want (you) to".
_WANT_LEVEL = re.compile(rf"^\s*(?:i\s+(?:want|need|would\s+like|'d\s+like)|let'?s\s+(?:have|get))\s+{_NAME}\s+(?:to\s+be|at)\s+"
                         r"(?P<amount>(?:minus\s+|-)?\d+(?:\.\d+)?)\s*dbs?\s*[.!?]?\s*$", re.I)
# "set the send for a reverb to fifty percent on the drum bus": return first, value, then the track.
_SEND_TRACK_LAST = re.compile(r"^\s*set\s+(?:the\s+)?(?:send\s+(?:for|to)\s+(?:the\s+|a\s+)?(?P<ret>[ab]-(?:reverb|delay)|reverb|verb|delay|[ab])"
                              r"|(?P<ret2>[ab]-(?:reverb|delay)|reverb|verb|delay)\s+send)\s+(?:to|at)\s+(?P<value>\d+(?:\.\d+)?)\s*(?:%|percent)\s+"
                              rf"(?:on|for)\s+{_NAME}\s*[.!?]?\s*$", re.I)
# Whole polite sentences from beginners (third blind set): "I need the bass track to be at -17 dB. Can you adjust
# that?", "move the kick all the way to the right", "I want the clap track to send 30% of its signal to B-Delay".
_ASK_TAIL = re.compile(r"\s*[.,!]?\s+(?:can|could|would|will)\s+(?:you|u)\s+(?:please\s+)?(?:do|adjust|set|change|fix|make|"
                       r"help(?:\s+me)?(?:\s+with)?)\s+(?:that|it|this)(?:\s+for\s+me)?\s*[?.!]*\s*$", re.I)
_STATE_LEVEL = re.compile(rf"^\s*(?:(?:i\s+(?:want|need|would\s+like|'d\s+like)\s+)?{_NAME}(?:\s+track)?\s+(?:to\s+be|should\s+be)"
                          rf"|make\s+sure\s+{_NAME.replace('name', 'name2')}(?:\s+track)?\s+is)\s+(?:at\s+)?"
                          r"(?P<amount>(?:minus\s+|-)?\d+(?:\.\d+)?)\s*dbs?(?:\s+exactly)?\s*[.!?]?\s*$", re.I)
_FAR_PAN = re.compile(rf"^\s*(?:move|pan|put|push)\s+{_NAME}(?:\s+track)?\s+(?:all\s+the\s+way\s+(?:to\s+the\s+|over\s+)?|"
                      r"(?:to\s+the\s+)?far\s+|(?:to\s+the\s+)?hard\s+)(?P<side>left|right)(?:\s+of\s+the\s+stereo\s+(?:field|image))?"
                      r"\s*[.!?]?\s*$", re.I)
_STATE_CENTRE = re.compile(rf"^\s*(?:i\s+(?:want|need|would\s+like|'d\s+like)\s+)?{_NAME}(?:\s+track)?\s+(?:to\s+be|should\s+be)\s+"
                           r"(?:perfectly\s+|back\s+in\s+the\s+)?(?:cent(?:er|re)(?:e?d)?|middle)(?:\s+again)?\s*[.!?]?\s*$", re.I)
_STATE_SEND = re.compile(rf"^\s*(?:i\s+(?:want|need|think|would\s+like|'d\s+like)\s+)?{_NAME}(?:\s+track)?\s+(?:should\s+|to\s+)send\s+"
                         r"(?P<value>\d+(?:\.\d+)?)\s*(?:%|percent)(?:\s+of\s+(?:its|the)\s+signal)?\s+to\s+(?:the\s+)?"
                         r"(?P<ret>[ab]-(?:reverb|delay)|reverb|delay)\s*[.!?]?\s*$", re.I)
_THRESHOLD_ON_COMPRESSOR = re.compile(rf"^\s*(?:change|adjust|move|set)\s+the\s+threshold\s+on\s+the\s+compressor\s+(?:for|of|on)\s+"
                                      rf"{_NAME}\s+by\s+(?P<sign>[-+])?(?P<change>\d+(?:\.\d+)?)\s*dbs?"
                                      r"(?:\s+(?P<direction>up|down))?\s*[.!?]?\s*$", re.I)
_NEW_TRACK_PURPOSE = re.compile(r"^(?P<head>\s*(?:create|make|add)\s+(?:a\s+)?new\s+(?:midi|audio|return)\s+track)\s+for\s+"
                                r"(?:me|(?:a|an|my|the|some)\s+[\w' -]+?)(?=\s+(?:called|named)\b|\s*[.!?]?\s*$)", re.I)
_GO_TO_TRACK_WITH = re.compile(r"^\s*(?:go\s+to|take\s+me\s+to|show\s+me|select|jump\s+to)\s+the\s+track\s+(?:that\s+has|that's\s+got|"
                               r"with|where)\s+(?:the\s+)?(?P<phrase>[\w' /-]+?)(?:\s+(?:is|are|on\s+it))?(?:\s+so\s+i\s+can\s+[\w ]+)?"
                               r"\s*[.!?]?\s*$", re.I)
# Beginners add a reason and ask for permission: "lower the snare by 2 dB to make it sit behind the kick, is that
# okay?". The reason named another track and KENN lowered the Kick; "mute the snare to focus on the hi-hats" muted the
# hats. The request is what comes before the reason (fifth blind set, 26 Sept).
_OKAY_TAIL = re.compile(r"\s*[,.;!]?\s*(?:is\s+that\s+(?:okay|ok|alright|all\s+right|possible|acceptable|correct|fine)|"
                        r"(?:could|can|would)\s+you\s+handle\s+that|would\s+that\s+work|does\s+that\s+make\s+sense)\s*[?.!]*\s*$", re.I)
_REASON_TAIL = re.compile(r"\s*,?\s+(?:so\s+(?:that\s+)?(?:it|they|its|the|i|we|there)\b|to\s+(?:make|give|help|add|keep|let|focus|"
                          r"check|ensure|match|balance|create|avoid|stop|bring|reduce|tame|clean|control|even|shape|cut|get)\b|"
                          r"for\s+(?:better|more|clarity|a\s+(?:more|better|cleaner|clearer|tighter)|some|the\s+sake)\b|because\b|"
                          r"since\b|in\s+order\s+to\b).*$", re.I)
_REQUEST_LEAD_END = re.compile(r"\b(?:want|need|like|love|going|trying|have|wish|able|ready|possible|mind|way|how)\s*$", re.I)
# "a bit louder, maybe -13 dB" names where it should end up. It used to be read as +13 dB.
_HEDGED_TARGET = re.compile(r"\b(?:(?:a\s+(?:bit|little|touch)|slightly|a\s+little\s+bit)\s+)?(?:louder|quieter|softer|lower|higher|"
                            r"up|down)\s*,?\s*(?:maybe|like|around|about|say|to)\s+(?P<amount>-\d+(?:\.\d+)?)\s*dbs?\b", re.I)
# "I want to solo the synth track. Can you go there?" soloed it; the question is where the request is.
_GO_THERE = re.compile(r"^(?P<first>.+?)[.!]\s*(?:can|could|would)\s+you\s+(?:please\s+)?(?:go\s+there|take\s+me\s+there|"
                       r"show\s+me\s+(?:that|the\s+(?P<shown>[\w' /-]+?))\s+track|select\s+it)\s*[?.!]*\s*$", re.I)
_COMPRESSOR_TO_THRESHOLD = re.compile(rf"^\s*set\s+(?:the\s+)?compressor\s+on\s+{_NAME}\s+to\s+threshold\s+(?:of\s+)?"
                                      r"(?P<amount>-?\d+(?:\.\d+)?)\s*(?:dbs?)?\s*[.!?]?\s*$", re.I)
_COMP_SETTING = re.compile(r"\b(?:threshold|ratio|attack|release|output|makeup|knee)\b", re.I)


# "snare reverb send 30%", "set the synth's delay send to 15%", "send A on the synth to 20%": the send said the
# producer's way round, rewritten into "send the snare to the reverb at 30%", which the send rules check against
# the set's return tracks.
_SEND_SAID_TRACK_FIRST = re.compile(
    r"^\s*(?:(?:set|put|make)\s+)?(?:the\s+)?(?P<name>[\w/&-]+(?:\s+[\w/&-]+){0,3}?)(?:'s)?\s+"
    r"(?P<ret>reverb|verb|delay|return\s+[ab]|[ab])\s+send\s+(?:(?:to|at)\s+)?(?P<value>\d+(?:\.\d+)?)\s*(?:%|percent)\s*[.!]?\s*$",
    re.I)
_SEND_SAID_LETTER_FIRST = re.compile(
    r"^\s*(?:set\s+)?send\s+(?P<ret>[ab])\s+on\s+(?:the\s+)?(?P<name>[\w/&-]+(?:\s+[\w/&-]+){0,3}?)\s+(?:to|at)\s+"
    r"(?P<value>\d+(?:\.\d+)?)\s*(?:%|percent)\s*[.!]?\s*$", re.I)


# "put 40% of the bass on reverb", "add 25% of the drums bus to delay", "make the vox go to a-reverb at 50%".
_SEND_SAID_PORTION = re.compile(
    r"^\s*(?:(?:can|could)\s+you\s+)?(?:put|add|send|give)\s+(?P<value>\d+(?:\.\d+)?)\s*(?:%|percent)\s+of\s+(?:the\s+)?"
    r"(?P<name>[\w/&-]+(?:\s+[\w/&-]+){0,3}?)\s+(?:on|to|into)\s+(?:the\s+)?(?P<ret>[\w-]+(?:\s+[\w-]+)?)\s*[.!?]?\s*$", re.I)
_SEND_SAID_AMOUNT_FIRST = re.compile(
    r"^\s*(?:put|send|add)\s+(?P<value>\d+(?:\.\d+)?)\s*(?:%|percent)?\s+(?:on|to|into)\s+(?:the\s+)?(?P<ret>reverb|verb|delay)\s+"
    r"(?:for|on|from)\s+(?:the\s+)?(?P<name>[\w/&-]+(?:\s+[\w/&-]+){0,3}?)\s*[.!?]?\s*$"
    r"|^\s*(?P<ret2>reverb|verb|delay)\s+(?P<value2>\d+(?:\.\d+)?)\s*(?:%|percent)?\s+on\s+(?:the\s+)?"
    r"(?P<name2>[\w/&-]+(?:\s+[\w/&-]+){0,3}?)\s*[.!?]?\s*$", re.I)
# "send the synth to A-Reverb 30 percent": the amount without "at".
_SEND_NO_AT = re.compile(
    r"^\s*(?:(?:can|could)\s+you\s+)?send\s+(?:the\s+)?(?P<name>[\w/&-]+(?:\s+[\w/&-]+){0,3}?)\s+to\s+(?:the\s+)?"
    r"(?P<ret>[\w-]+(?:\s+(?!at\b)[\w-]+)?)\s+(?P<value>\d+(?:\.\d+)?)\s*(?:%|percent)\s*[.!?]?\s*$", re.I)
_SEND_SAID_GO_TO = re.compile(
    r"^\s*make\s+(?:the\s+)?(?P<name>[\w/&-]+(?:\s+[\w/&-]+){0,3}?)\s+go\s+to\s+(?:the\s+)?(?P<ret>[\w-]+(?:\s+[\w-]+)?)\s+"
    r"at\s+(?P<value>\d+(?:\.\d+)?)\s*(?:%|percent)\s*[.!?]?\s*$", re.I)


# Speech-to-text spells units and signs out: "minus ten dee bee". A signed spoken number is always a number, so it
# becomes digits even with no unit after it ("turn the snare down to minus fifteen"); unsigned ones still need a unit.
_SPOKEN_DB = re.compile(r"\bdee[\s-]*bees?\b|\bd\s+b\b", re.I)
_SIGNED_SPOKEN_NUMBER = re.compile(
    r"\b(?:minus|negative)\s+(?P<first>" + "|".join(_SPOKEN_NUMBER_VALUES) + r")\b"
    r"(?:\s+(?P<second>" + "|".join(_SPOKEN_NUMBER_VALUES) + r")\b)?", re.I)


# Wording carried over from Logic and FL Studio: names in quotes ("the 'Kick' track"), a return called a bus or aux
# ("the 'A-Reverb' bus"), and a send "with 50%".
# Quotes after "named"/"called"/"as" mark where a new locator name ends, so those stay.
_QUOTED_NAME = re.compile(r"(?<!named )(?<!called )(?<!as )(?<![\w'])'(?P<name>[^']+?)'(?![\w'])", re.I)
_RETURN_AS_BUS = re.compile(r"\b(?P<ret>[ab]-(?:reverb|delay)|reverb|delay)\s+(?:bus|aux)\b", re.I)
_SEND_WITH_AMOUNT = re.compile(r"^(?P<head>\s*send\b.+?)\s+with\s+(?P<value>\d+(?:\.\d+)?\s*(?:%|percent))", re.I)


def _rewrite_other_daw(text: str) -> str:
    text = _QUOTED_NAME.sub(lambda m: m.group("name"), text)
    text = _RETURN_AS_BUS.sub(lambda m: m.group("ret"), text)
    return _SEND_WITH_AMOUNT.sub(lambda m: f"{m.group('head')} at {m.group('value')}", text)


def _rewrite_dictation(text: str) -> str:
    text = _SPOKEN_DB.sub("dB", text)

    def signed(match: re.Match[str]) -> str:
        first = _SPOKEN_NUMBER_VALUES[match.group("first").lower()]
        second = _SPOKEN_NUMBER_VALUES[match.group("second").lower()] if match.group("second") else 0
        if second and not (first >= 20 and second < 10):
            return f"-{first} {match.group('second')}"  # "minus ten five" isn't one number; leave the second word
        return f"-{first + second}"

    # Numbers with a unit after them are converted later too; doing it here lets the idiom rules below see digits.
    return _normalize_spoken_numbers(_SIGNED_SPOKEN_NUMBER.sub(signed, text))


def _rewrite_idioms(text: str) -> str:
    if _HOW_TO_QUESTION.match(text):
        return text
    if (m := _GO_THERE.match(text)):
        shown = m.group("shown") or next(iter(re.findall(r"\bthe\s+([\w' /-]+?)\s+track\b", m.group("first"), re.I)), None)
        if shown:
            return f"go to the {shown}"
    text = _ASK_TAIL.sub("", _TRAILING_ASIDE.sub("", _POLITE_TAIL.sub("", _OKAY_TAIL.sub("", text))))
    text = _STATE_REASON_TAIL.sub("", text) or text
    unreasoned = _REASON_TAIL.sub("", text)
    # "I want to reduce the kick by 4 dB": that "to" starts the request, not a reason.
    if len(unreasoned.split()) >= 2 and not _REQUEST_LEAD_END.search(unreasoned):
        text = unreasoned
    text = _HEDGED_TARGET.sub(lambda m: f"at {m.group('amount')} dB", text)
    if (m := _PROBLEM_THEN_IT.match(text)) and re.search(r"\bit\b", m.group("rest"), re.I) \
            and not _NOT_A_TRACK_NAME.search(m.group("name")):
        named = re.sub(r"^the\s+", "the ", m.group("name"), flags=re.I)  # "The clap" mid-sentence didn't resolve
        text = re.sub(r"\bit\b", named, m.group("rest"), count=1, flags=re.I)
    polite = _POLITE_LEAD.match(text)
    text = _POLITE_LEAD.sub("", text)
    if polite:
        text = text.rstrip(" ?")  # "can you solo the hats?" is a request, not a question
    if _COMP_SETTING.search(text):
        # "comp" is also a comped take; only next to a compressor setting is it the Compressor.
        text = re.sub(r"\bcomp\b", "compressor", text, flags=re.I)
    text = _A_DB.sub(lambda m: "0.5 dB" if m.group("half") else "1 dB", text)

    def name(match: re.Match[str], group: str = "name") -> str | None:
        found = match.group(group)
        return None if not found or _NOT_A_TRACK_NAME.search(found) or _TERSE_LEVEL_EXCLUDE.search(found) else found

    if (m := _TRANSPORT_IT.search(text)):
        return "stop" if m.group("verb").lower() in {"stop", "halt"} else "play"
    if (m := _SHOULD_BE_CALLED.match(text)) and name(m):
        return f"rename {m.group('name')} to {m.group('new').strip()}"
    if (m := _MOVE_TO_SIDE.match(text)) and name(m):
        return f"pan {m.group('name')} {m.group('side').lower()}"
    if (m := _LOCATOR_SAID.match(text)):
        return f"add a locator called {(m.group('locator') or m.group('locator2')).strip()}"
    if (m := _CALL_TRACK_THE.match(text) or _MAKE_CALLED.match(text)) and name(m):
        return f"rename {m.group('name')} to {m.group('new')}"
    if (m := _WANTED_STATE.match(text)) and name(m) and not m.group("neg") and \
            m.group("state").lower().startswith(("cent", "back")):
        return f"centre {m.group('name')}"
    if (m := _MAKE_SURE_STATE.match(text) or _WANTED_STATE.match(text)) and name(m) \
            and not m.group("state").lower().startswith(("cent", "back")):
        verb = {"muted": "mute", "soloed": "solo"}.get(m.group("state").lower(), "arm")
        if m.group("neg"):
            verb = "disarm" if verb == "arm" else f"un{verb}"
        return f"{verb} {m.group('name')}"
    if (m := _VAGUE_LEVEL_VERB.match(text)) and name(m) and not re.search(r"\d", text):  # "lower synth 3" has an amount
        up = m.group("verb").lower() in {"raise", "boost", "increase", "lift"}
        return f"turn {m.group('name')} {'up' if up else 'down'}{m.group('vague') or ''}"
    if (m := _PAN_ZERO.match(text)):
        group = "name" if m.group("name") else "name2"
        if name(m, group):
            return f"centre {m.group(group)}"
    if (m := _STATE_LEVEL.match(text)):
        group = "name" if m.group("name") else "name2"
        if name(m, group):
            return f"set {m.group(group)} to {m.group('amount')} dB"
    if (m := _FAR_PAN.match(text)) and name(m):
        return f"pan {m.group('name')} hard {m.group('side').lower()}"
    if (m := _STATE_CENTRE.match(text)) and name(m):
        return f"centre {m.group('name')}"
    if (m := _STATE_SEND.match(text)) and name(m) and float(m.group("value")) <= 100:
        ret = m.group("ret").lower().split("-")[-1]
        return f"send the {m.group('name')} to the {ret} at {m.group('value')}%"
    if (m := _THRESHOLD_ON_COMPRESSOR.match(text)) and name(m) and (m.group("sign") or m.group("direction")):
        down = m.group("sign") == "-" or (m.group("direction") or "").lower() == "down"
        return f"{'lower' if down else 'raise'} the {m.group('name')} compressor threshold by {m.group('change')} dB"
    if (m := _NEW_TRACK_PURPOSE.match(text)):
        return m.group("head") + text[m.end():]
    if (m := _GO_TO_TRACK_WITH.match(text)):
        return f"go to the {m.group('phrase')}"
    if (m := _WANT_LEVEL.match(text)) and name(m):
        return f"set {m.group('name')} to {m.group('amount')} dB"
    if (m := _SEND_TRACK_LAST.match(text)) and name(m) and float(m.group("value")) <= 100:
        ret = (m.group("ret") or m.group("ret2")).lower().split("-")[-1]
        return f"send the {m.group('name')} to the {'reverb' if ret == 'verb' else ret} at {m.group('value')}%"
    if (m := _COMPRESSOR_TO_THRESHOLD.match(text)):
        return f"set the compressor threshold on {m.group('name')} to {m.group('amount')} dB"
    if (m := _VERB_LEVEL.match(text)):
        group = "name" if m.group("name") else "name2"
        if name(m, group):
            return f"set {m.group(group)} to {m.group('amount' if group == 'name' else 'amount2')} dB"
    if (m := _PAN_NEUTRAL.match(text)) and name(m):
        return f"centre {m.group('name')}"
    if (m := _SEND_LETTER_AFTER.match(text)) and name(m):
        return f"send the {m.group('name')} to the {m.group('ret').lower()} at {m.group('value')}%"
    if (m := _SEND_SAID_AMOUNT_FIRST.match(text)):
        group = "name" if m.group("name") else "name2"
        if name(m, group):
            ret = (m.group("ret") or m.group("ret2")).lower()
            value = m.group("value") or m.group("value2")
            if float(value) <= 100:
                return f"send the {m.group(group)} to the {'reverb' if ret == 'verb' else ret} at {value}%"
    if (m := _SEND_SAID_PORTION.match(text) or _SEND_SAID_GO_TO.match(text) or _SEND_NO_AT.match(text)) and name(m):
        return f"send the {m.group('name')} to the {m.group('ret')} at {m.group('value')}%"
    if (m := _SEND_SAID_TRACK_FIRST.match(text) or _SEND_SAID_LETTER_FIRST.match(text)) and name(m):
        ret = m.group("ret").lower().replace("return ", "")
        ret = "reverb" if ret == "verb" else ret
        return f"send the {m.group('name')} to the {ret} at {m.group('value')}%"
    if (m := _SIGNED_CHANGE.match(text)):
        if m.group("name") and name(m):
            return f"turn {m.group('name')} {'up' if m.group('sign') == '+' else 'down'} {m.group('amount')} dB"
        # "vocal +2 dB" is a change; "set the kick to +3 dB" / "put the kick at +3 dB" is a level above 0 dB, and
        # used to come out as "turn the kick up 3 dB" (26 Sept 2026).
        if m.group("name2") and name(m, "name2"):
            if re.search(r"\b(?:to|at)\s*$", m.group("name2"), re.I):
                return f"{m.group('name2')} {m.group('amount2')} dB"
            return f"turn {m.group('name2')} up {m.group('amount2')} dB"
    if (m := _UNITLESS_CHANGE.match(text)):
        if m.group("name") and name(m):
            return f"turn {m.group('name')} {m.group('direction')} {m.group('amount')} dB"
        if m.group("name2") and name(m, "name2"):
            up = m.group("verb").lower() in {"raise", "boost", "up"}
            return f"turn {m.group('name2')} {'up' if up else 'down'} {m.group('amount2')} dB"
    if (m := _HARD_PAN_ON.match(text)) and name(m):
        return f"pan {m.group('name')} hard {m.group('side').lower()}"
    if (m := _VOL_ON.match(text)) and name(m):
        return f"set {m.group('name')} to {m.group('amount')} dB"
    if (m := _TERSE_THRESHOLD.match(text)):
        track = m.group("name") or m.group("name2")
        # "set the compressor threshold to -10 dB" took "the" as the track and came out "set the the compressor...".
        if track and not _NOT_A_TRACK_NAME.search(track) and track.casefold() not in {"the", "a", "my", "this", "that"}:
            if m.group("direction"):
                verb = "raise" if m.group("direction").lower() == "up" else "lower"
                return f"{verb} the {track} compressor threshold by {m.group('change')} dB"
            return f"set the {track} compressor threshold to {m.group('amount')} dB"
    if (m := _UNITLESS_LEVEL.match(text)) and name(m):
        return f"set {m.group('name')} to {m.group('amount')} dB"
    if (m := _BARE_PAN.match(text)) and name(m):
        return f"pan {m.group('name')} {m.group('amount')}% {m.group('side').lower()}"
    if (m := _LR_PAN.match(text)) and name(m):
        return f"pan {m.group('name')} {m.group('amount')}% {'left' if m.group('side').lower() == 'l' else 'right'}"
    if (m := _CENTRE_PAN.match(text)):
        if m.group("verb"):
            return re.sub(r"^\s*re-?", "", text)  # "re-centre the bass" is "centre the bass"
        if name(m):
            return f"centre {m.group('name')}"
    if (m := _MUTE_IDIOM.match(text)):
        found = next((g for g in ("name", "name2", "name3") if m.group(g)), None)
        if found and name(m, found):
            return f"mute {m.group(found)}"
    if (m := _UNMUTE_IDIOM.match(text)) and name(m):
        return f"unmute {m.group('name')}"
    return text


def _rewrite_common_phrasings(text: str) -> str:
    """Put a few everyday phrasings into forms the rules below already parse.

    "the second channel" -> "track 2"; a correction ("no wait, mute the snare
    not the hats") keeps only the new instruction; "call track 8 Sweeps" is a
    rename; "kick to -12 dB" is "set kick to -12 dB" (only with the unit said:
    a bare "kick to -9" still asks). Nothing here changes what a request means.
    """
    text = _ORDINAL_CHANNEL.sub(lambda m: f"track {_ORDINALS[m.group(1).lower()]}", text)
    text = _ORDINAL_SCENE.sub(lambda m: f"scene {_ORDINALS[m.group(1).lower()]}", text)
    if (m := _INSTEAD_OF.match(text)):
        after = m.group("after")
        obj = _INSTEAD_OBJECT.match(m.group("before"))
        if obj and re.search(r"\b(?:it|that)\b", after, re.I):
            after = re.sub(r"\b(?:it|that)\b", obj.group("obj"), after, count=1, flags=re.I)
        text = after
    if re.search(r"\bratio\b", text, re.I):
        # "ratio to 3 to 1" became a raw value of 3 and a range error.
        text = re.sub(r"\b(\d+(?:\.\d+)?)\s+(?:to|in)\s+(?:1|one)\b", r"\1:1", text, flags=re.I)
    if (m := _MID_CORRECTION.match(text)):
        after = m.group("after")
        obj = _CORRECTED_OBJECT.match(m.group("before"))
        if obj and re.search(r"\b(?:it|that)\b", after, re.I):
            after = re.sub(r"\b(?:it|that)\b", obj.group("obj"), after, count=1, flags=re.I)
        text = after
    elif (m := _MID_CORRECTION_TARGET.match(text)) and (obj := _CORRECTED_OBJECT.match(m.group("before"))):
        before = m.group("before")
        text = before[:obj.start("obj")] + m.group("target") + before[obj.end("obj"):]
    text = _rewrite_dictation(_rewrite_other_daw(text))
    text = _rewrite_idioms(text)
    corrected = _CORRECTION_LEAD.sub("", text)
    if corrected != text:
        text = _CORRECTION_TAIL.sub("", corrected)
    text = re.sub(r"\b((?:re)?name\b.*?\bto)\s+just\s+", r"\1 ", text, flags=re.I)
    call = _CALL_TRACK.match(text)
    if call:
        text = f"rename {call.group(1)} to {call.group(2)}"
    level = _TERSE_LEVEL.match(text)
    if level and not _TERSE_LEVEL_EXCLUDE.search(level.group("name")):
        text = f"set {level.group('name')} to {level.group('amount')} dB"  # "kick to -12 dB": an absolute level
    return text


# Typed in a hurry, from the phone-shorthand phrasing set (27 Sept 2026): "kik -3", "snar up a hair",
# "teh bus comp thresh -10", "hats 20 left", "verb on the snare". Each rule turns one shape into the full request the
# rules below already parse, and only when the words left over name a track in the set.
_SHORTHAND_TYPOS = (
    (re.compile(r"\bkik\b", re.I), "kick"),
    (re.compile(r"\bsnar\b", re.I), "snare"),
    (re.compile(r"\bteh\b", re.I), "the"),
    (re.compile(r"\bthresh\b", re.I), "threshold"),
)
_SHORT_WORD_BEFORE_BUS = {"drum", "drums", "reverb", "delay", "fx", "mix", "master", "group", "vocal", "vocals", "vox",
                          "synth", "bass", "music", "parallel", "aux"}
_SHORT_COMP_SETTING = re.compile(
    r"^\s*(?:(?P<pre>[\w/'&-]+(?:\s+[\w/'&-]+){0,2}?)\s+)?(?:comp|compressor)\s+"
    r"(?P<param>threshold|ratio|attack|release|makeup|output|knee)\s+(?P<value>[-+]?\d+(?:\.\d+)?)\s*(?P<unit>dbs?|ms|:1)?"
    r"(?:\s+on\s+(?:the\s+)?(?P<post>[\w/'&-]+(?:\s+[\w/'&-]+){0,2}?))?\s*[.!]?\s*$", re.I)
_SHORT_DEVICE_SWITCH = re.compile(
    r"^\s*(?P<name>[\w/'&-]+(?:\s+[\w/'&-]+){0,2}?)\s+(?P<device>comp|compressor|eq|eq\s*eight|saturator)\s+(?P<state>on|off)"
    r"\s*[.!]?\s*$|^\s*turn\s+(?P<state2>on|off)\s+the\s+comp\b", re.I)
_SHORT_LEVEL = re.compile(r"^\s*(?P<name>[\w/'&-]+(?:\s+[\w/'&-]+){0,2}?)\s+(?P<amount>[-+]\d+(?:\.\d+)?)\s*(?:dbs?)?\s*[.!]?\s*$",
                          re.I)
_SHORT_EQ = re.compile(
    r"^\s*(?:set\s+)?(?P<name>[\w/'&-]+(?:\s+[\w/'&-]+){0,2}?)\s+eq\s+(?:(?P<verb>boost|cut)\s+(?P<freq>\d+(?:\.\d+)?)\s*(?P<unit>k?hz)"
    r"|(?P<freq2>\d+(?:\.\d+)?)\s*(?P<unit2>k?hz)\s+(?P<verb2>boost|cut))(?:\s+(?:by\s+)?(?P<amount>\d+(?:\.\d+)?)\s*dbs?)?"
    r"\s*[.!]?\s*$", re.I)
_SHORT_FX_ON = re.compile(r"^\s*(?P<fx>reverb|verb|delay)\s+on\s+(?:the\s+)?(?P<name>[\w/'&-]+(?:\s+[\w/'&-]+){0,2}?)\s*[.!]?\s*$", re.I)
_SHORT_PANNED = re.compile(r"^\s*(?P<name>[\w/'&-]+(?:\s+[\w/'&-]+){0,2}?)\s+panned\s+(?P<side>left|right)\s*[.!]?\s*$", re.I)
_SHORT_VAGUE_LEVEL = re.compile(r"^\s*(?P<name>[\w/'&-]+(?:\s+[\w/'&-]+){0,2}?)\s+(?P<vague>a\s+(?:bit|little|touch|hair)\s+|slightly\s+)?"
                                r"(?P<dir>lower|quieter|softer|louder|higher)\s*[.!]?\s*$", re.I)
_SHORT_INSERT_ON = re.compile(r"^\s*(?:an?\s+)?(?P<device>saturator|auto\s+filter|glue\s+compressor|compressor|eq\s*eight|roar)\s+on\s+"
                              r"(?:the\s+)?(?P<name>[\w/'&-]+(?:\s+[\w/'&-]+){0,2}?)\s*[.!]?\s*$", re.I)
_SHORT_EQ_SETTING = re.compile(r"^\s*(?P<name>[\w/'&-]+(?:\s+[\w/'&-]+){0,2}?)\s+eq\s+(?P<param>low\s+cut|high\s+cut|low|mid|high)\s+"
                               r"(?P<value>[-+]?\d+(?:\.\d+)?)\s*(?P<unit>k?hz|dbs?)?\s*[.!]?\s*$", re.I)
_LIVE_PAN = re.compile(r"(?<![\w.])(?P<n>\d{1,2})\s*(?P<side>[lr])\b", re.I)


_DEVICE_SETTING_NO_TRACK = re.compile(r"^\s*set\s+the\s+(?P<device>compressor|eq(?:\s*eight)?)\s+"
                                      r"(?:threshold|ratio|attack|release|makeup|output|knee)\s+to\s+\S+", re.I)
# "delay 30%", "verb up a hair", "delay send to b": the send said with no track at all.
_SEND_NO_TRACK = re.compile(r"^\s*(?:the\s+)?(?P<fx>reverb|verb|delay)(?:\s+send)?\s+(?:(?:[-+]?\d|up\b|down\b|to\s+[ab]\b)"
                            r"(?!.*\b(?:on|for)\b)|on\s*[.!]?\s*$)", re.I)
# "turn the delay send on the bass down 5 dB", "lead vocal reverb send up": a nudge to a named track's send.
_SEND_NUDGE = re.compile(r"\b(?P<fx>reverb|verb|delay)\s+send\b(?=.*\b(?:up|down)\b)(?!.*\d\s*%)", re.I)
_EQ_CUT_NO_AMOUNT = re.compile(r"^\s*(?:boost|cut)\s+\d+(?:\.\d+)?\s*k?hz\s+on\s+(?:the\s+)?[\w/'&-]+(?:\s+[\w/'&-]+){0,2}\s*$",
                               re.I)


def _rewrite_shorthand(text: str, tracks: list[dict[str, Any]]) -> str:
    if not re.search(r"\b(?:named|called|rename|name)\b", text, re.I):  # a new name is spelled as the user wants it
        for pattern, word in _SHORTHAND_TYPOS:
            text = pattern.sub(word, text)
    if re.search(r"\bpan\b|\bleft\b|\bright\b|\d\s*[lr]\s*$", text, re.I):
        # Live's panner reads 50L to 50R, so "20L" as Live shows it is 40% left.
        text = _LIVE_PAN.sub(lambda m: f"{int(m.group('n')) * 2}% {'left' if m.group('side').lower() == 'l' else 'right'}"
                             if int(m.group("n")) <= 50 else m.group(0), text)

    def is_track(name: str | None) -> bool:
        # "the kick is lower" describes the mix; only a bare track name before the shorthand is a request.
        return (bool(name) and not _TERSE_LEVEL_EXCLUDE.search(name)
                and not re.search(r"\b(?:is|was|are|were|sounds?|feels?|seems?|looks?|i|we|it|still|too)\b|'s\b", name, re.I)
                and _find_track(name, tracks)[0] is not None)

    buses = [t for t in tracks if "bus" in re.split(r"[\s/_-]+", str(t.get("name", "")).casefold())]
    if len(buses) == 1:
        # "mute the bus", "bus comp on": one track in the set is a bus, so that's the one meant.
        bus_name = str(buses[0].get("name"))

        def one_bus(match: re.Match[str]) -> str:
            before = text[:match.start()].split()
            if before and before[-1].casefold() in _SHORT_WORD_BEFORE_BUS:
                return match.group(0)
            return f"the {bus_name}"

        if bus_name.casefold() not in text.casefold():
            text = re.sub(r"\b(?:the\s+)?bus\b", one_bus, text, flags=re.I)
    if (m := _SHORT_COMP_SETTING.match(text)) and (not (m.group("pre") or m.group("post"))
                                                   or is_track(m.group("pre") or m.group("post"))):
        target = m.group("pre") or m.group("post")
        unit = (m.group("unit") or {"threshold": "dB", "makeup": "dB", "output": "dB", "knee": "dB", "ratio": ":1",
                                    "attack": "ms", "release": "ms"}[m.group("param").lower()])
        unit = unit if unit == ":1" else f" {unit}"
        where = f" on the {target}" if target else ""
        return f"set the compressor {m.group('param').lower()}{where} to {m.group('value')}{unit}"
    if (m := _SHORT_DEVICE_SWITCH.match(text)):
        if m.group("state2"):
            return re.sub(r"\bcomp\b", "compressor", text, count=1, flags=re.I)
        if is_track(m.group("name")):
            device = "compressor" if m.group("device").lower().startswith("comp") else m.group("device")
            return f"turn {m.group('state').lower()} the {device} on the {m.group('name')}"
    if (m := _SHORT_EQ.match(text)) and is_track(m.group("name")):
        verb = (m.group("verb") or m.group("verb2")).lower()
        freq, unit = m.group("freq") or m.group("freq2"), (m.group("unit") or m.group("unit2")).lower()
        amount = f" by {m.group('amount')} dB" if m.group("amount") else ""
        return f"{verb} {freq} {'kHz' if unit == 'khz' else 'Hz'} on the {m.group('name')}{amount}"
    if (m := _SHORT_VAGUE_LEVEL.match(text)) and is_track(m.group("name")):
        up = m.group("dir").lower() in {"louder", "higher"}
        return f"turn {m.group('name')} {'up' if up else 'down'} {(m.group('vague') or '').strip()}".rstrip()
    if (m := _SHORT_INSERT_ON.match(text)) and is_track(m.group("name")):
        return f"add {m.group('device')} to the {m.group('name')}"
    if (m := _SHORT_EQ_SETTING.match(text)) and is_track(m.group("name")):
        unit = {"hz": " Hz", "khz": " kHz"}.get((m.group("unit") or "").lower(), " dB" if m.group("unit") else "")
        return f"set the eq eight {m.group('param').lower()} on the {m.group('name')} to {m.group('value')}{unit}"
    if (m := _SHORT_FX_ON.match(text)) and is_track(m.group("name")):
        return f"send the {m.group('name')} to the {'delay' if m.group('fx').lower() == 'delay' else 'reverb'}"
    if (m := _SHORT_PANNED.match(text)) and is_track(m.group("name")):
        return f"pan {m.group('name')} {m.group('side').lower()}"
    if (m := _SHORT_LEVEL.match(text)) and is_track(m.group("name")):
        return f"{m.group('name')} {m.group('amount')} dB"  # asks whether that's a level or a change
    return text


# Song tempo (27 Sept 2026). The word tempo or BPM has to be there: "set the kick to 124" is not a tempo, and a
# clip's warp or a delay synced "to 120 BPM" belongs to that clip or device, not the song.
_TEMPO_WORD = re.compile(r"\b(?:tempo|bpm)\b", re.I)
_TEMPO_NOT_SONG = re.compile(r"\b(?:clip|sample|samples|warp|warped|stretch|loop|delay|echo|lfo|arp|sync|synced|note|notes|"
                             r"track's|genre|techno|house|dnb|hip\s*hop|song\s+ideas?|generate|make\s+(?:a|me)\s)\b", re.I)
_TEMPO_ABSOLUTE = re.compile(
    r"^\s*(?:(?:set|change|put|make|bring|take|move|switch|go|drop|raise|lower|speed\s+up|slow\s+down)\s+)?"
    r"(?:(?:the|my|our|this)\s+)?(?:(?:song|project|set|session|global)\s+)?(?:tempo|bpm)?\s*(?:of\s+(?:the\s+)?(?:song|project|set)\s+)?"
    r"(?:(?:up|down)\s+)?(?:to|at|=)?\s*(?P<bpm>\d{1,4}(?:\.\d+)?)\s*(?:bpm)?\s*[.!]?\s*$", re.I)
_TEMPO_RELATIVE = re.compile(
    r"^\s*(?:(?P<verb>raise|increase|bump|push|lift|speed(?:\s+up)?|lower|decrease|drop|reduce|slow(?:\s+down)?|nudge|take|bring|"
    r"turn|move|put)\s+)?(?:(?:the|my|our|this)\s+)?(?:(?:song|project|set)\s+)?(?:tempo|bpm)\s+"
    r"(?:(?P<dir>up|down)\s+)?(?:by\s+)?(?P<amount>\d{1,3}(?:\.\d+)?)\s*(?:bpm)?(?:\s+(?P<dir2>up|down|faster|slower))?\s*[.!]?\s*$",
    re.I)
_TEMPO_IT_TO = re.compile(r"^\s*(?:can\s+you\s+|could\s+you\s+|please\s+)?(?:slow|speed|bring|take)\s+(?:it|things|everything|the\s+(?:song|track|set|tempo))"
                          r"\s+(?:down|up|back)\s+to\s+(?P<bpm>\d{2,3}(?:\.\d+)?)\s*bpm\b[\s?.!]*$", re.I)
_TEMPO_VAGUE = re.compile(r"^\s*(?:(?:speed|slow)\s+(?:it|the\s+(?:tempo|song|track|set))\s+(?:up|down)|"
                          r"(?:raise|increase|lower|decrease|bump|drop)\s+the\s+tempo|(?:make\s+it|go)\s+(?:faster|slower))"
                          r"(?:\s+(?:a\s+(?:bit|little|touch|hair)|slightly))?\s*[.!]?\s*$", re.I)


_SIGNATURE_REQUEST = re.compile(
    r"^\s*(?:(?:set|change|put|make|switch|go|move)\s+)?(?:(?:the|my|our|this|it)\s+)?(?:(?:song|project|set|session)\s*'?s?\s+)?"
    r"(?:(?:time\s+signature|meter|signature)\s+)?(?:to|in(?:to)?|=)?\s*(?P<num>\d{1,3})\s*/\s*(?P<den>\d{1,2})"
    r"(?:\s+time)?(?:\s+(?:time\s+signature|meter))?\s*[.!]?\s*$", re.I)


def _time_signature_request(text: str) -> dict[str, Any] | None:
    """"set the time signature to 3/4", "switch to 6/8 time": a time-signature change, or None."""
    if not re.search(r"\b(?:time\s+signature|meter|signature)\b|\d\s*/\s*\d+\s+time\b|^\s*(?:switch|go|change)\s+(?:it\s+)?to\s+\d+\s*/\s*\d+",
                     text, re.I):
        return None
    m = _SIGNATURE_REQUEST.match(text)
    if m is None:
        return None
    numerator, denominator = int(m.group("num")), int(m.group("den"))
    fields: dict[str, Any] = {"mode": "assist", "action": "set_time_signature", "confidence": 0.97}
    if not 1 <= numerator <= 99 or denominator not in (1, 2, 4, 8, 16):
        fields.update(missing_fields=["amount"], confirmation_required=False, ambiguity=[
            f"Live takes 1 to 99 beats over 1, 2, 4, 8 or 16, so {numerator}/{denominator} can't be set."])
        return fields
    fields.update(desired_value={"numerator": numerator, "denominator": denominator}, confirmation_required=True,
                  unit="time_signature")
    return fields


def _named_scene(lower: str, snapshot: dict[str, Any] | None) -> dict[str, Any] | None:
    if not re.search(r"\b(?:play|launch|fire|trigger)\b.*\bscene\b", lower):
        return None
    scenes = [sc for sc in ((snapshot or {}).get("scenes") or []) if isinstance(sc, dict) and str(sc.get("name", "")).strip()]
    hits = [sc for sc in scenes if re.search(rf"(?<![\w-]){re.escape(str(sc['name']).strip().casefold())}(?![\w-])", lower)]
    return hits[0] if len(hits) == 1 else None


def _tempo_request(text: str, snapshot: dict[str, Any] | None) -> dict[str, Any] | None:
    """A song-tempo change, as intent fields, or None when the message isn't one."""
    if _TEMPO_NOT_SONG.search(text):
        return None
    vague = _TEMPO_VAGUE.match(text)
    if not _TEMPO_WORD.search(text) and not vague:
        return None
    current = (snapshot or {}).get("tempo") if isinstance(snapshot, dict) else None
    current = float(current) if isinstance(current, (int, float)) and not isinstance(current, bool) else None
    fields: dict[str, Any] = {"mode": "assist", "action": "set_tempo", "confidence": 0.97}
    ask = None
    if (m := _TEMPO_RELATIVE.match(text)) and (m.group("verb") or m.group("dir") or m.group("dir2")):
        words = " ".join(filter(None, (m.group("verb"), m.group("dir"), m.group("dir2")))).lower()
        down = re.search(r"\b(?:lower|decrease|drop|reduce|slow|down|slower)\b", words)
        up = re.search(r"\b(?:raise|increase|bump|push|lift|speed|up|faster)\b", words)
        if bool(down) == bool(up):
            ask = "Faster or slower? Say \"tempo up 2 BPM\" or \"set the tempo to 124\"."
        elif current is None:
            ask = "Live didn't report its tempo, so a change by an amount can't be worked out. Say the tempo you want."
        else:
            amount = float(m.group("amount"))
            fields.update(desired_value=round(current + (-amount if down else amount), 3), relative=True,
                          requested_relative_bpm=-amount if down else amount)
    elif (m := _TEMPO_ABSOLUTE.match(text) or _TEMPO_IT_TO.match(text)) and _TEMPO_WORD.search(text):
        fields["desired_value"] = float(m.group("bpm"))
    elif vague or _TEMPO_WORD.search(text) and re.match(r"^\s*(?:set|change)\s+(?:the\s+)?tempo\s*[.!]?\s*$", text, re.I):
        now = f" It's {current:g} BPM now." if current is not None else ""
        ask = f"To what tempo?{now} For example \"set the tempo to 124\"."
    else:
        return None
    if ask:
        fields.update(missing_fields=["amount"], ambiguity=[ask], confirmation_required=False)
        return fields
    low, high = 20.0, 999.0
    if not low <= fields["desired_value"] <= high:
        fields.update(missing_fields=["amount"], confirmation_required=False,
                      ambiguity=[f"Live's tempo runs from {low:g} to {high:g} BPM, so {fields['desired_value']:g} can't be set."])
        return fields
    fields.update(confirmation_required=True, unit="bpm", requested_unit="bpm")
    return fields


_FOCUS_DEVICE_BY_NAME = re.compile(
    r"^\s*(?:show(?:\s+me)?|open|focus|select|go\s+to|jump\s+to|take\s+me\s+to)\s+(?:the\s+)?(?P<phrase>.+?)\s*[.!]?\s*$",
    re.I,
)


def _named_device_focus(text: str, tracks: list[dict[str, Any]]) -> tuple[dict[str, Any], dict[str, Any]] | None:
    """"show me the bass eq", "open the compressor on the vocal": one device on one named track.

    The device word must be a known device alias and exist on exactly one track
    whose name covers every other word said; anything less falls through.
    """
    match = _FOCUS_DEVICE_BY_NAME.match(text)
    if not match:
        return None
    phrase = match.group("phrase").casefold()
    for canonical, pattern in _INSERT_DEVICE_ALIASES:
        device_hit = re.search(rf"\b(?:{pattern}|comp)\b" if canonical == "Compressor" else rf"\b(?:{pattern})\b", phrase)
        if not device_hit:
            continue
        rest = (phrase[:device_hit.start()] + " " + phrase[device_hit.end():])
        rest = re.sub(r"\b(?:on|in|of|the|track|channel)\b", " ", rest)
        said = set(re.findall(r"[a-z0-9]+", rest))
        if not said:
            return None
        track, _candidates, error = _find_track(" ".join(rest.split()), tracks)
        if error or track is None:
            track_name = _nickname_track_name(" ".join(rest.split()), tracks)
            track = next((t for t in tracks if t.get("name") == track_name), None) if track_name else None
            if track is None:
                return None
        named = set(re.findall(r"[a-z0-9]+", str(track.get("name", "")).casefold()))
        if not said - named <= _NICKNAME_WORDS:
            return None  # an extra word ("... compressor ratio") means this is not just a focus request
        devices = [d for d in (track.get("devices") or []) if isinstance(d, dict)
                   and str(d.get("name", "")).casefold() == canonical.casefold()]
        return (track, devices[0]) if len(devices) == 1 else None
    return None


_BARE_DB = re.compile(r"(?<![\w.])([+-]?\d+(?:\.\d+)?)\s*dbs?\b", re.I)
_LOUDER = re.compile(r"\b(?:louder|up|raise|boost|lift|bump)\b", re.I)
_QUIETER = re.compile(r"\b(?:quieter|softer|down|lower|reduce|tuck|back)\b", re.I)
_VALUE_QUESTION_EXCLUDE = re.compile(
    r"\b(?:hz|khz|eq|band|threshold|ratio|attack|release|send|sends|reverb|delay|echo|compressor|gain|q|drive|"
    r"dry|wet|width|filter|cutoff|resonance)\b", re.I)


def _missing_value_question(lower: str, track_name: str) -> tuple[str, str, str] | None:
    """(action, missing field, question) for a clear request that lacks one value."""
    if _VALUE_QUESTION_EXCLUDE.search(lower):
        return None
    db = _BARE_DB.search(lower)
    louder, quieter = bool(_LOUDER.search(lower)), bool(_QUIETER.search(lower))
    if db and not (louder or quieter) and not re.search(r"\b(?:to|at|by)\b", lower):
        amount = float(db.group(1))
        size = f"{abs(amount):g}"
        direction = "quieter" if amount < 0 else "louder"
        verb = "down" if amount < 0 else "up"
        return ("set_volume", "absolute_or_relative",
                f"Do you want {track_name} at {amount:g} dB, or {size} dB {direction} than it is now? "
                f"Say \"set {track_name} to {amount:g} dB\" or \"turn {track_name} {verb} {size} dB\".")
    if not db and (louder or quieter) and not (louder and quieter) and not re.search(r"\d", lower) \
            and re.search(r"\b(?:louder|quieter|softer|turn|bring|make|volume|level|up|down)\b", lower):
        verb = "up" if louder else "down"
        return ("set_volume", "amount",
                f"By how much? For example \"turn {track_name} {verb} 2 dB\" or \"set {track_name} to -6 dB\".")
    side = re.search(r"\bpan\b.*?\b(left|right)\b", lower)
    if side and not re.search(r"\d|\b(?:hard|fully|all\s+the\s+way|cent(?:er|re)|middle)\b", lower):
        where = side.group(1)
        return ("set_pan", "amount",
                f"How far {where}? For example \"pan {track_name} 30% {where}\" or \"pan {track_name} hard {where}\".")
    return None


_KILOHERTZ = re.compile(r"(?<![\w.])(\d+(?:\.\d+)?)\s*(?:khz|kilohertz|k)\b", re.I)
_FREQUENCY_MENTION = re.compile(r"(?<![\w.])\d+(?:\.\d+)?\s*(?:hz|hertz)\b", re.I)


def _normalize_kilohertz(text: str) -> str:
    """"2k", "2 kHz", "1.5 kilohertz" -> "2000 Hz" etc., so every EQ rule sees one unit."""
    return _KILOHERTZ.sub(lambda m: f"{float(m.group(1)) * 1000:g} Hz", text)


_SINGLE_TRACK_ACTIONS = {"set_volume", "set_pan", "set_mute", "set_solo", "set_arm"}
_TONE_WORDS = re.compile(r"\b(?:high|low|top|bottom)\s+end\b|\b(?:highs|lows|mids|low[- ]mids|treble|brightness|"
                         r"muddiness|mud|boom|harshness|sibilance|air|presence)\b", re.I)
_EXCEPT = re.compile(r"\b(?:except|apart\s+from|other\s+than|all\s+but|everything\s+but|but\s+not)\b", re.I)
_PLAY_FROM = re.compile(r"\b(?:play|start|go)\b.*?\bfrom\s+(?:the\s+)?(?P<where>[\w\s-]+?)\s*[.!]?\s*$", re.I)
_SECTION_SCOPE = re.compile(r"\b(?:in|during|for|through)\s+(?:the\s+)?(?:first\s+|second\s+|last\s+|final\s+)?"
                            r"(?:verse|chorus|hook|drop|intro|outro|bridge|breakdown|build(?:[- ]?up)?|pre[- ]?chorus|"
                            r"section|middle\s+eight)s?\b", re.I)


def _single_track_change_question(parsed: dict[str, Any], snapshot: dict[str, Any] | None) -> str:
    """A question instead of a proposal when a one-track mixer change reads as something else.

    Two named tracks ("the bass 3 dB below the kick"), tone words ("the hats' high end") or a song section
    ("in the verse") mean the fader change KENN would make is not what was asked for.
    """
    if parsed.get("missing_fields") or parsed.get("ambiguity"):
        return ""
    if parsed.get("action") == "transport_play":
        start = _PLAY_FROM.search(str(parsed.get("query") or ""))
        if start:
            # "play from the chorus" used to start from wherever the playhead was, silently dropping "from the chorus".
            return (f"KENN can only start playback from where the playhead is, not from {start.group('where')}. Move the "
                    "playhead there in Live, then say \"play\".")
        return ""
    if parsed.get("action") not in _SINGLE_TRACK_ACTIONS:
        return ""
    query = str(parsed.get("query") or "")
    lowered = query.casefold()
    target = (parsed.get("track") or {}).get("name") if isinstance(parsed.get("track"), dict) else None
    named = [str(t.get("name")) for t in (snapshot or {}).get("tracks") or [] if isinstance(t, dict) and t.get("name")
             and re.search(rf"(?<![\w-]){re.escape(str(t['name']).casefold())}(?![\w-])", lowered)]
    if _EXCEPT.search(query):
        # "mute everything except the kick" used to mute the kick: the one track the producer wanted left alone.
        return (f"KENN changes one track at a time for now, so it can't do \"{_EXCEPT.search(query).group(0)} …\". "
                "Name the track to change, for example \"mute the snare\".")
    if len(set(named)) >= 2:
        return (f"That mentions {', '.join(sorted(set(named)))}. Which single track should change, and by how much? "
                "For example \"turn the Bass down 3 dB\".")
    tone = _TONE_WORDS.search(query)
    if tone and not any(tone.group(0).casefold() in str(name).casefold() for name in named):
        return (f"\"{tone.group(0)}\" sounds like an EQ change on {target or 'that track'}, not its fader. Say which "
                f"frequency, for example \"cut 3 dB at 8 kHz on {target or 'the hats'}\", or \"turn {target or 'it'} "
                "down 3 dB\" for the whole track.")
    section = _SECTION_SCOPE.search(query)
    if section:
        return (f"KENN can't change only {section.group(0)} yet (that needs automation); this would change "
                f"{target or 'the track'} for the whole song. Say it without \"{section.group(0)}\" to change the "
                "whole track.")
    return ""


# Live devices KENN can't insert yet. Checked before the insert aliases, because several contain one of their words
# ("EQ Three" has "eq", "Filter Delay" has "filter"): without this, "add a filter delay" became an Auto Filter.
_NOT_INSERTABLE_DEVICES = (
    ("Utility", r"utility"), ("Limiter", r"limiter"), ("Gate", r"(?:noise\s+)?gate"), ("Chorus-Ensemble", r"chorus"),
    ("Phaser-Flanger", r"phaser|flanger"), ("Redux", r"redux|bit\s*crusher"), ("Erosion", r"erosion"),
    ("Vinyl Distortion", r"vinyl\s+distortion"), ("Overdrive", r"overdrive"), ("Pedal", r"pedal"), ("Amp", r"amp"),
    ("Cabinet", r"cabinet"), ("Tuner", r"tuner"), ("Spectrum", r"spectrum"), ("Corpus", r"corpus"),
    ("Resonators", r"resonators?"), ("Vocoder", r"vocoder"), ("Beat Repeat", r"beat\s+repeat"),
    ("Grain Delay", r"grain\s+delay"), ("Filter Delay", r"filter\s+delay"), ("Align Delay", r"align\s+delay"),
    ("Auto Pan", r"auto\s*-?\s*pan|tremolo"), ("Frequency Shifter", r"frequency\s+shifter"), ("Channel EQ", r"channel\s+eq"),
    ("EQ Three", r"eq\s*(?:three|3)"), ("Dynamic Tube", r"dynamic\s+tube"), ("Shifter", r"(?:pitch\s+)?shifter"),
    ("Spectral Resonator", r"spectral\s+resonator"), ("Spectral Time", r"spectral\s+time"), ("Looper", r"looper"),
    ("Convolution Reverb", r"convolution\s+reverb"),
)
_ADD_VERB = re.compile(r"\b(?:add|append|insert|put|load|stick|drop|throw|slap|pop|chuck)\b", re.I)
_INSERTABLE_NAMES = "EQ Eight, Compressor, Glue Compressor, Multiband Dynamics, Saturator, Roar, Auto Filter, Drum Buss, " \
                    "Hybrid Reverb and Echo"
# "why is the FX Print track set to 0 dB?" became a proposal to set it to 0 dB. A why/should/is question asks about
# the set; it never changes it. ("can you ...?" is a request and is handled by the polite-lead rule.)
_QUESTION_NOT_REQUEST = re.compile(r"^\s*(?:why|how\s+come|should|shouldn't|is|isn't|are|aren't|does|doesn't|do|did|"
                                   r"was|were|what|which|where|who)\b", re.I)
# "The drum bus is set to -14 dB, but I want to make sure the compressor is working" describes the set. It became a
# proposal to set the Drum Bus to -14 dB.
_DESCRIBES_SET = re.compile(r"^\s*(?!(?:make|set|put|turn|bring|i|let|please|can|could)\b)(?:the\s+)?[\w/'&-]+(?:\s+[\w/'&-]+){0,3}\s+"
                            r"(?:is|are|'s)\s+(?:currently\s+|now\s+|already\s+|still\s+)?(?:(?:set\s+)?(?:at|to|on)|sent|routed|going|"
                            r"feeding|panned)\s+", re.I)
# "mute the drum bus lol jk", "mute the drum bus? nah": taken back in the same breath.
_RETRACTED = re.compile(r"\b(?:lol\s+)?(?:jk|j/k|just\s+kidding|kidding|nah|nope|never\s*mind|nvm|forget\s+it|"
                        r"scratch\s+that|ignore\s+(?:that|me))\W*$", re.I)
# "tomorrow mute the drum bus", "remember to mute the drum bus later": KENN changes things when asked, not later.
_DEFERRED = re.compile(r"^\s*(?:(?:later|tomorrow|tonight|next\s+time|at\s+some\s+point)\b|remember\s+to\b|"
                       r"i'?m\s+going\s+to\b)|\b(?:later|tomorrow|tonight|next\s+time)\s*[.!?]*\s*$", re.I)
# "don't mute the drum bus" proposed muting it, in every build to 27 Sept 2026: the "don't" was dropped.
_NEGATED_REQUEST = re.compile(
    r"^\s*(?:(?:please|pls|and|but|so|just|ok(?:ay)?)[,\s]+)*(?:don'?t|dont|do\s+not|never|no\s+need\s+to)\s+"
    r"(?:(?:ever|even|actually)\s+)?(?P<verb>mute|unmute|solo|unsolo|arm|disarm|record|pan|cent(?:er|re)|change|touch|move|"
    r"delete|remove|add|insert|put|send|rename|set|turn|bring|push|pull|lower|raise|boost|cut|drop|play|stop|start|focus|"
    r"select|apply|undo|make)\b", re.I)
_PAN_NO_SIDE = re.compile(r"^\s*pan\s+(?!.*\b(?:left|right|cent(?:er|re)|middle|hard|l\d|r\d)\b)", re.I)
_HEDGE = re.compile(r"\b(?:maybe|perhaps|possibly|might)\b", re.I)
_RETURN_MENTION = re.compile(r"\breturn(?:\s+tracks?)?\b|\b[ab]\s+return\b", re.I)
_MIXER_WORD = re.compile(r"\b(?:volume|fader|level|gain|louder|quieter|up|down|mute|unmute|solo|unsolo|pan|rename|name|"
                         r"called|set|turn|db)\b", re.I)
_SEND_IN_DB = re.compile(r"\bsend\b.*?-?\d+(?:\.\d+)?\s*db\b|-?\d+(?:\.\d+)?\s*db\b.*?\bsend\b", re.I)


def _not_supported_yet(text: str, parsed: dict[str, Any], snapshot: dict[str, Any] | None) -> tuple[str, str] | None:
    """A plain "KENN can't do that yet" for requests the rules would otherwise shrug at (or misread)."""
    # A locator called "chorus" is not the Chorus device.
    if (_ADD_VERB.search(text) and not _LOCATOR_REQUEST.search(text)
            and parsed.get("action") in {None, "insert_device", "insert_device_with_parameter"}):
        for device, pattern in _NOT_INSERTABLE_DEVICES:
            if re.search(rf"\b(?:{pattern})\b", text, re.I):
                return "device", (f"KENN can't add {device} yet. It can add {_INSERTABLE_NAMES}. "
                                  f"You can drag {device} in from Live's browser.")
    if parsed.get("action") is not None:
        return None
    earlier = set(parsed.get("missing_fields") or [])  # a more specific question from the rules wins, mostly
    if not earlier and _SEND_IN_DB.search(text):
        return "send_amount", ("KENN sets sends in percent for now (\"set the hats delay send to 30%\"); a send level "
                               "in dB hasn't been measured against Live yet, so nothing changed.")
    returns = [str(r.get("name") or "") for r in ((snapshot or {}).get("return_tracks") or []) if isinstance(r, dict)]
    named = next((name for name in returns if name and re.search(rf"\b{re.escape(name)}\b", text, re.I)), None)
    # "mute a-reverb" used to get "device enable, bypass, mute ... not in the qualified action set", as if A-Reverb
    # were a device.
    if (named or _RETURN_MENTION.search(text)) and _MIXER_WORD.search(text) and earlier <= {"device_action",
                                                                                         "return_track_action"}:
        which = f"{named} is a return track, and" if named else "That's a return track, and"
        return "return_track_action", (f"{which} KENN can't change return tracks yet (level, mute, pan or name). Sends "
                                "into them work: \"set the vocal's reverb send to 20%\".")
    return None


# A long chat message with the request buried in it (round 8 phrasing set, 27 Sept 2026): "The kick is too loud and the
# snare is getting lost. Maybe the compressor is too aggressive. Oh, can you lower the kick by 1db?" The clauses
# addressed to KENN are the request; "maybe I should…", "let me…" and "I think…" are the user thinking aloud.
_SENTENCE_END = re.compile(r"(?<=[.!?])\s+")
_ADDRESSED = re.compile(r"\b(?:can|could|would|will)\s+(?:you|we|u)\b|\bplease\b|\blet'?s\b(?!\s+(?:see|hear|try|check|think))",
                        re.I)
_IMPERATIVE_START = re.compile(r"^\s*(?:(?:oh|and|also|then|so|ok|okay|anyway|right)\s*,?\s+)*(?:set|turn|bring|push|pull|mute|unmute|"
                               r"solo|unsolo|pan|cent(?:er|re)|arm|disarm|send|add|insert|put|create|rename|play|stop|lower|"
                               r"raise|drop|boost|cut|slow|speed|launch|fire)\b", re.I)
_CORRECTED = re.compile(r"\b(?:no\s+wait|actually|scratch\s+that|instead|i\s+meant|sorry)\b", re.I)
_MUSING = re.compile(r"\b(?:maybe|perhaps|or\s+(?:is|maybe)|i\s+(?:think|guess|wonder|dunno|should|could|might)|let\s+me|"
                     r"not\s+sure|what'?s\s+your\s+take|what\s+do\s+you\s+think)\b", re.I)


def _buried_requests(query: str) -> list[str]:
    """The clauses of a multi-sentence message that ask KENN for something, from their "can you"/"please" on."""
    sentences = [s.strip() for s in _SENTENCE_END.split(str(query or "").strip()) if s.strip()]
    if not sentences or _CORRECTED.search(str(query)):
        return []  # a correction across sentences is handled by the whole-message rules
    asks = []
    for sentence in sentences:
        found = _ADDRESSED.search(sentence) or _IMPERATIVE_START.match(sentence)
        if found is None:
            continue
        clause = sentence[found.start():]
        if _MUSING.search(clause):
            continue  # "can you maybe…", "could we… or is it the compressor?": still deciding
        asks.append(clause)
    if len(sentences) == 1 and asks and asks[0] == sentences[0]:
        return []  # one plain request is the whole message; the ordinary rules have already had it
    return asks


TRACK_CHANGE_ACTIONS = {"set_volume", "set_pan", "set_mute", "set_solo", "set_arm"}
_IT_COULD_BE_AN_EFFECT = re.compile(r"\b(?:reverb|verb|delay|echo|compressor|comp|eq|saturator|filter|send|plugin|effect|"
                                    r"tempo|bpm)\b", re.I)


def _only_track_named(text: str, tracks: list[dict[str, Any]]) -> dict[str, Any] | None:
    """The one track the words just before a buried request name, when "it" can only mean that track.

    "The kick is a bit too loud, can you lower it" is the Kick. "The bass is fighting the kick, so let's lower it" names
    two tracks and "tired of the reverb on the vocal, can you turn it off" names an effect, so neither is guessed: a
    wrong track here was a wrong change (27 Sept 2026).
    """
    if _IT_COULD_BE_AN_EFFECT.search(text):
        return None
    named = []
    for track in tracks:
        name = str(track.get("name", "")).strip()
        words = [w for w in re.split(r"[\s/_-]+", name.casefold()) if len(w) >= 3 and w not in _GENERIC_TRACK_WORDS]
        patterns = [re.escape(name.casefold())] + [re.escape(w) + "s?" for w in words]
        if any(re.search(rf"(?<![\w-]){p}(?![\w-])", text.casefold()) for p in patterns):
            named.append(track)
    return named[0] if len(named) == 1 else None


def parse_request(query: str, session_snapshot: dict[str, Any] | None) -> dict[str, Any]:
    """Parse a request into a safe, non-executable intent result."""
    parsed = _parse_single_request(query, session_snapshot)
    if parsed.get("action") is not None and not parsed.get("missing_fields"):
        return parsed
    if set(parsed.get("missing_fields") or []) & {"negated", "deferred", "how_to"}:
        return parsed  # "mute the drum bus? nah": a "don't", "later" or a question is never overridden
    asks = _buried_requests(query)
    if not asks:
        return parsed
    tracks = [t for t in ((session_snapshot or {}).get("tracks") or []) if isinstance(t, dict)]
    found, unclear = [], None
    for clause in asks:
        attempt = _parse_single_request(clause, session_snapshot)
        if attempt.get("action") is None and re.search(r"\b(?:it|them)\b", clause, re.I):
            # "…the kick is a bit too loud, can you lower it a bit?": "it" is the track just named, from the same
            # sentence, or the sentence before when the request starts its own.
            before = str(query)[:str(query).find(clause)]
            sentences = [x for x in _SENTENCE_END.split(before.strip()) if x.strip()]
            context = "" if not sentences else (sentences[-1] if not re.search(r"[.!?]\s*$", before) else sentences[-1])
            earlier = _only_track_named(context, tracks)
            if earlier is not None:
                clause = re.sub(r"\b(?:it|them)\b", f"the {earlier.get('name')}", clause, count=1, flags=re.I)
                attempt = _parse_single_request(clause, session_snapshot)
            elif tracks and unclear is None:
                # What kind of change it is, with a stand-in track, so the question can be specific.
                probe = _parse_single_request(re.sub(r"\b(?:it|them)\b", f"the {tracks[0].get('name')}", clause, count=1,
                                                     flags=re.I), session_snapshot)
                if probe.get("action") in TRACK_CHANGE_ACTIONS:
                    unclear = (clause, probe["action"])
        if attempt.get("action") is not None:
            found.append((clause, attempt))
    if not found and unclear is not None:
        clause, action = unclear
        parsed.update({"action": action, "track": None, "desired_value": None, "confirmation_required": False,
                       "missing_fields": ["which_track"], "ambiguity": [
                           f"Which track do you mean by \"it\" in \"{clause.rstrip('?.! ')}\"? Name it and KENN prepares the "
                           "change. Nothing changed."]})
        return parsed
    if len(found) == 1:
        clause, attempt = found[0]
        attempt["picked_from_longer_message"] = clause
        return attempt
    if len(found) > 1:
        first = found[0][1]
        listed = " and ".join(f"\"{clause.rstrip('?.! ')}\"" for clause, _ in found[:3])
        first.update({"confirmation_required": False, "missing_fields": ["which_change"], "ambiguity": [
            f"I heard more than one change: {listed}. Which should I prepare first? Nothing changed."]})
        return first
    return parsed


def _parse_single_request(query: str, session_snapshot: dict[str, Any] | None) -> dict[str, Any]:
    parsed = _parse_request_rules(query, session_snapshot)
    text = str(parsed.get("query") or query or "")
    unsupported = _not_supported_yet(text, parsed, session_snapshot)
    if unsupported:
        parsed.update({"action": None, "desired_value": None, "confirmation_required": False,
                       "missing_fields": [unsupported[0]], "ambiguity": [unsupported[1]]})
        return parsed
    # "...so I can jump back to it later" is why it's wanted now, not a request for later.
    if parsed.get("action") and (_DEFERRED.search(str(query or "")) or _DEFERRED.search(text)) \
            and not re.search(r"\bso\s+(?:that\s+)?(?:i|we|you)\s+can\b|\bto\s+(?:find|jump|come\s+back|return|use)\b",
                              str(query or ""), re.I):
        parsed.update({"action": None, "desired_value": None, "confirmation_required": False, "missing_fields": ["deferred"],
                       "ambiguity": ["KENN makes a change when you ask for it, not later. Say it when you want it done. "
                                     "Nothing changed."]})
        return parsed
    tracks = [t for t in ((session_snapshot or {}).get("tracks") or []) if isinstance(t, dict)]
    # The shorthand questions below replace only the generic "no action/no track" miss, never a specific one.
    generic_miss = parsed.get("action") is None and set(parsed.get("missing_fields") or []) <= {"action", "track"}
    if generic_miss and not parsed.get("track") and (m := _DEVICE_SETTING_NO_TRACK.match(text)):
        # "comp thresh -10" names the setting but not the track: say which tracks have one instead of "no track found".
        device = "EQ Eight" if m.group("device").lower().startswith("eq") else "Compressor"
        holders = [str(t.get("name")) for t in tracks
                   if any(str(d.get("name", "")).casefold() == device.casefold() for d in (t.get("devices") or []) if isinstance(d, dict))]
        where = (f" The {device} is on {' and '.join(holders)}." if len(holders) <= 3 and holders else "")
        parsed.update({"action": "set_device_parameter", "confirmation_required": False, "missing_fields": ["which_track"],
                       "ambiguity": [f"Which track's {device}?{where} For example \"{text} on the "
                                     f"{holders[0] if holders else 'Drum Bus'}\". Nothing changed."]})
        return parsed
    if generic_miss and not parsed.get("track") and (m := _SEND_NO_TRACK.match(text)):
        fx = "delay" if m.group("fx").lower() == "delay" else "reverb"
        parsed.update({"action": "set_send", "confirmation_required": False, "missing_fields": ["which_track"],
                       "ambiguity": [f"Which track's {fx} send? For example \"send the Synth to the {fx} at 30%\". "
                                     "Nothing changed."]})
        return parsed
    if generic_miss and parsed.get("track") and (m := _SEND_NUDGE.search(text)):
        # KENN sets a send to a level; it doesn't nudge one.
        fx, track = ("delay" if m.group("fx").lower() == "delay" else "reverb"), parsed["track"].get("name")
        parsed.update({"action": "set_send", "confirmation_required": False, "missing_fields": ["amount"],
                       "ambiguity": [f"What level should {track}'s {fx} send be? For example \"send the {track} to the "
                                     f"{fx} at 20%\". Nothing changed."]})
        return parsed
    if generic_miss and parsed.get("track") and (m := _EQ_CUT_NO_AMOUNT.match(text)):
        parsed.update({"action": "set_eq_band_gain", "confirmation_required": False, "missing_fields": ["amount"],
                       "ambiguity": [f"By how much? For example \"{m.group(0).strip()} by 3 dB\". Nothing changed."]})
        return parsed
    if parsed.get("action") in {"insert_device", "insert_device_with_parameter"}:
        both = re.search(r"\b(?:to|on)\s+(?P<a>(?:the\s+)?[\w/'&-]+(?:\s+[\w/'&-]+){0,2}?)\s+and\s+(?P<b>(?:the\s+)?[\w/'&-]+(?:\s+[\w/'&-]+){0,2}?)\s*[.!?]?\s*$",
                         text, re.I)
        if both and _extract_track_phrase(both.group("b"), tracks):
            # "add reverb to the kick and the snare" inserted it on the Kick only (27 Sept 2026).
            parsed.update({"action": None, "desired_value": None, "confirmation_required": False,
                           "missing_fields": ["one_track"], "ambiguity": [
                               "KENN adds a device to one track at a time. Which track first? Nothing changed."]})
            return parsed
    if parsed.get("action") == "set_pan" and re.search(r"\bleft\b", text, re.I) and re.search(r"\bright\b", text, re.I):
        # "pan the kick 20% left and 20% right" panned left.
        parsed.update({"action": None, "desired_value": None, "confirmation_required": False, "missing_fields": ["pan_side"],
                       "ambiguity": ["Left or right? That names both sides. Nothing changed."]})
        return parsed
    if parsed.get("action") == "set_volume" and re.search(r"\b(?:up|louder|raise|boost)\b[^.]*?-\s*\d", text, re.I) \
            and not parsed.get("absolute_value"):
        parsed.update({"action": None, "desired_value": None, "confirmation_required": False, "missing_fields": ["amount"],
                       "ambiguity": ["Up or down? \"Up\" with a minus amount could mean either. Say \"up 3 dB\" or "
                                     "\"down 3 dB\". Nothing changed."]})
        return parsed
    if _NEGATED_REQUEST.match(text) or _NEGATED_REQUEST.match(str(query or "")) or _RETRACTED.search(str(query or "")):
        parsed.update({"action": None, "desired_value": None, "confirmation_required": False,
                       "missing_fields": ["negated"], "ambiguity": ["Okay, I'll leave it as it is. Nothing changed."]})
        return parsed
    if parsed.get("confirmation_required") and (_DESCRIBES_SET.match(text) or _DESCRIBES_SET.match(str(query or ""))):
        parsed.update({"action": None, "desired_value": None, "confirmation_required": False, "missing_fields": ["how_to"],
                       "ambiguity": ["That describes the set, so nothing changed. Say the change you want (\"set the Drum "
                                     "Bus to -10 dB\") and KENN prepares it."]})
        return parsed
    if parsed.get("confirmation_required") and _QUESTION_NOT_REQUEST.match(text):
        parsed.update({"action": None, "desired_value": None, "confirmation_required": False, "missing_fields": ["how_to"],
                       "ambiguity": ["That's a question, so nothing changed. Ask it in chat for an answer, or say the "
                                     "change you want (\"set FX Print to -6 dB\") and KENN prepares it."]})
        return parsed
    if parsed.get("action") in {"insert_device", "insert_device_with_parameter"} and _HEDGE.search(text):
        # "make the clap snappier and maybe add some reverb" is thinking aloud; it used to insert a Reverb.
        device = (parsed.get("device") or {}).get("name") or "that device"
        track = (parsed.get("track") or {}).get("name") or "the track"
        parsed.update({"action": None, "desired_value": None, "confirmation_required": False, "missing_fields": ["device"],
                       "ambiguity": [f"That sounds like you're still deciding, so nothing changed. Say \"add {device} to "
                                     f"{track}\" and KENN will prepare it."]})
        return parsed
    if (parsed.get("action") is None and parsed.get("track") and _PAN_NO_SIDE.match(text)
            and set(parsed.get("missing_fields") or []) <= {"action"}):
        # "pan the hats" / "pan the snare a bit" got "I'm not sure what you're asking", so the tester's "30% right"
        # afterwards had nothing to answer. Ask the real question instead; the reply then completes the request.
        track = parsed["track"].get("name") or "the track"
        parsed.update({"action": "set_pan", "mode": "assist", "desired_value": None, "confirmation_required": False,
                       "missing_fields": ["amount"],
                       "ambiguity": [f"Which side, and how far? For example \"pan {track} 30% left\" or \"pan {track} hard right\"."]})
        return parsed
    if _HOW_TO_QUESTION.match(str(query or "")):
        parsed.update({"action": None, "desired_value": None, "confirmation_required": False, "missing_fields": ["how_to"],
                       "ambiguity": ["That's a how-to question, so nothing changed. Ask it in chat and KENN explains the "
                                     "steps, or say it as a request (\"solo the lead vocal\") and KENN prepares it."]})
        return parsed
    if parsed.get("action") == "set_eq_band_gain" and not parsed.get("eq_band"):
        band = re.search(r"\bband\s*(\d+)\s*([ab])\b", str(parsed.get("query") or ""), re.I)
        if band:  # "cut 200 Hz on the bass by 3 dB, band 2A": the named band settles which one
            parsed["eq_band"] = f"{int(band.group(1))}{band.group(2).upper()}"
    question = _single_track_change_question(parsed, session_snapshot)
    if question:
        parsed.update({"desired_value": None, "confirmation_required": False,
                       "missing_fields": [*parsed.get("missing_fields", []), "clarification"], "ambiguity": [question]})
        return parsed
    if parsed.get("action") == "set_volume" and _FREQUENCY_MENTION.search(_normalize_kilohertz(str(parsed.get("query") or ""))):
        # "cut 2k on the bass by 3 dB" names a frequency: an EQ change, never the track fader.
        track = (parsed.get("track") or {}).get("name") or "the track"
        frequency = _FREQUENCY_MENTION.search(_normalize_kilohertz(str(parsed.get("query") or ""))).group(0)
        parsed.update({
            "desired_value": None, "confirmation_required": False, "missing_fields": ["eq_band"],
            "ambiguity": [f"That names a frequency ({frequency}), so it sounds like an EQ change on {track}, not its "
                          f"fader. Say it as \"cut 3 dB at {frequency} on {track}\", or \"turn {track} down 3 dB\" "
                          "for the fader."],
        })
    return parsed


def _parse_request_rules(query: str, session_snapshot: dict[str, Any] | None) -> dict[str, Any]:
    tracks_said = [t for t in ((session_snapshot or {}).get("tracks") or []) if isinstance(t, dict)]
    text = _rewrite_shorthand(_rewrite_common_phrasings(" ".join(str(query or "").strip().split())), tracks_said)
    numeric_text = _normalize_kilohertz(_normalize_spoken_numbers(text))
    base = {
        "schema": "kenn.ableton_intent.v1",
        "query": text,
        "mode": "inspect",
        "action": None,
        "track": None,
        "source_track": None,
        "target_track": None,
        "new_track_name": None,
        "track_reference": None,
        "device": None,
        "scene": None,
        "clip_slot": None,
        "source_clip_slot": None,
        "target_clip_slot": None,
        "locator_name": None,
        "return_track_name": None,
        "parameter": None,
        "desired_value": None,
        "relative": False,
        "unit": None,
        "confidence": 0.0,
        "missing_fields": [],
        "ambiguity": [],
        "follow_up": [],
        "confirmation_required": False,
    }
    if not text:
        base.update({"error": "A request is required.", "missing_fields": ["request"], "confidence": 1.0})
        return base
    safety_text = _safety_normalised(text)
    if _DESTRUCTIVE.search(safety_text) and _REMOVE_LOCATOR.fullmatch(text) is None:
        base.update({"mode": "refuse", "error": "Deleting, removing, overwriting, and replacing Live content are disabled by the KENN assistant boundary.", "confidence": 0.99})
        return base
    if _UNBOUNDED_EXECUTION.search(text):
        base.update({
            "mode": "refuse",
            "error": "Arbitrary code, scripts, and untyped OSC execution are outside KENN's safety boundary.",
            "confidence": 0.99,
        })
        return base
    if _SAFETY_BYPASS.search(text):
        base.update({
            "mode": "refuse",
            "error": "Requests to bypass KENN's confirmation, policy, or instruction boundary are refused.",
            "confidence": 0.99,
        })
        return base
    if _UNSAFE_MASTER_LEVEL.search(safety_text) or _UNSAFE_MASTER_MAX.search(safety_text):
        base.update({
            "mode": "refuse",
            "error": (
                "Master-track level changes are outside KENN's qualified control boundary, "
                "and I will not infer or apply a maximum output level. Nothing changed."
            ),
            "confidence": 0.99,
        })
        return base

    snapshot = session_snapshot or {}
    tracks = _track_entries(snapshot)
    lower = numeric_text.lower()
    duplicate_clip_match = _DUPLICATE_CLIP.fullmatch(numeric_text)
    rename_clip_match = _RENAME_CLIP.fullmatch(numeric_text)
    create_midi_track_match = _CREATE_MIDI_TRACK.fullmatch(text)
    if create_midi_track_match:
        requested_name = " ".join(str(create_midi_track_match.group("name") or "").split()).strip()
        base.update({
            "mode": "assist",
            "action": "create_midi_track",
            "new_track_name": requested_name,
            "confirmation_required": True,
            "confidence": 0.99,
        })
        return base
    create_return_track_match = _CREATE_RETURN_TRACK.fullmatch(text)
    if create_return_track_match:
        requested_name = " ".join(str(create_return_track_match.group("name") or "").split()).strip()
        base.update({
            "mode": "assist",
            "action": "create_return_track",
            "new_track_name": requested_name,
            "confirmation_required": True,
            "confidence": 0.99,
        })
        return base
    create_audio_track_match = _CREATE_AUDIO_TRACK.fullmatch(text)
    if create_audio_track_match:
        requested_name = " ".join(str(create_audio_track_match.group("name") or "").split()).strip()
        base.update({
            "mode": "assist",
            "action": "create_audio_track",
            "new_track_name": requested_name,
            "confirmation_required": True,
            "confidence": 0.99,
        })
        return base
    gain_stage_match = _GAIN_STAGE.fullmatch(text)
    if gain_stage_match:
        db_str = gain_stage_match.group("db") or gain_stage_match.group("level_db")
        target_db = float(db_str) if db_str else -6.0
        base.update({
            "mode": "assist",
            "action": "gain_stage_tracks",
            "desired_value": target_db,
            "unit": "dB",
            "confirmation_required": True,
            "confidence": 0.99,
        })
        return base
    group_tracks_match = _GROUP_TRACKS.fullmatch(text)
    if group_tracks_match:
        gtype = str(group_tracks_match.group("group_type") or "").strip().lower()
        track_refs = group_tracks_match.group("track_refs") if "track_refs" in group_tracks_match.groupdict() else None
        parsed_indices = None
        if track_refs:
            parsed_indices = [int(n) - 1 for n in re.findall(r"\d+", track_refs) if int(n) > 0]
        base.update({
            "mode": "assist",
            "action": "group_tracks",
            "group_type": gtype,
            "track_indices": parsed_indices,
            "confirmation_required": True,
            "confidence": 0.99,
        })
        return base
    rename_match = _RENAME_TRACK.search(text)
    device_setup_match = _DEVICE_SETUP.search(numeric_text) or _DEVICE_SETUP_TRAILING.search(numeric_text)
    device_setup_name = _device_setup_name(device_setup_match.group("device")) if device_setup_match else None
    insert_eq_tune = _insert_eq_tune_values(numeric_text)
    # "some reverb on the snare" is vague (how much? insert or send?): ask, don't insert.
    insert_device_name = (_insert_device_name(lower)
                          if _ADD_DEVICE.search(lower) and not _VAGUE_EFFECT.search(lower) else None)
    sounds_like_send = (re.search(r"\bsends?\b|\d\s*(?:%|percent)|\b\d+\s+(?:on|to|into)\s+(?:the\s+)?(?:reverb|delay|verb)\b",
                                  lower) and not device_setup_match and not re.search(r"\b(?:dry|wet|mix)\b", lower))
    send_to = re.match(r"^\s*send\s+(?:the\s+)?\S.*?\s+to\s+(?:the\s+)?(?P<dest>.+?)\s*[.!?]?\s*$", lower)
    return_names = [str(r.get("name") or "").lower() for r in ((session_snapshot or {}).get("return_tracks") or [])
                    if isinstance(r, dict)]
    if (send_to and not re.search(r"\d", lower) and not re.search(r"\b(?:dry|wet|mix)\b", lower)
            # Only to a return: "send MIDI to my external gear" isn't a send level.
            and (re.search(r"\b(?:reverb|verb|delay|echo|return)\b|^[ab]\b|^[ab]-", send_to.group("dest"))
                 or any(name and name in send_to.group("dest") for name in return_names))):
        # "send the synth to the A-Reverb": which send is clear, how much isn't.
        base["missing_fields"].append("send_amount")
        base["ambiguity"].append("How much? For example \"send the vocal to the reverb at 20%\". Nothing changed.")
        return base
    if insert_device_name and sounds_like_send:
        # "put 40% of the bass on reverb", "add a reverb send to the vocal" are sends, and used to insert a Reverb on
        # the track. With an amount the send rules below take it; without one, ask. "at 25% dry wet" is still an
        # insert with a setting.
        insert_device_name = None
        if not re.search(r"\d", lower):
            base["missing_fields"].append("send_amount")
            base["ambiguity"].append("That sounds like a send. How much? For example \"send the vocal to the reverb at "
                                     "20%\". Nothing changed.")
            return base
    add_device_match = insert_device_name is not None
    inspect_device_parameters_match = _INSPECT_DEVICE_PARAMETERS.search(lower)
    eq_band_match = _EQ_BAND_GAIN.search(numeric_text)
    eq_band_freq_first_match = None
    if eq_band_match is None:
        eq_band_freq_first_match = _EQ_BAND_GAIN_FREQ_FIRST.search(numeric_text)
    eq_band_compact_match = _EQ_BAND_COMPACT_GAIN.search(numeric_text)
    eq_band_short_match = _EQ_BAND_SHORT_GAIN.search(numeric_text)
    eq_band_only_match = _EQ_BAND_ONLY_GAIN.search(numeric_text)
    eq_band_untyped_match = _EQ_BAND_UNTYPED_SETTING.search(numeric_text)
    eq_band_absolute_match = _EQ_BAND_ABSOLUTE_GAIN.search(numeric_text)
    eq_band_tuning_match = _EQ_BAND_TUNING_GAIN.search(numeric_text)
    eq_band_tuning_absolute_match = _EQ_BAND_TUNING_GAIN_ABSOLUTE.search(numeric_text)
    eq_device_reference = _EQ_DEVICE_REFERENCE.search(lower)
    eq_device_index = None
    if eq_device_reference:
        # Device numbers in user commands are one-based; Live indices remain
        # zero-based in the typed intent and proposal.
        eq_device_index = int(eq_device_reference.group(1)) - 1
    eq_band_request = eq_band_match or eq_band_freq_first_match or eq_band_compact_match or eq_band_short_match or eq_band_only_match
    if any(cue in lower for cue in ("list my tracks", "what tracks", "show my tracks", "show the tracks")) or re.search(
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
    if _UNSUPPORTED_DEVICE_CONTROL.search(lower) and (
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

    # The new name isn't where the track is named: "rename the track with no devices to main synth" once renamed the
    # Synth because "synth" is in the new name.
    track_text = text[:rename_match.start(1)] if rename_match else text
    track_phrase = _extract_track_phrase(track_text, tracks)
    numbered_match = _NUMERIC_TRACK.search(track_text)
    ordinal_match = _ORDINAL_TRACK.search(track_text)
    spoken_track_match = _SPOKEN_TRACK_NUMBER.search(track_text)
    track_reference_match = numbered_match or ordinal_match or spoken_track_match
    track = None
    ambiguous = []
    track_error = None
    if device_setup_match:
        setup_track_phrase = " ".join(device_setup_match.group("track").strip(" '\"").split())
        if re.fullmatch(r"(?:track|trk|channel|chan|ch)\s*#?\s*\d+", setup_track_phrase, re.I):
            setup_track_number = int(re.search(r"\d+", setup_track_phrase).group(0))
            track, track_error = _find_numbered_track(setup_track_number, tracks)
            base["track_reference"] = {"kind": "user_track_number", "number": setup_track_number}
        else:
            track, ambiguous, track_error = _find_track(setup_track_phrase, tracks)
    elif track_reference_match:
        if numbered_match:
            display_number = int(numbered_match.group(1))
        elif ordinal_match:
            ordinal = str(ordinal_match.group("ordinal")).lower()
            display_number = len(tracks) if ordinal == "last" else _ORDINAL_TRACK_VALUES[ordinal]
        else:
            display_number = _SPOKEN_NUMBER_VALUES[spoken_track_match.group("number").lower()]
        track, track_error = _find_numbered_track(display_number, tracks)
        base["track_reference"] = {"kind": "user_track_number", "number": display_number}
    elif track_phrase:
        track, ambiguous, track_error = _find_track(track_phrase, tracks)
    if not track_phrase and not track_reference_match:
        base["missing_fields"].append("track")
        base["ambiguity"].append("No track name or number was found in the current Live snapshot.")
        if device_setup_match or insert_eq_tune or rename_match or add_device_match or eq_band_request or eq_band_tuning_match or eq_band_tuning_absolute_match or inspect_device_parameters_match:
            base.update({
                "mode": "assist",
                "action": "insert_device_with_parameter" if device_setup_match else ("insert_eq_band_tuning_gain" if insert_eq_tune else ("rename_track" if rename_match else ("insert_device" if add_device_match else ("set_eq_band_tuning_gain" if (eq_band_tuning_match or eq_band_tuning_absolute_match) else ("set_eq_band_gain" if eq_band_request else "inspect_device_parameters"))))),
                "confirmation_required": True,
                "confidence": 0.9,
            })
            if device_setup_match:
                setup_parameter, setup_unit = _device_setup_parameter(device_setup_match, device_setup_name)
                base["device"] = {"name": device_setup_name}
                base["parameter"] = {"name": setup_parameter}
                base["desired_value"] = float(device_setup_match.group("value"))
                base["relative"] = False
                base["unit"] = setup_unit
            elif insert_eq_tune:
                base["device"] = {"name": "EQ Eight"}
                base["parameter"] = {"name": "Frequency + Gain"}
                base["desired_value"] = insert_eq_tune["gain_db"]
                base["frequency_hz"] = insert_eq_tune["frequency_hz"]
                base["eq_band"] = insert_eq_tune["eq_band"]
                base["unit"] = "dB"
                if not insert_eq_tune["eq_band"]:
                    base["missing_fields"].append("eq_band")
                    base["ambiguity"].append("Name one exact new EQ Eight band such as 2A; KENN will not choose a band for you.")
            elif rename_match:
                base["desired_value"] = " ".join(rename_match.group(1).split()).strip()
                base["unit"] = "string"
                base["confidence"] = 0.95
            elif add_device_match:
                base["device"] = {"name": insert_device_name}
            elif inspect_device_parameters_match:
                base["mode"] = "inspect"
                base["confirmation_required"] = False
                base["missing_fields"].append("device")
            elif eq_band_tuning_match or eq_band_tuning_absolute_match:
                base["device"] = {"name": "EQ Eight", **({"index": eq_device_index} if eq_device_index is not None else {})}
                base["parameter"] = {"name": "Gain"}
                match = eq_band_tuning_match or eq_band_tuning_absolute_match
                base["desired_value"] = float(match.group(4)) if eq_band_tuning_absolute_match else _eq_gain_signed(match.group(0), match.group(4))
                base["relative"] = eq_band_tuning_absolute_match is None
                base["unit"] = "dB"
                base["frequency_hz"] = float(match.group(3))
                base["eq_band"] = f"{int(match.group(1))}{match.group(2).upper()}"
                base["missing_fields"].append("device")
            else:
                base["device"] = {"name": "EQ Eight", **({"index": eq_device_index} if eq_device_index is not None else {})}
                base["parameter"] = {"name": "Gain"}
                if eq_band_match:
                    base["desired_value"] = _eq_gain_signed(eq_band_match.group(0), eq_band_match.group(1))
                    base["relative"] = True
                    base["unit"] = "dB"
                    base["frequency_hz"] = float(eq_band_match.group(2))
                    if eq_band_match.group(3) and eq_band_match.group(4):
                        base["eq_band"] = f"{int(eq_band_match.group(3))}{eq_band_match.group(4).upper()}"
                elif eq_band_freq_first_match:
                    base["desired_value"] = _eq_gain_signed(eq_band_freq_first_match.group(0), eq_band_freq_first_match.group(2))
                    base["relative"] = True
                    base["unit"] = "dB"
                    base["frequency_hz"] = float(eq_band_freq_first_match.group(1))
                elif eq_band_compact_match:
                    base["desired_value"] = _eq_gain_signed(eq_band_compact_match.group(0), eq_band_compact_match.group(1))
                    base["relative"] = True
                    base["unit"] = "dB"
                    base["frequency_hz"] = float(eq_band_compact_match.group(2)) * (
                        1000.0 if eq_band_compact_match.group(3).lower() in {"khz", "kilohertz"} else 1.0
                    )
                elif eq_band_short_match:
                    base["desired_value"] = _eq_gain_signed(eq_band_short_match.group(0), eq_band_short_match.group(3))
                    base["relative"] = True
                    base["unit"] = "dB"
                    base["frequency_hz"] = float(eq_band_short_match.group(4))
                    base["eq_band"] = f"{int(eq_band_short_match.group(1))}{eq_band_short_match.group(2).upper()}"
                else:
                    base["desired_value"] = _eq_gain_signed(eq_band_only_match.group(0), eq_band_only_match.group(3))
                    base["relative"] = True
                    base["unit"] = "dB"
                    base["eq_band_number"] = int(eq_band_only_match.group(1))
                    if eq_band_only_match.group(2):
                        base["eq_band"] = f"{int(eq_band_only_match.group(1))}{eq_band_only_match.group(2).upper()}"
                base["missing_fields"].append("device")
            return base
        base["confidence"] = 0.5
        return base
    if track is None:
        base["ambiguity"].append(track_error or "track target is ambiguous")
        base["confidence"] = 0.2
        return base
    base["track"] = {"index": track.get("index"), "name": track.get("name")}

    if insert_eq_tune:
        base.update({
            "mode": "assist",
            "action": "insert_eq_band_tuning_gain",
            "device": {"name": "EQ Eight"},
            "parameter": {"name": "Frequency + Gain"},
            "desired_value": insert_eq_tune["gain_db"],
            "relative": False,
            "unit": "dB",
            "frequency_hz": insert_eq_tune["frequency_hz"],
            "eq_band": insert_eq_tune["eq_band"],
            "confirmation_required": bool(insert_eq_tune["eq_band"]),
            "confidence": 0.98,
        })
        if not insert_eq_tune["eq_band"]:
            base["missing_fields"].append("eq_band")
            base["ambiguity"].append("Name one exact new EQ Eight band such as 2A; KENN will not choose a band for you.")
        return base

    if device_setup_match:
        setup_parameter, setup_unit = _device_setup_parameter(device_setup_match, device_setup_name)
        base.update({
            "mode": "assist",
            "action": "insert_device_with_parameter",
            "device": {"name": device_setup_name},
            "parameter": {"name": setup_parameter},
            "desired_value": float(device_setup_match.group("value")),
            "relative": False,
            "unit": setup_unit,
            "confirmation_required": True,
            "confidence": 0.98,
        })
        return base

    if rename_match:
        new_name = " ".join(rename_match.group(1).split()).strip()
        if not new_name:
            base["ambiguity"].append("A new non-empty track name is required.")
            base["missing_fields"].append("new_track_name")
            return base
        base.update({
            "mode": "assist",
            "action": "rename_track",
            "desired_value": new_name,
            "unit": "string",
            "confirmation_required": True,
            "confidence": 0.98,
        })
        return base

    if eq_band_tuning_match or eq_band_tuning_absolute_match:
        match = eq_band_tuning_match or eq_band_tuning_absolute_match
        base.update({
            "mode": "assist",
            "action": "set_eq_band_tuning_gain",
            "device": {"name": "EQ Eight", **({"index": eq_device_index} if eq_device_index is not None else {})},
            "parameter": {"name": "Gain"},
            "desired_value": float(match.group(4)) if eq_band_tuning_absolute_match else _eq_gain_signed(match.group(0), match.group(4)),
            "relative": eq_band_tuning_absolute_match is None,
            "unit": "dB",
            "frequency_hz": float(match.group(3)),
            "eq_band": f"{int(match.group(1))}{match.group(2).upper()}",
            "confirmation_required": True,
            "confidence": 0.98,
        })
        return base

    if eq_band_absolute_match:
        base.update({
            "mode": "assist",
            "action": "set_eq_band_gain",
            "device": {"name": "EQ Eight", **({"index": eq_device_index} if eq_device_index is not None else {})},
            "parameter": {"name": "Gain"},
            "desired_value": float(eq_band_absolute_match.group(3)),
            "relative": False,
            "unit": "dB",
            "confirmation_required": True,
            "confidence": 0.95,
            "eq_band": f"{int(eq_band_absolute_match.group(1))}{eq_band_absolute_match.group(2).upper()}",
            "eq_band_number": int(eq_band_absolute_match.group(1)),
        })
        return base

    if eq_band_short_match:
        base.update({
            "mode": "assist",
            "action": "set_eq_band_gain",
            "device": {"name": "EQ Eight", **({"index": eq_device_index} if eq_device_index is not None else {})},
            "parameter": {"name": "Gain"},
            "desired_value": _eq_gain_signed(eq_band_short_match.group(0), eq_band_short_match.group(3)),
            "relative": True,
            "unit": "dB",
            "frequency_hz": float(eq_band_short_match.group(4)),
            "eq_band": f"{int(eq_band_short_match.group(1))}{eq_band_short_match.group(2).upper()}",
            "confirmation_required": True,
            "confidence": 0.95,
        })
        return base

    if add_device_match:
        base.update({
            "mode": "assist",
            "action": "insert_device",
            "device": {"name": insert_device_name},
            "confirmation_required": True,
            "confidence": 0.95,
        })
        if eq_band_request or eq_band_tuning_match or eq_band_tuning_absolute_match:
            # The request also names EQ frequency/gain tuning. Insertion and
            # tuning are separate guarded proposals: the tuning step can only
            # be bound once the device exists in a fresh snapshot, so record
            # it as non-blocking follow-up instead of silently dropping the
            # second half of the request. `ambiguity` stays reserved for
            # blockers; the command layer surfaces `follow_up` in its answer.
            follow_up = base.get("follow_up")
            if not isinstance(follow_up, list):
                follow_up = []
                base["follow_up"] = follow_up
            follow_up.append(
                "EQ frequency/gain tuning was also requested; it needs a second proposal after "
                f"{insert_device_name} exists on the track. Confirm the insertion first, then request the tuning."
            )
        return base

    if eq_band_request:
        gain_match = eq_band_match or eq_band_freq_first_match or eq_band_compact_match or eq_band_only_match
        gain_group = (
            eq_band_match.group(1) if eq_band_match
            else eq_band_freq_first_match.group(2) if eq_band_freq_first_match
            else eq_band_compact_match.group(1) if eq_band_compact_match
            else eq_band_only_match.group(3)
        )
        base.update({
            "mode": "assist",
            "action": "set_eq_band_gain",
            "device": {"name": "EQ Eight", **({"index": eq_device_index} if eq_device_index is not None else {})},
            "parameter": {"name": "Gain"},
            "desired_value": _eq_gain_signed(
                gain_match.group(0),
                gain_group,
            ),
            "relative": True,
            "unit": "dB",
            "confirmation_required": True,
            "confidence": 0.9,
        })
        if eq_band_match:
            base["frequency_hz"] = float(eq_band_match.group(2))
            if eq_band_match.group(3) and eq_band_match.group(4):
                base["eq_band"] = f"{int(eq_band_match.group(3))}{eq_band_match.group(4).upper()}"
        elif eq_band_freq_first_match:
            base["frequency_hz"] = float(eq_band_freq_first_match.group(1))
        elif eq_band_compact_match:
            base["frequency_hz"] = float(eq_band_compact_match.group(2)) * (
                1000.0 if eq_band_compact_match.group(3).lower() in {"khz", "kilohertz"} else 1.0
            )
        else:
            base["eq_band_number"] = int(eq_band_only_match.group(1))
            if eq_band_only_match.group(2):
                base["eq_band"] = f"{int(eq_band_only_match.group(1))}{eq_band_only_match.group(2).upper()}"
        return base

    if eq_band_untyped_match:
        band_number = int(eq_band_untyped_match.group(1))
        band_side = eq_band_untyped_match.group(2)
        base.update({
            "mode": "assist",
            "action": "set_eq_band_gain",
            "device": {"name": "EQ Eight"},
            "desired_value": float(eq_band_untyped_match.group(3)),
            "relative": False,
            "unit": None,
            "confirmation_required": True,
            "confidence": 0.75,
            "missing_fields": ["eq_parameter"],
            "ambiguity": [
                "'EQ Eight setting' is not a specific parameter. Say gain, frequency, or Q, and include units."
            ],
        })
        base["eq_band_number"] = band_number
        if band_side:
            base["eq_band"] = f"{band_number}{band_side.upper()}"
        else:
            base["ambiguity"].append(
                f"EQ band {band_number} has A/B controls. Specify {band_number}A or {band_number}B."
            )
        return base

    # "What plugins do I need for a punchy kick?" is advice, not a look at the Kick track's chain.
    asks_advice = re.search(r"\b(?:should|need|good|best|recommend|suggest|would you|to get|to make)\b", lower)
    if not asks_advice and (
        lower.startswith(("what devices", "show devices", "list devices"))
        or "devices on" in lower
        or re.search(r"\b(?:show|list|inspect|display|what|which)\b.*\b(?:chain|processors?|devices?|plugins?|plug-ins?)\b", lower)
        or re.search(r"\bwhat(?:'s| is| are|s)\s+on\s+(?:the\s+)?track\b", lower)
    ):
        base.update({"action": "inspect_devices", "confidence": 0.99})
        return base
    if (
        "current" in lower
        and any(word in lower for word in ("settings", "parameters", "controls"))
        and _DEVICE_PARAMETER_ACTION.search(lower) is None
    ):
        base.update({"action": "inspect_device_parameters", "confidence": 0.85})
        inspect_device_parameters_match = True

    action = None
    mute_off = re.search(
        r"\b(?:un-?mute|un[- ]?silence)\b|\b(?:turn|switch|take)\s+off\s+(?:the\s+)?mute\b|"
        r"\b(?:take|turn|switch)\b.*?\b(?:out\s+of|off)\s+(?:mute|silence)\b|"
        r"\b(?:turn|switch)\s+(?:mute|silence)\s+off\b|"
        # "take the mute off the kick": the noun-first order means off, not on.
        r"\b(?:take|turn|switch|pull|get)\s+(?:the\s+)?(?:mute|silence)\s+off\b",
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
            r"\b(?:take|turn|switch|pull|get)\s+(?:the\s+)?solo\s+off\b",
            lower,
        )
        # "the vocal on its own", "just the vocal please", "gimme only the bass".
        solo_slang = re.search(r"\bon\s+(?:its|their)\s+own\b|\bhear\b.*\b(?:alone|by\s+itself)\s*[.!]?\s*$|^\s*(?:(?:gimme|give\s+me|let\s+me\s+hear)\s+)?(?:just|only)\s+the\b", lower)
        if solo_off or re.search(r"\b(?:solo|isolate)\b", lower) or solo_slang:
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
    if action and _SECOND_ACTION.search(lower):
        # "solo the bass and turn it up 2 dB": proposing only the first part
        # would silently drop the rest. Supported two-step requests are
        # handled by parse_natural_recipe before this parser runs.
        base["missing_fields"].append("single_action")
        base["ambiguity"].append("This asks for more than one change. Say them one at a time, or join them with \"then\".")
        return base
    if action:
        base.update({"mode": "assist", "action": action, "confirmation_required": True, "confidence": 0.95})
        return base

    device_candidates = []
    for device_index, device in enumerate(track.get("devices", []) or []):
        if isinstance(device, dict):
            name = str(device.get("name", ""))
            device_candidates.append((device_index, name))
        else:
            device_candidates.append((device_index, str(device)))
    device = next(((index, name) for index, name in device_candidates if name and name.lower() in lower), None)
    if device is None and re.search(r"\b(?:threshold|ratio|attack|release|frequency|gain|q)\b", lower):
        base["missing_fields"].append("device")
        base["ambiguity"].append("I couldn't find that device on the track. Name the device as it appears in Live.")
        return base
    if device is not None:
        base["device"] = {"index": device[0], "name": device[1]}
    if inspect_device_parameters_match:
        if device is None:
            base["missing_fields"].append("device")
            base["ambiguity"].append("Specify one exact device whose parameters should be inspected.")
        else:
            base.update({"mode": "inspect", "action": "inspect_device_parameters", "confirmation_required": False, "confidence": 0.99})
        return base
    delta_match = re.search(r"\b(lower|reduce|decrease|raise|increase|boost)\b.*?\b(threshold|ratio|attack|release|frequency|gain|q)\b.*?by\s+" + _NUMBER + r"\s*(db|dbs|decibels?|hz|hertz|khz|kilohertz|%|percent|ms|milliseconds?|:1)?", lower)
    set_match = re.search(r"\bset\b.*?\b(threshold|ratio|attack|release|frequency|gain|q)\b.*?to\s+" + _NUMBER + r"\s*(db|dbs|decibels?|hz|hertz|khz|kilohertz|%|percent|ms|milliseconds?|:1)?", lower)
    if device is not None and (delta_match or set_match):
        match = delta_match or set_match
        relative = delta_match is not None
        direction = delta_match.group(1) if delta_match else "set"
        parameter_name = (delta_match.group(2) if delta_match else set_match.group(1)).title()
        amount = float(delta_match.group(3) if delta_match else set_match.group(2))
        requested_unit = (delta_match.group(4) if delta_match else set_match.group(3)) or "value"
        if str(requested_unit).lower() in {"khz", "kilohertz"}:
            amount = amount * 1000.0
            requested_unit = "hz"
        elif str(requested_unit).lower() in {"dbs", "decibel", "decibels"}:
            requested_unit = "db"
        elif str(requested_unit).lower() == "hertz":
            requested_unit = "hz"
        elif str(requested_unit).lower() == "percent":
            requested_unit = "%"
        display_error = _display_unit_error(
            device_name=device[1], parameter_name=parameter_name, value=amount,
            unit=requested_unit, relative=relative,
        )
        if display_error:
            base["missing_fields"].append("supported_unit_mapping")
            base["ambiguity"].append(display_error)
            return base
        if relative and direction in {"lower", "reduce", "decrease"}:
            amount = -abs(amount)
        elif relative:
            amount = abs(amount)
        base.update({
            "mode": "assist",
            "action": "set_device_parameter",
            "parameter": {"name": parameter_name},
            "desired_value": amount,
            "relative": relative,
            # Do not infer dB for an arbitrary device parameter. Threshold
            # and gain commonly use dB, but Live also exposes raw/discrete
            # controls such as Glue Compressor Attack and Ratio. An explicit
            # unit remains authoritative; otherwise the resolver labels the
            # value as a device value until Live metadata proves more.
            "unit": requested_unit,
            "confirmation_required": True,
            "confidence": 0.9,
        })
        return base
    if device is not None:
        generic_match = _generic_device_parameter_match(lower, device[1].lower())
        if not generic_match and _DEVICE_PARAMETER_ACTION.search(lower) and re.search(
                re.escape(device[1].lower()) + r"(?:\s+(?:on|for)\s+(?:the\s+)?[\w/&' -]+?)?\s+(?:to|by)\s+[-+]?\d", lower):
            # "set the compressor on the drum bus to -12 dB" names the device, not which of its settings.
            base.update(action="set_device_parameter")
            base["missing_fields"].append("parameter")
            base["ambiguity"].append(f"Which {device[1]} setting should change? For example \"set the "
                                     f"{device[1].lower()} threshold to -12 dB\". Nothing changed.")
            return base
        if generic_match:
            relative = generic_match["verb"].lower() == "by"
            amount = float(generic_match["value"])
            action_match = _DEVICE_PARAMETER_ACTION.search(lower)
            direction = action_match.group(1).lower() if action_match else "set"
            if relative and direction in {"lower", "reduce", "decrease", "back off"}:
                amount = -abs(amount)
            elif relative:
                amount = abs(amount)
            unit = generic_match["unit"] or ("dB" if relative else "value")
            if str(unit).lower() == "percent":
                unit = "%"
            if str(unit).lower() in {"khz", "kilohertz"}:
                # Live frequency displays use Hz; kilo-hertz is scaled here so
                # every downstream resolver sees canonical Hz values.
                amount = amount * 1000.0
                unit = "hz"
            elif str(unit).lower() in {"dbs", "decibel", "decibels"}:
                unit = "db"
            elif str(unit).lower() == "hertz":
                unit = "hz"
            parameter_name = generic_match["parameter"].strip().title()
            display_error = _display_unit_error(
                device_name=device[1], parameter_name=parameter_name, value=amount,
                unit=unit, relative=relative,
            )
            if display_error:
                base["missing_fields"].append("supported_unit_mapping")
                base["ambiguity"].append(display_error)
                return base
            base.update({
                "mode": "assist",
                "action": "set_device_parameter",
                "parameter": {"name": parameter_name},
                "desired_value": amount,
                "relative": relative,
                "unit": unit,
                "confirmation_required": True,
                "confidence": 0.88,
            })
            return base
    base["missing_fields"].append("action")
    base["ambiguity"].append("No supported Ableton action/value was recognized.")
    return base


__all__ = ["parse_request"]
