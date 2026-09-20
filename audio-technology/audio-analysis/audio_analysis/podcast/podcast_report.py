"""Shareable HTML report for the podcast/spoken-word analysis.

Pure renderer: an `analyze_podcast()` report dict -> a self-contained,
prospect-facing HTML page (same design language as Mix Doctor). No external
assets; inlines all CSS; degrades gracefully. Advice only.
"""

from __future__ import annotations

from html import escape

from audio_analysis.mix_review.shareable_report import BASE_CSS, check_rows

__all__ = ["render_podcast_report_html"]

_STATUS = {
    "fail": ("#e5484d", "Fix before publishing"),
    "warn": ("#f5a623", "Worth improving"),
    "ok": ("#3aa675", "Good"),
}

# Podcast-only addendum to the shared BASE_CSS -- the KENN-explanation cards
# have no equivalent in the delivery-check report.
_KENN_CSS = """
.kenn-list { display:flex; flex-direction:column; gap:10px; }
.kenn-item { background:#fafbfc; border:1px solid var(--line); border-radius:10px; padding:12px 14px; }
.kenn-item p { margin:6px 0 4px; font-size:14px; }
.kenn-item small { color:var(--muted); font-size:12px; }
""".strip("\n")


def _kenn_section(report: dict) -> str:
    """Grounded 'what KENN says' cards for the report's flagged checks --
    same shape as audio_analysis.mix_review.match_report's KENN section."""
    items = [x for x in (report.get("kenn_explanations") or []) if x.get("answer")]
    if not items:
        return ""
    cards = []
    for item in items:
        label = escape(str(item.get("parameter") or "Note"))
        answer = escape(str(item.get("answer", "")))
        sources = [
            (s.get("source") if isinstance(s, dict) else str(s)) for s in (item.get("sources") or [])
        ]
        sources = [s for s in sources if s][:2]
        cards.append(
            f'<div class="kenn-item"><b>{label}</b><p>{answer}</p>'
            + (f'<small>Source: {escape(", ".join(sources))}</small>' if sources else "")
            + "</div>"
        )
    return (
        '<section class="card"><h2>What KENN says</h2>'
        '<p style="color:var(--muted);font-size:13px;margin:0 0 12px">'
        "Grounded in the studio's own notes, not a generic guess.</p>"
        f'<div class="kenn-list">{"".join(cards)}</div></section>'
    )


def render_podcast_report_html(
    report: dict,
    *,
    title: str = "Your episode",
    brand: str = "Audio_Too",
    cta_label: str = "Get your podcast professionally edited",
    cta_url: str = "mailto:jack.gandy@gmail.com?subject=Podcast%20editing%20enquiry",
) -> str:
    report = report or {}
    checks = report.get("checks") or []
    score = report.get("score")
    summary = escape(str(report.get("summary") or "Your episode has been analysed."))
    target_label = escape(str(report.get("target_label") or ""))
    title_e = escape(str(title) or "Your episode")
    brand_e = escape(brand)
    cta_label_e = escape(cta_label)
    cta_url_e = escape(cta_url, quote=True)
    score_html = (
        f'<div class="score"><span class="num">{int(score)}</span><span class="max">/100</span></div>'
        if isinstance(score, (int, float)) else ""
    )
    target_html = f'<span class="goal">Target: {target_label}</span>' if target_label else ""
    calib_note = ("" if report.get("calibrated") else
                  '<footer>Thresholds are conservative heuristics pending calibration against a '
                  'reference dialogue corpus. Measurements are objective; final decisions are yours.</footer>')

    return f"""<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>Podcast check — {title_e}</title>
<style>
{BASE_CSS}
{_KENN_CSS}
</style>
</head>
<body>
<div class="wrap">
  <div class="brand">{brand_e} · Podcast check</div>
  <header class="hero">
    <div class="grow">
      <h1>{title_e}</h1>
      <div class="summary">{summary}</div>
      {target_html}
    </div>
    {score_html}
  </header>
  <section class="card">
    <h2>What we found</h2>
    {check_rows(checks, _STATUS)}
  </section>
  {_kenn_section(report)}
  <div class="cta"><a href="{cta_url_e}">{cta_label_e}</a></div>
  {calib_note}
</div>
</body>
</html>"""
