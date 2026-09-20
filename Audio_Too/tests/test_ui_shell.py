"""Guards the shared UI shell: themed pages link the dark theme + global nav.

As business pages migrate to the unified Thursday/KENN look, this locks in that
each themed page includes `studio-theme.css` and `app-shell.js`, and that those
shared assets exist — so a page can't silently drift back to the old look, and the
single-source nav can't be re-hardcoded per page.
"""

from __future__ import annotations

from pathlib import Path

STATIC = Path(__file__).resolve().parent.parent / "server" / "app" / "static"

# Pages migrated to the shared dark theme + global nav (every user-facing page).
THEMED_PAGES = [
    "dashboard.html",
    "thursday.html",
    "creative-lab.html",
    "audio-analysis.html",
    "hub.html",
    "automix.html",
    "portfolio.html",
    "tips.html",
    "index.html",
    "stem-upload.html",
    "demo.html",
    "audiogen.html",
]


def test_shared_shell_assets_exist():
    assert (STATIC / "studio-theme.css").is_file()
    assert (STATIC / "app-shell.js").is_file()


def test_themed_pages_link_theme_and_nav():
    for page in THEMED_PAGES:
        html = (STATIC / page).read_text(encoding="utf-8")
        assert "/studio-theme.css" in html, f"{page} is missing the shared dark theme"
        assert "/app-shell.js" in html, f"{page} is missing the global nav injector"


def test_app_shell_defines_the_global_nav_model():
    js = (STATIC / "app-shell.js").read_text(encoding="utf-8")
    for target in ("/hub", "/dashboard", "/creative-lab", "/audio-analysis"):
        assert target in js, f"app-shell nav is missing {target}"
