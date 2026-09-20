"""Before/after evidence report for reference spectral matching.

Mix Doctor shows a mix against a reference at one point in time. This shows the
thing that actually proves the match worked: **before vs after vs the target**,
with the tonal-balance score movement, the per-band numbers, the EQ moves that
were applied, and the delivery-safety metrics of the final master.

It is both the QA artifact (did matching help, and did it stay safe?) and the
client-facing artifact (a page you can send). Self-contained HTML -- inline CSS
and SVG, no external assets.

    from audio_analysis.mix_review.match_report import (
        build_match_evidence, render_match_report_html)
    ev = build_match_evidence(before_bytes, after_bytes, Path("reference_tracks/pop"))
    html = render_match_report_html(ev, mix_label="Client mix", ref_label="Pop")
"""

from __future__ import annotations

from html import escape
from pathlib import Path
from typing import Any

_BAND_ORDER = ("sub", "bass", "low_mids", "mids", "presence", "sibilance", "air")
_BAND_LABEL = {
    "sub": "Sub", "bass": "Bass", "low_mids": "Low mid", "mids": "Mid",
    "presence": "Presence", "sibilance": "Sib", "air": "Air",
}
_LOW_BANDS = ("sub", "bass", "low_mids")
_HIGH_BANDS = ("presence", "sibilance", "air")


def _high_to_low_ratio(bands7: dict[str, float]) -> float:
    """Sum of presence/sibilance/air energy over sum of sub/bass/low_mids --
    same single-number summary as ``scripts/eval/analyze_reference_tracks.py``
    (duplicated, not imported: that's a scripts-level CLI, this is the
    package, and it's five lines)."""
    low = sum(max(bands7.get(b, 0.0), 0.0) for b in _LOW_BANDS)
    high = sum(max(bands7.get(b, 0.0), 0.0) for b in _HIGH_BANDS)
    if low <= 0.0:
        return float("inf") if high > 0.0 else 0.0
    return high / low


def build_match_evidence(
    before_wav_bytes: bytes,
    after_wav_bytes: bytes,
    reference_track: Path,
    *,
    applied_bands: list[dict] | None = None,
    genre: str | None = None,
) -> dict:
    """Measure the before mix, the matched mix and the reference target on the
    perceptually-correct log bands, and package everything the report needs.

    ``reference_track`` may be a single file OR a genre directory (median target).
    ``applied_bands`` is the match-EQ cascade (from ``compute_reference_match_bands``)
    if you have it -- purely for display. ``genre`` (optional) is threaded into
    KENN's grounded explanations of the applied moves and the reference's own
    tonal profile -- same retrieval pipeline already wired into
    ``mixdown/mix_delivery.py``'s report, reused here rather than duplicated.
    """
    from audio_analysis.utils.audio_io import read_wav_mono
    from audio_analysis.analysis_core.dsp_metrics import log_band_ratios_track_average
    from audio_analysis.analysis_core.genre_profiles import (
        map_40_to_7_bands, compute_tonal_balance_score,
    )
    from audio_analysis.mixdown.spectral_match import reference_target_40band

    ref40, n_refs = reference_target_40band(reference_track)
    ref40_list = ref40.tolist()

    def _bands40(wav: bytes):
        d = read_wav_mono(wav, max_samples=0)
        return log_band_ratios_track_average(d["samples"], int(d["sample_rate"]))

    before40 = _bands40(before_wav_bytes)
    after40 = _bands40(after_wav_bytes)

    evidence: dict[str, Any] = {
        "score_before": round(float(compute_tonal_balance_score(before40, ref40_list)), 1),
        "score_after": round(float(compute_tonal_balance_score(after40, ref40_list)), 1),
        "bands_before": map_40_to_7_bands(before40),
        "bands_after": map_40_to_7_bands(after40),
        "bands_target": map_40_to_7_bands(ref40_list),
        "n_references": int(n_refs),
        "applied_bands": list(applied_bands or []),
        "safety": {},
    }
    evidence["score_delta"] = round(evidence["score_after"] - evidence["score_before"], 1)

    # Delivery safety of the FINAL master (never report a match as a win if it clipped).
    try:
        from audio_analysis.mix_review import mix_review
        rep = mix_review.analyze_wav(after_wav_bytes, "matched.wav", mix_goal="premaster")
        m = rep.get("metrics", {})
        evidence["safety"] = {
            "integrated_lufs": rep.get("technical_metrics", {}).get("integrated_lufs"),
            "true_peak_dbfs": m.get("true_peak_dbfs"),
            "clipped_frames": m.get("clipped_frames_estimate"),
            "stereo_correlation": m.get("stereo_correlation"),
        }
    except Exception:
        pass

    # KENN explanations (best-effort, never blocks the report): why each
    # applied match-EQ move was made, plus what the reference's own measured
    # tonal profile means. Same grounded-answer contract as every other
    # kenn_handoff annotate_* call site -- an index/retrieval problem here
    # must never prevent the evidence report from being written.
    kenn_explanations: list[dict] = []
    try:
        from audio_analysis.integration.kenn_handoff import (
            annotate_bus_eq_bands_with_kenn,
            annotate_reference_track_profiles_with_kenn,
        )
        if evidence["applied_bands"]:
            kenn_explanations += annotate_bus_eq_bands_with_kenn(
                evidence["applied_bands"], genre=genre,
            )
        ref_name = (
            f"{reference_track.name} genre reference ({evidence['n_references']} tracks, median)"
            if reference_track.is_dir() else reference_track.stem
        )
        kenn_explanations += annotate_reference_track_profiles_with_kenn(
            {ref_name: {
                "high_to_low_ratio": _high_to_low_ratio(evidence["bands_target"]),
                "bands7": evidence["bands_target"],
            }},
            genre=genre,
        )
    except Exception:
        pass
    evidence["kenn_explanations"] = kenn_explanations
    return evidence


