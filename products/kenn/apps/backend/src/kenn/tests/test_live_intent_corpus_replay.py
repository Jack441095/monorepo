"""Replay the whole phrasing corpus so a rule that moves shows up as a changed parse.

``test_live_intent_rule_order`` reads the driver's source with ``inspect.getsource``
and string-matches four calls. That pins the order of four statements and nothing
about what they return: a stage can be handed the wrong argument, or a branch can
be moved from one stage into the one behind it, and every outcome test in the
suite still passes. Splitting the 1241-line flat chain into a driver and four stage
modules needed better evidence than that, so the split was checked by running 96
phrasings against 4 different Live snapshots through both versions and diffing
the output byte for byte. That comparison lived in a throwaway script, so it
proved the split once and then evaporated.

This module makes the comparison permanent. It sits alongside
``test_live_intent_rule_order``'s source-text check rather than replacing it:
reordering the four stage calls is behaviour even where today's corpus cannot tell
the two orders apart, and only one of the two tests can notice a reorder that is
not equivalent. The corpus is stored in ``live_intent_parse_expectations.jsonl``,
one JSON object per phrasing per snapshot, and every row is the parse itself
rather than a hand-written summary of it.

Why the rows were captured from code rather than written by hand: there are 384 of
them, and a hand-written expectation is a second implementation of the parser. It
would agree with the code on every phrasing its author happened to run and quietly
disagree everywhere else, which is the failure mode this file exists to catch. So
they were recorded by running the corpus, then READ. Reading is the part that
matters and it does not scale past a few dozen rows, which is the other reason the
rows have to be stored rather than regenerated on every run.

Provenance: recorded against the pre-split parser at ``91b1b255`` (2 Oct 2026,
live_intent.py, 3938 lines) and re-run against the split driver plus the four
stage modules on the same corpus. The two runs are byte-identical, so the stored
rows are what the parser produced before the stages existed.

The displayed-track clarification change on 2 Oct updates two ambiguous-snapshot
rows: "the vocal on its own" and "vocal down 2 dB" now ask which track, instead
of reporting no match. Both still have no action; the other 382 rows are unchanged.

What makes the fixture stale, and what to do about it:

* A phrasing or a stage changes what it parses. Expected, and only the refactor
  that intends it should regenerate -- with ``KENN_RECORD_LIVE_INTENT_EXPECTATIONS=1``,
  which rewrites this file and prints every row it changed. Read that list. An
  unexplained action change is a behaviour change nobody looked at.
* A phrasing or a stage is deleted. The rows for it still assert the old parse, so
  the deletion fails here rather than passing unnoticed.
* A rule is added for a phrasing the corpus does not contain. Nothing notices. The
  corpus is the ceiling on what is pinned, and adding a phrasing is the only way to
  raise it.
"""

from __future__ import annotations

import json
import os
from pathlib import Path

import pytest

from kenn.core.live_intent import parse_request

FIXTURE = Path(__file__).resolve().parent / "live_intent_parse_expectations.jsonl"
RECORD_ENV = "KENN_RECORD_LIVE_INTENT_EXPECTATIONS"

