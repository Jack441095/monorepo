"""Public wrapper imports must not replace an embedded caller's model or index policy."""

from __future__ import annotations

import json
import os
from pathlib import Path
import subprocess
import sys

import pytest


KENN_ROOT = Path(__file__).resolve().parents[2]
WRAPPERS = (KENN_ROOT / "chat", KENN_ROOT / "packages" / "chat")
IMPORT_PROBE = r"""
import importlib.util
import json
import os
from pathlib import Path
import sys

wrapper, runtime, mode = Path(sys.argv[1]), Path(sys.argv[2]), sys.argv[3]
sys.path.insert(0, str(wrapper))
sys.path.insert(0, str(Path(os.environ['KENN_ENGINE_ROOT'])))
from kenn.llm import llm_rewrite
from kenn.llm.mlx_inference_engine import MLXInferenceEngine
from kenn.core import chat_constants, chat_retrieval
from kenn.retrieval import retrieval, index_store, build_index

llm_rewrite.load_env = lambda: None
attempted_io = []
def forbidden(*args, **kwargs):
    attempted_io.append('model or provider call')
    raise AssertionError('Import must not load a model or contact a provider.')
llm_rewrite._get_client = forbidden
MLXInferenceEngine.get_instance = forbidden
MLXInferenceEngine.load_model = forbidden
retrieval._get_embedding_model = forbidden

def index_paths():
    return {
        'chat_constants': str(chat_constants.INDEX_DIR),
        'chat_retrieval_chunks': str(chat_retrieval.CHUNKS_PATH),
        'retrieval': str(retrieval.INDEX_DIR),
        'index_store': str(index_store.INDEX_DIR),
        'build_index': str(build_index.INDEX_DIR),
    }

if mode == 'index':
    from index_runtime import configure_index_dir
    for name in ('caller', 'wrapper'):
        directory = runtime / name
        directory.mkdir()
        (directory / 'chunks.jsonl').write_text(json.dumps({'id': name, 'text': 'fixture'}) + '\n')
        (directory / 'terms.json').write_text(json.dumps({'total_docs': 1, 'term_counts': [{}]}))
    configure_index_dir(runtime / 'caller')
    os.environ['KENN_CHAT_INDEX_DIR'] = str(runtime / 'wrapper')
    assert chat_retrieval.load_chunks()[0]['id'] == 'caller'
    embedding_marker = object()
    retrieval._embedding_index = embedding_marker

before = {
    'legacy_enabled': os.environ.get('AUDIO_TOO_LLM_ENABLED'),
    'enabled': llm_rewrite.is_enabled(),
    'paths': index_paths(),
}
spec = importlib.util.spec_from_file_location('public_wrapper_probe', wrapper / 'app.py')
module = importlib.util.module_from_spec(spec)
sys.modules[spec.name] = module
spec.loader.exec_module(module)
after = {
    'legacy_enabled': os.environ.get('AUDIO_TOO_LLM_ENABLED'),
    'enabled': llm_rewrite.is_enabled(),
    'paths': index_paths(),
    'attempted_io': attempted_io,
}
if mode == 'index':
    after['cache_warm'] = chat_retrieval._load_index_bundle.cache_info().currsize == 1
    after['embedding_retained'] = retrieval._embedding_index is embedding_marker
    after['caller_chunk'] = chat_retrieval.load_chunks()[0]['id']
    def fixture_answer(*args, **kwargs):
        assert kwargs['retrieval_only'] is True
        assert kwargs['allow_llm'] is False
        assert retrieval.load_embedding_index() is None
        return {'chunk': chat_retrieval.load_chunks()[0]['id']}
    module.answer_payload = fixture_answer
    after['wrapper_chunk'] = module._scoped_answer_payload('How do I EQ a kick?', [], 'steps')['chunk']
    after['caller_after_request'] = chat_retrieval.load_chunks()[0]['id']
    after['embedding_after_request'] = retrieval._embedding_index is embedding_marker
print(json.dumps({'before': before, 'after': after}))
"""


def _import_probe(wrapper: Path, tmp_path: Path, *, enabled: str | None, mode="model") -> dict:
    env = os.environ.copy()
    for name in tuple(env):
        if name.startswith(("KENN_LLM_", "AUDIO_TOO_LLM_")):
            env.pop(name)
    env.pop("KENN_CHAT_INDEX_DIR", None)
    if enabled is not None:
        env["AUDIO_TOO_LLM_ENABLED"] = enabled
    env.update(
        KENN_ENGINE_ROOT=str(KENN_ROOT / "apps" / "backend" / "src"),
        KENN_LIVE_BACKEND="fake",
        KENN_CHAT_RUNTIME_DIR=str(tmp_path / "runtime"),
        KENN_CHATS_DIR=str(tmp_path / "chats"),
        KENN_DB_PATH=str(tmp_path / "memory.db"),
        KENN_SESSION_FILE=str(tmp_path / "session.json"),
    )
    completed = subprocess.run(
        [sys.executable, "-c", IMPORT_PROBE, str(wrapper), str(tmp_path), mode],
        cwd=tmp_path,
        env=env,
        check=True,
        capture_output=True,
        text=True,
        timeout=10,
    )
    return json.loads(completed.stdout.splitlines()[-1])


@pytest.mark.parametrize("wrapper", WRAPPERS, ids=["chat", "packages-chat"])
@pytest.mark.parametrize("enabled", [None, "0", "1"])
def test_public_wrapper_import_preserves_the_callers_model_policy(wrapper, tmp_path, enabled):
    # Importing either retrieval-only wrapper once disabled ordinary chats in the same process.
    result = _import_probe(wrapper, tmp_path, enabled=enabled)

    assert result["after"]["legacy_enabled"] == result["before"]["legacy_enabled"]
    assert result["after"]["enabled"] == result["before"]["enabled"]
    assert result["after"]["attempted_io"] == []


@pytest.mark.parametrize("wrapper", WRAPPERS, ids=["chat", "packages-chat"])
def test_public_wrapper_import_does_not_replace_an_embedded_callers_index(wrapper, tmp_path):
    result = _import_probe(wrapper, tmp_path, enabled="1", mode="index")

    assert result["after"]["paths"] == result["before"]["paths"]
    assert result["after"]["cache_warm"] is True
    assert result["after"]["embedding_retained"] is True
    assert result["after"]["caller_chunk"] == "caller"
    assert result["after"]["wrapper_chunk"] == "wrapper"
    assert result["after"]["caller_after_request"] == "caller"
    assert result["after"]["embedding_after_request"] is True
    assert result["after"]["attempted_io"] == []
