import importlib.util
import json
from pathlib import Path


def load_module():
    path = Path(__file__).with_name("build_factorised_training_manifest.py")
    spec = importlib.util.spec_from_file_location("factorised_manifest", path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_form_mapping_is_factorised():
    module = load_module()
    assert module.form_for("Kick") == "one-shot"
    assert module.form_for("Vocal Loop") == "loop"
    assert module.form_for("Vocal Phrase") == "phrase"
    assert module.form_for("Other/none") == "rejection"


def test_manifest_excludes_sealed_rows_and_is_content_deduplicated(tmp_path):
    module = load_module()
    wav_a = tmp_path / "a.wav"
    wav_b = tmp_path / "alias.wav"
    wav_a.write_bytes(b"same-audio")
    wav_b.write_bytes(b"same-audio")
    corpus = tmp_path / "corpus.npz"
    np = __import__("numpy")
    np.savez(corpus, paths=[str(wav_a), str(wav_b)], labels=["Kick", "Kick"])
    validation = tmp_path / "validation.json"
    validation.write_text(json.dumps([{"path": str(wav_b)}]))
    # This fixture cannot use the full inventory parser, so test the fail-closed
    # sealed-path check through the helper-independent branch by mocking it.
    original = module.collection_for
    module.collection_for = lambda path: ("fixture", "fixture||pack")
    try:
        result = module.build(corpus, validation)
    finally:
        module.collection_for = original
    assert result["summary"]["n_excluded_sealed_validation"] == 1
    assert result["summary"]["n_training_rows"] == 1
    assert result["safety"]["validation_rows_used_for_training"] is False

