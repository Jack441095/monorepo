#!/usr/bin/env python3
"""Weekly triage of what KENN did not understand: cluster the misses, propose the rule fix (plan B4).

KENN's installed app already keeps a log of the requests it had to ask about (``kenn/core/asked_log.py``,
written on the producer's own Mac, 300 rows, cleared from the support page). This script reads one or more
of those files, groups the misses by the rule family that came closest, and prints a report a human can
work down. It is not the scorer: ``score_natural_phrasings.py`` grades a fixture against expected labels
and owns the right/asked/wrong verdict, so nothing here re-grades anything and no pass rate is printed.

Input, one JSONL row per request. Three dialects are read, because the words arrive from three places:

1. the app's own asked log (``asked_log.jsonl``, or the ``asked_log`` array inside a diagnostics file)::

       {"timestamp": 1759000000.0, "said": "lower the bass a bit",
        "kenn_said": "By how much? ...", "status": "clarification_required",
        "next_said": "down 2", "next_status": "proposal_ready"}

2. a scorer run's ``--out`` file (``kenn.natural_phrasing_score.v1``), where the outcome is a ``verdict``
   of ``right``, ``asked`` or ``wrong`` and the wording is in ``query``::

       {"id": "blind-cl-000", "query": "get the kick sitting around minus 9",
        "expected": "set_volume", "got": {"action": "clarify"}, "verdict": "asked", "answer": "..."}

3. a phrasing fixture with no recorded outcome at all (``{"query": ..., "expected_action": ...}``). These
   are counted and never reported as misses, because nothing said KENN failed on them.

``said``, ``query`` and ``command`` are all accepted as the request; ``kenn_said`` and ``answer`` as KENN's
reply. ``status``, ``verdict`` and ``outcome`` are all accepted as the recorded outcome. A ``verdict`` or
``status`` of ``right`` (or any applied status) is a correct parse and is never a miss.

Each request is then re-read by ``kenn.core.live_intent.parse_request`` against a ``FakeLiveBackend``
snapshot, which is what turns "KENN asked" into "KENN understood the action but not the amount". Live is
never contacted: the backend is forced to ``fake`` before the import, so running this on the producer's
Mac with ``KENN_LIVE_BACKEND=osc`` set cannot reach their set.

Everything printed is a proposal for a human. This script never writes to ``live_intent.py``, and the only
file it writes is the report you ask for with ``--out``.

    triage_unparsed_requests.py asked_log.jsonl
    triage_unparsed_requests.py week1.jsonl week2.jsonl --examples 4 --out triage-2026-10-07.txt
    triage_unparsed_requests.py score.json --json | jq '.clusters[0]'
"""

from __future__ import annotations

import argparse
import json
import os
import re
import statistics
import sys
from collections import Counter
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Iterable

KENN_ROOT = Path(__file__).resolve().parents[2]
SOURCE_PATHS = [str(KENN_ROOT / "apps" / "backend" / "src"), str(KENN_ROOT / "tooling")]

# "Not understood" in the app's own words (kenn/core/asked_log.py, asked_log.ASKED_STATUSES) plus the two
# the scorer can add. Anything else that names a finished outcome is a correct parse.
ASKED_OUTCOMES = frozenset({"clarification_required", "refused", "unsupported", "invalid", "blocked", "asked"})
DONE_OUTCOMES = frozenset({"right", "proposal_ready", "confirmation_required", "confirmation_proposed", "applied",
                           "succeeded", "inspected", "unchanged"})
REQUEST_KEYS = ("said", "query", "command", "text", "request")
REPLY_KEYS = ("kenn_said", "answer", "reply")
OUTCOME_KEYS = ("status", "verdict", "outcome", "result")
PRONOUN = re.compile(r"\b(?:it|its|that|this|them|one)\b", re.I)
NUMBER = re.compile(r"(?<!\w)[+-]?\d+(?:\.\d+)?(?!\w)|(?<!\w)[+-]?(?:minus\s+)?[a-z]+\b(?=\s*(?:dbs?|decibels?|%))", re.I)
SPOKEN_NUMBERS = ("one two three four five six seven eight nine ten eleven twelve twelve twenty thirty forty fifty "
                  "sixty seventy eighty ninety hundred half quarter couple").split()

