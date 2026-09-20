from tools.song_quality_audit import analyze_song_events, quality_score_from_metrics


def _healthy_events():
    events = []
    for bar in range(4):
        start = float(bar * 4)
        events.append((0, 36, 82, start, 4.0, [36]))
        events.append((1, 60, 72, start, 4.0, [60, 64, 67]))
        events.append((2, 72 + (bar % 3), 76, start + 0.25, 0.75, [72 + (bar % 3)]))
        events.append((2, 74 + (bar % 3), 75, start + 1.5, 0.5, [74 + (bar % 3)]))
        events.append((3, 67, 64, start + 2.0, 0.5, [67]))
    return events


def test_quality_score_accepts_core_song_shape():
    metrics = analyze_song_events(
        _healthy_events(),
        bars=4,
        section_roles=["intro", "a", "b", "outro"],
    )
    score, issues = quality_score_from_metrics(metrics)

    assert metrics["missing_core_channels"] == []
    assert metrics["melody_events_per_bar"] == 2.0
    assert score >= 75.0
    assert "missing core channels" not in "; ".join(issues)


def test_quality_score_penalizes_missing_melody():
    events = [event for event in _healthy_events() if event[0] != 2]
    metrics = analyze_song_events(events, bars=4, section_roles=["intro", "a", "b", "outro"])
    score, issues = quality_score_from_metrics(metrics)

    assert metrics["missing_core_channels"] == ["melody"]
    assert score < 70.0
    assert any("missing core channels" in issue for issue in issues)


def test_quality_score_flags_phrase_boundary_crowding():
    events = _healthy_events()
    events.append((2, 79, 78, 15.9, 0.5, [79]))
    metrics = analyze_song_events(events, bars=8, section_roles=["intro", "a", "b", "outro"])
    score, issues = quality_score_from_metrics(metrics)

    assert metrics["melody_boundary_crowding_count"] >= 1
    assert score < 100.0
    assert any("phrase boundaries" in issue for issue in issues)


def test_quality_score_penalizes_deeper_quality_report_warnings():
    metrics = analyze_song_events(
        _healthy_events(),
        bars=4,
        section_roles=["intro", "a", "b", "outro"],
    )
    quality_report = {
        "checks": {
            "singable_lead_range": False,
            "bass_not_static": False,
            "memorable_hook": True,
            "chorus_stronger_than_verse": True,
            "lead_not_too_empty": True,
        },
        "values": {
            "lead_pitch_range": 31,
            "lead_max_leap": 15,
            "bass_static_sections": [1],
        },
    }

    score, issues = quality_score_from_metrics(metrics, quality_report)

    assert score < 85.0
    assert any("singability" in issue for issue in issues)
    assert any("bass motion" in issue for issue in issues)


def test_velocity_jump_metric_ignores_long_re_entries():
    events = [
        (3, 67, 90, 0.0, 0.5, [67]),
        (3, 67, 30, 40.0, 0.5, [67]),
    ]

    metrics = analyze_song_events(events, bars=12)

    assert metrics["max_velocity_jump_ratio"] == 1.0
