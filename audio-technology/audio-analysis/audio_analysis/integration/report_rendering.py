from __future__ import annotations

import html


def _escape(value: object) -> str:
    return html.escape(str(value if value is not None else ""), quote=True)


def _metric(report: dict, key: str, fallback: str = "n/a") -> str:
    metrics = report.get("metrics") or {}
    value = metrics.get(key, fallback)
    return _escape(value if value not in {None, ""} else fallback)


def _list_items(items: list[object]) -> str:
    if not items:
        return "<p>No items.</p>"
    return "<ul>" + "".join(f"<li>{_escape(item)}</li>" for item in items) + "</ul>"


def _actions_html(actions: list[dict]) -> str:
    if not actions:
        return "<p>No priority actions.</p>"
    rows = []
    for item in actions:
        rows.append(
            "<li>"
            f"<strong>{_escape(item.get('focus', 'Action'))}</strong>"
            f"<span>{_escape(item.get('action', ''))}</span>"
            f"<small>{_escape(item.get('reason', ''))}</small>"
            "</li>"
        )
    return "<ol class='actions'>" + "".join(rows) + "</ol>"


def _kenn_explanations_html(explanations: list[dict] | None) -> str:
    """Render KENN's cited explanations for AutoMix parameters / Mix Review flags.

    ``explanations`` items come from
    ``audio_analysis.integration.kenn_handoff`` (either
    ``annotate_mix_plan_with_kenn`` for AutoMix reports, or per-flag calls to
    ``explain_mix_review_flag`` for Mix Review reports) and carry a
    ``question``, ``answer``, and ``sources`` list so the report can show
    exactly which Training_Data_Notes entry backs each explanation.
    """
    if not explanations:
        return ""
    cards = []
    for item in explanations:
        label = item.get("parameter") or item.get("flag") or item.get("question") or "Parameter"
        subject = " ".join(
            part for part in (item.get("instrument"), item.get("stem_name")) if part
        ).strip()
        value = item.get("value")
        sources = item.get("sources") or []
        source_labels = [
            (src.get("source") if isinstance(src, dict) else str(src))
            for src in sources
        ][:3]
        cards.append(
            "<li class='kenn-explanation'>"
            f"<strong>{_escape(label)}{f' — {_escape(subject)}' if subject else ''}"
            f"{f' ({_escape(value)})' if value not in (None, '') else ''}</strong>"
            f"<p>{_escape(item.get('answer', ''))}</p>"
            + (f"<small>Sources: {_escape(', '.join(str(s) for s in source_labels if s))}</small>" if source_labels else "")
            + "</li>"
        )
    return (
        "<section><h2>KENN Explanations</h2>"
        "<ul class='kenn-explanations'>" + "".join(cards) + "</ul></section>"
    )


def _mix_review_critique_html(critique: dict | None) -> str:
    """Stage 10 AI critique — distinct section from the legacy ``mix_critique``."""
    if not critique:
        return ""
    text = _escape(critique.get("text", ""))
    mode = _escape(critique.get("mode", ""))
    return (
        "<section><h2>AI Mix Critique</h2>"
        f"<p>{text}</p>"
        + (f"<small>Mode: {mode}</small>" if mode else "")
        + "</section>"
    )


def _mix_style_html(style: dict | None) -> str:
    """Stage 10 style classification — era, loudness-war participation, genre."""
    if not style:
        return ""
    summary = _escape(style.get("summary", ""))
    rows = []
    for key, label in (
        ("era", "Era"),
        ("loudness_war", "Loudness War"),
        ("vintage_or_modern", "Vintage/Modern"),
    ):
        entry = style.get(key) or {}
        entry_label = entry.get("label") or entry.get("severity") or ""
        if not entry_label:
            continue
        reasoning = entry.get("reasoning", "")
        rows.append(
            f"<li><strong>{_escape(label)}:</strong> {_escape(entry_label)}"
            + (f" <small>({_escape(reasoning)})</small>" if reasoning else "")
            + "</li>"
        )
    genre_name = (style.get("genre") or {}).get("genre_name", "")
    if genre_name:
        rows.append(f"<li><strong>Genre:</strong> {_escape(genre_name)}</li>")
    return (
        "<section><h2>Mix Style</h2>"
        f"<p>{summary}</p>"
        f"<ul>{''.join(rows)}</ul>"
        "</section>"
    )


