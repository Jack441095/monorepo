"""Strict structural beat observations without Live, cached snapshots or exports."""

from __future__ import annotations

from copy import deepcopy
from dataclasses import FrozenInstanceError

import pytest

from kenn.ableton_osc_bridge import AbletonOSCClient
from kenn.core.arrangement_bounds import (
    ArrangementBoundsError, ArrangementBoundsReader, MAX_CLIPS,
    MAX_CLIPS_PER_TRACK, MAX_LABEL_BYTES, MAX_TRACKS,
)


_COUNT = "/live/song/get/num_tracks"
_NAMES = "/live/song/get/track_names"
_SONG_LENGTH = "/live/song/get/song_length"
_CLIP_NAMES = "/live/track/get/arrangement_clips/name"
_CLIP_LENGTHS = "/live/track/get/arrangement_clips/length"
_CLIP_STARTS = "/live/track/get/arrangement_clips/start_time"
_READS = {_COUNT, _NAMES, _SONG_LENGTH, _CLIP_NAMES, _CLIP_LENGTHS, _CLIP_STARTS}


class _Transport:
    """Serve the bundled handler's echoed-index shape with per-batch failures."""

    def __init__(self, tracks=None, song_length=160.0):
        self.tracks = deepcopy(tracks if tracks is not None else [
            {"name": "Drums", "clips": [("Verse", 16.0, 32.0), ("Outro", 96.0, 8.0)]},
            {"name": "Bass", "clips": [("Full", 8.0, 80.0)]},
        ])
        self.song_length = song_length
        self.calls = []
        self.overrides = {}
        self.after_batch = lambda *_: None

    def __call__(self, requests):
        self.calls.append(deepcopy(requests))
        batch = len(self.calls)
        replies = []
        for address, args in requests:
            assert address in _READS, "Only bundled structural read endpoints are allowed"
            index = args[0] if args else None
            if address == _COUNT:
                reply = [len(self.tracks)]
            elif address == _NAMES:
                reply = [track["name"] for track in self.tracks]
            elif address == _SONG_LENGTH:
                reply = [self.song_length]
            else:
                column = {_CLIP_NAMES: 0, _CLIP_STARTS: 1, _CLIP_LENGTHS: 2}[address]
                reply = [index] + [clip[column] for clip in self.tracks[index]["clips"]]
            replies.append(deepcopy(self.overrides.get((batch, address, index), reply)))
        self.after_batch(batch, self)
        return replies


def _reject(transport, code="invalid_reply", **kwargs):
    with pytest.raises(ArrangementBoundsError) as caught:
        ArrangementBoundsReader(transport, **kwargs).read()
    assert caught.value.code == code


def test_complete_repeated_reads_return_only_structural_beat_bounds():
    transport = _Transport()
    result = ArrangementBoundsReader(transport).read()

    assert len(transport.calls) == 6  # Two passes, each bracketed by track/song anchors.
    assert len(result.tracks) == 2
    assert result.clip_count == 3
    assert result.clip_start_beats == 8.0
    assert result.clip_end_beats == 104.0
    assert result.song_length_beats == 160.0
    assert result.tracks[0].clips[0].name == "Verse"
    assert not hasattr(result, "fingerprint")
    assert not hasattr(result, "source_kind")
    assert not hasattr(result, "render_start")
    assert not hasattr(result, "tail_policy")
    with pytest.raises(FrozenInstanceError):
        result.tracks[0].clips[0].start_beats = 0.0


@pytest.mark.parametrize("tracks", [[], [{"name": "Empty", "clips": []}]])
def test_explicit_empty_arrangements_keep_song_length_separate_from_clip_bounds(tracks):
    transport = _Transport(tracks)
    result = ArrangementBoundsReader(transport).read()
    assert result.clip_count == 0
    assert result.clip_start_beats is None and result.clip_end_beats is None
    assert result.song_length_beats == 160.0
    assert len(transport.calls) == (4 if not tracks else 6)


@pytest.mark.parametrize("address,index", [
    (_COUNT, None), (_NAMES, None), (_SONG_LENGTH, None),
    (_CLIP_NAMES, 0), (_CLIP_LENGTHS, 0), (_CLIP_STARTS, 0),
])
def test_missing_required_endpoint_never_becomes_an_empty_arrangement(address, index):
    # Unavailable clip columns previously looked like a valid empty inventory.
    transport = _Transport()
    batch = 1 if index is None else 2
    transport.overrides[batch, address, index] = None
    _reject(transport, "read_unavailable")


