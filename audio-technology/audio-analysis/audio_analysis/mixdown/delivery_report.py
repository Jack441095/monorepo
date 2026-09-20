"""Shareable HTML report for the delivery-spec conformance check.

Pure renderer: a check_delivery_conformance() report dict -> a self-contained,
prospect-facing HTML page (same design language as Mix Doctor / the podcast
check). No external assets; inlines all CSS. Advice only.
"""

from __future__ import annotations

from html import escape

from audio_analysis.mix_review.shareable_report import BASE_CSS, check_rows

__all__ = ["render_delivery_report_html"]

_STATUS = {
    "fail": ("#e5484d", "Fix before delivery"),
    "warn": ("#f5a623", "Worth a listen"),
    "ok": ("#3aa675", "Good"),
}


def render_delivery_report_html(
    report: dict,
    *,
    title: str = "Your master",
    brand: str = "Audio_Too",
    cta_label: str = "Get your master delivery-ready",
    cta_url: str = "mailto:jack.gandy@gmail.com?subject=Mastering%20enquiry",
) -> str:
    report = report or {}
    checks = report.get("checks") or []
    score = report.get("score")
    summary = escape(str(report.get("summary") or "Your master has been analysed."))
    target_label = escape(str(report.get("target_label") or ""))
    lra = report.get("loudness_range_lu")
    title_e = escape(str(title) or "Your master")
    brand_e = escape(brand)
    cta_label_e = escape(cta_label)
    cta_url_e = escape(cta_url, quote=True)
    score_html = (
        f'<div class="score"><span class="num">{int(score)}</span><span class="max">/100</span></div>'
        if isinstance(score, (int, float)) else ""
    )
    target_html = f'<span class="goal">Target: {target_label}</span>' if target_label else ""
    lra_html = (
        f'<p class="meta" style="margin:10px 0 0">Loudness range: {float(lra):.1f} LU '
        '(informational only -- music has no universal "should be narrow" target, unlike '
        "spoken word.)</p>" if isinstance(lra, (int, float)) else ""
    )

    return f"""<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>Delivery check — {title_e}</title>
<style>
{BASE_CSS}
</style>
</head>
<body>
<div class="wrap">
  <div class="brand">{brand_e} · Delivery check</div>
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
    {lra_html}
  </section>
  <div class="cta"><a href="{cta_url_e}">{cta_label_e}</a></div>
</div>
</body>
</html>"""