def _stem_solo_html(stem_solo: dict | None, stem_masking: dict | None) -> str:
    """Stage 10 stem-solo/masking — low-end overlap ranking + carving suggestions."""
    if not stem_solo and not stem_masking:
        return ""
    parts = []
    low_end = (stem_solo or {}).get("low_end_summary") or {}
    overlap_warning = low_end.get("overlap_warning", "")
    if overlap_warning:
        parts.append(f"<p>{_escape(overlap_warning)}</p>")
    ranked = low_end.get("ranked") or []
    if ranked:
        rows = "".join(
            f"<li>{_escape(item.get('name', ''))}: "
            f"{_escape(item.get('low_end_share', ''))}</li>"
            for item in ranked
        )
        parts.append(f"<ul>{rows}</ul>")
    suggestions = ((stem_masking or {}).get("erb_details") or {}).get("carving_suggestions") or []
    if suggestions:
        rows = "".join(
            f"<li>Carve {_escape(item.get('masker', ''))} to make room for "
            f"{_escape(item.get('masked', ''))} around {_escape(item.get('frequency_hz', ''))} Hz</li>"
            for item in suggestions
        )
        parts.append(f"<ul>{rows}</ul>")
    return "<section><h2>Stem Solo &amp; Masking</h2>" + "".join(parts) + "</section>"


def _session_report_html(session_report: dict | None) -> str:
    if not session_report:
        return ""
    reference = session_report.get("reference_comparison") if isinstance(session_report.get("reference_comparison"), dict) else {}
    reference_bits = []
    if reference.get("reference"):
        reference_bits.append(f"Reference: {reference.get('reference')}")
    for key, label in (("rms_delta_db", "RMS delta"), ("crest_delta_db", "Crest delta"), ("stereo_width_delta", "Width delta")):
        if reference.get(key) not in {None, ""}:
            reference_bits.append(f"{label}: {reference.get(key)}")
    advice = reference.get("advice") or []
    return f"""
      <section>
        <h2>Session Report</h2>
        <div class="metrics">
          <div><strong>{_escape(session_report.get('fix_first', 'n/a'))}</strong><span>Fix first</span></div>
          <div><strong>{_escape(session_report.get('fix_next', 'n/a'))}</strong><span>Fix next</span></div>
          <div><strong>{_escape(session_report.get('mix_target', 'n/a'))}</strong><span>Mix target</span></div>
          <div><strong>{_escape(session_report.get('version_label', '') or 'current')}</strong><span>Version</span></div>
        </div>
        <h3>Leave alone</h3>
        {_list_items(session_report.get("leave_alone") or [])}
        <h3>Ableton repair chain</h3>
        <p>{_escape(session_report.get("ableton_repair_chain", ""))}</p>
        <h3>V2 export checklist</h3>
        {_list_items(session_report.get("v2_export_checklist") or [])}
        {f'<h3>Reference comparison</h3><p>{_escape("; ".join(reference_bits))}</p>{_list_items(advice)}' if reference_bits or advice else ''}
        <h3>Client-friendly summary</h3>
        <p>{_escape(session_report.get("client_summary", ""))}</p>
      </section>
    """


def _goal_target_checks_html(metrics: dict) -> str:
    target_checks = metrics.get("goal_target_checks") or {}
    checks = target_checks.get("checks") or []
    if not checks:
        return ""
    rows = []
    for check in checks:
        status = "Needs attention" if check.get("status") == "warn" else "On target"
        rows.append(
            "<div>"
            f"<strong>{_escape(check.get('label', 'Target check'))}</strong>"
            f"<span>{_escape(status)} · value {_escape(check.get('value', 'n/a'))}</span>"
            f"<small>{_escape(check.get('target', ''))}</small>"
            f"<small>{_escape(check.get('education', ''))}</small>"
            "</div>"
        )
    goal = target_checks.get("goal") or metrics.get("mix_goal") or {}
    return f"""
      <section>
        <h2>Goal Target Checks</h2>
        <p><strong>{_escape(goal.get("label", "Selected goal"))}</strong> · {_escape(target_checks.get("summary", ""))}</p>
        <div class="metrics">{''.join(rows)}</div>
      </section>
    """


