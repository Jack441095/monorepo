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
_NUMERIC_TRACK = re.compile(r"\b(?:track|trk|channel|chan|ch)\s*#?\s*(\d+)\b", re.I)
_NUMBERED_SCENE = re.compile(r"\b(?:play|launch|fire|trigger)\b.*?\bscene\s*#?\s*(\d+)\b", re.I)
_LOCATOR_REQUEST = re.compile(
    r"\b(?:add|create|set|remove|delete)\b.{0,80}\b(?:locator|cue\s+point|marker)\b"
    r"|\b(?:locator|cue\s+point|marker)\b.{0,80}\b(?:add|create|set|remove|delete)\b",
    re.I,
)
_ADD_LOCATOR = re.compile(
    r"^\s*(?:add|create|set)\s+(?:a\s+)?(?:locator|cue\s+point|marker)\b"
    r"(?:\s+(?:called|named|label(?:ed|led)?|with\s+name)\s+['\"]?(?P<name>[^'\"]+?)['\"]?)?"
    r"(?:\s+(?:at|on)\s+(?:the\s+)?(?:current\s+position|cursor|playhead|song\s+position))?\s*$",
    re.I,
)
_REMOVE_LOCATOR = re.compile(
    r"^\s*(?:remove|delete)\s+(?:the\s+)?(?:locator|cue\s+point|marker)\b"
    r"(?:\s+(?:called|named|label(?:ed|led)?|with\s+name)\s+['\"]?(?P<name>[^'\"]+?)['\"]?)?"
    r"(?:\s+(?:at|on)\s+(?:the\s+)?(?:current\s+position|cursor|playhead|song\s+position))?\s*$",
    re.I,
)
_CREATE_MIDI_TRACK = re.compile(
    r"^\s*(?:create|add|make)\s+(?:a\s+)?(?:new\s+)?midi\s+track\b"
    r"(?:\s+(?:called|named|with\s+name)\s+['\"]?(?P<name>[^'\"]+?)['\"]?)?\s*[.!]?\s*$",
    re.I,
)
_CREATE_AUDIO_TRACK = re.compile(
    r"^\s*(?:create|add|make)\s+(?:an?\s+)?(?:new\s+)?audio\s+track\b"
    r"(?:\s+(?:called|named|with\s+name)\s+['\"]?(?P<name>[^'\"]+?)['\"]?)?\s*[.!]?\s*$",
    re.I,
)
_CREATE_RETURN_TRACK = re.compile(
    r"^\s*(?:create|add|make)\s+(?:a\s+)?(?:new\s+)?return\s+track\b"
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
    r"(?:\b(?:select|focus|follow)\b.*?|\b(?:show|open)\b(?:\s+me)?\s+(?:the\s+)?)(?:track|trk|channel|chan|ch)\s*#?\s*(\d+)\b",
    re.I,
)
_FOCUS_TRACK_NAME = re.compile(
    r"^\s*(?:select|focus|follow)\s+(?:the\s+)?(?P<name>.+?)\s+"
    r"(?:track|trk|channel|chan|ch)\s*$"
    r"|^\s*(?:show|open)\s+(?:me\s+)?(?:the\s+)?(?:track|trk|channel|chan|ch)\s+"
    r"(?P<show_name>.+?)\s*$",
    re.I,
)
_FOCUS_TRACK_BARE_NAME = re.compile(r"^\s*(?:select|focus|follow)\s+(?:the\s+)?(?P<name>[^.!?]+?)\s*[.!]?\s*$", re.I)
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
    r"\b(?:mute|unmute|enable|disable|bypass|solo|unsolo|arm|disarm|turn\s+(?:on|off))\b",
    re.I,
)


