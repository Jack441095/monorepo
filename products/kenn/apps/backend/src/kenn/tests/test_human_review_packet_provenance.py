from __future__ import annotations

import json
from pathlib import Path
import sys


sys.path.insert(0, str(Path(__file__).resolve().parents[5] / "tooling" / "scripts"))

import build_human_review_packet as packet_builder


def test_active_index_identity_records_reproducible_artifacts() -> None:
    identity = packet_builder._active_index_identity()

    assert identity["version_id"].startswith("v-")
    assert len(identity["content_sha256"]) >= 12
    assert identity["chunk_count"] > 0
    assert identity["retrieval_mode"] in {"bm25_only", "hybrid"}
    embedding = identity["embedding_model"]
    assert embedding["id"] == "Xenova/all-MiniLM-L6-v2"
    assert len(embedding["model_sha256"]) in {0, 64}
    assert len(embedding["tokenizer_sha256"]) in {0, 64}


def test_packet_builder_source_inputs_have_stable_digests() -> None:
    questions = packet_builder.REPO_ROOT / "apps" / "backend" / "src" / "kenn" / "evals" / "questions.json"

    assert len(packet_builder._sha256(questions)) == 64
    assert len(packet_builder._sha256(Path(packet_builder.__file__))) == 64
    assert packet_builder._source_revision() != "unavailable"
    assert isinstance(json.loads(questions.read_text(encoding="utf-8"))["cases"], list)
