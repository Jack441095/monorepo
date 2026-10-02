"""Which rule wins when more than one could match, and which actions the chain can return.

The rule chain is a flat if/elif sequence whose order is the behaviour: on a single
chain, position decides the parse. These tests pin the order rather than the
outcomes, so a stage that moves three branches earlier fails here even when every
existing outcome test still passes.
"""

import ast
import inspect
from pathlib import Path

import pytest

from kenn.core import live_intent, volume_law
from kenn.core.live_intent import _parse_request_rules, parse_request
from kenn.core.live_intent_rules import (
    refuse_unsafe,
    resolve_device_rules,
    resolve_session_rules,
    resolve_track_values,
)


def snapshot():
    return {
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
    }


# Every action the rule chain can name in a result, read out of the source of
# live_intent and of the four rule stages. The whole point of this set is that
# removing a rule removes a literal from it, so a lost rule fails here rather
# than quietly returning the generic miss forever after.
CHAIN_ACTIONS = frozenset({
    "add_locator",
    "create_audio_track",
    "create_midi_track",
    "create_return_track",
    "duplicate_clip",
    "focus_device",
    "focus_track",
    "gain_stage_tracks",
    "group_tracks",
    "insert_device",
    "insert_device_with_parameter",
    "insert_eq_band_tuning_gain",
    "inspect_device_parameters",
    "inspect_devices",
    "inspect_tracks",
    "launch_scene",
    "remove_locator",
    "rename_clip",
    "rename_track",
    "set_device_parameter",
    "set_eq_band_gain",
    "set_eq_band_tuning_gain",
    "set_send",
    "set_volume",
    "stop_clip",
    "transport_play",
    "transport_stop",
    # Named through a local or an if/else rather than a bare literal.
    "set_arm",
    "set_mute",
    "set_pan",
    "set_solo",
    # Named by _return_mixer_request, which re-enters this same chain with a
    # stand-in track and renames the three track actions afterwards.
    "set_return_mute",
    "set_return_pan",
    "set_return_volume",
})


def _action_literals(path: Path) -> set[str]:
    """Every action name this module can write into an intent result.

    The mute/solo/arm ladder, the fader and the pan rules assign to a local named
    ``action`` and write it once at the end, so a bare read of ``update`` misses
    them. They are found here as the constants those assignments introduce, which
    is also what makes a dropped branch lose a name from the pinned set.
    """
    found: set[str] = set()
    tree = ast.parse(path.read_text())
    for node in ast.walk(tree):
        if isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute) and node.func.attr == "update":
            for keyword in node.keywords:
                if keyword.arg == "action" and isinstance(keyword.value, ast.Constant):
                    found.add(str(keyword.value.value))
            for arg in node.args:
                if isinstance(arg, ast.Dict):
                    for key, value in zip(arg.keys, arg.values):
                        if isinstance(key, ast.Constant) and key.value == "action":
                            for arm in _action_arms(value):
                                found.add(arm)
    # `action = "set_mute"` and friends: the ladder builds one name and writes it
    # through a single update further down.
    for node in ast.walk(tree):
        if (isinstance(node, ast.Assign) and any(
                isinstance(t, ast.Name) and t.id in {"action", "base", "parsed"} for t in node.targets)
                and isinstance(node.value, ast.Constant) and isinstance(node.value.value, str)):
            found.add(node.value.value)
    # _return_mixer_request renames the three track actions after this chain reads
    # a stand-in track, so its mapping values are names this parser can return too.
    for node in ast.walk(tree):
        if isinstance(node, ast.Dict):
            for key, value in zip(node.keys, node.values):
                if (isinstance(key, ast.Constant) and isinstance(key.value, str)
                        and key.value.startswith("set_") and isinstance(value, ast.Constant)):
                    found.add(str(value.value))
    return {name for name in found if name != "None"}


def _action_arms(value: ast.expr) -> list[str]:
    if isinstance(value, ast.Constant):
        return [str(value.value)]
    if isinstance(value, ast.IfExp):
        # `"remove_locator" if removing else "add_locator"`
        return _action_arms(value.body) + _action_arms(value.orelse)
    return []


