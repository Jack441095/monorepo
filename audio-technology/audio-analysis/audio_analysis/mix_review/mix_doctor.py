"""Mix Doctor — a shareable, prospect-facing report renderer.

This is the public front-end surface for the existing Mix Review engine
(plan.md §14.1, Idea 1). The internal dashboard already produces a rich review
`report` dict; the missing product piece is a clean, self-contained,
*shareable* artifact a prospective client can open in a browser and act on —
ending in a clear call to action to book a mix.

Design constraints (deliberate):

- **Pure and dependency-free.** `render_report_html()` takes the review dict
  the engine already produces and returns an HTML string. No numpy, no I/O, no
  network — so it is trivially testable and safe to import anywhere.
- **Defensive.** Every field is read with `.get()` and degrades gracefully; a
  partial or older report still renders a useful page.
- **No new attack surface.** This module renders; it never accepts uploads,
  never writes to a live server, and never mutates the user's audio. The thin
  CLI in `scripts/mix_doctor_report.py` turns a stored review into a static
  file the engineer can host or send.

The `review` dict is the shape returned by
`mix_review.mix_review_status(id)["review"]` — i.e. the DB row merged with the
stored report: `title`, `metrics`, `flags`, `summary`, `action_plan`,
`prose_summary`, `mix_critique`, `comparison`, `comparison_advice`, etc.
"""

from __future__ import annotations

from html import escape
from typing import Any

__all__ = ["render_report_html", "report_headline"]

_PRIORITY_LABEL = {"high": "Fix first", "medium": "Worth doing", "low": "Polish"}
_PRIORITY_COLOR = {"high": "#e5484d", "medium": "#f5a623", "low": "#3aa675"}


def _num(value: Any) -> float | None:
    """Coerce a metric to float, or None if not numeric."""
    try:
        if value is None or isinstance(value, bool):
            return None
        return float(value)
    except (TypeError, ValueError):
        return None


def _score_and_rating(review: dict) -> tuple[int | None, str]:
    """Headline score/rating.

    Prefer values already on the report; otherwise derive from flags using the
    engine's own scoring so the shareable page never disagrees with the
    dashboard. Imported lazily to keep this module import-light and testable in
    isolation.
    """
    score = review.get("technical_score")
    rating = review.get("rating")
    if isinstance(score, (int, float)) and rating:
        return int(score), str(rating)

    flags = review.get("flags") or []
    try:
        from audio_analysis.mix_review import mix_review

        derived_score = mix_review.technical_score(flags)
        derived_rating = rating or mix_review.rating_from_score(derived_score)
        return int(derived_score), str(derived_rating)
    except Exception:
        # Fall back to a flag-count heuristic if the engine isn't importable
        # (e.g. rendering a detached report in a minimal environment).
        highs = sum(1 for f in flags if str(f.get("severity")) == "high")
        mediums = sum(1 for f in flags if str(f.get("severity")) == "medium")
        score = max(0, 100 - highs * 20 - mediums * 8)
        rating = "Excellent" if score >= 90 else "Good" if score >= 75 else (
            "Fair" if score >= 55 else "Needs work"
        )
        return score, rating


def report_headline(review: dict) -> dict:
    """A compact headline: `{score, rating, one_liner, title}`.

    Useful for the "mix-health score" lead-magnet tool (plan.md §13) as well as
    the full report header.
    """
    score, rating = _score_and_rating(review)
    summary = str(review.get("summary") or "").strip()
    prose = review.get("prose_summary") or {}
    if not summary and isinstance(prose, dict):
        summary = str(prose.get("text") or "").strip()
    one_liner = summary.split("\n")[0][:200] if summary else "Your mix has been analysed."
    return {
        "score": score,
        "rating": rating,
        "one_liner": one_liner,
        "title": str(review.get("title") or "Your mix").strip() or "Your mix",
    }


