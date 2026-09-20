"""Stage 11.2 — session documentation: real mix run, real metrics, grounded rationale.

Renders a real synthetic mix through the actual AutoMix pipeline
(``generate_mix_plan`` + ``mix_and_render_stems``, the same path
``test_mix_validator.py``/``test_mix_delivery.py`` use), generates a
session document from it, and verifies the document contains the mix's
*actual* measured numbers (not placeholder text) and that any KENN
rationale present is real, sourced, retrieval-pipeline output rather than
invented prose.

KENN-grounding assertions are skipped (not failed) when no KENN index has
been built in this environment, matching the pattern already used by
``tests/test_kenn_automix_parameter_explanations.py`` — this suite does
not attempt its own index build.
"""

from __future__ import annotations

from pathlib import Path

import numpy as np
import pytest

from audio_analysis.export.session_documentation import (
    build_session_document_data,
    generate_session_markdown,
    generate_session_pdf,
    render_session_markdown,
    session_markdown_to_pdf_bytes,
)
from audio_analysis.mixdown.mix_decision_engine import generate_mix_plan
from audio_analysis.mixdown.mix_renderer import mix_and_render_stems
from audio_analysis.mixdown.stem_classifier import StemProfile

INDEX_CHUNKS = (
    Path(__file__).resolve().parent.parent.parent
    / "studio" / "kenn" / "kenn" / "data" / "index" / "chunks.jsonl"
)


def _real_render_result(genre: str = "pop", target_lufs: float = -14.0) -> dict:
    sample_rate = 44100
    duration_samples = 44100  # 1 second, real audio content
    t = np.linspace(0, 1.0, duration_samples, endpoint=False)
    kick_samples = np.sin(2.0 * np.pi * 60.0 * t) * 0.6
    vocal_samples = np.sin(2.0 * np.pi * 440.0 * t) * 0.3

    prepared_stems = [
        {"name": "kick.wav", "samples": kick_samples.tolist(), "sample_rate": sample_rate},
        {"name": "vocal.wav", "samples": vocal_samples.tolist(), "sample_rate": sample_rate},
    ]
    profiles = [
        StemProfile(name="kick.wav", instrument="kick", peak_dbfs=-6.0, rms_dbfs=-18.0, crest_factor_db=12.0),
        StemProfile(name="vocal.wav", instrument="vocal", peak_dbfs=-10.0, rms_dbfs=-22.0, crest_factor_db=12.0),
    ]
    plan = generate_mix_plan(profiles, masking_results=None, genre=genre, target_lufs=target_lufs)
    return mix_and_render_stems(prepared_stems, plan)


@pytest.fixture(scope="module")
def real_render():
    return _real_render_result()


@pytest.fixture(scope="module", autouse=True)
def kenn_state_isolation(tmp_path_factory):
    import os
    state_dir = tmp_path_factory.mktemp("kenn-session-doc")
    os.environ["KENN_CHATS_DIR"] = str(state_dir)
    os.environ["KENN_DB_PATH"] = str(state_dir / "kenn.db")
    os.environ["KENN_SESSION_FILE"] = str(state_dir / "session.json")
    yield


# ---------------------------------------------------------------------------
# Data assembly: real numbers, not placeholders
# ---------------------------------------------------------------------------


def test_build_session_document_data_uses_real_measured_numbers(real_render):
    data = build_session_document_data(real_render, project_id="proj_test_001", client_name="Test Client")

    assert data["project_id"] == "proj_test_001"
    assert data["genre"] == "pop"
    assert data["target_lufs"] == pytest.approx(-14.0)

    # measured_lufs must be the render's actual measured value, not a stub/None.
    assert data["measured_lufs"] is not None
    assert isinstance(data["measured_lufs"], (int, float))
    assert -60.0 < data["measured_lufs"] < 0.0

    # final_validation metrics must be real (computed), matching what the
    # delivery pipeline's own pre-write gate (verify_render_output) measures.
    metrics = data["final_validation"]["metrics"]
    assert metrics["true_peak_dbtp"] is not None
    assert metrics["peak_dbfs"] is not None
    assert -1.0 <= metrics["phase_correlation"] <= 1.0

    # Decisions log must be the real plan's log, not empty/placeholder.
    assert len(data["decisions_log"]) > 0
    assert all(isinstance(line, str) and line for line in data["decisions_log"])

    # Stem rows reflect the two real input stems.
    stem_names = {s["stem_name"] for s in data["stems"]}
    assert stem_names == {"kick.wav", "vocal.wav"}
    for stem in data["stems"]:
        assert isinstance(stem["gain_db"], (int, float))


