"""Chat decides between changing Live and answering from the notes the way the rule parser reads the message."""

from __future__ import annotations

import pytest

from kenn.core.chat_live_router import asks_how_to, wants_live_change
from kenn.core.fake_live import FakeLiveBackend


@pytest.fixture()
def demo() -> dict:
    return FakeLiveBackend().query_session_state()


# 26 Sept 2026: these reached the notes, because they didn't open with one of the chat's command verbs.
@pytest.mark.parametrize("request_text", [
    "can you solo the hats",
    "bump the synth up 1 dB",
    "Send the synth to A-Reverb 30 percent",
    "I want to send 50% of the snare and clap to the B-Delay to add some depth, could you handle that?",
    "drumbus down 2 dB",
    "go to the kick",
])
def test_requests_worded_any_way_reach_live(demo, request_text) -> None:
    assert wants_live_change(request_text, demo)


# 26 Sept 2026: these came back as Live proposals (the Synth turned down, a Glue Compressor, a mute).
@pytest.mark.parametrize("question", [
    "I'm mixing vocals and they sound a bit muddy. How can I make them clearer without losing their warmth?",
    "My drum tracks have a lot of low-end rumble. What's a quick way to clean them up without affecting the punch?",
    "I need a way to quickly mute the bass during a breakdown without affecting the rest of the track.",
    "I want to add more depth to my synth sounds, but I don't want it to sound muddy or too processed.",
    "how do I mute a track",
])
def test_asking_how_stays_with_the_notes(demo, question) -> None:
    assert asks_how_to(question)
    assert not wants_live_change(question, demo)


def test_nothing_goes_to_live_without_a_connected_set() -> None:
    assert not wants_live_change("mute the kick", {"status": "offline", "tracks": []})
    assert not wants_live_change("mute the kick", None)


# 26 Sept 2026, a sealed set of chat messages written by Qwen3 8B on the box: 76% of requests reached Live on first
# score. These are the general shapes it found; none of them changed anything before.
@pytest.mark.parametrize("request_text, action, track", [
    ("Can you lower the bass a bit?", "set_volume", "Bass"),                      # asks by how much
    ("The kick is too loud, can you bring it down to -16?", "set_volume", "Kick"),
    ("bring the kick down to -16, it's too loud", "set_volume", "Kick"),
    ("I need the lead vocal back to center, please.", "set_pan", "Lead Vocal"),
    ("Just make sure the snare is centered.", "set_pan", "Snare / Clap"),
    ("I need the drum bus muted for now.", "set_mute", "Drum Bus"),
    ("Focus on the hi-hats for a moment.", "focus_track", "Hi-Hats"),
    ("Let's focus on the lead vocal track.", "focus_track", "Lead Vocal"),
])
def test_everyday_chat_wording_reads_as_the_request(demo, request_text, action, track) -> None:
    from kenn.core.live_intent import parse_request

    intent = parse_request(request_text, demo)
    assert intent["action"] == action and intent["track"]["name"] == track


@pytest.mark.parametrize("not_a_request", [
    "the drum bus is muted",                      # describing the set
    "the kick is too loud",                       # a complaint, no request
    "just the kick",                              # still means solo the kick, not a stripped "just"
    "send a track out to my hardware compressor and back into Live",
])
def test_the_new_wording_rules_leave_these_alone(demo, not_a_request) -> None:
    from kenn.core.live_intent import parse_request

    intent = parse_request(not_a_request, demo)
    assert intent.get("action") in {None, "set_solo"} and "send_amount" not in (intent.get("missing_fields") or [])


def test_a_send_without_an_amount_asks_how_much(demo) -> None:
    from kenn.core.live_intent import parse_request

    assert "send_amount" in parse_request("Could you send the synth to the A-Reverb?", demo)["missing_fields"]
    assert wants_live_change("Could you send the synth to the A-Reverb?", demo)


@pytest.mark.parametrize("negated", ["don't mute the drum bus", "please don't solo the kick", "never arm the synth",
                                     "do not pan the bass left"])
def test_a_negated_request_changes_nothing(demo, negated) -> None:
    # Every build to 27 Sept 2026 dropped the "don't" and proposed exactly what was asked not to be done.
    from kenn.core.live_intent import parse_request

    intent = parse_request(negated, demo)
    assert intent.get("action") is None and intent["missing_fields"] == ["negated"]
    assert intent["ambiguity"] == ["Okay, I'll leave it as it is. Nothing changed."]