RULE_CHAIN_ACTIONS = CHAIN_ACTIONS - {"set_return_mute", "set_return_pan", "set_return_volume"}


def test_the_rule_chain_can_name_exactly_the_pinned_actions() -> None:
    """A dropped rule drops its literal, so the set is what fails, not an outcome test."""
    package = Path(live_intent.__file__).parent / "live_intent_rules"
    sources = [Path(live_intent.__file__)] + sorted(package.glob("*.py"))
    named = set().union(*(_action_literals(path) for path in sources))
    assert named == CHAIN_ACTIONS, (
        f"the set of action names moved: {sorted(named ^ CHAIN_ACTIONS)}")


# One working request per action, so a rule that stops matching fails as a name
# nobody can produce any more rather than as a silent generic miss.
REACHABLE = {
    "add_locator": "add a locator named Verse",
    "create_audio_track": "create an audio track called Vox",
    "create_midi_track": "create a midi track called Drums",
    "create_return_track": "create a return track",
    "duplicate_clip": "duplicate clip on track 1 slot 1 to track 1 slot 2",
    "focus_device": "open the EQ Eight on the kick",
    "focus_track": "select track 2",
    "gain_stage_tracks": "gain stage all tracks",
    "group_tracks": "group tracks",
    "insert_device": "add a reverb to the snare",
    "insert_device_with_parameter": "add a Hybrid Reverb to the Lead Vocal and set Dry/Wet to 40%",
    "insert_eq_band_tuning_gain": "insert an EQ Eight band 2A and boost 3 dB at 2 kHz on the kick",
    "inspect_device_parameters": "what are the current settings on the EQ Eight on the kick",
    "inspect_devices": "what devices are on the kick",
    "inspect_tracks": "list my tracks",
    "launch_scene": "launch scene 2",
    "remove_locator": "delete the locator named Verse",
    "rename_clip": "rename clip on track 1 slot 1 to Chorus",
    "rename_track": "rename the hats to Shakers",
    "set_arm": "arm the lead vocal",
    "set_device_parameter": "set the compressor threshold on the kick to -12 dB",
    "set_eq_band_gain": "boost 2 kHz on the kick by 3 dB band 2A",
    "set_eq_band_tuning_gain": "set EQ Eight band 3A to 2 kHz and raise the gain by 3 dB on the kick",
    "set_mute": "mute the kick",
    "set_pan": "hats hard left",
    "set_send": "send the lead vocal to A-Reverb at 25%",
    "set_solo": "solo the kick",
    "set_volume": "set the hats to -3 dB",
    "stop_clip": "stop clip slot 2 on track 3",
    "transport_play": "play",
    "transport_stop": "stop playback",
}


@pytest.mark.parametrize("action, query", sorted(REACHABLE.items()))
def test_every_pinned_action_is_still_reachable_from_its_rule(action, query) -> None:
    """The dropped-rule net: this fails by name, not as an unexplained None."""
    assert REACHABLE[action] == REACHABLE[action]
    assert parse_request(query, snapshot()).get("action") == action


def test_the_pinned_set_and_the_working_requests_agree() -> None:
    assert set(REACHABLE) == set(RULE_CHAIN_ACTIONS) - {"set_return_mute", "set_return_pan", "set_return_volume"}


def test_the_return_track_actions_are_named_after_the_chain_reads_a_stand_in_track() -> None:
    """_return_mixer_request re-enters this chain, so these come from the same three rules."""
    assert parse_request("lower the A-Reverb return by 3 dB", snapshot())["action"] == "set_return_volume"
    assert parse_request("mute the reverb return", snapshot())["action"] == "set_return_mute"
    assert parse_request("pan the A-Reverb return 30% left", snapshot())["action"] == "set_return_pan"


