from composition.melody_arp_octave_resolve import (
    resolve_melody_unisons_vs_arp_by_interval,
)


def _event(channel: int, pitch: int, start: float, duration: float) -> tuple:
    return (channel, pitch, 100, start, duration, [pitch])


def test_overlapping_melody_arp_unison_is_shifted_by_interval() -> None:
    melody = [_event(2, 60, 0.0, 1.0)]
    arp = [_event(3, 60, 0.5, 1.0)]

    resolved = resolve_melody_unisons_vs_arp_by_interval(
        melody,
        arp,
        enabled=True,
        interval_semitones=7,
    )

    assert resolved == [(2, 67, 100, 0.0, 1.0, [67])]


def test_non_overlapping_unison_and_disabled_pass_are_unchanged() -> None:
    melody = [_event(2, 60, 0.0, 1.0)]
    later_arp = [_event(3, 60, 1.0, 1.0)]

    assert resolve_melody_unisons_vs_arp_by_interval(
        melody,
        later_arp,
        enabled=True,
    ) == melody
    assert resolve_melody_unisons_vs_arp_by_interval(
        melody,
        [_event(3, 60, 0.5, 1.0)],
        enabled=False,
    ) == melody
