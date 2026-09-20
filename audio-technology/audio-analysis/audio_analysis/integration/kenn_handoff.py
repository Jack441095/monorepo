"""KENN handoff for AutoMix parameter explanations (Stage 9).

This module builds rich, source-grounded questions that get routed through
KENN's existing retrieval + answer pipeline (``kenn.core.chat_answer``) so
AutoMix parameter choices ("why is the compression ratio 3.5:1 on the vocal
bus?") and Mix Review flags ("why did I get a 'true peak clipping' flag?")
come back as answers cited to a real note in
``studio/kenn/kenn/Training_Data_Notes/`` — never an invented number from a
parallel LLM call.

Design notes
------------
- We deliberately do NOT build a second LLM call path here. Every explanation
  goes through ``kenn.core.chat_answer.answer_payload``/``answer_payload_stream``,
  which already does BM25+embedding retrieval, note-grounded template
  synthesis, quality gating, and (optionally, if configured) LLM rewriting
  validated against the retrieved evidence. That's what keeps answers
  grounded to real notes instead of inventing plausible-sounding numbers.
- The *only* numbers we're willing to assert as fact are the ones already
  present in the actual rendered ``MixPlan``/``StemMixConfig``/``BusMixConfig``
  (i.e. the real values AutoMix used) or a Mix Review flag/metric payload.
  Those real values get folded into the natural-language question itself
  (e.g. "...currently set to 3.5:1...") so KENN's retrieval is anchored to
  the actual figure, and the returned "Sources:" section identifies which
  Training_Data_Notes file backs the explanation.
"""

from __future__ import annotations

import dataclasses
from typing import Any


def _strip_past_reasoning_block(answer: str) -> str:
    """Remove chat_answer.py's "Past reasoning on this topic:" block from an
    answer before it goes into a written report.

    That block is stitched in from a GLOBAL, cross-session, query-text-
    similarity lookup (``query_reasoning_traces`` in
    ``kenn/knowledge/reasoning.py``) -- not scoped to the current session or
    topic. Verified directly (2026-07-30, building the podcast-check
    explanations below): a set of topically-different podcast checks asked
    back-to-back (hum, then rumble) had the *rumble* answer's entire body
    replaced by the *hum* answer, because "past reasoning" matched on shared
    vocabulary ("podcast", "recording", frequency numbers) rather than topic.
    chat_answer.py's own comment says its TTS layer relies on the blank-line
    boundaries around this block to strip it before speech; a written report
    needs the same treatment and has no such layer, hence this helper. This
    only trims the block for report display -- it does not touch (and can't
    fix) the underlying global reasoning-trace matching."""
    marker = "Past reasoning on this topic:"
    if marker not in answer:
        return answer
    before, _, rest = answer.partition(marker)
    # The block ends at the first blank line after the marker (chat_answer.py
    # always appends a trailing "" after past_reasoning for this exact reason).
    _, _, after = rest.partition("\n\n")
    return (before.rstrip() + ("\n\n" + after.lstrip() if after.strip() else "")).strip()


def _as_dict(obj: Any) -> dict:
    """Normalize a StemMixConfig/BusMixConfig dataclass (or a plain dict) to a dict."""
    if obj is None:
        return {}
    if dataclasses.is_dataclass(obj) and not isinstance(obj, type):
        return dataclasses.asdict(obj)
    if isinstance(obj, dict):
        return dict(obj)
    return {}


# ── AutoMix parameter explanations ──────────────────────────────────────


def build_parameter_question(
    parameter: str,
    *,
    stem_name: str | None = None,
    instrument: str | None = None,
    genre: str | None = None,
    value: Any = None,
    decision_log_line: str | None = None,
) -> str:
    """Build a natural-language question grounded in the *real* AutoMix value.

    ``parameter`` is a short description such as "compression ratio",
    "reverb send level", "stereo width", or "gain staging". ``value`` is the
    actual value AutoMix chose (pulled from the rendered MixPlan), so the
    question itself carries the real figure rather than asking KENN to
    guess one.
    """
    subject = " ".join(part for part in (instrument, stem_name) if part).strip() or "this stem"
    genre_clause = f" in a {genre} mix" if genre else ""
    if value not in (None, ""):
        question = f"Why is the {parameter} for {subject} set to {value}{genre_clause}?"
    else:
        question = f"Why does AutoMix choose the {parameter} it uses for {subject}{genre_clause}?"
    if decision_log_line:
        question += f" AutoMix's own decision log says: \"{decision_log_line}\""
    return question