def _source_hypotheses_html(items: list[dict]) -> str:
    if not items:
        return ""
    rows = []
    for item in items:
        sources = ", ".join(str(source) for source in item.get("likely_sources", []) if source)
        checks = item.get("checks") or []
        rows.append(
            "<div>"
            f"<strong>{_escape(item.get('issue', 'Mix issue'))}</strong>"
            f"<span>{_escape(sources)}</span>"
            f"<small>{_escape(item.get('first_move', ''))}</small>"
            f"<small>{_escape('; '.join(str(check) for check in checks[:3]))}</small>"
            "</div>"
        )
    return f"""
      <section>
        <h2>Where To Look First</h2>
        <div class="metrics">{''.join(rows)}</div>
      </section>
    """


def _frequency_repair_map_html(items: list[dict]) -> str:
    if not items:
        return ""
    rows = []
    for item in items:
        raw_val = 0.0
        try:
            raw_val = float(item.get("raw_share", 0.0) or 0.0)
        except (TypeError, ValueError):
            pass
        perceived_val = 0.0
        try:
            perceived_val = float(item.get("perceived_share", 0.0) or 0.0)
        except (TypeError, ValueError):
            pass
            
        max_scale = max(0.15, raw_val, perceived_val)
        raw_pct = min(100.0, (raw_val / max_scale) * 100.0) if max_scale > 0 else 0.0
        perceived_pct = min(100.0, (perceived_val / max_scale) * 100.0) if max_scale > 0 else 0.0

        rows.append(
            "<div>"
            f"<strong>{_escape(item.get('label', 'Band'))} · {_escape(item.get('range', ''))}</strong>"
            f"<span>{_escape(item.get('message', ''))}</span>"
            f"<div class='bar-chart'>"
            f"  <div class='bar-container'>"
            f"    <span class='bar-label'>Raw</span>"
            f"    <div class='bar-bg'><div class='bar-fill raw' style='width: {raw_pct:.1f}%'></div></div>"
            f"    <span class='bar-value'>{raw_val:.1%}</span>"
            f"  </div>"
            f"  <div class='bar-container'>"
            f"    <span class='bar-label'>Perceived</span>"
            f"    <div class='bar-bg'><div class='bar-fill perceived' style='width: {perceived_pct:.1f}%'></div></div>"
            f"    <span class='bar-value'>{perceived_val:.1%}</span>"
            f"  </div>"
            f"</div>"
            f"<small>{_escape(item.get('reading', 'normal'))} · {_escape(item.get('listen_for', ''))}</small>"
            f"<small><strong>Next move:</strong> {_escape(item.get('first_move', ''))}</small>"
            "</div>"
        )
    return f"""
      <section>
        <h2>Frequency Repair Map</h2>
        <div class="metrics">{''.join(rows)}</div>
      </section>
    """


def _revision_agent_html(agent: dict | None) -> str:
    if not agent:
        return ""
    steps = agent.get("steps") or []
    if not steps:
        return ""
    rows = []
    for step in steps:
        rows.append(
            "<li>"
            f"<strong>{_escape(step.get('focus', 'Revision step'))}</strong>"
            f"<span>{_escape(step.get('action', ''))}</span>"
            f"<small>{_escape(step.get('why', ''))}</small>"
            "</li>"
        )
    return f"""
      <section>
        <h2>Revision Agent Checklist</h2>
        <p>{_escape(agent.get("goal") or agent.get("summary") or "Next revision checklist.")}</p>
        <ol class="actions">{''.join(rows)}</ol>
      </section>
    """


def _revision_impact_html(impact: dict | None) -> str:
    if not impact:
        return ""
    return f"""
      <section>
        <h2>Revision Impact</h2>
        <p><strong>{_escape(str(impact.get("verdict", "mixed")).title())}</strong></p>
        <h3>Improved</h3>
        {_list_items(impact.get("improvements") or [])}
        <h3>Regressions</h3>
        {_list_items(impact.get("regressions") or [])}
        <h3>Checks</h3>
        {_list_items(impact.get("checks") or [])}
      </section>
    """


def _revision_lesson_html(lesson: dict | None) -> str:
    if not lesson:
        return ""
    goal = lesson.get("goal") or {}
    return f"""
      <section>
        <h2>Revision Lesson</h2>
        <p><strong>{_escape(lesson.get("objective", "Next revision"))}</strong> · {_escape(goal.get("label", "Mix"))}</p>
        <p>{_escape(lesson.get("why_it_matters", ""))}</p>
        <h3>Try this</h3>
        {_list_items(lesson.get("steps") or [])}
        <h3>Listening checks</h3>
        {_list_items(lesson.get("listening_checks") or [])}
      </section>
    """