# Which missing field was the one that stopped the plan. Ordered outermost first: "which track" gates every
# other field, and a producer can always answer it, so it outranks the rest.
MISSING_ORDER: tuple[tuple[str, frozenset[str]], ...] = (
    ("two_changes", frozenset({"single_action", "which_change"})),
    ("negated_or_deferred", frozenset({"negated", "deferred"})),
    ("how_to", frozenset({"how_to"})),
    ("needs_track", frozenset({"track", "which_track"})),
    ("ambiguous_track_match", frozenset({"one_track"})),
    ("needs_pan_side", frozenset({"pan_side"})),
    ("needs_eq_target", frozenset({"eq_band", "eq_parameter"})),
    ("needs_device", frozenset({"device", "which_device"})),
    ("needs_direction", frozenset({"absolute_or_relative"})),
    ("not_qualified", frozenset({"supported_unit_mapping", "parameter", "send_amount", "transport_target",
                                 "return_track_action", "return_track_name", "device_action", "valid_volume",
                                 "which_action"})),
    ("needs_amount", frozenset({"amount"})),
)

# No rule matched at all, so the wording names the family a human would hear. Ordered most specific first.
WORD_FAMILIES: tuple[tuple[str, re.Pattern[str]], ...] = (
    ("transport", re.compile(r"\b(?:stop|start|play|playing|playback|roll|tape|transport|metronome|loop|recording)\b", re.I)),
    ("sends_fx", re.compile(r"\b(?:send|sends|reverb|verb|delay|echo|aux|return|returns|room|plate|hall)\b", re.I)),
    ("eq_target", re.compile(r"\b(?:eq|equaliser|equalizer|band|bands|highs|mids|lows|scoop|scooped|notch)\b", re.I)),
    ("question", re.compile(r"^\s*(?:what|why|how|where|which|who|is|are|can|could|does|do|should|would)\b", re.I)),
    ("taste", re.compile(r"\b(?:make|makes|sound|sounds|feel|feels|slap|punch|punchy|sit|sits|tight|tighter|tighten|"
                         r"clean|cleaner|thick|thicker|thin|thinner|boom|boomy|boxy|muddy|harsh|warm|warmer|bright|"
                         r"dull|crisp|glue|glued|gluey|weight|heavier|lighter|nice|nicer|professional|balanced|wide|"
                         r"wider|widen|narrow|loosen|soften|soft|open|clarity|full|empty|louder|softer|quieter|hotter|"
                         r"bigger|smaller)\b", re.I)),
)

SIGNAL_LABELS = {
    "refused": "KENN refused: the assistant boundary, not a wording gap",
    "wrong_plan": "KENN planned the wrong thing",
    "asked_after_parsing": "the rules parsed it and the gateway still asked",
    "needs_track": "the change is named, the track is not",
    "ambiguous_track_match": "two tracks matched one phrase",
    "needs_pan_side": "a pan is named, the side is not",
    "needs_eq_target": "an EQ change is named, the band is not",
    "needs_device": "a device control is named, the device is not",
    "needs_direction": "a number is given, level-or-change is not",
    "needs_amount": "action and track are named, the number is not",
    "not_qualified": "the slot is named but KENN has no measured value for it",
    "two_changes": "two changes in one sentence",
    "negated_or_deferred": "a 'don't' or a 'later' read as a change",
    "how_to": "asked how, not for a change",
    # A rule matched nothing at all, so the wording names the family a human would hear. First match wins.
    "no_action/taste": "no rule matched: a result with no measurable target",
    "no_action/transport": "no rule matched: the transport, asked for with words the rules do not take",
    "no_action/question": "no rule matched: a question, not a request",
    "no_action/sends_fx": "no rule matched: an FX level with no send or return named",
    "no_action/eq_target": "no rule matched: a tone named with no gain",
    "no_action/bare": "no rule matched: nothing recognisable in the wording",
}