def explain_automix_parameter(
    parameter: str,
    *,
    stem_name: str | None = None,
    instrument: str | None = None,
    genre: str | None = None,
    value: Any = None,
    decision_log_line: str | None = None,
    session_id: str = "",
    allow_llm: bool = True,
) -> dict:
    """Ask KENN to explain a specific AutoMix parameter decision.

    Returns the full KENN answer payload (answer text, sources, grounding,
    confidence, etc.) from ``kenn.core.chat_answer.answer_payload`` — the
    same pipeline used for every other KENN question, so this reuses
    retrieval/quality-gating rather than a parallel path.
    """
    from kenn.core.chat_answer import answer_payload

    question = build_parameter_question(
        parameter,
        stem_name=stem_name,
        instrument=instrument,
        genre=genre,
        value=value,
        decision_log_line=decision_log_line,
    )
    payload = answer_payload(question, limit=5, allow_llm=allow_llm, session_id=session_id)
    if isinstance(payload.get("answer"), str):
        payload["answer"] = _strip_past_reasoning_block(payload["answer"])
    payload["automix_parameter"] = parameter
    payload["automix_stem_name"] = stem_name or ""
    payload["automix_instrument"] = instrument or ""
    payload["automix_value"] = value
    payload["automix_decision_log_line"] = decision_log_line or ""
    return payload


def explain_mix_review_flag(
    flag_label: str,
    *,
    detail: str = "",
    severity: str = "",
    session_id: str = "",
    allow_llm: bool = True,
) -> dict:
    """Ask KENN to explain a Mix Review flag/warning (e.g. "true peak clipping")."""
    from kenn.core.chat_answer import answer_payload

    severity_clause = f" (flagged as {severity})" if severity else ""
    detail_clause = f" The report says: \"{detail}\"" if detail else ""
    question = f"What does the mix review flag '{flag_label}'{severity_clause} mean and how do I fix it?{detail_clause}"
    payload = answer_payload(question, limit=5, allow_llm=allow_llm, session_id=session_id)
    if isinstance(payload.get("answer"), str):
        payload["answer"] = _strip_past_reasoning_block(payload["answer"])
    payload["mix_review_flag_label"] = flag_label
    payload["mix_review_flag_severity"] = severity
    payload["mix_review_flag_detail"] = detail
    return payload


# ── Bulk annotation for report injection ────────────────────────────────


def _stem_parameter_candidates(stem: Any) -> list[dict]:
    """Pick the parameters worth explaining for a single stem config."""
    cfg = _as_dict(stem)
    stem_name = cfg.get("stem_name", "")
    instrument = cfg.get("instrument", "")
    out: list[dict] = []

    if cfg.get("gain_db") not in (None, 0.0):
        out.append({
            "parameter": "gain staging",
            "stem_name": stem_name,
            "instrument": instrument,
            "value": f"{cfg['gain_db']:+.1f} dB",
        })

    compressor = cfg.get("compressor")
    if compressor:
        ratio = compressor.get("ratio")
        out.append({
            "parameter": "compression ratio",
            "stem_name": stem_name,
            "instrument": instrument,
            "value": f"{ratio}:1" if ratio is not None else None,
        })

    if cfg.get("reverb_send"):
        out.append({
            "parameter": "reverb send level",
            "stem_name": stem_name,
            "instrument": instrument,
            "value": f"{cfg['reverb_send'] * 100:.0f}%",
        })

    width = cfg.get("stereo_width")
    if width is not None and abs(width - 1.0) > 1e-4:
        out.append({
            "parameter": "stereo width",
            "stem_name": stem_name,
            "instrument": instrument,
            "value": f"{width:.2f}",
        })

    return out