def _revision_coaching_html(coaching: dict | None) -> str:
    if not coaching:
        return ""
    deltas = coaching.get("metric_deltas") or []
    delta_rows = "".join(
        f"<div><strong>{_escape(item.get('value', 'n/a'))}{(' ' + _escape(item.get('unit', ''))) if item.get('unit') else ''}</strong><span>{_escape(item.get('label', 'Delta'))}</span></div>"
        for item in deltas
        if isinstance(item, dict)
    )
    return f"""
      <section>
        <h2>Before/After Coaching</h2>
        <p><strong>{_escape(coaching.get("headline", "Revision comparison"))}</strong></p>
        <p>Verdict: {_escape(coaching.get("verdict", "revision"))} · Score change: {_escape(coaching.get("score_delta", 0))}</p>
        {f'<div class="metrics">{delta_rows}</div>' if delta_rows else ''}
        <h3>Next focus</h3>
        <p>{_escape(coaching.get("next_focus", ""))}</p>
        <h3>Listening test</h3>
        <p>{_escape(coaching.get("listening_test", ""))}</p>
      </section>
    """


def _lesson_cards_html(cards: list[dict]) -> str:
    if not cards:
        return ""
    rows = []
    for card in cards:
        rows.append(
            "<article>"
            f"<h3>{_escape(card.get('flag', 'Mix issue'))}</h3>"
            f"<p>{_escape(card.get('meaning', ''))}</p>"
            f"<p><strong>Listen for:</strong> {_escape(card.get('listen_for', ''))}</p>"
            "<h4>First fixes</h4>"
            f"{_list_items(card.get('first_fixes') or [])}"
            "</article>"
        )
    return f"""
      <section>
        <h2>Educational Notes</h2>
        {''.join(rows)}
      </section>
    """


def _comparison_table(title: str, comparison: dict | None, advice: list[str]) -> str:
    if not comparison:
        return ""
    largest = comparison.get("largest_spectral_difference") or {}
    largest_perceived = comparison.get("largest_perceptual_difference") or {}
    return f"""
      <section>
        <h2>{_escape(title)}</h2>
        <div class="metrics">
          <div><strong>{_escape(comparison.get('rms_delta_db', 'n/a'))}</strong><span>RMS delta</span></div>
          <div><strong>{_escape(comparison.get('crest_delta_db', 'n/a'))}</strong><span>Crest delta</span></div>
          <div><strong>{_escape(comparison.get('stereo_width_delta', 'n/a'))}</strong><span>Width delta</span></div>
          <div><strong>{_escape(largest.get('band', 'n/a'))}</strong><span>Largest spectral</span></div>
          <div><strong>{_escape(largest_perceived.get('band', 'n/a'))}</strong><span>Largest perceived</span></div>
        </div>
        {_list_items(advice)}
      </section>
    """


def _reference_coaching_html(coaching: dict | None) -> str:
    if not coaching:
        return ""
    return f"""
      <section>
        <h2>Reference Coaching</h2>
        <p><strong>{_escape(coaching.get("headline", "Reference coaching"))}</strong></p>
        <p>{_escape(coaching.get("level_message", ""))}</p>
        <p>{_escape(coaching.get("tonal_message", ""))}</p>
        <p>{_escape(coaching.get("perceived_message", ""))}</p>
        <p>{_escape(coaching.get("dynamics_message", ""))}</p>
        <p>{_escape(coaching.get("stereo_message", ""))}</p>
        <p><strong>Next move:</strong> {_escape(coaching.get("next_move", ""))}</p>
        <p>{_escape(coaching.get("safe_use", ""))}</p>
      </section>
    """