# One entry per signal, and for the ones where the action changes which pattern would catch it, one entry per
# (signal, action). Every symbol named here is a real name in live_intent.py, checked 30 Sept 2026.
PROPOSALS: dict[str, dict[str, str]] = {
    "refused": {
        "rules": "_DESTRUCTIVE, _SAFETY_BYPASS, _UNBOUNDED_EXECUTION, _SAFETY_WORDS",
        "change": "Not a wording gap: the boundary did its job and nothing should change here. Keep the count "
                  "so a rising number is noticed, and do not add a rule to make these parse.",
        "test": "none; a refusal that starts parsing is a regression, not a feature",
        "action_rules": "",
    },
    "wrong_plan": {
        "rules": "nothing in live_intent.py is obviously at fault; read the row first",
        "change": "A wrong plan is the scorer says matters most: a producer who presses Apply gets a change "
                  "they did not ask for. Re-run that exact wording with "
                  "`score_natural_phrasings.py --show wrong` and fix the rule it lands on before anything in "
                  "this report.",
        "test": "one test per wrong plan, phrased as the producer's sentence",
        "action_rules": "",
    },
    "asked_after_parsing": {
        "rules": "none; the rules understood it",
        "change": "parse_request returned an action with nothing missing, so this is not a live_intent.py "
                  "problem. Look in core/live_command.py for the staleness check, the measured range, or a "
                  "track that was not in the snapshot at that moment. Replaying the request on FakeLiveBackend "
                  "should not reproduce it; if it does, the parser has moved since the log was written.",
        "test": "the gateway's stale or out-of-range path, with the snapshot the log had",
        "action_rules": "",
    },
    "needs_track": {
        "rules": "_find_track, _TRACK_NICKNAMES, _TRACK_QUALIFIERS, and parse_request's pronoun swap in _buried_requests",
        "change": "These name a track only by pronoun, only as 'the other one', or only in the sentence "
                  "before. parse_request already substitutes the track named earlier in the message; extending "
                  "that is the fix, not a new verb. Keep asking 'which track?' as the fallback: guessing the "
                  "target is the one error a producer pays for. 'The other one' itself is B5's flow, once KENN "
                  "has listed two tracks; outside that flow it belongs here.",
        "test": "test_the_other_one_asks_when_only_one_track_matches",
        "action_rules": "",
    },
    "ambiguous_track_match": {
        "rules": "_ORDINALS, _ORDINAL_TRACK, _SPOKEN_TRACK_NUMBER, _TRACK_NICKNAMES",
        "change": "Two tracks matched the phrase, so KENN asks. That is right; the fix is to ask with both "
                  "names and a number the producer can say back ('Hi-Hats or Kick?'), so the next turn resolves.",
        "test": "test_two_matching_tracks_are_both_named_in_the_question",
        "action_rules": "",
    },
    "needs_pan_side": {
        "rules": "_MOVE_TO_SIDE, _HARD_PAN_ON, _CENTRE_PAN, _FAR_PAN",
        "change": "A pan with no side is a coin toss, so KENN asks. Widen the words that mean 'hard left' "
                  "rather than the words that mean 'somewhere left'.",
        "test": "test_a_side_word_without_a_distance_asks_how_far",
        "action_rules": "",
    },
    "needs_eq_target": {
        "rules": "_EQ_BAND_QUALIFIER, _EQ_BAND_FULL, _EQ_BAND_UNTYPED_SETTING, _EQ_BAND_TUNING_GAIN",
        "change": "The band was not named. 'The low end', '2 to 4 kHz' and 'the highs' each need one pattern; "
                  "a frequency without a gain is a separate gap that belongs to the parameter families.",
        "test": "test_a_frequency_range_without_a_gain_asks_for_the_gain",
        "action_rules": "",
    },
    "needs_device": {
        "rules": "_DEVICE_CONTROL_REFERENCE, _ADD_DEVICE, _INSERT_DEVICE_ALIASES",
        "change": "A control was named with no device, and KENN asks which one. Widen the words that mean a "
                  "device ('the comp', 'the reverb on it') before adding new controls, and check the alias list "
                  "is what a producer would actually say.",
        "test": "test_a_control_with_no_device_name_asks_which_device",
        "action_rules": "",
    },
    "needs_direction": {
        "rules": "_VERB_LEVEL, _UNITLESS_LEVEL, _TERSE_LEVEL, _HEDGED_TARGET",
        "change": "'Set the hats to -6' reads as a level in _VERB_LEVEL when a verb leads and asks when it "
                  "does not. The holdout carries both shapes labelled, so this is a policy call between "
                  "'every set X to -N is a level' and 'keep asking' with a better question, not a bug.",
        "test": "test_a_negative_bare_number_is_a_level_or_a_change_and_says_which",
        "action_rules": "",
    },
    "needs_amount": {
        "rules": "_VAGUE_LEVEL_VERB, _RELATIVE_VOLUME_AMOUNT, _MOVE_TO_SIDE, _SET_SEND, _DEVICE_PARAMETER_ACTION",
        "change": "KENN asks here on purpose: a dB with no direction, or a pan with no distance, is a guess, "
                  "and a guess becomes a wrong plan. This cluster is a wording shape to answer better, not a "
                  "gap to fill. The only safe rules are the ones where the wording carries the amount and only "
                  "the phrasing around it is new.",
        "test": "test_a_vague_level_asks_a_question_the_producer_can_answer_with_a_number",
        "action_rules": (
            "set_volume: _RELATIVE_VOLUME_AMOUNT and _RELATIVE_VOLUME_UP/_DOWN carry 'a bit', 'a touch' and "
            "'slightly'; decide whether those get a default or stay a question. "
            "set_pan: _MOVE_TO_SIDE and _FAR_PAN carry 'over to the left a little'. "
            "set_send: _SET_SEND's _SEND_TAIL needs a percentage; 'down 3 dB' on a send is not one. "
            "set_device_parameter: _DEVICE_PARAMETER_ACTION needs a value in the measured unit."
        ),
    },
    "not_qualified": {
        "rules": "_UNSUPPORTED_DEVICE_CONTROL, _UNSUPPORTED_SEND_CONTROL, _UNSUPPORTED_RETURN_CONTROL, "
                 "_UNSUPPORTED_CLIP_CONTROL, _not_supported_yet",
        "change": "The slot is named and KENN has no measured value for it. This is a Live night and a "
                  "DeviceUnitProfile in core/device_units.py, not a wording pattern. Do not add a default "
                  "number here.",
        "test": "one test per qualified parameter, on the fake backend, then the Live-night row",
        "action_rules": "",
    },
    "two_changes": {
        "rules": "_AND_SPLIT, _SECOND_ACTION, parse_natural_recipe, _RECIPE_TRACK_ACTIONS",
        "change": "parse_request reads the first change and marks single_action; parse_natural_recipe is what "
                  "turns two into steps, and the gateway already proposes a two-step recipe for the clean "
                  "ones. Check which of these the gateway answers with a recipe and which still land here; if "
                  "the answer is B6's 'do the first, then the second?' buttons, the change is in the app and "
                  "this cluster should not produce a parser edit at all.",
        "test": "test_two_changes_in_one_sentence_come_back_as_two_steps",
        "action_rules": "",
    },
    "negated_or_deferred": {
        "rules": "_MID_CORRECTION, _INSTEAD_OF, _CORRECTION_LEAD, _CORRECTION_TAIL",
        "change": "A 'don't' or a 'later' was read as a change. parse_request returns these early on purpose, "
                  "so the fix is recognising the negation and never overriding it, not making it parse.",
        "test": "test_a_negated_request_is_left_alone",
        "action_rules": "",
    },
    "how_to": {
        "rules": "_HOW_TO_QUESTION",
        "change": "By design these are answered with notes, not a proposal. Check they reached the notes route "
                  "instead of the command route; a parse edit here would turn a question into a change nobody "
                  "asked for.",
        "test": "test_a_how_do_i_question_is_answered_not_applied",
        "action_rules": "",
    },
    "no_action": {
        "rules": "_parse_request_rules and the anchored phrase tables it tries in order",
        "change": "No rule matched and substituting a track name for the pronoun does not help, so no amount of "
                  "track resolution fixes this. The sub-family below says which kind of request it is.",
        "test": "one test per wording added, on the fake backend",
        "action_rules": "",
    },
    "no_action/transport": {
        "rules": "_STOP_CLIP_MENTION and the transport_play / transport_stop rules",
        "change": "'Kill playback' and 'roll the tape' have no transport rule; 'stop the transport' parses. "
                  "This is the pinned policy call B2 owes a decision on, not a regex gap, and it needs a "
                  "human answer on whether 'kill playback' means stop or mute everything.",
        "test": "test_kill_playback_does_the_thing_the_policy_decided",
        "action_rules": "",
    },
    "no_action/taste": {
        "rules": "_WANTED_STATE and the state phrases (muted, centred, armed); nothing for 'slap' or 'sit better'",
        "change": "These ask for a result with no measurable target. No rule can pick the dB, and a rule that "
                  "guessed would be a wrong plan. Two honest routes: a named recipe (drum bus compression plus "
                  "a level), or KENN asking which control and how far.",
        "test": "test_a_result_with_no_measurable_target_asks_which_control",
        "action_rules": "",
    },
    "no_action/question": {
        "rules": "_HOW_TO_QUESTION covers 'how do I', not 'what can you do for me'",
        "change": "A question about KENN or the set, not a request. Check the router sent it to the command "
                  "route by mistake; if it did, that is a routing fix, not a rule.",
        "test": "test_a_question_about_kenn_reaches_the_chat_route",
        "action_rules": "",
    },
    "no_action/sends_fx": {
        "rules": "_BARE_EFFECT_LEVEL, _SET_SEND, _TRACK_TO_RETURN, _VAGUE_EFFECT, _ADD_DEVICE",
        "change": "An FX level named with neither a return nor a send. _BARE_EFFECT_LEVEL already asks when a "
                  "return of that name is in the set; these are the cases where it was not. Watch for _ADD_DEVICE "
                  "firing on wording that names no device at all: 'add 2 dB to the reverb return' reaches "
                  "insert_device, which is a false positive and belongs under needs_track, not here.",
        "test": "test_an_fx_level_with_no_return_in_the_set_says_so",
        "action_rules": "",
    },
    "no_action/eq_target": {
        "rules": "_EQ_BAND_UNTYPED_SETTING, _EQ_DEVICE_REFERENCE, _EQ_BAND_ONLY_GAIN",
        "change": "EQ wording with no gain attached ('cut the lows on the bass'). The band pattern exists; the "
                  "request is a tone, not a number, so this needs a question rather than a pattern.",
        "test": "test_a_tone_request_without_a_gain_asks_how_much",
        "action_rules": "",
    },
    "no_action/bare": {
        "rules": "nothing in the anchored phrase tables matched",
        "change": "No recognisable verb, track or number. Read the examples before touching the parser; a row "
                  "with nothing in it is usually a tester testing KENN, or a chat message that reached the "
                  "command route.",
        "test": "one test per wording that is meant to be a request",
        "action_rules": "",
    },
}