@pytest.mark.parametrize("description", ["the vocal is sent to the reverb at 20%", "the vocal is panned 20% left"])
def test_describing_a_send_or_pan_is_not_a_request(demo, description) -> None:
    from kenn.core.live_intent import parse_request

    assert parse_request(description, demo).get("action") is None


def test_asking_for_an_opinion_stays_with_the_notes(demo) -> None:
    assert not wants_live_change("The kick is too loud, do you think I should bring it down?", demo)


def test_naming_the_device_but_not_the_setting_asks_which(demo) -> None:
    # "set the compressor on the drum bus to -12 dB": before, "on the drum bus" was taken as the setting's name.
    from kenn.core.live_intent import parse_request

    intent = parse_request("Can you set the compressor on the drum bus to -12 dB?", demo)
    assert intent["action"] == "set_device_parameter" and intent["missing_fields"] == ["parameter"]
    assert intent["ambiguity"][0].startswith("Which Compressor setting should change?")


@pytest.mark.parametrize("text, track", [("rather than solo the kick, mute the snare", "Snare / Clap"),
                                         ("instead of soloing the kick, mute the snare", "Snare / Clap"),
                                         ("instead of muting the drum bus, turn it down 3 dB", "Drum Bus")])
def test_instead_of_acts_on_the_second_clause(demo, text, track) -> None:
    # 27 Sept 2026: "rather than solo the kick, mute the snare" proposed muting the Kick.
    from kenn.core.live_intent import parse_request

    assert parse_request(text, demo)["track"]["name"] == track


@pytest.mark.parametrize("text, missing", [("mute the drum bus lol jk", "negated"), ("mute the drum bus? nah", "negated"),
                                           ("tomorrow mute the drum bus", "deferred"),
                                           ("remember to mute the drum bus later", "deferred")])
def test_taken_back_or_for_later_changes_nothing_now(demo, text, missing) -> None:
    from kenn.core.live_intent import parse_request

    intent = parse_request(text, demo)
    assert intent.get("action") is None and intent["missing_fields"] == [missing]


@pytest.mark.parametrize("text, tracks", [
    ("turn the kick and snare down 2 dB", ["Kick", "Snare / Clap"]),
    ("mute the kick, the snare and the hats", ["Kick", "Snare / Clap", "Hi-Hats"]),
    ("pan the kick and bass left 20%", ["Kick", "Bass"]),
])
def test_every_track_named_is_changed_not_just_the_first(demo, text, tracks) -> None:
    # 27 Sept 2026: the first two changed only the Kick, and only the Kick and Hi-Hats, with no word about the rest.
    from kenn.core.live_intent import parse_natural_recipe

    recipe = parse_natural_recipe(text, demo)
    assert [step["track_name"] for step in recipe["steps"]] == tracks


def test_a_half_that_cannot_be_done_stops_the_whole_request(demo) -> None:
    from kenn.core.live_intent import parse_natural_recipe

    # Before, the Synth went up and the vocal was silently left out.
    recipe = parse_natural_recipe("turn the synth and vocal up 1 dB", demo)
    assert recipe["steps"] == []
    assert recipe["ambiguity"] == ["Step 2: 'Lead Vocal' is at 0.0 dB, so up 1 dB would take it above 0 dB, "
                                   "which KENN doesn't set."]


@pytest.mark.parametrize("text, missing", [("turn the kick up -3 dB", "amount"),
                                           ("pan the kick 20% left and 20% right", "pan_side")])
def test_a_contradiction_asks_instead_of_picking_one(demo, text, missing) -> None:
    # 27 Sept 2026: "up -3 dB" went up 3 dB, and a pan naming both sides went left.
    from kenn.core.live_intent import parse_request

    intent = parse_request(text, demo)
    assert intent.get("action") is None and intent["missing_fields"] == [missing]


def test_two_tracks_panned_opposite_ways_are_two_steps(demo) -> None:
    # Before, "pan the kick left and the bass right" panned only the Kick.
    from kenn.core.live_intent import parse_natural_recipe

    recipe = parse_natural_recipe("pan the kick hard left and the bass hard right", demo)
    assert [(step["track_name"], step["value"]) for step in recipe["steps"]] == [("Kick", -1.0), ("Bass", 1.0)]