def _metric_tiles(metrics: dict) -> list[tuple[str, str, str]]:
    """(label, value, hint) tiles for the headline measurements."""
    tiles: list[tuple[str, str, str]] = []
    lufs = _num(metrics.get("integrated_lufs"))
    if lufs is not None:
        tiles.append(("Loudness", f"{lufs:.1f} LUFS", "Integrated (streaming target ≈ −14)"))
    peak = _num(metrics.get("true_peak_dbfs"))
    if peak is None:
        peak = _num(metrics.get("peak_dbfs"))
    if peak is not None:
        tiles.append(("Peak", f"{peak:.1f} dBFS", "True/sample peak — headroom"))
    crest = _num(metrics.get("crest_factor_db"))
    if crest is not None:
        tiles.append(("Dynamics", f"{crest:.1f} dB", "Crest factor — punch vs. squash"))
    corr = _num(metrics.get("stereo_correlation"))
    if corr is not None:
        tiles.append(("Stereo", f"{corr:+.2f}", "Correlation (1 = mono, <0 = phase risk)"))
    lra = _num(metrics.get("loudness_range_lu"))
    if lra is not None:
        tiles.append(("Range", f"{lra:.1f} LU", "Loudness range across the track"))
    return tiles


def _action_cards(actions: list[dict]) -> str:
    rows: list[str] = []
    for action in actions:
        if not isinstance(action, dict):
            continue
        priority = str(action.get("priority") or "low").lower()
        color = _PRIORITY_COLOR.get(priority, "#888")
        tag = _PRIORITY_LABEL.get(priority, priority.title())
        focus = escape(str(action.get("focus") or action.get("decision") or "Adjustment"))
        move = escape(str(action.get("action") or "Review this area of the mix."))
        reason = escape(str(action.get("reason") or "").strip())
        confidence = escape(str(action.get("confidence") or "").strip())
        conf_html = (
            f'<span class="conf">{confidence} confidence</span>' if confidence else ""
        )
        reason_html = f'<p class="reason">{reason}</p>' if reason else ""
        rows.append(
            f'<li class="action" style="border-left-color:{color}">'
            f'<div class="action-head"><span class="tag" style="background:{color}">{escape(tag)}</span>'
            f'<span class="focus">{focus}</span>{conf_html}</div>'
            f'<p class="move">{move}</p>{reason_html}</li>'
        )
    if not rows:
        return '<p class="empty">No priority issues found — nice work. A human pass can still add polish.</p>'
    return f'<ul class="actions">{"".join(rows)}</ul>'


def _flag_pills(flags: list[dict]) -> str:
    pills: list[str] = []
    for flag in flags:
        if not isinstance(flag, dict):
            continue
        severity = str(flag.get("severity") or "low").lower()
        color = _PRIORITY_COLOR.get(severity, "#888")
        label = escape(str(flag.get("label") or "Flag"))
        detail = escape(str(flag.get("detail") or ""))
        pills.append(
            f'<span class="pill" style="border-color:{color}" title="{detail}">{label}</span>'
        )
    return f'<div class="pills">{"".join(pills)}</div>' if pills else ""


# Canonical order for the 7-band tonal-balance view (matches
# analysis_core.genre_profiles.map_40_to_7_bands).
_BAND_ORDER = ("sub", "bass", "low_mids", "mids", "presence", "sibilance", "air")
_BAND_LABEL = {
    "sub": "Sub", "bass": "Bass", "low_mids": "Low mid", "mids": "Mid",
    "presence": "Presence", "sibilance": "Sib", "air": "Air",
}