def _chart(ev: dict) -> str:
    """Grouped-bar SVG: before / after / target per band. Self-contained."""
    b, a, t = ev["bands_before"], ev["bands_after"], ev["bands_target"]
    bands = [x for x in _BAND_ORDER if x in b and x in a and x in t]
    if len(bands) < 3:
        return ""

    def v(d: dict, k: str) -> float:
        try:
            return max(0.0, float(d.get(k, 0.0)))
        except (TypeError, ValueError):
            return 0.0

    peak = max([v(b, x) for x in bands] + [v(a, x) for x in bands] + [v(t, x) for x in bands]) or 1.0
    w, h = 760, 260
    pad_l, pad_r, pad_t, pad_b = 16, 16, 26, 46
    plot_h = h - pad_t - pad_b
    group_w = (w - pad_l - pad_r) / len(bands)
    bar_w = group_w * 0.22
    base_y = pad_t + plot_h
    series = (("Before", b, "#c9ced6"), ("After", a, "#3a6df0"), ("Target", t, "#17b26a"))
    rects, labels = [], []
    for i, band in enumerate(bands):
        cx = pad_l + group_w * (i + 0.5)
        for j, (name, data, color) in enumerate(series):
            val = v(data, band)
            bh = (val / peak) * plot_h
            x = cx + (j - 1.5) * bar_w
            rects.append(
                f'<rect x="{x:.1f}" y="{base_y - bh:.1f}" width="{bar_w:.1f}" height="{bh:.1f}" '
                f'rx="2" fill="{color}"><title>{escape(_BAND_LABEL.get(band, band))} '
                f'{name}: {val * 100:.1f}%</title></rect>'
            )
        labels.append(
            f'<text x="{cx:.1f}" y="{base_y + 16:.1f}" text-anchor="middle" '
            f'font-size="12" fill="#5b6470">{escape(_BAND_LABEL.get(band, band))}</text>'
        )
    legend = ""
    for k, (name, _d, color) in enumerate(series):
        lx = pad_l + k * 92
        legend += (f'<rect x="{lx}" y="6" width="12" height="12" rx="2" fill="{color}"/>'
                   f'<text x="{lx + 18}" y="16" font-size="12" fill="#1a1d21">{name}</text>')
    return (
        f'<svg viewBox="0 0 {w} {h}" role="img" aria-label="Tonal balance before, after and target" '
        f'style="width:100%;height:auto;display:block">'
        f'<line x1="{pad_l}" y1="{base_y:.1f}" x2="{w - pad_r}" y2="{base_y:.1f}" stroke="#e6e8ec"/>'
        f'{legend}{"".join(rects)}{"".join(labels)}</svg>'
    )


