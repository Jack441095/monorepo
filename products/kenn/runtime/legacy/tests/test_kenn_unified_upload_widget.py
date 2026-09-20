"""Presence checks for KENN's unified mix-review/AutoMix upload widget
(studio/kenn/kenn/static/index.html + app.js), mirroring
tests/test_ableton_visualizer.py's lightweight string-presence pattern --
not a real browser test, just a guard against gross regressions."""

from __future__ import annotations

from pathlib import Path

STATIC_ROOT = Path(__file__).resolve().parent.parent.parent / "studio" / "kenn" / "kenn" / "static"


def test_upload_widget_html_elements():
    content = (STATIC_ROOT / "index.html").read_text(encoding="utf-8")

    assert 'id="mix-review-file"' in content
    assert "multiple" in content.split('id="mix-review-file"')[1].split(">")[0]
    assert 'id="automix-genre"' in content
    assert 'id="mix-review-submit"' in content
    assert 'id="single-file-mode-toggle"' in content
    assert 'value="separate"' in content
    assert 'id="review-only-fields"' in content
    assert "upload-card" in content
    assert 'id="automix-genre-label"' in content
    # Copy shouldn't still describe only mix review -- see the 2026-08-02
    # "unified" design pass that added stem separation + AutoMix here.
    assert "stem" in content.lower()
    assert "automix" in content.lower()


def test_upload_widget_js_logic():
    content = (STATIC_ROOT / "app.js").read_text(encoding="utf-8")

    assert "/api/automix-upload" in content
    assert "/api/automix-status" in content
    assert "buildAutomixFormData" in content
    assert "submitAutomixUpload" in content
    assert "AUTOMIX_TERMINAL_STATUSES" in content
    assert "/api/stem-separate-upload" in content
    assert "/api/stem-separate-status" in content
    assert "/api/stem-separate-download" in content
    assert "submitStemSeparation" in content
    assert "selectedSingleFileMode" in content
    assert "updateUploadWidgetUI" in content
    # Balanced braces/parens -- cheap sanity net given no JS runtime is
    # available in this environment to actually parse the file.
    assert content.count("{") == content.count("}")
    assert content.count("(") == content.count(")")


def test_automix_form_data_sends_indexed_stem_fields():
    content = (STATIC_ROOT / "app.js").read_text(encoding="utf-8")
    assert 'formData.append(`stem_${index}`' in content
    assert 'formData.append("genre"' in content