# Four states, because the parser reads the snapshot as well as the wording. The
# same phrasing can be a write against one set, a question against the next and a
# refusal against the last, and a corpus run against only one of them would pin
# almost nothing.
SNAPSHOTS: dict[str, dict] = {
    # Eight tracks, two returns and three scenes: every rule has something to bind
    # to, so this state exercises the writes.
    "full": {
        "status": "connected",
        "tracks": [
            {"index": 0, "name": "Kick", "volume": 0.5, "devices": [
                {"index": 0, "name": "EQ Eight"}, {"index": 1, "name": "Compressor"}]},
            {"index": 1, "name": "Snare / Clap", "volume": 0.5, "devices": [{"index": 0, "name": "EQ Eight"}]},
            {"index": 2, "name": "Hi-Hats", "volume": 0.5, "devices": []},
            {"index": 3, "name": "Drum Bus", "volume": 0.5, "devices": [{"index": 0, "name": "EQ Eight"}]},
            {"index": 4, "name": "Bass", "volume": 0.5, "devices": [{"index": 0, "name": "EQ Eight"}]},
            {"index": 5, "name": "Synth", "volume": 0.5, "devices": [{"index": 0, "name": "Auto Release"}]},
            {"index": 6, "name": "Lead Vocal", "volume": 0.5, "devices": [{"index": 0, "name": "EQ Eight"}]},
            {"index": 7, "name": "FX Print", "volume": 0.5, "devices": []},
        ],
        "return_tracks": [{"index": 0, "name": "A-Reverb"}, {"index": 1, "name": "B-Delay"}],
        "scenes": [{"index": 0, "name": "Intro"}, {"index": 1, "name": "Chorus"}, {"index": 2, "name": "Outro"}],
    },
    # Lead Vocal and Backing Vocal both hold the word "vocal", so "vocal down 2 dB"
    # is a question here and a write in the full set.
    "ambiguous": {
        "status": "connected",
        "tracks": [
            {"index": 0, "name": "Lead Vocal", "volume": 0.5, "devices": []},
            {"index": 1, "name": "Backing Vocal", "volume": 0.5, "devices": []},
        ],
        "return_tracks": [{"index": 0, "name": "A-Reverb"}],
        "scenes": [{"index": 0, "name": "Chorus"}],
    },
    # Nothing to bind to: every track rule has to ask rather than default to index 0.
    "empty": {"status": "connected", "tracks": []},
    # Tracks are present but carry no level, so a relative dB change cannot be
    # computed and the parse has to say so instead of reading a stale 0.5.
    "no_volume": {
        "status": "connected",
        "tracks": [
            {"index": 0, "name": "Kick", "devices": [{"index": 0, "name": "EQ Eight"}]},
            {"index": 1, "name": "Bass", "devices": []},
        ],
        "return_tracks": [],
        "scenes": [{"index": 0, "name": "Chorus"}],
    },
}

# The fields a caller acts on, flattened so each stored row is a flat object and a
# diff shows one changed field rather than a rewritten blob. Keys whose value is
# None or [] are dropped on both sides, which is why a field going from nothing to
# something still fails: the live row gains a key the stored one does not have.
SCALARS = (
    "mode", "action", "error", "scene", "clip_slot", "source_clip_slot", "target_clip_slot",
    "locator_name", "return_track_name", "new_track_name", "unit", "requested_unit", "relative",
    "confidence", "confirmation_required", "desired_value", "absolute_value", "requested_relative_db",
)
# Nested dicts reduced to the keys that name them, so an index or a device choice
# shows up without the whole structure moving.
NESTED = ("track", "device", "parameter", "track_reference")
NESTED_KEYS = frozenset({"index", "name", "number", "kind"})


def _round(value):
    # volume_law is deterministic, so this is not hiding float drift; it keeps 0.85
    # from being written as 0.8499999999999996 by a future repr.
    if isinstance(value, bool) or not isinstance(value, float):
        return value
    return round(value, 6)


def _project(parsed: dict) -> dict:
    row: dict = {"said": parsed.get("query")}
    row.update({key: _round(parsed.get(key)) for key in SCALARS})
    for key in NESTED:
        nested = parsed.get(key)
        row[key] = None if not isinstance(nested, dict) else {
            k: _round(v) for k, v in sorted(nested.items()) if k in NESTED_KEYS}
    row["missing_fields"] = list(parsed.get("missing_fields") or [])
    row["ambiguity"] = [str(line) for line in (parsed.get("ambiguity") or [])]
    return {k: v for k, v in row.items() if v is not None and v != []}


def _stored() -> list[dict]:
    return [json.loads(line) for line in FIXTURE.read_text(encoding="utf-8").splitlines() if line.strip()]


def _serialise(rows: list[dict]) -> str:
    return "".join(json.dumps(row, sort_keys=True, ensure_ascii=False) + "\n" for row in rows)


def _parse_every_row() -> list[dict]:
    return [{"q": q, "snap": name, **_project(parse_request(q, SNAPSHOTS[name]))}
            for q, name in ((row["q"], row["snap"]) for row in _stored())]


def test_the_corpus_still_parses_the_way_it_did_before_the_stages_were_split() -> None:
    """384 parses, one per phrasing per snapshot, against the recorded output."""
    stored = _stored()
    parsed = _parse_every_row()
    if os.environ.get(RECORD_ENV) == "1":
        changed = [(old["q"], old["snap"]) for old, new in zip(stored, parsed) if old != new]
        FIXTURE.write_text(_serialise(parsed), encoding="utf-8")
        print(f"\nrewrote {len(parsed)} rows in {FIXTURE.name}; {len(changed)} changed:")
        for phrasing, name in changed:
            print(f"  {name}: {phrasing!r}")
        return
    drifted = []
    for old, new in zip(stored, parsed):
        if old == new:
            continue
        differing = {k: (old.get(k), new.get(k)) for k in set(old) | set(new) if old.get(k) != new.get(k)}
        drifted.append(f"  {old['snap']}: {old['q']!r} -> {differing}")
    assert not drifted, (
        f"{len(drifted)} of {len(stored)} parses changed:\n" + "\n".join(drifted[:40]))