def _band_table(ev: dict) -> str:
    b, a, t = ev["bands_before"], ev["bands_after"], ev["bands_target"]
    rows = []
    for band in _BAND_ORDER:
        if band not in b or band not in t:
            continue
        bv, av, tv = float(b.get(band, 0)), float(a.get(band, 0)), float(t.get(band, 0))
        # closer to target after? (absolute distance shrank)
        moved = abs(av - tv) < abs(bv - tv)
        arrow = '<span style="color:#17b26a">▼ closer</span>' if moved else '<span style="color:#8a919b">—</span>'
        rows.append(
            f"<tr><td>{escape(_BAND_LABEL.get(band, band))}</td>"
            f"<td>{bv * 100:.1f}%</td><td><b>{av * 100:.1f}%</b></td>"
            f"<td>{tv * 100:.1f}%</td><td>{arrow}</td></tr>"
        )
    return (
        '<table><thead><tr><th>Band</th><th>Before</th><th>After</th>'
        f'<th>Target</th><th></th></tr></thead><tbody>{"".join(rows)}</tbody></table>'
    )


def _moves(ev: dict) -> str:
    bands = ev.get("applied_bands") or []
    if not bands:
        return ""
    items = []
    for x in sorted(bands, key=lambda d: float(d.get("frequency", 0)))[:24]:
        f = float(x.get("frequency", 0))
        g = float(x.get("gain_db", 0))
        colour = "#17b26a" if g > 0 else "#d1495b"
        items.append(
            f'<li><span class="f">{f:,.0f} Hz</span> '
            f'<span style="color:{colour}">{g:+.1f} dB</span></li>'
        )
    return (f'<h2>Corrections applied</h2><p class="sub">{len(bands)} master EQ move(s).</p>'
            f'<ul class="moves">{"".join(items)}</ul>')


def _kenn(ev: dict) -> str:
    """Grounded 'what KENN says' cards -- why the applied moves were made and
    what the reference's own tonal profile means, each cited to a real note."""
    items = [x for x in (ev.get("kenn_explanations") or []) if x.get("answer")]
    if not items:
        return ""
    cards = []
    for item in items:
        label = item.get("parameter") or "Note"
        subject = item.get("stem_name") or ""
        value = item.get("value")
        heading = escape(str(label))
        if subject and subject != label:
            heading += f" — {escape(str(subject))}"
        if value not in (None, ""):
            heading += f' <span style="color:#8a919b;font-weight:400">({escape(str(value))})</span>'
        sources = [
            (s.get("source") if isinstance(s, dict) else str(s)) for s in (item.get("sources") or [])
        ]
        sources = [s for s in sources if s][:2]
        cards.append(
            f'<div class="kenn-item"><b>{heading}</b><p>{escape(item.get("answer", ""))}</p>'
            + (f'<small>Source: {escape(", ".join(sources))}</small>' if sources else "")
            + "</div>"
        )
    return (
        '<h2>What KENN says</h2>'
        '<p class="sub">Grounded in the studio\'s own notes, not a generic guess.</p>'
        f'<div class="kenn-list">{"".join(cards)}</div>'
    )


def _safety(ev: dict) -> str:
    s = ev.get("safety") or {}
    if not s:
        return ""
    def fmt(v, suffix=""):
        return f"{v}{suffix}" if v is not None else "—"
    clipped = s.get("clipped_frames")
    clip_ok = (clipped == 0)
    return (
        '<h2>Delivery safety</h2><div class="tiles">'
        f'<div class="tile"><span>Loudness</span><b>{fmt(s.get("integrated_lufs"))} LUFS</b></div>'
        f'<div class="tile"><span>True peak</span><b>{fmt(s.get("true_peak_dbfs"))} dBFS</b></div>'
        f'<div class="tile"><span>Clipping</span><b style="color:{"#17b26a" if clip_ok else "#d1495b"}">'
        f'{"none" if clip_ok else clipped}</b></div>'
        f'<div class="tile"><span>Mono compatibility</span><b>{fmt(s.get("stereo_correlation"))}</b></div>'
        '</div>'
    )


