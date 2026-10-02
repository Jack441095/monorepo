"""The build command must import the moved backend before selecting writable storage."""

from __future__ import annotations

from pathlib import Path
import runpy
import sys
from types import ModuleType

import pytest


SERVICE_ROOT = Path(__file__).resolve().parents[1]
SCRIPT = SERVICE_ROOT / "build_runtime_index.py"
DEFAULT_ENGINE_ROOT = SERVICE_ROOT.parent / "apps" / "backend" / "src"


@pytest.fixture
def fake_builder(monkeypatch):
    calls = []
    kenn = ModuleType("kenn")
    kenn.__path__ = []
    retrieval = ModuleType("kenn.retrieval")
    retrieval.__path__ = []
    builder = ModuleType("kenn.retrieval.build_index")
    builder.build_index = lambda: calls.append(("build", None))
    retrieval.build_index = builder
    kenn.retrieval = retrieval
    runtime = ModuleType("index_runtime")
    runtime.configure_index_dir = lambda directory: calls.append(("configure", directory))
    for name, module in (
        ("kenn", kenn),
        ("kenn.retrieval", retrieval),
        ("kenn.retrieval.build_index", builder),
        ("index_runtime", runtime),
    ):
        monkeypatch.setitem(sys.modules, name, module)
    monkeypatch.setattr(sys, "path", list(sys.path))
    monkeypatch.delenv("KENN_ENGINE_ROOT", raising=False)
    monkeypatch.delenv("KENN_CHAT_INDEX_DIR", raising=False)
    monkeypatch.setenv("AUDIO_TOO_LLM_ENABLED", "1")
    return calls


def test_default_builder_uses_the_canonical_backend_without_writing_assets(fake_builder):
    # The old default retained legacy source ownership after the backend moved into the product.
    result = runpy.run_path(str(SCRIPT), run_name="__main__")

    assert result["ENGINE_ROOT"] == DEFAULT_ENGINE_ROOT
    assert (result["ENGINE_ROOT"] / "kenn" / "retrieval" / "build_index.py").is_file()
    assert str(DEFAULT_ENGINE_ROOT) in sys.path
    assert fake_builder == [
        ("configure", SERVICE_ROOT / ".runtime" / "index"),
        ("build", None),
    ]


@pytest.mark.parametrize("selected_index", [False, True])
def test_explicit_engine_checkout_keeps_the_selected_runtime_index(
    tmp_path, monkeypatch, fake_builder, selected_index
):
    engine = tmp_path / "engine"
    engine.mkdir()
    monkeypatch.setenv("KENN_ENGINE_ROOT", str(engine))
    index = tmp_path / "runtime-index" if selected_index else SERVICE_ROOT / ".runtime" / "index"
    if selected_index:
        monkeypatch.setenv("KENN_CHAT_INDEX_DIR", str(index))

    result = runpy.run_path(str(SCRIPT), run_name="__main__")

    assert result["ENGINE_ROOT"] == engine
    assert str(engine) in sys.path
    assert result["RUNTIME_INDEX_DIR"] == index
    assert fake_builder == [("configure", index), ("build", None)]
    assert list(engine.iterdir()) == []
    if selected_index:
        assert not index.exists()


def test_runtime_index_override_does_not_replace_the_default_engine(tmp_path, monkeypatch, fake_builder):
    index = tmp_path / "runtime-index"
    monkeypatch.setenv("KENN_CHAT_INDEX_DIR", str(index))

    result = runpy.run_path(str(SCRIPT), run_name="__main__")

    assert result["ENGINE_ROOT"] == DEFAULT_ENGINE_ROOT
    assert result["RUNTIME_INDEX_DIR"] == index
    assert fake_builder == [("configure", index), ("build", None)]
    assert not index.exists()


def test_relative_engine_and_index_overrides_keep_the_callers_working_directory(
    tmp_path, monkeypatch, fake_builder
):
    engine = tmp_path / "engine"
    engine.mkdir()
    monkeypatch.chdir(tmp_path)
    monkeypatch.setenv("KENN_ENGINE_ROOT", "engine")
    monkeypatch.setenv("KENN_CHAT_INDEX_DIR", "runtime-index")

    result = runpy.run_path(str(SCRIPT), run_name="__main__")

    assert result["ENGINE_ROOT"] == engine
    assert result["RUNTIME_INDEX_DIR"] == Path("runtime-index")
    assert fake_builder == [("configure", Path("runtime-index")), ("build", None)]
    assert list(engine.iterdir()) == []
    assert not (tmp_path / "runtime-index").exists()


@pytest.mark.parametrize("kind", ["missing", "file"])
def test_invalid_engine_override_stops_before_configuring_or_building(
    tmp_path, monkeypatch, fake_builder, kind
):
    engine = tmp_path / kind
    if kind == "file":
        engine.write_text("not a checkout")
    monkeypatch.setenv("KENN_ENGINE_ROOT", str(engine))

    with pytest.raises(RuntimeError, match="KENN engine checkout not found"):
        runpy.run_path(str(SCRIPT), run_name="__main__")

    assert fake_builder == []
    assert str(engine) not in sys.path
    if kind == "missing":
        assert not engine.exists()