def test_measured_lufs_in_doc_matches_render_result_exactly(real_render):
    data = build_session_document_data(real_render)
    assert data["measured_lufs"] == real_render["measured_lufs"]


# ---------------------------------------------------------------------------
# Markdown rendering: contains actual values, not generic placeholder text
# ---------------------------------------------------------------------------


def test_markdown_contains_actual_metrics_not_placeholders(real_render):
    md = generate_session_markdown(real_render, project_id="proj_test_002")

    assert "# Mix Session Notes — proj_test_002" in md
    assert "pop" in md  # real genre
    # The exact measured LUFS value must appear formatted in the doc.
    measured = real_render["measured_lufs"]
    assert f"{measured:.2f}" in md or f"{measured:.1f}" in md
    assert "kick.wav" in md
    assert "vocal.wav" in md
    # No leftover template placeholders.
    for placeholder in ("TODO", "{{", "}}", "PLACEHOLDER", "XXX"):
        assert placeholder not in md


def test_markdown_decisions_log_is_the_real_automix_log(real_render):
    md = generate_session_markdown(real_render)
    plan = real_render["mix_plan"]
    # At least the first real decision-log line must appear verbatim.
    assert plan.decisions_log
    assert plan.decisions_log[0] in md


# ---------------------------------------------------------------------------
# KENN rationale: real, grounded, cited (skipped if no index built)
# ---------------------------------------------------------------------------


@pytest.mark.skipif(not INDEX_CHUNKS.exists(), reason="KENN index not built")
def test_kenn_rationale_is_real_grounded_output_not_invented(real_render):
    data = build_session_document_data(real_render, allow_llm=False)
    explanations = data["kenn_explanations"]
    assert explanations, "expected at least one KENN explanation for a real MixPlan with gain/compression/etc set"

    for item in explanations:
        assert item["answer"], "KENN explanation must have real answer text"
        # Every explanation must either cite a real source file, or be an
        # honest abstention (weak_match) with no fabricated sources.
        if item.get("weak_match"):
            assert not item["sources"]
            continue
        assert item["sources"], f"non-abstaining explanation has no cited sources: {item}"

    md = render_session_markdown(data)
    assert "## KENN Rationale" in md
    # At least one cited source filename must appear in the rendered doc.
    any_source_in_md = any(
        (src.get("source", "") if isinstance(src, dict) else str(src)) in md
        for item in explanations
        for src in (item.get("sources") or [])
    )
    assert any_source_in_md or all(item.get("weak_match") for item in explanations)


def test_session_doc_never_calls_a_parallel_llm_path():
    """Stage 11.2 requirement: reuse Stage 9's kenn_handoff, don't rebuild explanation logic."""
    import inspect
    import audio_analysis.export.session_documentation as session_documentation

    source = inspect.getsource(session_documentation)
    assert "annotate_mix_plan_with_kenn" in source
    assert "import openai" not in source
    assert "import anthropic" not in source


# ---------------------------------------------------------------------------
# PDF export (best-effort, dependency-free)
# ---------------------------------------------------------------------------


def test_pdf_export_is_structurally_valid_and_contains_real_text(real_render, tmp_path):
    md = generate_session_markdown(real_render, project_id="proj_pdf_test")
    pdf_bytes = session_markdown_to_pdf_bytes(md)

    assert pdf_bytes.startswith(b"%PDF-1.4")
    assert pdf_bytes.rstrip().endswith(b"%%EOF")

    pypdf = pytest.importorskip("pypdf")
    reader = pypdf.PdfReader.__new__(pypdf.PdfReader)  # avoid strict-mode surprises
    import io
    reader = pypdf.PdfReader(io.BytesIO(pdf_bytes))
    assert len(reader.pages) >= 1

    extracted = "\n".join(page.extract_text() or "" for page in reader.pages)
    assert "Mix Session Notes" in extracted
    assert "proj_pdf_test" in extracted
    assert "kick.wav" in extracted

    out_path = generate_session_pdf(md, tmp_path / "session.pdf")
    assert out_path.exists()
    assert out_path.read_bytes() == pdf_bytes