def annotate_mix_plan_with_kenn(
    mix_plan: Any,
    *,
    max_items: int = 6,
    session_id: str = "",
    allow_llm: bool = False,
) -> list[dict]:
    """Explain the most notable parameter decisions in a rendered MixPlan.

    Bounded to ``max_items`` so report generation stays fast (each KENN
    call is local retrieval, not a network LLM call by default —
    ``allow_llm`` defaults to False here specifically to keep this path
    fast and deterministic for report injection). Any failure explaining an
    individual parameter is swallowed so a KENN/index problem never blocks
    mixdown delivery — the report simply omits that explanation.
    """
    genre = getattr(mix_plan, "genre", None) or (mix_plan.get("genre") if isinstance(mix_plan, dict) else None)
    stems = getattr(mix_plan, "stems", None)
    if stems is None and isinstance(mix_plan, dict):
        stems = mix_plan.get("stems", [])
    stems = stems or []

    bus = getattr(mix_plan, "bus", None)
    if bus is None and isinstance(mix_plan, dict):
        bus = mix_plan.get("bus")

    candidates: list[dict] = []
    for stem in stems:
        candidates.extend(_stem_parameter_candidates(stem))

    bus_cfg = _as_dict(bus)
    if bus_cfg.get("bus_compressor"):
        ratio = bus_cfg["bus_compressor"].get("ratio")
        candidates.append({
            "parameter": "compression ratio",
            "stem_name": "master bus",
            "instrument": "master bus",
            "value": f"{ratio}:1" if ratio is not None else None,
        })
    if bus_cfg.get("limiter_ceiling_db") is not None:
        candidates.append({
            "parameter": "limiter ceiling",
            "stem_name": "master bus",
            "instrument": "master bus",
            "value": f"{bus_cfg['limiter_ceiling_db']:.1f} dBFS",
        })

    explanations: list[dict] = []
    for item in candidates[:max_items]:
        try:
            payload = explain_automix_parameter(
                item["parameter"],
                stem_name=item.get("stem_name"),
                instrument=item.get("instrument"),
                genre=genre,
                value=item.get("value"),
                session_id=session_id,
                allow_llm=allow_llm,
            )
        except Exception:
            continue
        explanations.append({
            "parameter": item["parameter"],
            "stem_name": item.get("stem_name", ""),
            "instrument": item.get("instrument", ""),
            "value": item.get("value"),
            "question": payload.get("question", ""),
            "answer": payload.get("answer", ""),
            "sources": payload.get("sources", []),
            "confidence": payload.get("confidence", ""),
            "weak_match": payload.get("weak_match", False),
        })
    return explanations


# ── Live in-DAW session suggestions (Stage L, 2026-07-12) ───────────────
#
# Read-only. This is the *only* Python-side entry point for Stage L's
# near-term MVP: it takes a small slice of Ableton Live Object Model (LOM)
# state (handed to it by an M4L device, over HTTP — see
# app/routes/ableton_routes.py's /api/ableton/live-suggestion) and turns it
# into a grounded KENN question, same answer_payload() pipeline as every
# other explanation in this module. There is nothing in this function, or
# anywhere it calls into, that can write a value back into a live Ableton
# session — the M4L device shows the user the returned suggestion; the user
# decides whether to touch their own session. See Stage L §L4/§L5 in
# docs/AUDIO_MVP_MASTER_PLAN.md.


def build_live_session_question(
    *,
    track_name: str,
    device_chain: list[str] | None = None,
    key_params: dict | None = None,
    genre: str | None = None,
) -> str:
    """Build a natural-language question grounded in a live track's real,
    currently-loaded device chain and parameter values (not guessed)."""
    genre_clause = f" in a {genre} mix" if genre else ""
    chain_clause = ""
    if device_chain:
        chain_clause = f" It currently has this device chain: {', '.join(device_chain)}."
    params_clause = ""
    if key_params:
        pairs = ", ".join(f"{key}={value}" for key, value in key_params.items())
        params_clause = f" Key parameter values right now: {pairs}."
    return (
        f"What would you suggest for the track '{track_name}'{genre_clause}?"
        f"{chain_clause}{params_clause}"
    )


def explain_live_session_state(
    *,
    track_name: str,
    device_chain: list[str] | None = None,
    key_params: dict | None = None,
    genre: str | None = None,
    session_id: str = "",
    allow_llm: bool = True,
) -> dict:
    """Ask KENN for a grounded, read-only suggestion about a live track's
    current state.

    Returns the full KENN answer payload (answer text, sources,
    ``weak_match``, ``found``, etc.) from
    ``kenn.core.chat_answer.answer_payload`` — the same retrieval/quality-
    gating pipeline as every other KENN-grounded surface in this codebase.
    A ``weak_match``/not-``found`` result must be shown to the user as
    "KENN isn't confident here" rather than suppressed or guessed past,
    same rule as ``explain_automix_parameter`` above.
    """
    from kenn.core.chat_answer import answer_payload

    question = build_live_session_question(
        track_name=track_name, device_chain=device_chain, key_params=key_params, genre=genre,
    )
    payload = answer_payload(question, limit=5, allow_llm=allow_llm, session_id=session_id)
    if isinstance(payload.get("answer"), str):
        payload["answer"] = _strip_past_reasoning_block(payload["answer"])
    payload["live_track_name"] = track_name
    payload["live_device_chain"] = device_chain or []
    payload["live_key_params"] = key_params or {}
    return payload


