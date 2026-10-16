"""Observe complete, repeated Arrangement clip positions through read-only OSC.

This module samples structural beat bounds only. It does not authenticate
audio content, unsaved automation or plug-in state, choose an effect-tail policy,
or convert musical positions into Live's Export dialog strings. It is deliberately
independent of OfflineScanService and has no production runtime wiring. The
existing OSC replies have no request nonce or set epoch: matching delayed replies
can satisfy a request, so uncached sampling does not prove current-source freshness.
"""

from __future__ import annotations

from dataclasses import dataclass
import math
import time
from typing import Any, Callable


MAX_TRACKS = 256  # Regular tracks per complete structural observation.
MAX_CLIPS_PER_TRACK = 256  # Arrangement clips; excess is rejected, never truncated.
MAX_CLIPS = 4096  # Arrangement clips across all tracks in one observation.
MAX_LABEL_BYTES = 512  # UTF-8 bytes per track or clip label.
MAX_READ_SECONDS = 10.0  # One deadline covers both complete observations.

_ANCHOR_REQUESTS = (
    ("/live/song/get/num_tracks", None),
    ("/live/song/get/track_names", None),
    ("/live/song/get/song_length", None),
)
_CLIP_ENDPOINTS = (
    "/live/track/get/arrangement_clips/name",
    "/live/track/get/arrangement_clips/length",
    "/live/track/get/arrangement_clips/start_time",
)
_QueryMany = Callable[[list[tuple[str, list[Any] | None]]], list[list[Any] | None]]


class ArrangementBoundsError(ValueError):
    """Reject an incomplete observation with a stable reason and no cached fallback."""

    def __init__(self, code: str, message: str):
        super().__init__(message)
        self.code = code


@dataclass(frozen=True)
class ArrangementClip:
    index: int
    name: str
    start_beats: float
    length_beats: float


@dataclass(frozen=True)
class ArrangementTrack:
    index: int
    name: str
    clips: tuple[ArrangementClip, ...]


@dataclass(frozen=True)
class ArrangementStructureObservation:
    """Retain structural clip positions; never use this as an audio-source token.

    Empty arrangements have None clip bounds, including when Live reports a
    positive song length. Matching repeated reads do not establish atomicity or
    detect delayed replies or a change reverted between reads. Song length is
    retained separately because it is not a qualified effect-tail boundary.
    """

    tracks: tuple[ArrangementTrack, ...]
    song_length_beats: float

    @property
    def clip_count(self) -> int:
        return sum(len(track.clips) for track in self.tracks)

    @property
    def clip_start_beats(self) -> float | None:
        return min((clip.start_beats for track in self.tracks for clip in track.clips), default=None)

    @property
    def clip_end_beats(self) -> float | None:
        return max((clip.start_beats + clip.length_beats for track in self.tracks for clip in track.clips), default=None)


def _number(value: Any, *, positive: bool = False) -> float:
    try:
        number = float(value) if type(value) in {int, float} else math.nan
    except OverflowError:
        # OSC integers outside float range cannot name a finite beat position.
        number = math.nan
    if not math.isfinite(number) or number < 0 or (positive and number == 0):
        raise ArrangementBoundsError("invalid_reply", "Arrangement beat values must be finite and nonnegative; clip lengths must be positive.")
    return number


def _label(value: Any) -> str:
    if not isinstance(value, str):
        raise ArrangementBoundsError("invalid_reply", "Arrangement labels must be strings.")
    try:
        size = len(value.encode("utf-8"))
    except UnicodeEncodeError:
        # A malformed label cannot participate in an exact repeated observation.
        raise ArrangementBoundsError("invalid_reply", "Arrangement labels must be valid UTF-8.") from None
    if size > MAX_LABEL_BYTES:
        raise ArrangementBoundsError("budget_exceeded", "An arrangement label exceeds the 512-byte limit.")
    return value