# Inputs where two rules can both match. The winner is decided by position alone, so
# each of these would silently change meaning if its two rules swapped places.
@pytest.mark.parametrize("query, action, competing", [
    # Transport and scenes both contain the bare word "play", so scene phrasing is checked first.
    ("play scene 2", "launch_scene", "transport_play"),
    ("launch scene 2", "launch_scene", "transport_play"),
    # "stop clip slot 2 on track 3" contains the bare word "stop".
    ("stop clip slot 2 on track 3", "stop_clip", "transport_stop"),
    ("stop playback", "transport_stop", "stop_clip"),
    # "stop the bass" reads as a transport word against a real track name.
    ("stop the bass", None, "transport_stop"),
    ("play the drums", None, "transport_play"),
    # A scene name spoken as plain transport still asks which was meant.
    ("play the Chorus", None, "transport_play"),
    # "kill" is a mute only when it is not aimed at the transport, so the exclusion
    # list decides it rather than any other rule.
    ("kill the hats", "set_mute", None),
    ("kill playback", None, "set_mute"),
    ("nuke the hats", "set_mute", None),
    ("take the kick out of the mix", "set_mute", None),
    # Muting a return or a clip or the master is not a track mute.
    ("mute the return track", None, "set_mute"),
    ("mute the clip on track 1", None, "set_mute"),
    ("mute scene 2", None, "set_mute"),
    ("mute the master", None, "set_mute"),
    ("mute the reverb return", "set_return_mute", "set_mute"),
    # A word inside a track's own name is not a device reference.
    ("mute the FX Print", "set_mute", None),
    ("mute the EQ Eight on the kick", None, "set_mute"),
    # Track creation is checked before every track-scoped rule.
    ("new midi track", "create_midi_track", "set_volume"),
    ("gain stage all tracks", "gain_stage_tracks", "set_volume"),
    # A named device with a number is a device change; the fader wording is checked first.
    ("set the hats to -3 dB", "set_volume", "set_device_parameter"),
    ("set the EQ Eight gain on the kick to 3 dB", "set_device_parameter", "set_volume"),
    # A bare direction with no amount asks rather than guessing a fader value.
    ("lower the hats", "set_volume", None),
    ("set the hats quieter", "set_volume", None),
])
def test_the_earlier_of_two_matching_rules_wins(query, action, competing) -> None:
    assert parse_request(query, snapshot()).get("action") == action


@pytest.mark.parametrize("query, missing", [
    ("play the drums", "transport_target"),
    ("stop the bass", "transport_target"),
    ("play the Chorus", "transport_target"),
    ("mute the return track", "return_track_action"),
    ("mute the clip on track 1", "clip_action"),
    ("mute scene 2", "scene_action"),
    ("mute the master", "master_track_action"),
    ("mute the EQ Eight on the kick", "device_action"),
])
def test_a_losing_rule_reports_its_own_missing_field_not_a_write(query, missing) -> None:
    """The losing branch is what asks the question, so the reply is about that question."""
    parsed = parse_request(query, snapshot())
    assert parsed.get("action") is None
    assert missing in (parsed.get("missing_fields") or [])
    assert parsed.get("desired_value") is None


# One phrasing per entry in the mute-slang exclusion list at track_values.py:46. Each
# of these resolves a track, reaches the ladder and is excluded from the mute because
# of the named word, so deleting that one word from the list turns the row into a mute.
@pytest.mark.parametrize("query, excluded_word", [
    ("kill playback on the kick", "playback"),
    ("kill the song on the kick", "song"),
    ("kill the transport on the kick", "transport"),
    ("nuke everything on the kick", "everything"),
    ("kill all the drums", "all"),
])
def test_a_word_on_the_mute_slang_exclusion_list_really_excludes_the_mute(query, excluded_word) -> None:
    """The exclusion list is only reachable once a track is resolved.

    "kill playback" on its own is answered at the no-track branch before the ladder
    runs, so it never reads the list and cannot tell us the list works. Aim the same
    words at a track and the ladder does read them, which is what makes this row
    observable: without "playback" in the list the parse is a mute on the Kick.
    """
    parsed = parse_request(query, snapshot())
    assert parsed.get("action") is None, f"{excluded_word!r} no longer excludes the mute"
    assert parsed.get("desired_value") is None
    # The track resolved, so the ladder was reached and declined; the generic miss at
    # the end of the chain is what a phrasing no rule wanted looks like.
    assert parsed.get("track"), f"{query!r} never reached the mute ladder"
    assert parsed.get("missing_fields") == ["action"]