# ── Dynamic EQ explanations (Stage C, 2026-07-09) ───────────────────────


def explain_dynamic_eq_cut(
    frequency_hz: float,
    *,
    mean_prominence_db: float | None = None,
    persistence: float | None = None,
    genre: str | None = None,
    session_id: str = "",
    allow_llm: bool = True,
) -> dict:
    """Ask KENN to explain a dynamic EQ cut AutoMix applied at a specific
    frequency — same grounded-answer pipeline as
    ``explain_automix_parameter``, not a parallel LLM path.

    ``frequency_hz``/``mean_prominence_db``/``persistence`` come from
    ``analysis_core.resonance_detection.detect_resonant_bands`` (via the
    ``dynamic_eq_bands`` key on ``mix_and_render_stems``'s render result) —
    the real values the detector measured, not invented ones, folded into
    the question the same way AutoMix's real parameter values are.
    """
    from kenn.core.chat_answer import answer_payload

    genre_clause = f" in a {genre} mix" if genre else ""
    detail_bits = []
    if mean_prominence_db is not None:
        detail_bits.append(f"it was sticking out {mean_prominence_db:.1f} dB above its neighboring frequencies")
    if persistence is not None:
        detail_bits.append(f"present for {persistence * 100:.0f}% of the track")
    detail_clause = f" ({', '.join(detail_bits)})" if detail_bits else ""
    question = (
        f"Why did AutoMix apply a dynamic EQ cut around {frequency_hz:.0f} Hz{genre_clause}?"
        f"{detail_clause}"
    )
    payload = answer_payload(question, limit=5, allow_llm=allow_llm, session_id=session_id)
    if isinstance(payload.get("answer"), str):
        payload["answer"] = _strip_past_reasoning_block(payload["answer"])
    payload["dynamic_eq_frequency_hz"] = frequency_hz
    payload["dynamic_eq_mean_prominence_db"] = mean_prominence_db
    payload["dynamic_eq_persistence"] = persistence
    return payload


def annotate_dynamic_eq_with_kenn(
    dynamic_eq_bands: list[dict],
    *,
    genre: str | None = None,
    max_items: int = 6,
    session_id: str = "",
    allow_llm: bool = False,
) -> list[dict]:
    """Explain every dynamic EQ cut in a rendered mix (bounded, best-effort —
    mirrors ``annotate_mix_plan_with_kenn``'s shape and defaults exactly, so
    both feed the same report-rendering path). ``allow_llm`` defaults to
    False here too, for the same reason: report injection should stay fast
    and deterministic, not block on a network/local LLM call per band.
    """
    explanations: list[dict] = []
    for band in (dynamic_eq_bands or [])[:max_items]:
        frequency_hz = band.get("frequency_hz")
        if frequency_hz is None:
            continue
        try:
            payload = explain_dynamic_eq_cut(
                float(frequency_hz),
                mean_prominence_db=band.get("mean_prominence_db"),
                persistence=band.get("persistence"),
                genre=genre,
                session_id=session_id,
                allow_llm=allow_llm,
            )
        except Exception:
            continue
        explanations.append({
            "parameter": "dynamic EQ cut",
            "stem_name": "master bus",
            "instrument": f"{frequency_hz:.0f} Hz",
            "value": f"{band.get('mean_prominence_db', 0):.1f} dB reduction" if band.get("mean_prominence_db") is not None else None,
            "question": payload.get("question", ""),
            "answer": payload.get("answer", ""),
            "sources": payload.get("sources", []),
            "confidence": payload.get("confidence", ""),
            "weak_match": payload.get("weak_match", False),
        })
    return explanations


# ── Master bus EQ band explanations (Stage 9.6, 2026-07-17) ─────────────
#
# Every ``bus_eq_bands`` entry that carries a ``reason`` string (reference-
# track matching in ``generate_mix_plan``'s "D. Reference EQ Matching" step,
# verbal-feedback corrections in ``apply_feedback_to_plan``, or a diagnostic
# caller-supplied band via ``run_local_automix(extra_bus_eq_bands=...)``) is
# already a real, grounded decision AutoMix made for a stated reason — this
# folds that reason into the question the same way ``explain_dynamic_eq_cut``
# folds in the detector's measured prominence, so KENN answers "why is there
# a +4.0 dB shelf at 300 Hz on the master bus?" grounded to a real note
# instead of staying silent on it. Bands with no ``reason`` (defaults with no
# stated cause) are skipped — there is nothing real to ground a question in.