_CSS = """
:root{color-scheme:light}
*{box-sizing:border-box}
body{margin:0;font:15px/1.55 -apple-system,BlinkMacSystemFont,"Segoe UI",Roboto,sans-serif;
color:#1a1d21;background:#f6f7f9}
.wrap{max-width:860px;margin:0 auto;padding:32px 20px 56px}
h1{font-size:24px;margin:0 0 4px}
h2{font-size:16px;margin:28px 0 10px;letter-spacing:.01em}
.sub{color:#5b6470;margin:0 0 14px;font-size:14px}
.card{background:#fff;border:1px solid #e6e8ec;border-radius:12px;padding:20px;margin-top:16px}
.score{display:flex;align-items:baseline;gap:14px;flex-wrap:wrap}
.score .big{font-size:40px;font-weight:650;line-height:1}
.score .arrow{font-size:22px;color:#8a919b}
.score .delta{font-size:15px;font-weight:600;color:#17b26a}
table{width:100%;border-collapse:collapse;font-size:14px}
th,td{text-align:right;padding:7px 8px;border-bottom:1px solid #eef0f3}
th:first-child,td:first-child{text-align:left}
th{color:#5b6470;font-weight:600;font-size:12px;text-transform:uppercase;letter-spacing:.04em}
.tiles{display:flex;gap:10px;flex-wrap:wrap}
.tile{flex:1 1 150px;background:#fbfcfd;border:1px solid #eef0f3;border-radius:9px;padding:10px 12px}
.tile span{display:block;color:#5b6470;font-size:12px;margin-bottom:2px}
.tile b{font-size:16px}
ul.moves{list-style:none;padding:0;margin:0;display:flex;flex-wrap:wrap;gap:6px}
ul.moves li{background:#fbfcfd;border:1px solid #eef0f3;border-radius:7px;padding:5px 9px;font-size:13px}
ul.moves .f{color:#5b6470;margin-right:5px}
.kenn-list{display:flex;flex-direction:column;gap:10px}
.kenn-item{background:#fbfcfd;border:1px solid #eef0f3;border-radius:9px;padding:10px 12px}
.kenn-item b{font-size:13.5px}
.kenn-item p{margin:6px 0 4px;font-size:13.5px;color:#333}
.kenn-item small{color:#8a919b;font-size:12px}
footer{color:#8a919b;font-size:12.5px;margin-top:26px;line-height:1.6}
@media (max-width:560px){.score .big{font-size:32px}}
"""


def render_match_report_html(
    evidence: dict,
    *,
    mix_label: str = "Your mix",
    ref_label: str = "reference",
    title: str | None = None,
) -> str:
    """Self-contained HTML evidence report. No external assets."""
    before = evidence.get("score_before")
    after = evidence.get("score_after")
    delta = evidence.get("score_delta")
    n_refs = evidence.get("n_references", 1)
    ref_desc = (f"{escape(ref_label)} ({n_refs} reference tracks, median target)"
                if n_refs > 1 else escape(ref_label))
    page_title = title or f"Spectral match — {mix_label}"
    delta_html = (f'<span class="delta">+{delta} closer to target</span>'
                  if isinstance(delta, (int, float)) and delta > 0 else "")
    kenn_html = _kenn(evidence)
    kenn_card = f'<div class="card">{kenn_html}</div>' if kenn_html else ""

    return (
        f'<div class="wrap">'
        f'<h1>{escape(page_title)}</h1>'
        f'<p class="sub">Tonal balance of <b>{escape(mix_label)}</b> matched toward '
        f'<b>{ref_desc}</b>.</p>'
        f'<div class="card"><h2 style="margin-top:0">Match score</h2>'
        f'<div class="score"><span style="color:#8a919b">{before}</span>'
        f'<span class="arrow">&rarr;</span><span class="big">{after}</span>'
        f'<span style="color:#8a919b">/100</span>{delta_html}</div>'
        f'<p class="sub" style="margin-top:10px">How closely the mix\'s spectral balance '
        f'resembles the reference. Higher is closer.</p></div>'
        f'<div class="card"><h2 style="margin-top:0">Tonal balance</h2>{_chart(evidence)}'
        f'{_band_table(evidence)}</div>'
        f'<div class="card">{_safety(evidence)}{_moves(evidence)}</div>'
        f'{kenn_card}'
        f'<footer>This is a technical comparison of spectral balance, not a judgement of '
        f'musical quality &mdash; a high score means the tonal balance resembles the '
        f'reference. Delivery-safety figures describe the final master as delivered.</footer>'
        f'</div>'
        f'<style>{_CSS}</style>'
    )
