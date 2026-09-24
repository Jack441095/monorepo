"""The setup page and its two routes are wired into the server (the install route must be allowlisted)."""

from __future__ import annotations

from pathlib import Path

SERVER = Path(__file__).resolve().parents[1] / "server.py"


def test_setup_page_ships_with_the_package() -> None:
    page = SERVER.with_name("setup_page.html").read_text(encoding="utf-8")
    assert "/api/setup/status" in page and "/api/setup/install-remote-script" in page
    assert "confirm: true" in page  # the install is always an explicit button press


def test_routes_are_registered_and_the_install_post_is_allowlisted() -> None:
    source = SERVER.read_text(encoding="utf-8")
    assert 'parsed.path == "/setup"' in source
    assert '"/api/setup/status"' in source
    allowlist = source[source.index("        if parsed.path not in {"):]
    allowlist = allowlist[:allowlist.index("}:")]
    assert '"/api/setup/install-remote-script"' in allowlist