@dataclass(frozen=True)
class Row:
    """One request, the outcome the log recorded for it, and where it came from."""

    source: str
    line: int
    query: str
    reply: str
    recorded: str
    raw: dict[str, Any] = field(default_factory=dict, repr=False)


@dataclass(frozen=True)
class Diagnosis:
    """What the parser made of one request, and which family came closest."""

    query: str
    disposition: str
    signal: str
    action: str
    missing: tuple[str, ...]
    mode: str
    track_resolved: str
    probe: tuple[str, ...]
    words: int
    has_number: bool
    reply: str
    recorded: str
    source: str

    @property
    def family(self) -> str:
        return f"{self.signal}/{self.action}" if self.action and self.signal != "refused" else self.signal

    @property
    def label(self) -> str:
        label = SIGNAL_LABELS.get(self.signal, "no rule matched")
        return f"{label} ({self.action})" if self.action and self.signal != "refused" else label


@dataclass
class Cluster:
    family: str
    signal: str
    action: str
    label: str
    rows: list[Diagnosis]

    @property
    def wordings(self) -> list[str]:
        seen: list[str] = []
        for row in self.rows:
            if row.query not in seen:
                seen.append(row.query)
        return seen

    @property
    def missing(self) -> tuple[str, ...]:
        names: list[str] = []
        for row in self.rows:
            for name in row.missing:
                if name not in names:
                    names.append(name)
        return tuple(names)

    @property
    def replies(self) -> list[str]:
        """The distinct things KENN said back, longest first. A cluster where KENN asked something specific and
        one where it only said "I didn't catch a change" are the same parser gap and two different problems."""
        unique = {row.reply for row in self.rows if row.reply}
        return sorted(unique, key=len, reverse=True)

    @property
    def probe(self) -> list[str]:
        """Every track name whose substitution made the request parse, over every row in the cluster."""
        return sorted({name for row in self.rows for name in row.probe})

    @property
    def proposed(self) -> dict[str, str]:
        return PROPOSALS.get(self.family) or PROPOSALS.get(self.signal) or PROPOSALS["no_action"]

    def as_dict(self) -> dict[str, Any]:
        return {"family": self.family, "label": self.label, "signal": self.signal, "action": self.action,
                "rows": len(self.rows), "distinct_wordings": len(self.wordings), "missing_fields": list(self.missing),
                "wordings": self.wordings,
                "replies": self.replies[:3],
                "shape": {"mean_words": round(statistics.fmean(row.words for row in self.rows), 1),
                          "carrying_a_number": sum(1 for row in self.rows if row.has_number),
                          "track_resolved": sum(1 for row in self.rows if row.track_resolved)},
                "probe": self.probe,
                "proposal": self.proposed}


