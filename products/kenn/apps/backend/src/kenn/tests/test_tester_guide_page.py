"""The tester guide is readable inside KENN, known limitations included."""

from __future__ import annotations

from kenn.core import tester_guide


def test_guide_page_renders_the_markdown_guide(monkeypatch, tmp_path) -> None:
    monkeypatch.setattr(tester_guide, "PRERENDERED", tmp_path / "missing.html")
    page = tester_guide.guide_html()
    assert "<title>KENN tester guide</title>" in page
    assert "Known limitations" in page and 'href="/setup?support"' in page


def test_the_app_build_uses_its_prerendered_copy(monkeypatch, tmp_path) -> None:
    built = tmp_path / "BETA_TESTER_GUIDE.html"
    built.write_text("<h2>Known limitations in this build</h2>", encoding="utf-8")
    monkeypatch.setattr(tester_guide, "PRERENDERED", built)
    assert "<h2>Known limitations in this build</h2>" in tester_guide.guide_html()


def test_without_markdown_the_guide_still_shows_as_text(monkeypatch, tmp_path) -> None:
    monkeypatch.setattr(tester_guide, "PRERENDERED", tmp_path / "missing.html")

    def no_markdown(_text):
        raise ImportError("markdown")

    monkeypatch.setattr(tester_guide, "render_markdown", no_markdown)
    assert "<pre>" in tester_guide.guide_html() and "Known limitations" in tester_guide.guide_html()