# Every action name the corpus reaches. The set is the whole point: a rule that stops
# matching leaves its row asserting the old action, and a rule that starts matching
# a new phrasing leaves this set short of what the parser can now name.
# set_tempo is here because _tempo_request writes it into a dict bound to `fields`
# (live_intent.py:2065), a local name that test_live_intent_rule_order's AST scan
# does not look at, so that file's CHAIN_ACTIONS is one action narrower than the
# parser really is.
CORPUS_ACTIONS = frozenset({
    "add_locator", "create_audio_track", "create_midi_track", "create_return_track", "duplicate_clip",
    "focus_device", "focus_track", "gain_stage_tracks", "group_tracks", "insert_device",
    "insert_device_with_parameter", "insert_eq_band_tuning_gain", "inspect_device_parameters",
    "inspect_devices", "inspect_tracks", "launch_scene", "remove_locator", "rename_clip", "rename_track",
    "set_arm", "set_device_parameter", "set_eq_band_gain", "set_eq_band_tuning_gain", "set_mute", "set_pan",
    "set_return_mute", "set_return_pan", "set_return_volume", "set_send", "set_solo", "set_tempo",
    "set_volume", "stop_clip", "transport_play", "transport_stop",
})

# The questions the corpus reaches. A request it cannot answer is half the behaviour:
# the generic miss reads back as "KENN didn't understand" where a named missing field
# reads back as "by how much?", and the chat layer shows the difference to the producer.
# "action" is the generic miss itself, and it is here because two phrasings reach it:
# they resolve a track and then no rule behind the ladder wants them.
CORPUS_MISSING_FIELDS = frozenset({
    "action", "amount", "clip_action", "current_volume", "device", "device_action",
    "master_track_action", "pan_side", "return_track_action", "scene", "scene_action",
    "send_amount", "single_action", "source_track", "target_track", "track", "transport_target",
    "valid_volume", "which_track",
})


def test_the_corpus_reaches_every_action_and_every_question_it_claims_to() -> None:
    rows = _stored()
    reached = {row["action"] for row in rows if row.get("action")}
    assert reached == CORPUS_ACTIONS, f"actions moved: {sorted(reached ^ CORPUS_ACTIONS)}"
    asked = {field for row in rows for field in row.get("missing_fields", [])}
    assert asked == CORPUS_MISSING_FIELDS, f"missing fields moved: {sorted(asked ^ CORPUS_MISSING_FIELDS)}"
    assert {row["mode"] for row in rows} == {"assist", "inspect", "refuse"}


def test_the_four_session_states_each_change_at_least_one_parse() -> None:
    """67 of the 96 phrasings parse differently across the four snapshots.

    If a state changed nothing, its 96 rows would be 96 duplicates of another
    state's and the corpus would be a quarter of the size it looks like.
    """
    rows = _stored()
    phrasings = sorted({row["q"] for row in rows})
    assert len(phrasings) == 96
    differing = 0
    for phrasing in phrasings:
        states = [row for row in rows if row["q"] == phrasing]
        assert sorted(row["snap"] for row in states) == sorted(SNAPSHOTS)
        decided = {(row.get("action"), row.get("desired_value"), tuple(row.get("missing_fields", [])),
                    (row.get("track") or {}).get("index")) for row in states}
        if len(decided) > 1:
            differing += 1
    assert differing == 67, f"the snapshot spread moved: {differing} phrasings differ across the four states"


@pytest.mark.parametrize("phrasing, snapshot", [
    ("kill playback on the kick", "full"),
    ("pan track 2 hard left", "full"),
])
def test_the_corpus_row_exists_for_the_two_phrasings_the_mutation_hunt_needed(phrasing, snapshot) -> None:
    """The two phrasings that made an unreachable branch observable are pinned here.

    Without them in the corpus, dropping "playback" from the mute-slang exclusion
    list and demoting pan_hard_match under pan_match both went unnoticed.
    """
    assert any(row["q"] == phrasing and row["snap"] == snapshot for row in _stored())