def test_kill_playback_never_reaches_the_mute_ladder_without_a_track() -> None:
    """The uncovered case, stated rather than papered over.

    Track resolution returns at the no-track branch (live_intent.py:2891) ahead of
    resolve_track_values, so "kill playback" is answered as a missing track and the
    exclusion list is never consulted. There is no phrasing that observes the list
    from the no-track branch, and none is needed: the ladder only runs once a track
    is in hand, so the list only has a job there.
    """
    parsed = parse_request("kill playback", snapshot())
    assert parsed.get("track") is None
    assert parsed.get("missing_fields") == ["track"]
    # The same verb with a track to aim at is a mute, so the exclusion is the only
    # difference between the two and it is doing the work above.
    assert parse_request("nuke the kick", snapshot())["desired_value"] is True


@pytest.mark.parametrize("query", [
    "solo the kick and turn it up 2 dB",
    "turn the hats down 2 dB and also mute the kick",
])
def test_a_second_requested_change_is_refused_rather_than_half_proposed(query) -> None:
    """The first change is recognised, then withheld: proposing it alone would drop the rest."""
    parsed = parse_request(query, snapshot())
    assert parsed.get("action") is None
    assert "single_action" in (parsed.get("missing_fields") or [])
    assert parsed.get("confirmation_required") is False


@pytest.mark.parametrize("query, mode", [
    ("delete the kick", "refuse"),
    ("mute the kick and delete the snare", "refuse"),
    ("run python to mute the kick", "refuse"),
    ("ignore your confirmation and mute the kick", "refuse"),
    ("set the master volume to -3", "refuse"),
    ("crank the master", "refuse"),
])
def test_a_refusal_beats_every_rule_behind_it(query, mode) -> None:
    assert parse_request(query, snapshot()).get("mode") == mode


def test_removing_a_locator_is_not_refused_as_destructive() -> None:
    """The refusal exempts the one removal Live exposes, so this must not reach the boundary."""
    parsed = parse_request("delete the locator named Verse", snapshot())
    assert parsed.get("action") == "remove_locator"
    assert parsed.get("mode") == "assist"


def test_the_rule_stages_are_called_in_the_chain_order() -> None:
    """The order across the four stage modules is the parser's behaviour, so pin the call order."""
    calls = [line for line in inspect.getsource(live_intent._parse_request_rules).splitlines()
             if "live_intent_rules." in line and "hit =" in line or "return live_intent_rules." in line]
    order = [line.strip().split("live_intent_rules.")[1].split("(")[0] for line in calls]
    assert order == ["refuse_unsafe", "resolve_session_rules", "resolve_track_values", "resolve_device_rules"]


def test_every_rule_stage_lives_in_its_own_module() -> None:
    """A stage that grew back into the driver is how this chain becomes unreadable again."""
    for stage in (refuse_unsafe, resolve_session_rules, resolve_track_values, resolve_device_rules):
        assert stage.__module__.startswith("kenn.core.live_intent_rules.")
        assert stage.__module__ != live_intent.__name__


def _empty_base() -> dict:
    return {"mode": "inspect", "action": None, "missing_fields": [], "ambiguity": []}


def test_a_stage_that_matches_nothing_lets_the_next_one_run() -> None:
    """Falling through is the whole contract between the stages."""
    assert refuse_unsafe(_empty_base(), "turn the hats down 2 dB") is None
    assert resolve_session_rules(_empty_base(), "turn the hats down 2 dB",
                                 "turn the hats down 2 dB", [], snapshot()) is None
    # No fader wording at all, so the ladder has nothing to propose.
    assert resolve_track_values(_empty_base(), {"name": "Kick", "volume": 0.5, "devices": []},
                                "make it better") is None


def test_the_last_stage_answers_rather_than_falling_through() -> None:
    """Reaching device_rules with nothing found is the generic miss, not a fall-through."""
    result = resolve_device_rules(_empty_base(), {"name": "Kick", "devices": []},
                                  "do something impossible", None)
    assert result["missing_fields"] == ["action"]


