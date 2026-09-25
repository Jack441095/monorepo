"""The beta tester guide as a page inside KENN, so testers can read the known limitations without the repo.

The packaged app has no Markdown library, so build_kenn_app.py renders the guide to HTML at build time. A dev
checkout renders the Markdown on the fly (or shows it as plain text if Markdown isn't installed).
"""

from __future__ import annotations

import html

from kenn.paths import PRODUCT_ROOT

GUIDE = PRODUCT_ROOT / "docs" / "BETA_TESTER_GUIDE.md"
PRERENDERED = GUIDE.with_suffix(".html")

PAGE = """<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>KENN tester guide</title>
<style>
  :root {{ --bg: #f7f7f5; --text: #1d1d1f; --muted: #5f6368; --line: #d9d9d6; --accent: #2f5bd3; }}
  @media (prefers-color-scheme: dark) {{ :root {{ --bg: #17181a; --text: #ececec; --muted: #a3a6ab; --line: #34363a; --accent: #8aa8ff; }} }}
  body {{ margin: 0; background: var(--bg); color: var(--text); font: 15px/1.55 -apple-system, BlinkMacSystemFont, "Helvetica Neue", sans-serif; }}
  main {{ max-width: 760px; margin: 0 auto; padding: 32px 20px 64px; }}
  a {{ color: var(--accent); }}
  h1 {{ font-size: 26px; margin-top: 0; }} h2 {{ font-size: 19px; margin-top: 32px; }}
  table {{ border-collapse: collapse; width: 100%; font-size: 14px; }} th, td {{ border-bottom: 1px solid var(--line); padding: 6px 8px; text-align: left; vertical-align: top; }}
  code {{ font-size: 13px; }} .back {{ font-size: 14px; }}
</style>
</head>
<body><main>
<p class="back"><a href="/setup?support">← Setup &amp; Support</a> · <a href="/">Open KENN</a></p>
{body}
</main></body>
</html>
"""


def render_markdown(text: str) -> str:
    import markdown

    return markdown.markdown(text, extensions=["tables"])


def guide_html() -> str:
    if PRERENDERED.is_file():
        body = PRERENDERED.read_text(encoding="utf-8")
    else:
        text = GUIDE.read_text(encoding="utf-8")
        try:
            body = render_markdown(text)
        except ImportError:
            body = f"<pre>{html.escape(text)}</pre>"
    return PAGE.format(body=body)


__all__ = ["GUIDE", "PRERENDERED", "guide_html", "render_markdown"]
