"""The download-pdfs CLI must exist and refuse to lie about what it fetched.

Regression (29 Sept 2026 manual-ingestion audit): main.py has shelled out to
tooling/scripts/setup/download_training_pdfs.py since 2026-09-01, but the file
was never written, so the documented way to obtain the Ableton manual always
"failed cleanly" with Python's file-not-found. These tests pin the replacement
at its honesty edges: reference-only policies never download, a soft-404 HTML
body never lands as a .pdf, and partial writes never survive a failure.
"""

from __future__ import annotations

import importlib.util
import io
import json
from pathlib import Path

import pytest


SCRIPT = Path(__file__).resolve().parents[5] / "tooling" / "scripts" / "setup" / "download_training_pdfs.py"
module = importlib.util.module_from_spec(
    spec := importlib.util.spec_from_file_location("download_training_pdfs", SCRIPT)
)
assert spec.loader
spec.loader.exec_module(module)


CATALOG = [
    {"title": "Live 12 Manual", "filename": "live12-manual-en.pdf", "category": "ableton",
     "priority": "essential", "index_policy": "local_opt_in"},
    {"title": "Live 11 Manual", "filename": "live11-manual-en.pdf", "category": "ableton",
     "priority": "medium", "index_policy": "local_opt_in", "download_url": "https://example/live11.pdf"},
    {"title": "Push 3 Manual", "filename": "push3-manual-en.pdf", "category": "ableton",
     "priority": "medium", "index_policy": "reference_only", "download_url": "https://example/push3.pdf"},
    {"title": "EBU R 128", "filename": "ebu-r128-v4.pdf", "category": "standards",
     "priority": "essential", "download_url": "https://example/r128.pdf"},
]


class _FakeResponse:
    def __init__(self, body: bytes, content_type: str, status: int = 200):
        self._body, self._done = [body], False
        self.status = status
        self.headers = {"Content-Type": content_type}

    def read(self, _size: int) -> bytes:
        if self._done:
            return b""
        self._done = True
        return self._body.pop()

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        return False


def test_reference_only_policies_are_never_fetched() -> None:
    titles = [e["title"] for e in module.select_entries(CATALOG)]
    assert "Push 3 Manual" not in titles
    assert {"Live 11 Manual", "EBU R 128", "Live 12 Manual"} == set(titles)


def test_essential_flag_drops_non_essential_entries() -> None:
    titles = [e["title"] for e in module.select_entries(CATALOG, essential_only=True)]
    assert set(titles) == {"Live 12 Manual", "EBU R 128"}


def test_catalog_entries_without_a_url_report_how_to_obtain(tmp_path, monkeypatch, capsys) -> None:
    monkeypatch.setattr(module, "PDF_DIR", tmp_path)
    monkeypatch.setattr(module, "load_catalog", lambda *a: CATALOG)
    # pytest.fail inside the canary: any real download attempt blows the test.
    monkeypatch.setattr(module.urllib.request, "urlopen",
                        lambda *a, **k: pytest.fail("unexpected network call"))
    module.main(["--list"])
    out = capsys.readouterr().out
    assert "[manual] Live 12 Manual" in out
    assert "push3" not in out.lower()


def test_soft_404_html_body_never_lands_as_a_pdf(tmp_path, monkeypatch) -> None:
    monkeypatch.setattr(module.urllib.request, "urlopen",
                        lambda *a, **k: _FakeResponse(b"<html>404</html>", "text/html"))
    entry = {"title": "Live 11", "filename": "live11-manual-en.pdf", "download_url": "https://example/x"}
    with pytest.raises(RuntimeError, match="not a PDF"):
        module.fetch_pdf(entry, tmp_path / "live11-manual-en.pdf")
    assert list(tmp_path.iterdir()) == []  # neither the file nor a .part survives


def test_successful_fetch_streams_to_final_name_only(tmp_path, monkeypatch) -> None:
    monkeypatch.setattr(module.urllib.request, "urlopen",
                        lambda *a, **k: _FakeResponse(b"%PDF-1.4 fake manual bytes", "application/pdf"))
    entry = {"title": "Live 11", "filename": "live11-manual-en.pdf", "download_url": "https://example/x"}
    saved = module.fetch_pdf(entry, tmp_path / "live11-manual-en.pdf")
    assert saved.read_bytes() == b"%PDF-1.4 fake manual bytes"
    assert not (tmp_path / "live11-manual-en.pdf.part").exists()


def test_empty_body_is_rejected(tmp_path, monkeypatch) -> None:
    monkeypatch.setattr(module.urllib.request, "urlopen",
                        lambda *a, **k: _FakeResponse(b"", "application/pdf"))
    entry = {"title": "Live 11", "filename": "live11.pdf", "download_url": "https://example/x"}
    with pytest.raises(RuntimeError, match="empty body"):
        module.fetch_pdf(entry, tmp_path / "live11.pdf")
    assert not (tmp_path / "live11.pdf").exists()


def test_shipped_catalog_is_valid_json_and_pins_manual_policies() -> None:
    # The two Live manuals must be downloadable via the CLI (local_opt_in), while
    # anything nobody vetted stays reference_only -- this edit is the deliberate
    # gate, so a casual flip is a code-reviewed change, not a typo in passing.
    catalog = json.loads(module.CATALOG_PATH.read_text(encoding="utf-8"))
    by_name = {e["filename"]: e for e in catalog}
    assert by_name["live11-manual-en.pdf"]["index_policy"] == "local_opt_in"
    assert by_name["live11-manual-en.pdf"]["download_url"].startswith("https://cdn-resources.ableton.com/")
    assert by_name["live12-manual-en.pdf"]["index_policy"] == "local_opt_in"
    assert by_name["push3-manual-en.pdf"]["index_policy"] == "reference_only"