def _rows_from_items(items: Any, source: str) -> list[Row]:
    rows = []
    for number, item in enumerate(items, start=1):
        if not isinstance(item, dict):
            continue
        query = next((str(item[key]) for key in REQUEST_KEYS if str(item.get(key) or "").strip()), "")
        if not query:
            continue
        reply = next((str(item[key]) for key in REPLY_KEYS if str(item.get(key) or "").strip()), "")
        recorded = next((str(item[key]) for key in OUTCOME_KEYS if str(item.get(key) or "").strip()), "")
        rows.append(Row(source=source, line=int(item.get("_line") or number), query=" ".join(query.split()),
                        reply=" ".join(reply.split())[:200], recorded=recorded, raw=item))
    return rows


def read_log_files(paths: Iterable[Path]) -> tuple[list[Row], int]:
    """Rows from every JSONL file, or from the JSON wrapper a diagnostics or scorer file uses.

    A JSONL file also starts with '{', so the whole text is tried as one JSON value first. A single-row JSONL
    file parses as one object, so only a list or a dict carrying one of the wrapper keys counts as a wrapper;
    anything else falls through to the per-line reading.
    """
    rows: list[Row] = []
    skipped = 0
    for path in paths:
        try:
            text = path.read_text(encoding="utf-8")
        except OSError as exc:
            raise SystemExit(f"Could not read {path}: {exc}") from exc
        items: Any = []
        try:
            payload = json.loads(text)
        except ValueError:
            payload = None
        if isinstance(payload, list):
            items = payload
        elif isinstance(payload, dict):
            wrapper = next((payload[key] for key in ("asked_log", "rows", "entries") if payload.get(key)), None)
            if wrapper is not None:
                items = wrapper
        if not items:
            for number, line in enumerate(text.splitlines(), start=1):
                if not line.strip():
                    continue
                try:
                    item = json.loads(line)
                except ValueError:
                    # The support page can append while a technician reads the file, so a torn last line is normal.
                    skipped += 1
                    continue
                if isinstance(item, dict):
                    items.append(item | {"_line": number})
        rows.extend(_rows_from_items(items, str(path)))
    return rows, skipped