def explain_bus_eq_band(
    frequency_hz: float,
    *,
    gain_db: float | None = None,
    band_type: str = "",
    reason: str = "",
    genre: str | None = None,
    session_id: str = "",
    allow_llm: bool = True,
) -> dict:
    """Ask KENN to explain a master bus EQ band AutoMix applied for a stated
    reason — same grounded-answer pipeline as ``explain_automix_parameter``
    and ``explain_dynamic_eq_cut``, not a parallel path.
    """
    from kenn.core.chat_answer import answer_payload

    genre_clause = f" in a {genre} mix" if genre else ""
    gain_clause = f" ({gain_db:+.1f} dB)" if gain_db is not None else ""
    type_clause = f" {band_type}" if band_type else ""
    reason_clause = f" AutoMix's own reasoning: \"{reason}\"" if reason else ""
    question = (
        f"Why does AutoMix have a{type_clause} master bus EQ band at "
        f"{frequency_hz:.0f} Hz{gain_clause}{genre_clause}?{reason_clause}"
    )
    payload = answer_payload(question, limit=5, allow_llm=allow_llm, session_id=session_id)
    if isinstance(payload.get("answer"), str):
        payload["answer"] = _strip_past_reasoning_block(payload["answer"])
    payload["bus_eq_frequency_hz"] = frequency_hz
    payload["bus_eq_gain_db"] = gain_db
    payload["bus_eq_type"] = band_type
    payload["bus_eq_reason"] = reason
    return payload


def annotate_bus_eq_bands_with_kenn(
    bus_eq_bands: list[dict],
    *,
    genre: str | None = None,
    max_items: int = 6,
    session_id: str = "",
    allow_llm: bool = False,
) -> list[dict]:
    """Explain every reasoned master bus EQ band in a rendered mix (bounded,
    best-effort — mirrors ``annotate_dynamic_eq_with_kenn``'s shape and
    defaults exactly, so all three feed the same report-rendering path).
    Only bands carrying a non-empty ``reason`` are explained; unreasoned
    default bands are skipped.
    """
    explanations: list[dict] = []
    reasoned = [b for b in (bus_eq_bands or []) if isinstance(b, dict) and b.get("reason")]
    for band in reasoned[:max_items]:
        frequency_hz = band.get("frequency")
        if frequency_hz is None:
            continue
        try:
            payload = explain_bus_eq_band(
                float(frequency_hz),
                gain_db=band.get("gain_db"),
                band_type=str(band.get("type", "")),
                reason=str(band.get("reason", "")),
                genre=genre,
                session_id=session_id,
                allow_llm=allow_llm,
            )
        except Exception:
            continue
        explanations.append({
            "parameter": "master bus EQ band",
            "stem_name": "master bus",
            "instrument": f"{frequency_hz:.0f} Hz",
            "value": f"{band.get('gain_db', 0):+.1f} dB" if band.get("gain_db") is not None else None,
            "question": payload.get("question", ""),
            "answer": payload.get("answer", ""),
            "sources": payload.get("sources", []),
            "confidence": payload.get("confidence", ""),
            "weak_match": payload.get("weak_match", False),
        })
    return explanations


# ── Masking de-mask correction explanations (Stage 9.7, 2026-07-18) ─────
#
# mix_and_render_stems' render result carries ``masking_corrections`` — a
# dict keyed by stem name, valued by the exact move dict applied (real
# frequency_hz/max_reduction_db pulled from the relationship engine's own
# scored candidate, not invented). Same grounded-answer contract as every
# other explanation in this module.


def explain_masking_correction(
    stem_name: str,
    *,
    frequency_hz: float,
    max_reduction_db: float | None = None,
    genre: str | None = None,
    session_id: str = "",
    allow_llm: bool = True,
) -> dict:
    """Ask KENN to explain a masking de-mask move AutoMix applied to a stem."""
    from kenn.core.chat_answer import answer_payload

    genre_clause = f" in a {genre} mix" if genre else ""
    reduction_clause = f" (up to {max_reduction_db:.1f} dB reduction)" if max_reduction_db is not None else ""
    question = (
        f"Why did AutoMix apply a masking de-mask correction to '{stem_name}' "
        f"at {frequency_hz:.0f} Hz{reduction_clause}{genre_clause}?"
    )
    payload = answer_payload(question, limit=5, allow_llm=allow_llm, session_id=session_id)
    if isinstance(payload.get("answer"), str):
        payload["answer"] = _strip_past_reasoning_block(payload["answer"])
    payload["masking_stem_name"] = stem_name
    payload["masking_frequency_hz"] = frequency_hz
    payload["masking_max_reduction_db"] = max_reduction_db
    return payload


