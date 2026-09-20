from pathlib import Path
import importlib.util
import json
import stat

P = Path(__file__).resolve().parents[5] / "tooling" / "scripts" / "soak_companion.py"
S = importlib.util.module_from_spec(spec := importlib.util.spec_from_file_location("soak_companion", P)); spec.loader.exec_module(S)

def _health(status="connected", *, ok=True, proposals=0, receipts=0, reviews=0):
    return {"ok": ok, "subsystems": {
        "abletonosc": {"status": status},
        "runtime_state": {
            "pending_proposals": proposals, "pending_proposals_limit": 11_000,
            "action_receipts": receipts, "action_receipts_limit": 10_000,
            "mix_reviews": reviews, "mix_reviews_limit": 500,
        },
    }}

def test_soak_passes_bounded_healthy_samples():
    values = iter([100, 110, 120])
    result = S.run(endpoint="http://x", pid=7, samples=3, interval=1,
        fetcher=lambda _: _health(),
        stat_reader=lambda _: {"rss_bytes": next(values), "thread_count": 4}, sleeper=lambda _: None)
    assert result["qualified"] is True
    assert result["summary"]["rss_growth_bytes"] == 20
    assert result["summary"]["rss_peak_growth_bytes"] == 20
    assert result["summary"]["peak_thread_growth"] == 0
    assert result["runner_sha256"] == S.runner_sha256()
    assert result["progress"] == {
        "status": "complete", "complete": True,
        "completed_sample_count": 3, "expected_sample_count": 3,
    }

def test_soak_checkpoints_each_sample_but_never_marks_partial_as_qualified():
    checkpoints = []
    result = S.run(endpoint="http://x", pid=7, samples=3, interval=1,
        fetcher=lambda _: _health(),
        stat_reader=lambda _: {"rss_bytes": 100, "thread_count": 4}, sleeper=lambda _: None,
        revision="revision-test", checkpoint=checkpoints.append)

    assert result["qualified"] is True
    assert len(checkpoints) == 3
    assert [item["sample_count"] for item in checkpoints] == [1, 2, 3]
    assert all(item["qualified"] is False for item in checkpoints)
    assert all(item["progress"]["complete"] is False for item in checkpoints)
    assert checkpoints[-1]["source_git_commit"] == "revision-test"
    assert checkpoints[-1]["runner_sha256"] == S.runner_sha256()

def test_soak_checkpoint_write_is_atomic_and_private(tmp_path):
    destination = tmp_path / "nested" / "soak.json"
    value = {"schema": S.SCHEMA, "qualified": False, "progress": {"complete": False}}

    S.write_checkpoint(destination, value)

    assert json.loads(destination.read_text()) == value
    assert stat.S_IMODE(destination.stat().st_mode) == 0o600
    assert list(destination.parent.glob(".*.tmp")) == []

def test_soak_fails_on_health_error_or_excess_growth():
    values = iter([0, 200 * 1024 * 1024])
    result = S.run(endpoint="http://x", pid=7, samples=2, interval=1,
        fetcher=lambda _: _health("unknown", ok=False), stat_reader=lambda _: {"rss_bytes": next(values), "thread_count": 2}, sleeper=lambda _: None)
    assert result["qualified"] is False
    assert result["summary"]["error_samples"] == 2

def test_soak_fails_on_transient_rss_spike_even_if_final_rss_recovers():
    values = iter([100, 200 * 1024 * 1024, 100])
    result = S.run(endpoint="http://x", pid=7, samples=3, interval=1,
        fetcher=lambda _: _health(),
        stat_reader=lambda _: {"rss_bytes": next(values), "thread_count": 2}, sleeper=lambda _: None)
    assert result["summary"]["rss_growth_bytes"] == 0
    assert result["summary"]["rss_peak_growth_bytes"] > 128 * 1024 * 1024
    assert result["qualified"] is False

def test_soak_fails_on_transient_thread_spike_even_if_threads_recover():
    threads = iter([4, 13, 4])
    result = S.run(endpoint="http://x", pid=7, samples=3, interval=1,
        fetcher=lambda _: _health(),
        stat_reader=lambda _: {"rss_bytes": 100, "thread_count": next(threads)}, sleeper=lambda _: None)
    assert result["summary"]["thread_end_count"] == 4
    assert result["summary"]["peak_thread_growth"] == 9
    assert result["qualified"] is False

def test_soak_qualifies_an_observed_disconnect_and_reconnect():
    statuses = iter(["connected", "offline", "offline", "connected"])
    result = S.run(endpoint="http://x", pid=7, samples=4, interval=10,
        min_ableton_reconnects=1, max_ableton_outage_seconds=20,
        require_ableton_connected_end=True,
        fetcher=lambda _: _health(next(statuses)),
        stat_reader=lambda _: {"rss_bytes": 100, "thread_count": 4}, sleeper=lambda _: None)
    assert result["qualified"] is True
    assert result["summary"]["ableton_disconnect_events"] == 1
    assert result["summary"]["ableton_reconnect_events"] == 1
    assert result["summary"]["longest_ableton_outage_seconds"] == 20
    assert result["summary"]["ableton_connected_at_end"] is True

def test_soak_fails_when_required_reconnect_is_missing_or_outage_is_too_long():
    statuses = iter(["connected", "offline", "offline", "offline"])
    result = S.run(endpoint="http://x", pid=7, samples=4, interval=10,
        min_ableton_reconnects=1, max_ableton_outage_seconds=20,
        require_ableton_connected_end=True,
        fetcher=lambda _: _health(next(statuses)),
        stat_reader=lambda _: {"rss_bytes": 100, "thread_count": 4}, sleeper=lambda _: None)
    assert result["qualified"] is False
    assert result["summary"]["ableton_reconnect_events"] == 0
    assert result["summary"]["longest_ableton_outage_seconds"] == 30
    assert result["summary"]["ableton_connected_at_end"] is False

def test_soak_records_bounded_runtime_state_growth():
    counts = iter([(2, 5, 8), (3, 6, 9), (4, 8, 10)])
    def fetcher(_):
        proposals, receipts, reviews = next(counts)
        return _health(proposals=proposals, receipts=receipts, reviews=reviews)
    result = S.run(endpoint="http://x", pid=7, samples=3, interval=1,
        fetcher=fetcher, stat_reader=lambda _: {"rss_bytes": 100, "thread_count": 4}, sleeper=lambda _: None)
    assert result["qualified"] is True
    assert result["summary"]["runtime_state"]["pending_proposals"]["growth"] == 2
    assert result["summary"]["runtime_state"]["action_receipts"]["maximum"] == 8
    assert result["summary"]["runtime_state"]["mix_reviews"]["end"] == 10

def test_soak_fails_closed_when_runtime_state_is_missing_or_over_limit():
    missing = S.run(endpoint="http://x", pid=7, samples=1, interval=1,
        fetcher=lambda _: {"ok": True, "subsystems": {"abletonosc": {"status": "connected"}}},
        stat_reader=lambda _: {"rss_bytes": 100, "thread_count": 4}, sleeper=lambda _: None)
    over_limit = S.run(endpoint="http://x", pid=7, samples=1, interval=1,
        fetcher=lambda _: _health(proposals=11_001),
        stat_reader=lambda _: {"rss_bytes": 100, "thread_count": 4}, sleeper=lambda _: None)
    assert missing["qualified"] is False
    assert over_limit["qualified"] is False