def _outcome(row: Row) -> str:
    """What the log says happened: a miss, a refusal, or a correct parse. Blank when it recorded nothing."""
    value = row.recorded.strip().casefold()
    if not value:
        return ""
    if value in {"right", "correct", "understood"} or value in DONE_OUTCOMES:
        return "correct"
    if value == "wrong":
        return "wrong_plan"
    if value in ASKED_OUTCOMES:
        return "refused" if value in {"refused", "blocked"} else "asked"
    return value


def _word_family(query: str) -> str:
    for name, pattern in WORD_FAMILIES:
        if pattern.search(query):
            return name
    return "bare"


def _probe_track(query: str, snapshot: dict[str, Any], parse: Any) -> tuple[str, tuple[str, ...]]:
    """Which action the request would have had, and for which tracks, if its pronoun were a track name.

    This is the substitution parse_request already tries in _buried_requests, run over every track in the
    snapshot. It is what separates "lower it a bit" from "make the drums slap": the first becomes a set_volume
    once a track is named, so a track rule is the fix; the second does not parse for any track, so no amount of
    track resolution helps and the wording family is the fix.
    """
    if not PRONOUN.search(query):
        return "", ()
    action, hits = "", []
    for track in (snapshot.get("tracks") or []):
        name = str(track.get("name") or "") if isinstance(track, dict) else ""
        if not name:
            continue
        probed = PRONOUN.sub(f"the {name}", query, count=1)
        if probed == query:
            continue
        intent = parse(probed, snapshot)
        if intent.get("action"):
            action = action or str(intent["action"])
            hits.append(name)
    return (action if hits else ""), tuple(hits)


def _has_number(query: str) -> bool:
    if NUMBER.search(query):
        return True
    words = set(re.findall(r"[a-z']+", query.casefold()))
    return any(word in words for word in SPOKEN_NUMBERS)