def annotate_masking_corrections_with_kenn(
    masking_corrections: dict[str, dict],
    *,
    genre: str | None = None,
    max_items: int = 6,
    session_id: str = "",
    allow_llm: bool = False,
) -> list[dict]:
    """Explain every applied masking de-mask move in a rendered mix (bounded,
    best-effort — mirrors ``annotate_dynamic_eq_with_kenn``'s shape and
    defaults exactly, so all of these feed the same report-rendering path).
    """
    explanations: list[dict] = []
    items = list((masking_corrections or {}).items())[:max_items]
    for stem_name, move in items:
        if not isinstance(move, dict):
            continue
        frequency_hz = move.get("frequency_hz")
        if frequency_hz is None:
            continue
        try:
            payload = explain_masking_correction(
                stem_name,
                frequency_hz=float(frequency_hz),
                max_reduction_db=move.get("max_reduction_db"),
                genre=genre,
                session_id=session_id,
                allow_llm=allow_llm,
            )
        except Exception:
            continue
        explanations.append({
            "parameter": "masking de-mask correction",
            "stem_name": stem_name,
            "instrument": f"{frequency_hz:.0f} Hz",
            "value": f"{move.get('max_reduction_db', 0):.1f} dB max reduction" if move.get("max_reduction_db") is not None else None,
            "question": payload.get("question", ""),
            "answer": payload.get("answer", ""),
            "sources": payload.get("sources", []),
            "confidence": payload.get("confidence", ""),
            "weak_match": payload.get("weak_match", False),
        })
    return explanations


# ── Mono-compatibility correction explanations (Stage 9.7, 2026-07-18) ──
#
# mix_and_render_stems' render result carries ``mono_compat_corrections`` —
# a dict keyed by stem name, valued by {"severity": ..., "correction_factor":
# ...}, the real values the detector/correction stage applied.


def explain_mono_compat_correction(
    stem_name: str,
    *,
    severity: str,
    correction_factor: float | None = None,
    genre: str | None = None,
    session_id: str = "",
    allow_llm: bool = True,
) -> dict:
    """Ask KENN to explain a mono-compatibility narrowing correction AutoMix
    applied to a stem."""
    from kenn.core.chat_answer import answer_payload

    genre_clause = f" in a {genre} mix" if genre else ""
    factor_clause = f" (narrowed to a {correction_factor:.2f} width factor)" if correction_factor is not None else ""
    question = (
        f"Why did AutoMix apply a mono-compatibility correction to '{stem_name}' "
        f"(flagged {severity}){factor_clause}{genre_clause}?"
    )
    payload = answer_payload(question, limit=5, allow_llm=allow_llm, session_id=session_id)
    if isinstance(payload.get("answer"), str):
        payload["answer"] = _strip_past_reasoning_block(payload["answer"])
    payload["mono_compat_stem_name"] = stem_name
    payload["mono_compat_severity"] = severity
    payload["mono_compat_correction_factor"] = correction_factor
    return payload


def annotate_mono_compat_corrections_with_kenn(
    mono_compat_corrections: dict[str, dict],
    *,
    genre: str | None = None,
    max_items: int = 6,
    session_id: str = "",
    allow_llm: bool = False,
) -> list[dict]:
    """Explain every applied mono-compatibility correction in a rendered mix
    (bounded, best-effort — same shape/defaults as the other annotate_*
    helpers in this module).
    """
    explanations: list[dict] = []
    items = list((mono_compat_corrections or {}).items())[:max_items]
    for stem_name, correction in items:
        if not isinstance(correction, dict):
            continue
        severity = correction.get("severity")
        if not severity:
            continue
        try:
            payload = explain_mono_compat_correction(
                stem_name,
                severity=str(severity),
                correction_factor=correction.get("correction_factor"),
                genre=genre,
                session_id=session_id,
                allow_llm=allow_llm,
            )
        except Exception:
            continue
        explanations.append({
            "parameter": "mono-compatibility correction",
            "stem_name": stem_name,
            "instrument": str(severity),
            "value": f"{correction.get('correction_factor', 0):.2f} width factor" if correction.get("correction_factor") is not None else None,
            "question": payload.get("question", ""),
            "answer": payload.get("answer", ""),
            "sources": payload.get("sources", []),
            "confidence": payload.get("confidence", ""),
            "weak_match": payload.get("weak_match", False),
        })
    return explanations


