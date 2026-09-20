"""Shared HTML/CSS building blocks for the advice-only shareable reports
(podcast check, delivery check) -- same design language as Mix Doctor.

Extracted after podcast/podcast_report.py and mixdown/delivery_report.py
were found character-for-character identical in their check-list renderer
and base CSS, aside from the "fail"/"warn" status label text and podcast's
extra KENN-explanation section/CSS. Each caller keeps its own render
function (they genuinely differ: KENN section, calibration footnote, LRA
note, CTA copy/defaults) -- only the provably-identical parts live here.
"""

from __future__ import annotations

from html import escape

__all__ = ["ORDER", "BASE_CSS", "check_rows"]

ORDER = {"fail": 0, "warn": 1, "ok": 2}

# Shared design tokens/layout/typography. Callers with extra sections
# (e.g. podcast's .kenn-*) append their own rules after this block.
BASE_CSS = """
:root { --bg:#f6f7f9; --card:#fff; --ink:#1a1d21; --muted:#5b6470; --line:#e6e8ec; --accent:#3a6df0; }
* { box-sizing:border-box; }
body { margin:0; font:16px/1.55 -apple-system,BlinkMacSystemFont,"Segoe UI",Roboto,Helvetica,Arial,sans-serif; background:var(--bg); color:var(--ink); }
.wrap { max-width:820px; margin:0 auto; padding:28px 20px 64px; }
.brand { font-weight:700; letter-spacing:.02em; color:var(--muted); font-size:14px; text-transform:uppercase; }
header.hero { display:flex; gap:20px; align-items:center; flex-wrap:wrap; background:linear-gradient(135deg,#1a1d21,#2b3444); color:#fff; border-radius:16px; padding:24px; margin:12px 0 20px; }
header.hero .grow { flex:1 1 260px; min-width:0; }
header.hero h1 { margin:.1em 0; font-size:26px; line-height:1.2; word-wrap:break-word; }
header.hero .summary { margin-top:8px; color:#dbe1ea; font-size:15px; }
.goal { display:inline-block; margin-top:8px; font-size:13px; background:rgba(255,255,255,.14); padding:3px 10px; border-radius:999px; }
.score { background:rgba(255,255,255,.1); border-radius:14px; padding:14px 18px; text-align:center; }
.score .num { font-size:44px; font-weight:800; }
.score .max { font-size:16px; color:#c9d2e0; }
.card { background:var(--card); border:1px solid var(--line); border-radius:14px; padding:18px 20px; margin:0 0 16px; }
.card h2 { margin:0 0 12px; font-size:18px; }
ul.checks { list-style:none; margin:0; padding:0; }
li.check { background:#fafbfc; border:1px solid var(--line); border-left:4px solid #888; border-radius:10px; padding:12px 14px; margin-bottom:10px; }
.check-head { display:flex; gap:10px; align-items:center; flex-wrap:wrap; }
.tag { color:#fff; font-size:11px; font-weight:700; padding:2px 8px; border-radius:999px; text-transform:uppercase; letter-spacing:.03em; }
.clabel { font-weight:700; }
.meta { margin:6px 0 0; font-size:13px; color:var(--muted); }
.fix { margin:6px 0 0; }
.cta { text-align:center; margin:26px 0 8px; }
.cta a { display:inline-block; background:var(--accent); color:#fff; text-decoration:none; font-weight:700; padding:14px 26px; border-radius:12px; font-size:16px; }
footer { text-align:center; color:var(--muted); font-size:12px; margin-top:24px; }
""".strip("\n")


def check_rows(checks: list[dict], status_colors: dict[str, tuple[str, str]]) -> str:
    """Render a report's `checks` list as the shared `<ul class="checks">`
    markup. `status_colors` maps status -> (hex_color, tag_label), so each
    caller can use its own tag wording (e.g. "Fix before publishing" vs
    "Fix before delivery") while sharing the row-building logic."""
    rows: list[str] = []
    for c in sorted(checks, key=lambda c: ORDER.get(c.get("status"), 3)):
        if not isinstance(c, dict):
            continue
        status = str(c.get("status") or "ok")
        color, tag = status_colors.get(status, ("#888", status))
        label = escape(str(c.get("label") or "Check"))
        measured = escape(str(c.get("measured") or ""))
        target = escape(str(c.get("target") or ""))
        fix = escape(str(c.get("fix") or ""))
        meta = " · ".join(p for p in (f"measured {measured}" if measured else "",
                                      f"target {target}" if target else "") if p)
        rows.append(
            f'<li class="check" style="border-left-color:{color}">'
            f'<div class="check-head"><span class="tag" style="background:{color}">{escape(tag)}</span>'
            f'<span class="clabel">{label}</span></div>'
            f'{f"<p class=meta>{escape(meta)}</p>" if meta else ""}'
            f'<p class="fix">{fix}</p></li>'
        )
    return f'<ul class="checks">{"".join(rows)}</ul>' if rows else '<p>No issues detected.</p>'