@pytest.mark.parametrize("address,value", [
    (_COUNT, []), (_COUNT, [True]), (_COUNT, [-1]), (_COUNT, [2.0]), (_COUNT, [2, 2]),
    (_NAMES, []), (_NAMES, ["Only one"]), (_NAMES, ["Drums", None]),
    (_NAMES, "Drums"), (_SONG_LENGTH, []), (_SONG_LENGTH, [1, 2]),
    (_SONG_LENGTH, [True]), (_SONG_LENGTH, ["160"]), (_SONG_LENGTH, [-1]),
    (_SONG_LENGTH, [float("nan")]), (_SONG_LENGTH, [float("inf")]),
    (_SONG_LENGTH, [10 ** 1000]), (_NAMES, ["\ud800", "Bass"]),
])
def test_malformed_track_anchor_is_rejected(address, value):
    transport = _Transport()
    transport.overrides[1, address, None] = value
    _reject(transport)


@pytest.mark.parametrize("address,value", [
    (_CLIP_NAMES, []), (_CLIP_NAMES, [1, "Verse", "Outro"]),
    (_CLIP_NAMES, [False, "Verse", "Outro"]), (_CLIP_NAMES, [0.0, "Verse", "Outro"]),
    (_CLIP_NAMES, [0, "Verse"]), (_CLIP_NAMES, [0, "Verse", 3]),
    (_CLIP_LENGTHS, [0, 32.0]), (_CLIP_STARTS, [0, 16.0, 96.0, 100.0]),
])
def test_columns_require_exact_echoes_labels_and_matching_counts(address, value):
    transport = _Transport()
    transport.overrides[2, address, 0] = value
    _reject(transport)


@pytest.mark.parametrize("address,value", [
    (_CLIP_LENGTHS, 0), (_CLIP_LENGTHS, -1), (_CLIP_LENGTHS, True),
    (_CLIP_LENGTHS, "32"), (_CLIP_LENGTHS, float("nan")),
    (_CLIP_STARTS, -1), (_CLIP_STARTS, False), (_CLIP_STARTS, float("inf")),
])
def test_clip_positions_and_lengths_are_finite_beats(address, value):
    transport = _Transport()
    transport.overrides[2, address, 0] = [0, value, 8.0]
    _reject(transport)


def test_finite_clip_values_with_overflowing_end_are_rejected():
    _reject(_Transport([{"name": "Overflow", "clips": [("Clip", 1e308, 1e308)]}]))


@pytest.mark.parametrize("address,value", [(_NAMES, ["Replaced", "Bass"]), (_SONG_LENGTH, [161.0])])
def test_anchor_changes_within_one_pass_are_rejected(address, value):
    transport = _Transport()
    transport.overrides[3, address, None] = value
    _reject(transport, "changed_during_read")


@pytest.mark.parametrize("address,value", [
    (_CLIP_NAMES, [0, "Replaced", "Outro"]),
    (_CLIP_LENGTHS, [0, 33.0, 8.0]), (_CLIP_STARTS, [0, 17.0, 96.0]),
])
def test_changed_clip_observation_between_passes_is_rejected(address, value):
    transport = _Transport()
    transport.overrides[5, address, 0] = value
    _reject(transport, "changed_during_read")


def test_track_count_budget_is_checked_before_any_clip_request():
    transport = _Transport([{"name": "Track", "clips": []}] * (MAX_TRACKS + 1))
    _reject(transport, "budget_exceeded")
    assert len(transport.calls) == 1


def test_exact_track_budget_remains_complete():
    tracks = [{"name": "Empty", "clips": []}] * MAX_TRACKS
    result = ArrangementBoundsReader(_Transport(tracks)).read()
    assert len(result.tracks) == MAX_TRACKS and result.clip_count == 0