# ── Reference track profile explanations (Stage 9.8, 2026-07-18) ────────
#
# Unlike every other explain_*/annotate_* pair in this module, this one is
# not explaining a decision AutoMix made about a render — it grounds a
# question about a *reference track itself* (its own measured tonal-balance
# profile, from scripts/eval/analyze_reference_tracks.py), so KENN can
# answer "how bright/dark is this reference track" with a real number
# instead of a guess. Same answer_payload() pipeline as everything else.


def explain_reference_track_profile(
    track_name: str,
    *,
    high_to_low_ratio: float,
    bands7: dict[str, float] | None = None,
    genre: str | None = None,
    session_id: str = "",
    allow_llm: bool = True,
) -> dict:
    """Ask KENN to explain what a reference track's measured tonal-balance
    profile (high-to-low energy ratio, and optionally its 7-band shares)
    means -- e.g. how bright/dark/balanced it reads."""
    from kenn.core.chat_answer import answer_payload

    genre_clause = f" in a {genre} context" if genre else ""
    bands_clause = ""
    if bands7:
        top = sorted(bands7.items(), key=lambda kv: -kv[1])[:2]
        bands_clause = f" Its most prominent bands are {top[0][0]} and {top[1][0]}." if len(top) >= 2 else ""
    question = (
        f"What does a high-to-low energy ratio of {high_to_low_ratio:.2f} mean for the "
        f"reference track '{track_name}'{genre_clause}?{bands_clause}"
    )
    payload = answer_payload(question, limit=5, allow_llm=allow_llm, session_id=session_id)
    if isinstance(payload.get("answer"), str):
        payload["answer"] = _strip_past_reasoning_block(payload["answer"])
    payload["reference_track_name"] = track_name
    payload["reference_track_high_to_low_ratio"] = high_to_low_ratio
    payload["reference_track_bands7"] = bands7 or {}
    return payload


def annotate_reference_track_profiles_with_kenn(
    profiles: dict[str, dict],
    *,
    genre: str | None = None,
    max_items: int = 6,
    session_id: str = "",
    allow_llm: bool = False,
) -> list[dict]:
    """Explain every analyzed reference track's profile (bounded,
    best-effort — same shape/defaults as the other annotate_* helpers).
    ``profiles`` is keyed by filename, valued by
    ``scripts/eval/analyze_reference_tracks.py``'s per-track output
    (``high_to_low_ratio``, ``bands7``, ...).
    """
    explanations: list[dict] = []
    items = list((profiles or {}).items())[:max_items]
    for track_name, profile in items:
        if not isinstance(profile, dict):
            continue
        ratio = profile.get("high_to_low_ratio")
        if ratio is None:
            continue
        try:
            payload = explain_reference_track_profile(
                track_name,
                high_to_low_ratio=float(ratio),
                bands7=profile.get("bands7"),
                genre=genre,
                session_id=session_id,
                allow_llm=allow_llm,
            )
        except Exception:
            continue
        explanations.append({
            "parameter": "reference track profile",
            "stem_name": track_name,
            "instrument": "reference track",
            "value": f"{ratio:.2f} high-to-low ratio",
            "question": payload.get("question", ""),
            "answer": payload.get("answer", ""),
            "sources": payload.get("sources", []),
            "confidence": payload.get("confidence", ""),
            "weak_match": payload.get("weak_match", False),
        })
    return explanations


# ── Mix Review flag explanations, proactive (Stage D, 2026-07-09) ───────


_SEVERITY_RANK = {"high": 0, "medium": 1, "low": 2}


