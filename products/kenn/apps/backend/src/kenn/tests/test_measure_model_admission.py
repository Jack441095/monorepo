"""The offline probe must distinguish overlapping requests from a serialized control."""

import json
import threading

import pytest

from kenn.core import answer_upgrades
from kenn.llm import llm_rewrite as llm
from scripts import measure_model_admission as tool


@pytest.mark.parametrize("surface", ["payload", "stream"])
@pytest.mark.parametrize("serialized", [False, True])
def test_admission_probe_counts_overlap_only_while_both_provider_requests_are_active(surface, serialized):
    # The serialized transport is a counterfactual control, not a production admission fix.
    result = tool.probe(surface, serialize_transport=serialized)
    assert result["peak_provider_requests"] == (1 if serialized else 2)
    assert result["foreground_entered_before_background_release"] is not serialized
    assert result["second_background_blocked"] is True
    assert result["background_status"] == "rejected"
    assert result["foreground_errors"] == []
    assert result["provider_calls"] == [
        {"owner": "background", "stream": False, "think": False},
        {"owner": "foreground", "stream": surface == "stream", "think": False},
    ]


def test_admission_probe_restores_state_and_does_not_contact_a_model_or_write_caches(monkeypatch):
    def forbidden(*args, **kwargs):
        raise AssertionError("Offline admission probe contacted a provider or wrote data")

    monkeypatch.setattr(llm, "_get_client", forbidden)
    monkeypatch.setattr(llm, "_cache_get", forbidden)
    monkeypatch.setattr(llm, "_cache_put", forbidden)
    monkeypatch.setattr(answer_upgrades, "log_outcome", forbidden)
    turns, results, lock, busy = (answer_upgrades._TURNS, answer_upgrades._RESULTS,
                                answer_upgrades._LOCK, answer_upgrades._BUSY)
    for surface in ("payload", "stream", "payload"):
        assert tool.probe(surface)["foreground_errors"] == []
        assert answer_upgrades._TURNS is turns and answer_upgrades._RESULTS is results
        assert answer_upgrades._LOCK is lock and answer_upgrades._BUSY is busy
        assert llm._get_client is forbidden and llm._cache_put is forbidden
    assert not any(thread.name.startswith("kenn-answer-upgrade-")
                   or thread.name == "kenn-admission-probe" for thread in threading.enumerate())


@pytest.mark.parametrize("require_single, expected", [(False, 0), (True, 1)])
def test_admission_probe_cli_can_fail_the_single_request_requirement(monkeypatch, capsys, require_single, expected):
    monkeypatch.setattr("sys.argv", ["measure_model_admission.py"]
                        + (["--require-single-request"] if require_single else []))
    assert tool.main() == expected
    receipt = json.loads(capsys.readouterr().out)
    assert receipt["kind"] == "offline_admission_probe" and receipt["latency_measured"] is False
    assert len(receipt["rows"]) == 2 and "Fixture" not in json.dumps(receipt)


def test_admission_probe_rejects_an_unknown_surface():
    with pytest.raises(ValueError, match="Unknown surface"):
        tool.probe("unknown")