def diagnose(row: Row, snapshot: dict[str, Any], parse: Any) -> Diagnosis:
    """One request against one snapshot, into the family that came closest."""
    intent = parse(row.query, snapshot)
    action = str(intent.get("action") or "")
    mode = str(intent.get("mode") or "")
    missing = tuple(str(name) for name in (intent.get("missing_fields") or []))
    track = intent.get("track") if isinstance(intent.get("track"), dict) else {}
    recorded = _outcome(row)

    signal = ""
    probe_action, probe_hits = "", ()
    if mode == "refuse":
        signal = "refused"
    elif recorded == "wrong_plan":
        # A scorer row only: the plan was produced and it was not what was meant.
        signal = "wrong_plan"
    else:
        for name, wanted in MISSING_ORDER:
            if wanted & set(missing):
                if name == "needs_track":
                    # Only believe it if a track name makes the request parse; otherwise nothing was understood.
                    probe_action, probe_hits = _probe_track(row.query, snapshot, parse)
                    if not probe_action:
                        break
                    action = probe_action
                signal = name
                break
    if not signal:
        if action and not missing:
            signal = "correct" if recorded == "correct" else ("asked_after_parsing" if recorded else "understood")
        else:
            signal = f"no_action/{_word_family(row.query)}"

    return Diagnosis(query=row.query, disposition=recorded or signal, signal=signal, action=action,
                     missing=missing, mode=mode, track_resolved=str(track.get("name") or ""), probe=probe_hits,
                     words=len(row.query.split()), has_number=_has_number(row.query), reply=row.reply,
                     recorded=row.recorded, source=row.source)


def is_miss(row: Diagnosis) -> bool:
    """A correct parse is not a miss, and neither is a row nobody recorded an outcome for that the rules
    understood: those two are counted in the report so the counts add up, and never reach a cluster."""
    return row.disposition not in {"correct", "understood"}


def cluster(diagnoses: Iterable[Diagnosis]) -> list[Cluster]:
    """Groups keyed by (signal, action), biggest first. Correct parses are never grouped."""
    grouped: dict[str, list[Diagnosis]] = {}
    for row in diagnoses:
        if not is_miss(row):
            continue
        grouped.setdefault(row.family, []).append(row)
    clusters = [Cluster(family=family, signal=rows[0].signal, action=rows[0].action, label=rows[0].label, rows=rows)
                for family, rows in grouped.items()]
    # Rows first, then wordings: a cluster of 20 copies of one sentence is 20 rows and 1 wording, and saying so
    # is the difference between a real win and a producer's typo.
    clusters.sort(key=lambda group: (-len(group.rows), -len(group.wordings), group.label))
    return clusters


