import csv
import importlib.util
import json
from pathlib import Path


MODULE_PATH = Path(__file__).with_name("import_blind_labels_to_owner_decisions.py")
SPEC = importlib.util.spec_from_file_location("import_blind_labels_to_owner_decisions", MODULE_PATH)
MODULE = importlib.util.module_from_spec(SPEC)
assert SPEC and SPEC.loader
SPEC.loader.exec_module(MODULE)


def _csv(path: Path, rows: list[dict[str, str]]) -> None:
    with path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=list(rows[0].keys()))
        writer.writeheader()
        writer.writerows(rows)


def test_join_maps_agreement_disagreement_and_skip(tmp_path):
    queue = tmp_path / "queue.csv"
    _csv(queue, [
        {"path": "/a.wav", "destination": "/A.wav", "predicted_class": "Kick", "owner_decision": "", "owner_reviewer": "", "owner_note": ""},
        {"path": "/b.wav", "destination": "/B.wav", "predicted_class": "Clap", "owner_decision": "", "owner_reviewer": "", "owner_note": ""},
        {"path": "/c.wav", "destination": "/C.wav", "predicted_class": "Snare", "owner_decision": "", "owner_reviewer": "", "owner_note": ""},
    ])
    manifest = tmp_path / "manifest.json"
    manifest.write_text(json.dumps([{"id": 0, "path": "/a.wav"}, {"id": 1, "path": "/b.wav"}, {"id": 2, "path": "/c.wav"}]))
    labels = tmp_path / "labels.csv"
    _csv(labels, [
        {"id": "0", "label": "Kick", "path": "/a.wav", "note": ""},
        {"id": "1", "label": "Snare", "path": "/b.wav", "note": "heard snare"},
        {"id": "2", "label": "__skip__", "path": "/c.wav", "note": ""},
    ])
    rows = MODULE.build_decisions(queue, manifest, labels, "owner")
    assert [row["owner_decision"] for row in rows] == ["approve", "reject", "defer"]
    assert rows[1]["owner_note"] == "independent_label=Snare; heard snare"


def test_join_rejects_path_mismatch(tmp_path):
    queue = tmp_path / "queue.csv"
    _csv(queue, [{"path": "/a.wav", "destination": "/A.wav", "predicted_class": "Kick", "owner_decision": "", "owner_reviewer": "", "owner_note": ""}])
    manifest = tmp_path / "manifest.json"
    manifest.write_text(json.dumps([{"id": 0, "path": "/a.wav"}]))
    labels = tmp_path / "labels.csv"
    _csv(labels, [{"id": "0", "label": "Kick", "path": "/wrong.wav", "note": ""}])
    try:
        MODULE.build_decisions(queue, manifest, labels, "owner")
    except ValueError as exc:
        assert "does not match manifest" in str(exc)
    else:
        raise AssertionError("path mismatch must fail closed")
