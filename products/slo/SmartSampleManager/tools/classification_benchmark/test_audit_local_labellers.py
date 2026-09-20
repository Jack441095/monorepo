import importlib.util
from pathlib import Path


MODULE_PATH = Path(__file__).with_name("audit_local_labellers.py")
SPEC = importlib.util.spec_from_file_location("audit_local_labellers", MODULE_PATH)
MODULE = importlib.util.module_from_spec(SPEC)
assert SPEC and SPEC.loader
SPEC.loader.exec_module(MODULE)


def test_unreachable_labeller_is_reported_without_mutation(monkeypatch):
    def fail(_port, timeout=2.0):
        return {"port": _port, "reachable": False, "meta": None, "error": "offline"}
    monkeypatch.setattr(MODULE, "fetch_meta", fail)
    result = MODULE.summarize([8751])
    assert result["summary"] == {"n_servers": 1, "n_reachable": 0, "total_queued": 0, "total_done": 0}
    assert result["safety"]["servers_restarted"] is False