class ArrangementBoundsReader:
    """Read through an injected OSC batch callable, without snapshots or writes.

    Bind an existing AbletonOSCClient._query_many callable when explicitly
    qualifying this reader. Its deadline bounds result acceptance, not runtime:
    the transport must bound each call itself, and this reader cannot interrupt
    a blocked call. Budgets limit accepted result size after transport allocation;
    they do not bound the injected transport's allocation or prove reply freshness.
    """

    def __init__(self, query_many: _QueryMany, *, clock: Callable[[], float] = time.monotonic):
        self._query_many = query_many
        self._clock = clock

    def _deadline(self, deadline: float) -> None:
        if self._clock() >= deadline:
            raise ArrangementBoundsError("read_deadline", "The structural arrangement read exceeded its deadline.")

    def _batch(self, requests: list[tuple[str, list[Any] | None]], deadline: float) -> list[list[Any]]:
        self._deadline(deadline)
        try:
            replies = self._query_many(requests)
        except Exception:
            # A transport failure is unavailable evidence, never an empty set.
            raise ArrangementBoundsError("read_unavailable", "The structural arrangement transport failed.") from None
        self._deadline(deadline)
        if not isinstance(replies, list) or len(replies) != len(requests):
            raise ArrangementBoundsError("invalid_reply", "The arrangement batch reply is incomplete or malformed.")
        if any(reply is None for reply in replies):
            raise ArrangementBoundsError("read_unavailable", "A required arrangement endpoint did not answer.")
        if any(not isinstance(reply, list) for reply in replies):
            raise ArrangementBoundsError("invalid_reply", "Arrangement endpoint arguments must be lists.")
        return replies

    def _anchor(self, deadline: float) -> tuple[tuple[str, ...], float]:
        counts, names, lengths = self._batch(list(_ANCHOR_REQUESTS), deadline)
        if len(counts) != 1 or type(counts[0]) is not int or counts[0] < 0:
            raise ArrangementBoundsError("invalid_reply", "A complete nonnegative track count is required.")
        if counts[0] > MAX_TRACKS or len(names) > MAX_TRACKS:
            raise ArrangementBoundsError("budget_exceeded", "The arrangement exceeds the 256-track limit.")
        if len(names) != counts[0] or len(lengths) != 1:
            raise ArrangementBoundsError("invalid_reply", "Track names and song length must match the complete count reply.")
        return tuple(_label(name) for name in names), _number(lengths[0])

    def _observe(self, deadline: float) -> ArrangementStructureObservation:
        anchor = self._anchor(deadline)
        requests = [(endpoint, [index]) for index in range(len(anchor[0])) for endpoint in _CLIP_ENDPOINTS]
        # A zero-track set needs no clip request. Its empty anchor still has to
        # answer again, so a timeout cannot masquerade as an empty arrangement.
        replies = self._batch(requests, deadline) if requests else []
        tracks: list[ArrangementTrack] = []
        total = 0
        for index, name in enumerate(anchor[0]):
            columns = replies[index * 3:index * 3 + 3]
            if any(not column or type(column[0]) is not int or column[0] != index for column in columns):
                raise ArrangementBoundsError("invalid_reply", "Each arrangement column must echo its exact track index.")
            sizes = {len(column) - 1 for column in columns}
            if len(sizes) != 1:
                raise ArrangementBoundsError("invalid_reply", "Arrangement clip columns have different lengths.")
            count = sizes.pop()
            total += count
            if count > MAX_CLIPS_PER_TRACK or total > MAX_CLIPS:
                raise ArrangementBoundsError("budget_exceeded", "The arrangement exceeds the 256 clips per track or 4096 total clips limit.")
            clips: list[ArrangementClip] = []
            for position in range(count):
                clip_name = _label(columns[0][position + 1])
                length = _number(columns[1][position + 1], positive=True)
                start = _number(columns[2][position + 1])
                if not math.isfinite(start + length):
                    raise ArrangementBoundsError("invalid_reply", "An arrangement clip end is not finite.")
                clips.append(ArrangementClip(position, clip_name, start, length))
            tracks.append(ArrangementTrack(index, name, tuple(clips)))
        if self._anchor(deadline) != anchor:
            raise ArrangementBoundsError("changed_during_read", "Arrangement track identity or song length changed during the read.")
        return ArrangementStructureObservation(tuple(tracks), anchor[1])

    def read(self, *, timeout_seconds: float = MAX_READ_SECONDS) -> ArrangementStructureObservation:
        """Return two matching complete reads or raise without retaining old results."""
        if type(timeout_seconds) not in {int, float} or not 0 < timeout_seconds <= MAX_READ_SECONDS:
            raise ValueError("The structural read deadline must be positive and at most 10 seconds.")
        deadline = self._clock() + timeout_seconds
        first = self._observe(deadline)
        second = self._observe(deadline)
        if first != second:
            raise ArrangementBoundsError("changed_during_read", "Arrangement clip structure changed between complete reads.")
        self._deadline(deadline)
        return second