def _chords_html(metrics: dict) -> str:
    chords_data = metrics.get("chords")
    if not chords_data:
        return ""
    key = chords_data.get("estimated_key", "Unknown")
    timeline = chords_data.get("progression", [])
    intervals = chords_data.get("intervals", [])
    
    timeline_html = []
    if not timeline:
        timeline_html.append("<p>No clear chords detected.</p>")
    else:
        timeline_html.append("<div class='chord-timeline'>")
        for seg in timeline:
            chord = seg.get("chord", "N.C.")
            duration = seg.get("duration", 0.0)
            start = seg.get("start_time", 0.0)
            end = seg.get("end_time", 0.0)
            extra_class = " nc" if chord == "N.C." else ""
            timeline_html.append(
                f"<div class='chord-card{extra_class}'>"
                f"<strong class='chord-name'>{_escape(chord)}</strong>"
                f"<span class='chord-time'>{start}s - {end}s</span>"
                f"<small class='chord-dur'>({duration}s)</small>"
                f"</div>"
            )
        timeline_html.append("</div>")

    intervals_html = []
    if intervals:
        intervals_html.append("<h3>Interval Relations</h3>")
        intervals_html.append("<ul class='interval-list'>")
        for iv in intervals:
            from_c = iv.get("from_chord", "")
            to_c = iv.get("to_chord", "")
            interval = iv.get("interval", "")
            intervals_html.append(
                f"<li>"
                f"<span class='chord-transition'><strong>{_escape(from_c)}</strong> ➔ <strong>{_escape(to_c)}</strong></span>"
                f" · <span class='interval-badge'>{_escape(interval)}</span>"
                f"</li>"
            )
        intervals_html.append("</ul>")

    return f"""
      <section>
        <h2>Musical Chord & Key Analysis</h2>
        <p><strong>Estimated Key:</strong> <span class="key-badge">{_escape(key)}</span></p>
        <h3>Chord Timeline</h3>
        {''.join(timeline_html)}
        {''.join(intervals_html)}
      </section>
    """