def render(clusters: list[Cluster], diagnoses: list[Diagnosis], skipped: int, sources: list[str], examples: int,
           tracks: int = 0, returns: int = 0) -> str:
    counts = Counter(row.disposition for row in diagnoses)
    misses = [row for row in diagnoses if is_miss(row)]
    correct = counts["correct"]
    understood = counts["understood"]
    unknown = sum(1 for row in diagnoses if is_miss(row) and row.disposition not in {"asked", "refused",
                                                                                     "wrong_plan"})
    shown_rows = sum(len(group.rows) for group in clusters)

    lines = [
        "KENN wording triage - the requests KENN did not understand",
        f"Sources: {len(sources)} file(s), {len(diagnoses)} request(s)" + (f", {skipped} unreadable line(s) skipped"
                                                                            if skipped else ""),
    ]
    for source in sources:
        lines.append(f"  {source}")
    lines.append("")
    lines.append(f"Rows: {len(diagnoses)} read, {len(misses)} miss(es), {correct} correct parse(s), {understood} with "
                 f"no recorded outcome and understood by the rules, {unknown} unclassified")
    lines.append(f"  asked {counts['asked']}   refused {counts['refused']}   wrong plan {counts['wrong_plan']}   "
                 f"correct {counts['correct']}   understood, not recorded {counts['understood']}")
    if not diagnoses:
        lines += ["", "No rows. Either KENN understood everything this week, or the log was cleared from the "
                      "support page.", "There is nothing to cluster until the log has a row in it."]
        return "\n".join(lines) + "\n"
    lines.append(f"Clusters: {len(clusters)}, holding {shown_rows} of {len(misses)} miss(es), biggest first.")
    lines.append("")
    lines.append("A proposal below is for a human. This script never edits live_intent.py and never touches Live.")
    lines.append("After any rule change: python3 tooling/scripts/score_natural_phrasings.py  (Stage 1 gate: >= 95% "
                 "correct on >= 500 natural phrasings)")
    lines.append("")

    for number, group in enumerate(clusters, start=1):
        proposal = group.proposed
        lines.append(f"{number:2}. {len(group.rows)} row(s), {len(group.wordings)} wording(s) - {group.label}")
        lines.append(f"    closest rules: {proposal['rules']}")
        if group.missing:
            lines.append(f"    what the parser said: missing {', '.join(group.missing)}")
        if group.probe:
            lines.append(f"    with a track name substituted for the pronoun: {len(group.probe)} of the "
                         f"{tracks} names parse it ({', '.join(group.probe[:4])}), so a track rule "
                         "would have caught it")
        mean_words = statistics.fmean(row.words for row in group.rows)
        lines.append(f"    shape: {mean_words:.1f} words on average, "
                     f"{sum(1 for row in group.rows if row.has_number)} of {len(group.rows)} carried a number or the "
                     f"word for one, "
                     f"{sum(1 for row in group.rows if row.track_resolved)} of {len(group.rows)} resolved a track")
        for wording in group.wordings[:examples]:
            lines.append(f"      - {wording}")
        if len(group.wordings) > examples:
            lines.append(f"      - ... {len(group.wordings) - examples} more wording(s)")
        for reply in group.replies[:2]:
            lines.append(f"    KENN said: {reply[:110]}{'...' if len(reply) > 110 else ''}")
        lines.append(f"    PROPOSAL: {proposal['change']}")
        if proposal["action_rules"]:
            lines.append(f"    by action: {proposal['action_rules']}")
        lines.append(f"    test to add: {proposal['test']}")
        lines.append("")

    lines.append("Refusals are the boundary working. They are counted above and belong to a policy decision, not "
                 "a rule fix.")
    lines.append(f"Parsed on FakeLiveBackend: {tracks} track(s), {returns} return track(s). No Live session was read "
                 "or written.")
    return "\n".join(lines) + "\n"


def report(clusters: list[Cluster], diagnoses: list[Diagnosis], skipped: int, sources: list[str]) -> dict[str, Any]:
    return {"schema": "kenn.wording_triage.v1",
            "sources": list(sources),
            "rows": len(diagnoses),
            "skipped_lines": skipped,
            "dispositions": dict(Counter(row.disposition for row in diagnoses)),
            "clusters": [group.as_dict() for group in clusters],
            "writes_to_live_intent": False}


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("sources", nargs="+", type=Path, help="asked_log.jsonl files, scorer --out files, or fixtures")
    parser.add_argument("--out", type=Path, help="write the report here; the only file this script writes")
    parser.add_argument("--json", action="store_true", help="print the structured report instead of the text one")
    parser.add_argument("--examples", type=int, default=3, help="wordings shown per cluster")
    args = parser.parse_args()

    # Before the import: on the producer's Mac KENN_LIVE_BACKEND is often "osc", and this tool only ever wants
    # the fake set. Forcing it here means a triage run cannot read or write a real session.
    os.environ["KENN_LIVE_BACKEND"] = "fake"
    for name in list(sys.modules):
        if name == "kenn" or name.startswith(("kenn.", "scripts")):
            del sys.modules[name]
    sys.path[:0] = SOURCE_PATHS

    from kenn.core.fake_live import FakeLiveBackend
    from kenn.core.live_intent import parse_request

    snapshot = FakeLiveBackend().query_session_state()
    rows, skipped = read_log_files(args.sources)
    diagnoses = [diagnose(row, snapshot, parse_request) for row in rows]
    clusters = cluster(diagnoses)
    sources = [str(path) for path in args.sources]
    if args.json:
        text = json.dumps(report(clusters, diagnoses, skipped, sources), indent=1) + "\n"
    else:
        text = render(clusters, diagnoses, skipped, sources, max(0, args.examples),
                      len(snapshot.get("tracks") or []), len(snapshot.get("return_tracks") or []))
    if args.out:
        args.out.parent.mkdir(parents=True, exist_ok=True)
        args.out.write_text(text, encoding="utf-8")
    print(text, end="")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