def _display_unit_error(*, device_name: str, parameter_name: str, value: float, unit: str, relative: bool) -> str | None:
    """Return a fail-closed explanation for an unsupported display request."""
    normalized = normalize_unit(unit)
    if normalized not in {"ms", "ratio"}:
        return None
    if find_profile(device_name, parameter_name, normalized) is None:
        return (
            "That Live display unit is not safely mapped to a raw parameter value yet. "
            "Inspect the exact parameter profile or specify an explicit raw value; nothing will change."
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
_RENAME_TRACK = re.compile(
    r"\b(?:rename|name)\b.*?\b(?:to|as)\s+['\"]?([^'\"]+?)['\"]?\s*$",
    re.I,
)
_INSERT_DEVICE_ALIASES = (
    ("Glue Compressor", r"glue\s+compressor"),
    ("Auto Filter", r"auto\s+filter"),
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
    r"\b(?:add|append|insert|put|load)\b.*\b(?:glue\s+compressor|auto\s+filter|drum\s+buss|saturator|eq(?:ualizer)?(?:\s+eight)?|eq\s*8|hybrid\s+reverb|reverb|echo|delay|compressor)\b"
    r"|\b(?:glue\s+compressor|auto\s+filter|drum\s+buss|saturator|eq(?:ualizer)?(?:\s+eight)?|eq\s*8|hybrid\s+reverb|reverb|echo|delay|compressor)\b.*\b(?:add|append|insert|put|load)\b",
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
_RELATIVE_VOLUME_UP = re.compile(r"\b(?:up|raise|boost|louder|push|bump|increase|lift)\b", re.I)


def _volume_range_message(db: float | None) -> str:
    if db is not None and db > 0.0:
        return "That would take the track above 0 dB, which KENN does not set."
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
        return abs(value)
    if not up and not down and re.search(r"\bby\s+[+-]\d", lower):
        return value
    return None


_TRACK_NICKNAMES = (
    (re.compile(r"\b(?:high|hi)[\s-]*hats?\b|\bhihats?\b", re.I), "hi hats"),
    (re.compile(r"\b(?:vox|vocals|voc)\b", re.I), "vocal"),
    (re.compile(r"\bdrums\b", re.I), "drum"),
)
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
    tail = text[device_match.end():]
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


def parse_natural_recipe(query: str, session_snapshot: dict[str, Any] | None) -> dict[str, Any] | None:
    """Parse a small natural-language recipe into typed, non-executable steps.

    Existing track/transport actions are typed immediately. A generic
    existing-device parameter action is retained as a parsed intent for the
    live-side sparse-index and unit resolver. Device insertion and EQ band
    actions are rejected rather than guessed inside a recipe.
    """
    text = " ".join(str(query or "").strip().split())
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
    segments = split_recipe_request(text)
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


def parse_request(query: str, session_snapshot: dict[str, Any] | None) -> dict[str, Any]:
    """Parse a request into a safe, non-executable intent result."""
    text = " ".join(str(query or "").strip().split())
    numeric_text = _normalize_spoken_numbers(text)
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
    if _DESTRUCTIVE.search(text) and _REMOVE_LOCATOR.fullmatch(text) is None:
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
    if _UNSAFE_MASTER_LEVEL.search(text):
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
    if any(cue in lower for cue in ("list my tracks", "what tracks", "show my tracks", "show the tracks")):
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
            said = set(re.findall(r"[a-z0-9]+", bare.group("name").casefold())) - {"track", "the"}
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
    # Scene launch phrasing ("play scene 2") must be checked before the
    # generic transport play/stop match below, since both contain the bare
    # word "play"/"stop" and scene requests are otherwise unrelated to
    # transport state.
    scene_match = _NUMBERED_SCENE.search(lower)
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
                  or _SET_TRACK_SEND.search(lower))
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
    if _UNSUPPORTED_DEVICE_CONTROL.search(lower) and (
        _DEVICE_CONTROL_REFERENCE.search(lower)
        or any(
            re.search(rf"(?<!\w){re.escape(name)}(?!\w)", text, re.I)
            for name in mentioned_devices
        )
    ):
        base["missing_fields"].append("device_action")
        base["ambiguity"].append(
            "Device enable, bypass, mute, solo, and arm controls are not in the qualified action set; "
            "no track-level action was inferred."
        )
        return base
    if re.search(r"\b(play|start playback)\b", lower):
        base.update({"mode": "assist", "action": "transport_play", "confirmation_required": True, "confidence": 0.99})
        return base
    if re.search(r"\b(stop playback|stop the session|stop)\b", lower):
        base.update({"mode": "assist", "action": "transport_stop", "confirmation_required": True, "confidence": 0.99})
        return base

    track_phrase = _extract_track_phrase(text, tracks)
    numbered_match = _NUMERIC_TRACK.search(text)
    ordinal_match = _ORDINAL_TRACK.search(text)
    spoken_track_match = _SPOKEN_TRACK_NUMBER.search(text)
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

    if (
        lower.startswith(("what devices", "show devices", "list devices"))
        or "devices on" in lower
        or re.search(r"\b(?:show|list|inspect|display|what)\b.*\b(?:chain|processors?|devices?)\b", lower)
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
        r"\b(?:unmute|un[- ]?silence)\b|"
        r"\b(?:take|turn|switch)\b.*?\b(?:out\s+of|off)\s+(?:mute|silence)\b|"
        r"\b(?:turn|switch)\s+(?:mute|silence)\s+off\b|"
        # "take the mute off the kick": the noun-first order means off, not on.
        r"\b(?:take|turn|switch|pull|get)\s+(?:the\s+)?(?:mute|silence)\s+off\b",
        lower,
    )
    if mute_off or re.search(r"\b(?:mute|silence)\b", lower):
        action = "set_mute"
        base.update({"desired_value": not bool(mute_off), "unit": "boolean"})
    else:
        solo_off = re.search(
            r"\b(?:unsolo|un[- ]?isolate)\b|"
            r"\b(?:take|turn|switch)\b.*?\b(?:out\s+of|off)\s+(?:solo|isolation)\b|"
            r"\b(?:turn|switch)\s+solo\s+off\b|"
            r"\b(?:take|turn|switch|pull|get)\s+(?:the\s+)?solo\s+off\b",
            lower,
        )
        if solo_off or re.search(r"\b(?:solo|isolate)\b", lower):
            action = "set_solo"
            base.update({"desired_value": not bool(solo_off), "unit": "boolean"})
        else:
            arm_off = re.search(
                r"\bdisarm\b|"
                r"\b(?:take|turn|switch)\b.*?\b(?:out\s+of|off)\s+(?:arm|record[- ]?enable|record[- ]?ready)\b|"
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
            volume_match = re.search(r"\b(?:put|set|sit|pull|push|drop|turn)\b.*?\b(?:to|at)\s+" + _NUMBER + r"\s*db\b", lower)
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
            if side == "left":
                amount = -abs(amount)
            elif side == "right":
                amount = abs(amount)
            normalized = amount / 100.0 if unit else amount
            if not -1.0 <= normalized <= 1.0:
                base["ambiguity"].append("Pan value is outside the supported -1.0 to 1.0 range; no clamping was applied.")
                base["missing_fields"].append("valid_pan_value")
                return base
            base.update({"desired_value": normalized, "unit": "normalized", "requested_unit": "%" if unit else "normalized"})
            action = "set_pan"

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
        base["ambiguity"].append("The request names a device parameter, but no matching device name exists in the Live snapshot.")
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
