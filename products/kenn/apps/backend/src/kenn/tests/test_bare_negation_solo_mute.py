"""A bare negation on a solo or a mute, with no verb to carry it.

Round 9's mix-notes register (2026-09-30) found that every negation pattern in ``live_intent.py`` required a verb --
turn, switch, take -- so "Lead Vocal off solo" matched the positive branch and KENN soloed a track the producer had
asked it to un-solo. That is the worst class of bug in this file: the write lands, reads back cleanly and is
journalled as verified, so nothing downstream can notice. The test cases below are the exact wordings that were wrong.
"""

from __future__ import annotations

import pytest

from kenn.core.fake_live import FakeLiveBackend
from kenn.core.live_intent import parse_request


@pytest.fixture(scope="module")
def snapshot():
    return FakeLiveBackend().query_session_state()


@pytest.mark.parametrize("request_text, action, track, value", [
    # The round-9 find, and the two shapes that failed the same way.
    ("Lead Vocal off solo", "set_solo", "Lead Vocal", False),
    ("Lead Vocal no solo", "set_solo", "Lead Vocal", False),
    ("Lead Vocal solo off", "set_solo", "Lead Vocal", False),
    ("Kick mute off", "set_mute", "Kick", False),
    ("Lead Vocal off mute", "set_mute", "Lead Vocal", False),
    # The verb-carrying forms that already worked, pinned so the bare form cannot be fixed by breaking these.
    ("take the Lead Vocal off solo", "set_solo", "Lead Vocal", False),
    ("un-solo the Lead Vocal", "set_solo", "Lead Vocal", False),
    ("turn the vocal back on", "set_mute", "Lead Vocal", False),
    # The positive forms, pinned because "off" must not leak the other way.
    ("Lead Vocal solo", "set_solo", "Lead Vocal", True),
    ("Lead Vocal mute", "set_mute", "Lead Vocal", True),
    ("solo the Lead Vocal", "set_solo", "Lead Vocal", True),
    ("put the Bass on solo", "set_solo", "Bass", True),
    ("let me hear the synth alone", "set_solo", "Synth", True),
])
def test_a_bare_negation_on_solo_or_mute_is_not_read_as_the_opposite(snapshot, request_text, action, track, value) -> None:
    parsed = parse_request(request_text, snapshot)
    assert parsed["action"] == action, f"{request_text!r} parsed as {parsed['action']}, wanted {action}"
    assert parsed["track"]["name"] == track
    assert parsed["desired_value"] is value, f"{request_text!r} would write {parsed['desired_value']}, wanted {value}"
    assert not parsed["missing_fields"]


def test_the_negation_only_bites_next_to_solo_or_mute(snapshot) -> None:
    """"off" on its own still means switch off, which is a mute on -- the new pattern must not reach any further."""
    parsed = parse_request("Lead Vocal off", snapshot)
    assert parsed["action"] == "set_mute" and parsed["desired_value"] is True