def _tonal_balance_chart(review: dict) -> str:
    """Self-contained SVG grouped-bar chart of the mix's tonal balance vs a
    reference (normalized 7-band energy). Returns "" if either series is
    missing. No external assets; scales to its container."""
    metrics = review.get("metrics") or {}
    reference = review.get("reference") or {}
    mix_bands = metrics.get("bands") or metrics.get("perceptual_bands") or {}
    ref_bands = (reference.get("metrics") or {}).get("bands") or {}
    if not isinstance(mix_bands, dict) or not isinstance(ref_bands, dict):
        return ""
    bands = [b for b in _BAND_ORDER if b in mix_bands and b in ref_bands]
    if len(bands) < 3:
        return ""

    def _val(d: dict, k: str) -> float:
        try:
            return max(0.0, float(d.get(k, 0.0)))
        except (TypeError, ValueError):
            return 0.0

    peak = max([_val(mix_bands, b) for b in bands] + [_val(ref_bands, b) for b in bands]) or 1.0

    # Geometry (viewBox units; the SVG scales to 100% width).
    w, h = 700, 240
    pad_l, pad_r, pad_t, pad_b = 16, 16, 22, 46
    plot_h = h - pad_t - pad_b
    n = len(bands)
    group_w = (w - pad_l - pad_r) / n
    bar_w = group_w * 0.30
    base_y = pad_t + plot_h
    rects, labels = [], []
    for i, band in enumerate(bands):
        cx = pad_l + group_w * (i + 0.5)
        for j, (series, color) in enumerate((("mix", "#3a6df0"), ("ref", "#b8c0cc"))):
            v = _val(mix_bands if series == "mix" else ref_bands, band)
            bh = (v / peak) * plot_h
            x = cx + (j - 1) * bar_w - bar_w * 0.05
            rects.append(
                f'<rect x="{x:.1f}" y="{base_y - bh:.1f}" width="{bar_w:.1f}" height="{bh:.1f}" '
                f'rx="2" fill="{color}"><title>{escape(_BAND_LABEL.get(band, band))} '
                f'{series}: {v * 100:.0f}%</title></rect>'
            )
        labels.append(
            f'<text x="{cx:.1f}" y="{base_y + 16:.1f}" text-anchor="middle" '
            f'font-size="12" fill="#5b6470">{escape(_BAND_LABEL.get(band, band))}</text>'
        )
    legend = (
        f'<rect x="{pad_l}" y="6" width="12" height="12" rx="2" fill="#3a6df0"/>'
        f'<text x="{pad_l + 18}" y="16" font-size="12" fill="#1a1d21">Your mix</text>'
        f'<rect x="{pad_l + 92}" y="6" width="12" height="12" rx="2" fill="#b8c0cc"/>'
        f'<text x="{pad_l + 110}" y="16" font-size="12" fill="#1a1d21">Reference</text>'
    )
    return (
        f'<svg viewBox="0 0 {w} {h}" role="img" aria-label="Tonal balance versus reference" '
        f'style="width:100%;height:auto;display:block">'
        f'<line x1="{pad_l}" y1="{base_y:.1f}" x2="{w - pad_r}" y2="{base_y:.1f}" stroke="#e6e8ec"/>'
        f'{legend}{"".join(rects)}{"".join(labels)}</svg>'
    )


def _freq_label(freq: float) -> str:
    if freq < 120:
        return "Low"
    if freq < 500:
        return "Low mid"
    if freq < 2000:
        return "Mid"
    if freq < 6000:
        return "Presence"
    return "Air"


def _reference_moves(review: dict) -> str:
    """Render the reference-match EQ suggestions the analysis engine already
    computed (comparison.eq_bands: a constrained 4-band parametric solve toward
    the uploaded reference) as concrete, human-readable moves. Reuses the proven
    `solve_parametric_eq` output rather than re-deriving it."""
    comparison = review.get("comparison") or {}
    eq_bands = comparison.get("eq_bands") or []
    rows: list[str] = []
    for band in eq_bands:
        if not isinstance(band, dict):
            continue
        try:
            freq = float(band.get("freq"))
            gain = float(band.get("gain"))
        except (TypeError, ValueError):
            continue
        if abs(gain) < 0.5:
            continue  # transparent when the move is negligible
        verb = "Boost" if gain > 0 else "Reduce"
        rows.append(
            f'<li class="move"><span class="focus">{escape(_freq_label(freq))}</span> '
            f'{verb} {abs(gain):.1f} dB around {freq:.0f} Hz to move toward the reference.</li>'
        )
    if not rows:
        return ""
    return (
        '<p class="ref-moves-title">Suggested moves to match the reference</p>'
        f'<ul class="actions">{"".join(rows)}</ul>'
    )


def _match_score(review: dict) -> int | None:
    comparison = review.get("comparison")
    if not isinstance(comparison, dict) or not comparison:
        return None
    try:
        from audio_analysis.integration.comparison import match_score
        return int(match_score(comparison))
    except Exception:
        return None