def report_html(report: dict) -> str:
    metrics = report.get("metrics") or {}
    flags = report.get("flags") or []
    flag_labels = [flag.get("label", "") for flag in flags if flag.get("label")]
    title = report.get("title") or metrics.get("filename") or "Mix Review Report"
    version = report.get("version_label", "")
    critique = (report.get("mix_critique") or {}).get("text", "")
    created = report.get("created_at", "")
    return f"""<!doctype html>
<html lang="en">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>{_escape(title)} mix review</title>
  <style>
    body {{ margin: 0; font-family: Inter, system-ui, -apple-system, BlinkMacSystemFont, "Segoe UI", sans-serif; color: #17201c; background: #f4f6f2; }}
    main {{ max-width: 980px; margin: 0 auto; padding: 36px 22px 60px; }}
    header, section {{ background: #fff; border: 1px solid #dce3d8; border-radius: 8px; padding: 20px; margin-bottom: 16px; box-shadow: 0 10px 24px rgba(32,44,36,.06); }}
    h1, h2 {{ margin: 0 0 12px; line-height: 1.1; }}
    h1 {{ font-size: 2rem; }}
    h2 {{ font-size: 1.1rem; color: #2f6f46; }}
    p {{ line-height: 1.55; }}
    .meta, .disclaimer {{ color: #4f5d53; }}
    .score {{ display: inline-flex; align-items: baseline; gap: 8px; color: #2f6f46; font-weight: 800; }}
    .score strong {{ font-size: 2.4rem; }}
    .metrics {{ display: grid; grid-template-columns: repeat(4, minmax(0, 1fr)); gap: 10px; }}
    .metrics div {{ border: 1px solid #edf1ea; border-radius: 8px; padding: 12px; background: #f7faf4; }}
    .metrics strong, .metrics span {{ display: block; overflow-wrap: anywhere; }}
    .metrics span, small {{ color: #4f5d53; font-size: .82rem; }}
    ul, ol {{ padding-left: 22px; }}
    li {{ margin: 8px 0; }}
    .actions li strong, .actions li span, .actions li small {{ display: block; }}
    pre {{ white-space: pre-wrap; overflow-wrap: anywhere; background: #f7faf4; border: 1px solid #edf1ea; border-radius: 8px; padding: 14px; }}
    @media (max-width: 680px) {{ .metrics {{ grid-template-columns: 1fr 1fr; }} }}
    @media (max-width: 460px) {{ .metrics {{ grid-template-columns: 1fr; }} main {{ padding: 18px 12px 40px; }} }}
    .key-badge {{
      display: inline-block;
      background: linear-gradient(135deg, #2f6f46, #418c5a);
      color: #fff;
      font-weight: bold;
      padding: 4px 10px;
      border-radius: 12px;
      font-size: 0.9rem;
    }}
    .chord-timeline {{
      display: flex;
      flex-wrap: wrap;
      gap: 10px;
      margin: 16px 0;
    }}
    .chord-card {{
      border: 1px solid #edf1ea;
      border-radius: 8px;
      padding: 12px 16px;
      background: #f7faf4;
      min-width: 100px;
      text-align: center;
      transition: transform 0.2s, box-shadow 0.2s;
    }}
    .chord-card:hover {{
      transform: translateY(-2px);
      box-shadow: 0 4px 12px rgba(47, 111, 70, 0.15);
      border-color: #2f6f46;
    }}
    .chord-card.nc {{
      background: #fafafa;
      border-color: #e0e0e0;
      color: #757575;
    }}
    .chord-card.nc:hover {{
      box-shadow: 0 4px 12px rgba(0, 0, 0, 0.05);
      border-color: #9e9e9e;
    }}
    .chord-name {{
      display: block;
      font-size: 1.2rem;
      margin-bottom: 4px;
      color: #17201c;
    }}
    .chord-card.nc .chord-name {{
      color: #757575;
    }}
    .chord-time, .chord-dur {{
      display: block;
      font-size: 0.8rem;
      color: #555;
    }}
    .interval-list {{
      list-style: none;
      padding: 0;
    }}
    .interval-list li {{
      padding: 8px 12px;
      background: #fdfdfd;
      border: 1px solid #edf1ea;
      border-radius: 6px;
      margin-bottom: 6px;
      display: inline-flex;
      align-items: center;
      gap: 12px;
    }}
    .interval-badge {{
      background: #eef5f0;
      color: #2f6f46;
      padding: 2px 8px;
      border-radius: 4px;
      font-size: 0.85rem;
      font-weight: bold;
    }}
    .chord-transition {{
      font-size: 0.95rem;
    }}
    .bar-chart {{
      margin: 10px 0;
      display: flex;
      flex-direction: column;
      gap: 6px;
    }}
    .bar-container {{
      display: flex;
      align-items: center;
      gap: 8px;
      font-size: 0.8rem;
    }}
    .bar-label {{
      width: 65px;
      color: #4f5d53;
      font-weight: 500;
    }}
    .bar-bg {{
      flex: 1;
      height: 8px;
      background: #edf1ea;
      border-radius: 4px;
      overflow: hidden;
    }}
    .bar-fill {{
      height: 100%;
      border-radius: 4px;
      transition: width 0.3s ease;
    }}
    .bar-fill.raw {{
      background: #418c5a;
    }}
    .bar-fill.perceived {{
      background: #2f6f46;
    }}
    .bar-value {{
      width: 45px;
      text-align: right;
      font-weight: bold;
      color: #17201c;
    }}
  </style>
</head>
<body>
  <main>
    <header>
      <p class="meta">Audio_Too Mix Review Lab · {_escape(created)}</p>
      <h1>{_escape(title)}{f" · {_escape(version)}" if version else ""}</h1>
      <p class="score"><strong>{_metric(report, "technical_score")}</strong><span>{_metric(report, "technical_rating")}</span></p>
      {f'<p class="score"><strong>{_escape((report.get("comparison") or {}).get("tonal_balance_score"))}</strong><span>Tonal balance vs reference</span></p>' if (report.get("comparison") or {}).get("tonal_balance_score") is not None else ''}
      <p>{_escape(report.get("summary", ""))}</p>
    </header>
    {_session_report_html(report.get("session_report"))}
    <section>
      <h2>Key Metrics</h2>
      <div class="metrics">
        <div><strong>{_metric(report, "peak_dbfs")}</strong><span>Peak dBFS</span></div>
        <div><strong>{_metric(report, "rms_dbfs_estimate")}</strong><span>RMS estimate</span></div>
        <div><strong>{_metric(report, "crest_factor_db")}</strong><span>Crest factor</span></div>
        <div><strong>{_metric(report, "stereo_correlation")}</strong><span>Stereo correlation</span></div>
        <div><strong>{_metric(report, "stereo_width_ratio")}</strong><span>Width ratio</span></div>
        <div><strong>{_escape((metrics.get("perceptual_summary") or {}).get("dominant_band", "n/a"))}</strong><span>Perceived focus</span></div>
        <div><strong>{_metric(report, "sample_rate")}</strong><span>Sample rate</span></div>
        <div><strong>{_metric(report, "duration_seconds")}</strong><span>Duration seconds</span></div>
      </div>
    </section>
    <section>
      <h2>Deeper Diagnostics</h2>
      <div class="metrics">
        <div><strong>{_escape((metrics.get("tonal_balance") or {}).get("profile", "n/a"))}</strong><span>Tonal profile</span></div>
        <div><strong>{_escape((metrics.get("dynamic_profile") or {}).get("profile", "n/a"))}</strong><span>Dynamics</span></div>
        <div><strong>{_escape((metrics.get("stereo_field") or {}).get("image", "n/a"))}</strong><span>Stereo image</span></div>
        <div><strong>{_escape((metrics.get("spectral_features") or {}).get("centroid_hz", "n/a"))}</strong><span>Centroid Hz</span></div>
      </div>
      <p>{_escape((metrics.get("tonal_balance") or {}).get("summary", ""))}</p>
      <p>{_escape((metrics.get("dynamic_profile") or {}).get("summary", ""))}</p>
      <p>{_escape((metrics.get("stereo_field") or {}).get("summary", ""))}</p>
    </section>
    <section>
      <h2>Transient &amp; Groove Analysis</h2>
      <div class="metrics">
        <div><strong>{_escape((metrics.get("transient_analysis") or {}).get("profile", "n/a"))}</strong><span>Transient profile</span></div>
        <div><strong>{_escape(((metrics.get("transient_analysis") or {}).get("compression_impact") or {}).get("status", "n/a"))}</strong><span>Compression impact</span></div>
        <div><strong>{_escape((metrics.get("transient_analysis") or {}).get("median_attack_ms", "n/a"))}</strong><span>Median attack ms</span></div>
        <div><strong>{_escape((metrics.get("transient_analysis") or {}).get("median_attack_sustain_ratio_db", "n/a"))}</strong><span>Attack/sustain dB</span></div>
        <div><strong>{_escape((metrics.get("groove_analysis") or {}).get("bpm", "n/a"))}</strong><span>Detected BPM</span></div>
        <div><strong>{_escape((metrics.get("groove_analysis") or {}).get("timing_class", "n/a"))}</strong><span>Timing class</span></div>
        <div><strong>{_escape((metrics.get("groove_analysis") or {}).get("mean_abs_deviation_ms", "n/a"))}</strong><span>Grid deviation ms</span></div>
        <div><strong>{_escape((metrics.get("groove_analysis") or {}).get("swing_percentage", "n/a"))}</strong><span>Swing percent</span></div>
        <div><strong>{_escape((metrics.get("groove_analysis") or {}).get("timing_consistency_percent", "n/a"))}</strong><span>Timing consistency</span></div>
      </div>
      <p>{_escape(((metrics.get("transient_analysis") or {}).get("compression_impact") or {}).get("diagnosis", ""))}</p>
    </section>
    {_chords_html(metrics)}
    {_goal_target_checks_html(metrics)}
    <section>
      <h2>Priority Actions</h2>
      {_actions_html(report.get("action_plan") or [])}
    </section>
    {_source_hypotheses_html(report.get("source_hypotheses") or [])}
    {_frequency_repair_map_html(report.get("frequency_repair_map") or [])}
    {_revision_coaching_html(report.get("revision_coaching"))}
    {_revision_lesson_html(report.get("revision_lesson"))}
    {_lesson_cards_html(report.get("lesson_cards") or [])}
    {_revision_agent_html(report.get("revision_agent"))}
    {_revision_impact_html(report.get("revision_impact"))}
    <section>
      <h2>Flags</h2>
      {_list_items(flag_labels)}
    </section>
    {_kenn_explanations_html(report.get("kenn_explanations"))}
    {_mix_review_critique_html(report.get("mix_review_critique"))}
    {_mix_style_html(report.get("mix_style"))}
    {_stem_solo_html(report.get("stem_solo"), report.get("stem_masking"))}
    {_comparison_table("Revision Comparison", report.get("version_comparison"), report.get("version_advice") or [])}
    {_reference_coaching_html(report.get("reference_coaching"))}
    {_comparison_table("Reference Comparison", report.get("comparison"), report.get("comparison_advice") or [])}
    <section>
      <h2>Engineer Critique</h2>
      <pre>{_escape(critique)}</pre>
    </section>
    <p class="disclaimer">{_escape(report.get("disclaimer", "First-pass technical analysis only. Use references and human listening for final decisions."))}</p>
  </main>
</body>
</html>"""