def annotate_flags_with_kenn(
    flags: list[dict],
    *,
    max_items: int = 4,
    session_id: str = "",
    allow_llm: bool = False,
) -> list[dict]:
    """Proactively explain the most consequential Mix Review flags in a
    report, not just ones a user happens to ask about (Stage 9's
    ``explain_mix_review_flag`` was request-only; this is the same grounded
    pipeline, just triggered automatically at report-generation time — same
    ``allow_llm=False`` default and best-effort-per-item contract as
    ``annotate_mix_plan_with_kenn`` for the same reason: report generation
    should stay fast and deterministic, and one bad KENN call must never
    block the whole report).

    Bounded to the ``max_items`` highest-severity flags (high before medium
    before low, stable order within a severity tier) — a report with many
    minor flags shouldn't trigger a KENN call for every single one.
    """
    ranked = sorted(
        (f for f in (flags or []) if isinstance(f, dict) and f.get("label")),
        key=lambda f: _SEVERITY_RANK.get(str(f.get("severity", "")).lower(), 3),
    )
    explanations: list[dict] = []
    for flag in ranked[:max_items]:
        label = str(flag["label"])
        try:
            payload = explain_mix_review_flag(
                label,
                detail=str(flag.get("detail", "")),
                severity=str(flag.get("severity", "")),
                session_id=session_id,
                allow_llm=allow_llm,
            )
        except Exception:
            continue
        explanations.append({
            "flag": label,
            "severity": flag.get("severity", ""),
            "detail": flag.get("detail", ""),
            "question": payload.get("question", ""),
            "answer": payload.get("answer", ""),
            "sources": payload.get("sources", []),
            "confidence": payload.get("confidence", ""),
            "weak_match": payload.get("weak_match", False),
        })
    return explanations


# ── Podcast readiness check explanations (Stage 9's pattern, extended to
# audio_analysis/podcast/podcast_analysis.py's spoken-word checks) ──────


def explain_podcast_check(
    label: str,
    *,
    status: str = "",
    measured: str = "",
    target: str = "",
    fix: str = "",
    session_id: str = "",
    allow_llm: bool = True,
) -> dict:
    """Ask KENN to explain a podcast/spoken-word readiness check (e.g.
    "Sibilance", "Electrical hum") -- same grounded-answer contract as
    ``explain_mix_review_flag``, just phrased for dialogue delivery instead
    of a music mix."""
    from kenn.core.chat_answer import answer_payload

    status_clause = f" (flagged as {status})" if status else ""
    measured_clause = f" Measured {measured}, target {target}." if measured else ""
    fix_clause = f" The report's suggested fix: \"{fix}\"" if fix else ""
    question = (
        f"For a podcast or spoken-word recording, what does the check "
        f"'{label}'{status_clause} mean and how do I fix it?{measured_clause}{fix_clause}"
    )
    payload = answer_payload(question, limit=5, allow_llm=allow_llm, session_id=session_id)
    if isinstance(payload.get("answer"), str):
        payload["answer"] = _strip_past_reasoning_block(payload["answer"])
    payload["podcast_check_label"] = label
    payload["podcast_check_status"] = status
    return payload


def annotate_podcast_checks_with_kenn(
    checks: list[dict],
    *,
    max_items: int = 6,
    session_id: str = "",
    allow_llm: bool = False,
) -> list[dict]:
    """Proactively explain a podcast report's non-"ok" checks (bounded,
    best-effort -- same ``allow_llm=False``/never-blocks contract as
    ``annotate_flags_with_kenn``). A clean "ok" check doesn't need grounding;
    only "warn"/"fail" checks are worth a KENN call, ranked fail-before-warn.

    Each check gets its own generated session id rather than sharing the
    caller's ``session_id`` across every call in the loop, so KENN's
    followup/session-context logic (``is_followup_query`` /
    ``_build_session_context`` in ``chat_answer.py``, genuinely session-
    scoped) can't treat one check as a followup to a previous, unrelated one.
    This does NOT fix the separate "past reasoning" contamination documented
    on ``_strip_past_reasoning_block`` -- that lookup is global and keyed by
    query text, not session id; ``explain_podcast_check`` strips it directly.
    """
    import uuid as _uuid

    ranked = sorted(
        (c for c in (checks or []) if isinstance(c, dict) and c.get("label")
         and c.get("status") in ("warn", "fail")),
        key=lambda c: 0 if c.get("status") == "fail" else 1,
    )
    explanations: list[dict] = []
    for check in ranked[:max_items]:
        label = str(check["label"])
        check_session_id = f"{session_id}:podcast-check:{check.get('id', label)}:{_uuid.uuid4().hex[:8]}"
        try:
            payload = explain_podcast_check(
                label,
                status=str(check.get("status", "")),
                measured=str(check.get("measured", "")),
                target=str(check.get("target", "")),
                fix=str(check.get("fix", "")),
                session_id=check_session_id,
                allow_llm=allow_llm,
            )
        except Exception:
            continue
        explanations.append({
            "parameter": label,
            "stem_name": "podcast",
            "instrument": "",
            "value": check.get("measured"),
            "question": payload.get("question", ""),
            "answer": payload.get("answer", ""),
            "sources": payload.get("sources", []),
            "confidence": payload.get("confidence", ""),
            "weak_match": payload.get("weak_match", False),
        })
    return explanations