def _comparison_block(review: dict) -> str:
    advice = review.get("comparison_advice") or []
    reference = review.get("reference") or {}
    ref_name = escape(str(reference.get("name") or reference.get("filename") or "a reference"))
    chart = _tonal_balance_chart(review)
    moves = _reference_moves(review)
    score = _match_score(review)
    items = [escape(str(a)) for a in advice if str(a).strip()]
    if not chart and not items and not moves and score is None:
        return ""
    score_html = (
        f'<div class="match"><span class="mnum">{score}</span><span class="mlabel">/100 match</span></div>'
        if score is not None else ""
    )
    lis = "".join(f"<li>{a}</li>" for a in items[:6])
    advice_html = f'<ul class="advice">{lis}</ul>' if items else ""
    return (
        f'<section class="card"><div class="card-head"><h2>Versus {ref_name}</h2>{score_html}</div>'
        f'{chart}{moves}{advice_html}</section>'
    )


def render_report_html(
    review: dict,
    *,
    brand: str = "Audio_Too",
    cta_label: str = "Get this mixed properly",
    cta_url: str = "mailto:jack.gandy@gmail.com?subject=Mix%20enquiry",
) -> str:
    """Render a self-contained, shareable HTML report from a review dict.

    The output inlines all CSS and embeds no external assets, so it can be
    saved to a file, emailed, or hosted anywhere and still render identically.
    It is theme-light by design (a client-facing document), responsive, and
    never scrolls horizontally.
    """
    review = review or {}
    metrics = review.get("metrics") or {}
    head = report_headline(review)
    score = head["score"]
    rating = head["rating"]
    title = escape(head["title"])
    one_liner = escape(head["one_liner"])

    goal = metrics.get("mix_goal") or {}
    goal_name = escape(str(goal.get("name") or goal.get("key") or "").strip())
    goal_html = f'<span class="goal">Target: {goal_name}</span>' if goal_name else ""

    score_html = f'<div class="score"><span class="num">{score}</span><span class="max">/100</span></div>' if score is not None else ""

    tiles = _metric_tiles(metrics)
    tiles_html = "".join(
        f'<div class="tile"><div class="tval">{escape(v)}</div>'
        f'<div class="tlabel">{escape(label)}</div><div class="thint">{escape(hint)}</div></div>'
        for label, v, hint in tiles
    )
    tiles_section = f'<section class="tiles">{tiles_html}</section>' if tiles_html else ""

    actions_html = _action_cards(review.get("action_plan") or [])
    flags_html = _flag_pills(review.get("flags") or [])
    comparison_html = _comparison_block(review)

    prose = review.get("prose_summary") or {}
    prose_text = ""
    if isinstance(prose, dict):
        prose_text = str(prose.get("text") or "").strip()
    if not prose_text:
        critique = review.get("mix_critique") or {}
        if isinstance(critique, dict):
            prose_text = str(critique.get("text") or "").strip()
    prose_html = (
        f'<section class="card"><h2>The short version</h2><p class="prose">{escape(prose_text)}</p></section>'
        if prose_text
        else ""
    )

    brand_e = escape(brand)
    cta_label_e = escape(cta_label)
    cta_url_e = escape(cta_url, quote=True)

    return f"""<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>Mix Doctor — {title}</title>
<style>
:root {{ --bg:#f6f7f9; --card:#fff; --ink:#1a1d21; --muted:#5b6470; --line:#e6e8ec; --accent:#3a6df0; }}
* {{ box-sizing:border-box; }}
body {{ margin:0; font:16px/1.55 -apple-system,BlinkMacSystemFont,"Segoe UI",Roboto,Helvetica,Arial,sans-serif;
  background:var(--bg); color:var(--ink); }}
.wrap {{ max-width:820px; margin:0 auto; padding:28px 20px 64px; }}
.brand {{ font-weight:700; letter-spacing:.02em; color:var(--muted); font-size:14px; text-transform:uppercase; }}
header.hero {{ display:flex; gap:20px; align-items:center; flex-wrap:wrap;
  background:linear-gradient(135deg,#1a1d21,#2b3444); color:#fff; border-radius:16px; padding:24px; margin:12px 0 20px; }}
header.hero .grow {{ flex:1 1 260px; min-width:0; }}
header.hero h1 {{ margin:.1em 0; font-size:26px; line-height:1.2; word-wrap:break-word; }}
header.hero .rating {{ font-size:15px; color:#c9d2e0; }}
header.hero .oneliner {{ margin-top:8px; color:#dbe1ea; font-size:15px; }}
.goal {{ display:inline-block; margin-top:8px; font-size:13px; background:rgba(255,255,255,.14); padding:3px 10px; border-radius:999px; }}
.score {{ background:rgba(255,255,255,.1); border-radius:14px; padding:14px 18px; text-align:center; }}
.score .num {{ font-size:44px; font-weight:800; }}
.score .max {{ font-size:16px; color:#c9d2e0; }}
.tiles {{ display:grid; grid-template-columns:repeat(auto-fit,minmax(130px,1fr)); gap:10px; margin:0 0 20px; }}
.tile {{ background:var(--card); border:1px solid var(--line); border-radius:12px; padding:12px 14px; }}
.tile .tval {{ font-size:20px; font-weight:700; }}
.tile .tlabel {{ font-size:13px; color:var(--muted); font-weight:600; margin-top:2px; }}
.tile .thint {{ font-size:11px; color:var(--muted); margin-top:4px; }}
.card {{ background:var(--card); border:1px solid var(--line); border-radius:14px; padding:18px 20px; margin:0 0 16px; }}
.card h2 {{ margin:0 0 12px; font-size:18px; }}
.card-head {{ display:flex; align-items:center; justify-content:space-between; gap:12px; flex-wrap:wrap; }}
.card-head h2 {{ margin:0; }}
.match {{ background:#eef2fe; color:var(--accent); border-radius:10px; padding:4px 12px; white-space:nowrap; }}
.match .mnum {{ font-size:22px; font-weight:800; }}
.match .mlabel {{ font-size:12px; }}
.ref-moves-title {{ font-weight:700; margin:14px 0 8px; }}
.prose {{ margin:0; color:#2b3138; }}
ul.actions {{ list-style:none; margin:0; padding:0; }}
li.action {{ background:#fafbfc; border:1px solid var(--line); border-left:4px solid #888; border-radius:10px; padding:12px 14px; margin-bottom:10px; }}
.action-head {{ display:flex; gap:10px; align-items:center; flex-wrap:wrap; }}
.tag {{ color:#fff; font-size:11px; font-weight:700; padding:2px 8px; border-radius:999px; text-transform:uppercase; letter-spacing:.03em; }}
.focus {{ font-weight:700; }}
.conf {{ font-size:12px; color:var(--muted); }}
.move {{ margin:8px 0 0; }}
.reason {{ margin:6px 0 0; font-size:14px; color:var(--muted); }}
.empty {{ color:var(--muted); }}
.pills {{ display:flex; flex-wrap:wrap; gap:8px; }}
.pill {{ font-size:13px; border:1px solid #888; border-radius:999px; padding:3px 10px; background:#fff; }}
ul.advice {{ margin:0; padding-left:18px; }}
ul.advice li {{ margin-bottom:6px; }}
.cta {{ text-align:center; margin:26px 0 8px; }}
.cta a {{ display:inline-block; background:var(--accent); color:#fff; text-decoration:none; font-weight:700;
  padding:14px 26px; border-radius:12px; font-size:16px; }}
.cta p {{ color:var(--muted); font-size:14px; margin-top:10px; }}
footer {{ text-align:center; color:var(--muted); font-size:12px; margin-top:28px; }}
</style>
</head>
<body>
<div class="wrap">
  <div class="brand">{brand_e} · Mix Doctor</div>
  <header class="hero">
    <div class="grow">
      <h1>{title}</h1>
      <div class="rating">{escape(str(rating))} mix{" · " if flags_html else ""}</div>
      <div class="oneliner">{one_liner}</div>
      {goal_html}
    </div>
    {score_html}
  </header>
  {prose_html}
  {tiles_section}
  <section class="card">
    <h2>Priority fixes</h2>
    {actions_html}
    {flags_html}
  </section>
  {comparison_html}
  <div class="cta">
    <a href="{cta_url_e}">{cta_label_e}</a>
    <p>This report was generated automatically. A human final pass is where the magic happens.</p>
  </div>
  <footer>Analysed by {brand_e} Mix Doctor. Measurements are objective; the mix decisions are yours.</footer>
</div>
</body>
</html>"""
