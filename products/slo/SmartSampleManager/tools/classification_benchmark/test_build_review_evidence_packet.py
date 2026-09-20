import importlib.util
from pathlib import Path

import numpy as np


MODULE_PATH = Path(__file__).with_name("build_review_evidence_packet.py")
SPEC = importlib.util.spec_from_file_location("build_review_evidence_packet", MODULE_PATH)
MODULE = importlib.util.module_from_spec(SPEC)
assert SPEC and SPEC.loader
SPEC.loader.exec_module(MODULE)


def test_nearest_reference_stays_in_predicted_class_when_available(tmp_path):
    candidate = np.array([[1.0, 0.0]], dtype=np.float32)
    corpus = np.array([[1.0, 0.0], [0.0, 1.0]], dtype=np.float32)
    refs = MODULE.nearest_references(
        ["/tmp/candidate.wav"], candidate,
        ["/tmp/kick.wav", "/tmp/snare.wav"], corpus,
        np.array(["Kick", "Snare"]), ["Kick"],
    )
    assert refs[0]["label"] == "Kick"
    assert refs[0]["scope"] == "predicted_class"


def test_nearest_reference_excludes_the_candidate_path():
    refs = MODULE.nearest_references(
        ["/tmp/kick.wav"], np.array([[1.0, 0.0]], dtype=np.float32),
        ["/tmp/kick.wav", "/tmp/other-kick.wav"],
        np.array([[1.0, 0.0], [0.9, 0.1]], dtype=np.float32),
        np.array(["Kick", "Kick"]), ["Kick"],
    )
    assert refs[0]["path"] == str(Path("/tmp/other-kick.wav").resolve())


def test_nearest_reference_falls_back_without_label_transfer():
    refs = MODULE.nearest_references(
        ["/tmp/candidate.wav"], np.array([[0.0, 1.0]], dtype=np.float32),
        ["/tmp/kick.wav"], np.array([[1.0, 0.0]], dtype=np.float32),
        np.array(["Kick"]), ["Unknown Future Class"],
    )
    assert refs[0]["scope"] == "all_labelled_classes"
    assert refs[0]["label"] == "Kick"