@pytest.mark.parametrize("total", [False, True])
def test_clip_budgets_reject_excess_instead_of_returning_a_prefix(total):
    clips = [("Clip", 0.0, 1.0)] * (MAX_CLIPS_PER_TRACK if total else MAX_CLIPS_PER_TRACK + 1)
    tracks = [{"name": "Track", "clips": clips}] * (MAX_CLIPS // MAX_CLIPS_PER_TRACK + 1 if total else 1)
    _reject(_Transport(tracks), "budget_exceeded")


def test_exact_clip_budget_and_unicode_label_byte_budget_are_accepted():
    # These limits count clips and UTF-8 bytes; slicing either hides source data.
    label = "界" * (MAX_LABEL_BYTES // 3) + "ab"
    clips = [(label, 0.0, 1.0)] * MAX_CLIPS_PER_TRACK
    tracks = [{"name": label, "clips": clips}] * (MAX_CLIPS // MAX_CLIPS_PER_TRACK)
    result = ArrangementBoundsReader(_Transport(tracks)).read()
    assert result.clip_count == MAX_CLIPS


@pytest.mark.parametrize("track_label", [False, True])
def test_label_budget_is_measured_in_utf8_bytes(track_label):
    label = "界" * (MAX_LABEL_BYTES // 3 + 1)
    tracks = [{"name": label if track_label else "Track", "clips": [("Clip" if track_label else label, 0.0, 1.0)]}]
    _reject(_Transport(tracks), "budget_exceeded")


@pytest.mark.parametrize("reply", [None, {}, [], [[], [], [], []]])
def test_transport_batch_shape_must_match_every_requested_endpoint(reply):
    _reject(lambda _: reply)


def test_transport_exception_has_an_explicit_unavailable_code():
    def unavailable(_):
        raise OSError("Synthetic transport failure")
    _reject(unavailable, "read_unavailable")


def test_late_reply_cannot_publish_even_when_all_values_match():
    now = [0.0]
    transport = _Transport()
    transport.after_batch = lambda *_: now.__setitem__(0, 11.0)
    _reject(transport, "read_deadline", clock=lambda: now[0])
    assert len(transport.calls) == 1


def test_deadline_includes_the_final_anchor_reply():
    now = [0.0]
    transport = _Transport()
    transport.after_batch = lambda batch, _: now.__setitem__(0, 10.0 if batch == 6 else 0.0)
    _reject(transport, "read_deadline", clock=lambda: now[0])
    assert len(transport.calls) == 6


@pytest.mark.parametrize("timeout", [0, -1, 11, 10 ** 1000, True, "10", float("nan"), float("inf")])
def test_invalid_deadline_is_rejected_before_transport(timeout):
    transport = _Transport()
    with pytest.raises(ValueError, match="deadline"):
        ArrangementBoundsReader(transport).read(timeout_seconds=timeout)
    assert transport.calls == []


def test_failures_do_not_reuse_old_observations_and_instances_are_isolated():
    first, second = _Transport(), _Transport([{"name": "Other", "clips": [("Only", 2.0, 3.0)]}])
    reader, other = ArrangementBoundsReader(first), ArrangementBoundsReader(second)
    prior = reader.read()
    assert other.read().clip_end_beats == 5.0
    first.overrides[7, _NAMES, None] = None
    with pytest.raises(ArrangementBoundsError, match="did not answer"):
        reader.read()
    first.tracks[0]["clips"][0] = ("New", 200.0, 1.0)
    assert reader.read().clip_end_beats == 201.0
    assert prior.clip_end_beats == 104.0
    assert other.read().clip_end_beats == 5.0


def test_existing_bridge_batch_seam_is_read_only_and_never_uses_snapshot_cache():
    transport = _Transport()
    client = AbletonOSCClient.__new__(AbletonOSCClient)
    client._cached_session_state = {"status": "connected", "tracks": [], "song_length": 9999.0}

    def fake_responses(requests):
        return [{"args": reply} if reply is not None else None for reply in transport(requests)]

    def forbidden(*_, **__):
        pytest.fail("Structural reads must not use cached snapshots, aggregate fallback or mutations")

    client._request_responses_many = fake_responses
    client.query_session_state = forbidden
    client.query_session_understanding = forbidden
    client.get_arrangement_clips = forbidden
    client._send_only = forbidden
    result = ArrangementBoundsReader(client._query_many).read()
    assert result.clip_end_beats == 104.0 and result.song_length_beats == 160.0
    assert all(address in _READS for batch in transport.calls for address, _ in batch)
    assert all("/get/" in address for batch in transport.calls for address, _ in batch)
    assert client._cached_session_state["song_length"] == 9999.0
