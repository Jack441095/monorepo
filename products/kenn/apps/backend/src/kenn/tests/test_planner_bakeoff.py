import scripts.planner_bakeoff as bakeoff
from kenn.core import live_command


def test_production_snapshot_attaches_parameter_evidence_like_the_gateway(monkeypatch) -> None:
    seen = {}

    def fake_plan(command, snapshot):
        seen[command] = snapshot
        return None, {"status": "rejected"}

    monkeypatch.setattr(live_command, "_generate_llm_plan", fake_plan)
    # run() normally writes LLM settings into os.environ; keep them out of later tests.
    monkeypatch.setattr(bakeoff, "_configure", lambda model: None)
    cases = [{"query": "set the drum bus compressor threshold to -12 dB", "expected_action": "set_device_parameter"},
             {"query": "mute the snare", "expected_action": "set_mute"}]
    bakeoff.run("stub-model", cases, production_snapshot=True)
    entries = (seen[cases[0]["query"]].get("planner_capabilities") or {}).get("entries") or []
    assert entries and entries[0]["device_name"] == "Compressor"
    assert "planner_capabilities" not in seen[cases[1]["query"]]

    seen.clear()
    bakeoff.run("stub-model", cases[:1])
    assert "planner_capabilities" not in seen[cases[0]["query"]]