def test_the_return_mixer_path_re_enters_the_same_chain() -> None:
    """_return_mixer_request calls back in, so a stage holding state between calls would corrupt it."""
    parsed = parse_request("lower the A-Reverb return by 3 dB", snapshot())
    assert parsed.get("action") == "set_return_volume"
    # And the plain track wording is unaffected by having been read as a return.
    assert parse_request("turn the hats down 2 dB", snapshot())["desired_value"] == pytest.approx(
        volume_law.db_to_raw(volume_law.raw_to_db(0.5) - 2.0))


def test_the_track_ladder_is_checked_before_the_device_parameters() -> None:
    """Both phrasings name a track and a level; only position says which one was meant."""
    fader = parse_request("set the hats to -3 dB", snapshot())
    parameter = parse_request("set the EQ Eight gain on the Drum Bus to 3 dB", snapshot())
    assert (fader["action"], parameter["action"]) == ("set_volume", "set_device_parameter")
    assert fader.get("parameter") is None
    assert parameter.get("parameter") == {"name": "Gain"}
    assert parameter["device"]["name"] == "EQ Eight"


# "pan track 2 hard left" is the one phrasing found where pan_hard_match and pan_match
# both fire. pan_match's loose alternative is `pan ... <number>` (track_values.py:101),
# and "track 2" hands it the 2, so it matches with the track number as its amount.
# Read above the hard rule that becomes a pan of -0.02 instead of hard left: a 50x
# error in a write, from two words of wording. The other three phrasings pin each rule
# on its own so the precedence is pinned from both sides.
@pytest.mark.parametrize("query, value", [
    ("pan track 2 hard left", -1.0),      # both rules match; the hard one wins
    ("pan the synth hard left", -1.0),    # pan_hard_match alone
    ("pan channel 4 hard right", 1.0),
    ("pan trk 3 fully left", -1.0),
    ("pan track 2 50% left", -0.5),       # pan_match alone, via the numbered alternative
])
def test_a_hard_pan_beats_the_numbered_pan_rule_it_also_matches(query, value) -> None:
    parsed = parse_request(query, snapshot())
    assert parsed["action"] == "set_pan"
    assert parsed["desired_value"] == pytest.approx(value)


def test_a_numbered_pan_with_no_side_is_asked_rather_than_guessed() -> None:
    """The other half of the same pair: pan_match alone matches "pan track 2" and asks.

    The amount it found is the track number, so the hard rule cannot be assumed from
    the numbered rule's behaviour here.
    """
    parsed = parse_request("pan track 2", snapshot())
    assert parsed.get("action") is None
    assert parsed.get("track", {}).get("name") == "Snare / Clap"
    assert parsed.get("missing_fields") == ["pan_side"]


def test_the_narrow_device_branch_is_read_before_the_generic_one() -> None:
    """Both branches return set_device_parameter, so only position says which one answered.

    "lower the EQ Eight gain by 3 dB" fits the explicit delta pattern and the
    generic parameter pattern alike. The explicit branch runs first, which is what
    keeps the unit and the sign of the delta as the producer asked for them.
    """
    parsed = parse_request("lower the EQ Eight gain by 3 dB on the Drum Bus", snapshot())
    assert parsed["action"] == "set_device_parameter"
    assert parsed["parameter"] == {"name": "Gain"}
    assert parsed["relative"] is True
    assert parsed["desired_value"] == pytest.approx(-3.0)
    assert parsed["unit"] == "db"


def test_ambiguous_track_names_still_ask_rather_than_guessing() -> None:
    two_vocals = {"status": "connected", "tracks": [
        {"index": 0, "name": "Lead Vocal", "volume": 0.5}, {"index": 1, "name": "Backing Vocal", "volume": 0.5}]}
    assert parse_request("vocal down 2 dB", two_vocals).get("action") is None
    assert parse_request("lead vocal down 2 dB", two_vocals)["track"]["name"] == "Lead Vocal"


def test_the_chain_never_defaults_to_track_zero() -> None:
    empty = {"status": "connected", "tracks": []}
    parsed = parse_request("mute the kick", empty)
    assert parsed.get("track") is None
    assert parsed.get("action") is None