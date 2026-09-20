from composition.evaluation import evaluate_song
from composition.song_postprocess.texture_floors import reduce_song_lead_arp_overlap


def _dense_lead_arp_overlap_events():
    events = []
    for bar in range(4):
        start = float(bar * 4)
        events.append((2, 72, 92, start + 0.25, 0.75, [72]))
        for step in (0.0, 0.5, 1.0, 1.5, 2.0, 2.5, 3.0, 3.5):
            events.append((3, 67, 78, start + step, 0.25, [67]))
    return events


def test_reduce_song_lead_arp_overlap_lowers_masking_metric():
    events = _dense_lead_arp_overlap_events()
    before = evaluate_song(events, beats_per_bar=4.0, bars=4)

    out, meta = reduce_song_lead_arp_overlap(
        events,
        section_bars=[16],
        section_roles=["verse"],
        beats_per_bar=4.0,
        min_arp_per_bar=2,
        min_arp_per_bar_chorus=4,
        velocity_duck=16,
    )
    after = evaluate_song(out, beats_per_bar=4.0, bars=4)

    assert meta["enabled"] is True
    assert meta["removed_events"] + meta["ducked_events"] + meta["shortened_events"] > 0
    assert after.lead_arp_overlap < before.lead_arp_overlap


def test_reduce_song_lead_arp_overlap_stronger_for_high_overlap_emotion():
    events = _dense_lead_arp_overlap_events()
    before = evaluate_song(events, beats_per_bar=4.0, bars=4)

    out_default, _meta_default = reduce_song_lead_arp_overlap(
        events,
        section_bars=[16],
        section_roles=["verse"],
        beats_per_bar=4.0,
    )
    out_pride, meta_pride = reduce_song_lead_arp_overlap(
        events,
        section_bars=[16],
        section_roles=["verse"],
        beats_per_bar=4.0,
        primary_emotion="pride",
    )
    after_default = evaluate_song(out_default, beats_per_bar=4.0, bars=4)
    after_pride = evaluate_song(out_pride, beats_per_bar=4.0, bars=4)

    assert meta_pride["enabled"] is True
    assert after_pride.lead_arp_overlap <= after_default.lead_arp_overlap
    assert after_pride.lead_arp_overlap < before.lead_arp_overlap


def test_reduce_song_lead_arp_overlap_stronger_for_love():
    events = _dense_lead_arp_overlap_events()
    before = evaluate_song(events, beats_per_bar=4.0, bars=4)

    out_default, _meta_default = reduce_song_lead_arp_overlap(
        events,
        section_bars=[16],
        section_roles=["verse"],
        beats_per_bar=4.0,
        primary_emotion="approval",
    )
    out_love, meta_love = reduce_song_lead_arp_overlap(
        events,
        section_bars=[16],
        section_roles=["verse"],
        beats_per_bar=4.0,
        primary_emotion="love",
    )
    after_default = evaluate_song(out_default, beats_per_bar=4.0, bars=4)
    after_love = evaluate_song(out_love, beats_per_bar=4.0, bars=4)

    assert meta_love["enabled"] is True
    assert after_love.lead_arp_overlap <= after_default.lead_arp_overlap
    assert after_love.lead_arp_overlap < before.lead_arp_overlap


def test_reduce_song_lead_arp_overlap_preserves_lead():
    events = _dense_lead_arp_overlap_events()
    out, _meta = reduce_song_lead_arp_overlap(
        events,
        section_bars=[16],
        section_roles=["verse"],
        beats_per_bar=4.0,
    )
    lead = [ev for ev in out if ev[0] == 2]
    assert len(lead) == 4
