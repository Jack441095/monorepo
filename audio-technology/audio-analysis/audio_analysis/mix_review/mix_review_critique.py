"""Stage 10 — AI-augmented mix critique.

Generates prose critique text for a mix review report, LLM-assisted when
enabled and reachable, with a deterministic template fallback otherwise.

Env-gating mirrors the pattern used by KENN's local LM in
``studio/kenn/kenn/core/chat_answer.py::make_answer`` — specifically the
fix applied there: the environment flag is checked *together with* the
caller's ``allow_llm`` parameter using ``and``, so a caller that explicitly
passes ``allow_llm=False`` always gets the deterministic path even if the
env var is set, and the env var being unset always gives the deterministic
path even if a caller passes ``allow_llm=True``. Neither condition alone is
sufficient to reach the LLM branch — this was a real bug in KENN (a caller
could unintentionally get an LLM answer when it had asked for a
non-LLM/deterministic-only response, because the code checked the env var
without accounting for the parameter, or vice versa) and is deliberately
replicated here in its fixed form:

    if allow_llm and os.environ.get("MIX_REVIEW_CRITIQUE_ENABLED") == "1":
        ...use the LLM...
    # else: deterministic fallback, always.

Off by default: unless ``MIX_REVIEW_CRITIQUE_ENABLED=1`` is set in the
environment AND the caller passes ``allow_llm=True`` (the default), this
module never calls out to an LLM.
"""

from __future__ import annotations

import os
from typing import Any, Protocol

from audio_analysis.integration.handoff import (
    project_report_publication, qualified_stem_masking_summary, stem_masking_evidence,
    transient_preservation_evidence,
)


def _critique_env_enabled() -> bool:
    return os.environ.get("MIX_REVIEW_CRITIQUE_ENABLED", "").strip().lower() in {"1", "true", "yes", "on"}


class CritiqueLLMProvider(Protocol):
    """Minimal interface this module needs from an LLM provider.

    Deliberately compatible with ``audio_too.model_runtime.LLMProvider``
    (``generate(messages, timeout) -> LLMResult`` with a ``.content``
    attribute) so Thursday/KENN's existing local-first provider stack can
    be reused as-is rather than inventing a second LLM client here.
    """

    def generate(self, messages: list[dict[str, str]], timeout: int = 10) -> Any: ...


def _metric_float(value: object, fallback: float = 0.0) -> float:
    try:
        return float(value)
    except (TypeError, ValueError):
        return fallback


def _default_provider() -> CritiqueLLMProvider | None:
    try:
        from nite_core.model_runtime import DEFAULT_LLM
        return DEFAULT_LLM
    except Exception:
        return None


def _qualified_transient_payload(transient: object) -> dict:
    """Retain the critique's historical score key only with raw source activity proof."""
    qualified = transient_preservation_evidence(transient) if isinstance(transient, dict) else {}
    if not qualified:
        # Empty proof marks an attempted but unqualified comparison for both critique paths.
        return {}
    return {
        "preservation_score": qualified["score"], "profile": qualified["profile"],
        "matched_event_count": qualified["matched_event_count"], "activity": qualified["activity"],
    }


def critique_metrics_payload(report: dict) -> dict:
    """Extract the Stage 10 + core metrics a critique should reason about.

    Kept separate from the wider action-plan/comparison payload used by the
    pre-existing whole-report critique in ``analysis_interpretation.py`` —
    this one is scoped to the new richer diagnostics (per-section LRA,
    stereo asymmetry, transient preservation, stem masking) plus the small
    set of core numbers needed to make those readable in context.
    """
    # Cached flags can contain the same unqualified comparison prose as the report.
    report = project_report_publication(report)
    metrics = report.get("metrics") or report
    # The workflow stores optional analyses at the top level; explicit canonical
    # abstention must take precedence over an older nested metrics cache.
    transient = report.get("transient_preservation", metrics.get("transient_preservation"))
    masking = report.get("stem_masking", metrics.get("stem_masking"))
    return {
        "technical_rating": metrics.get("technical_rating"),
        "technical_score": metrics.get("technical_score"),
        "integrated_lufs": metrics.get("integrated_lufs"),
        "true_peak_dbfs": metrics.get("true_peak_dbfs"),
        "crest_factor_db": metrics.get("crest_factor_db"),
        "stereo_correlation": metrics.get("stereo_correlation"),
        "stereo_width_ratio": metrics.get("stereo_width_ratio"),
        "stereo_asymmetry": metrics.get("stereo_asymmetry"),
        "loudness_range_lu": metrics.get("loudness_range_lu"),
        "loudness_range_by_section": metrics.get("loudness_range_by_section"),
        "transient_preservation": _qualified_transient_payload(transient) if transient is not None else None,
        # Share handoff qualification so neither deterministic nor LLM critique
        # receives name-derived profiles or unsupported repair predictions.
        "stem_masking": stem_masking_evidence(masking) if masking is not None else None,
        "style_classification": metrics.get("style_classification"),
        "tonal_balance": metrics.get("tonal_balance"),
        "flags": [flag.get("label") for flag in (report.get("flags") or []) if flag.get("label")][:6],
    }


def _fmt(value: object, unit: str = "", digits: int = 2) -> str:
    if value is None or value == "n/a":
        return "not measured"
    try:
        return f"{float(value):.{digits}f}{unit}"
    except (TypeError, ValueError):
        return str(value)


def deterministic_critique(payload: dict) -> str:
    """Template-based critique built directly from measured Stage 10 metrics.

    No invented claims — every sentence is traceable to a specific field in
    ``payload``. This is the fallback used whenever the LLM path is
    disabled, unreachable, or returns something unusable, so it must stand
    on its own as a genuinely useful critique, not a placeholder.
    """
    lines: list[str] = []

    rating = payload.get("technical_rating") or "Technical review"
    score = payload.get("technical_score")
    lines.append(f"Overall: {rating}" + (f" ({score}/100)." if score is not None else "."))

    lufs = payload.get("integrated_lufs")
    tp = payload.get("true_peak_dbfs")
    crest = payload.get("crest_factor_db")
    lines.append(
        f"Loudness reads {_fmt(lufs, ' LUFS')} integrated with a true peak of {_fmt(tp, ' dBFS')} "
        f"and {_fmt(crest, ' dB')} crest factor."
    )

    lra_sections = payload.get("loudness_range_by_section") or []
    measured_sections = [s for s in lra_sections if s.get("loudness_range_lu") is not None]
    if measured_sections:
        lras = [s["loudness_range_lu"] for s in measured_sections]
        widest = max(measured_sections, key=lambda s: s["loudness_range_lu"])
        narrowest = min(measured_sections, key=lambda s: s["loudness_range_lu"])
        if max(lras) - min(lras) > 2.0:
            lines.append(
                f"Loudness range varies noticeably across sections — widest around "
                f"{_fmt(widest.get('start_seconds'), 's', 1)} ({_fmt(widest['loudness_range_lu'], ' LU')}) "
                f"versus a tighter section near {_fmt(narrowest.get('start_seconds'), 's', 1)} "
                f"({_fmt(narrowest['loudness_range_lu'], ' LU')}); worth checking whether that's an "
                f"intentional arrangement dynamic or an inconsistency to smooth out."
            )
        else:
            lines.append("Loudness range is fairly consistent section-to-section.")

    asym = payload.get("stereo_asymmetry") or {}
    if asym.get("asymmetric"):
        lines.append(
            f"Stereo image is biased toward the {asym.get('louder_channel', 'one')} channel "
            f"({_fmt(asym.get('level_asymmetry_db'), ' dB', 2)} persistent level difference) — "
            f"confirm this is intentional panning rather than a gain-staging or export mistake."
        )
    elif asym:
        lines.append("L/R channel balance looks even; no persistent one-sided bias detected.")

    raw_transient = payload.get("transient_preservation")
    tp_data = _qualified_transient_payload(raw_transient)
    if tp_data:
        lines.append(
            f"Transient preservation across matched render events is '{tp_data['profile'].lower()}' "
            f"(score {tp_data['preservation_score']:.2f}/1.0). "
            "This matched-event proxy does not establish audible damage or its cause; "
            "compare the renders at matched loudness."
        )
    elif raw_transient is not None:
        # Direct template callers need the same source gate as the LLM payload builder.
        lines.append("Transient preservation withheld: both raw render RMS readings must "
                     "exceed -60 dBFS and matched events must be available.")

    masking = payload.get("stem_masking")
    summary = qualified_stem_masking_summary(masking) or stem_masking_evidence(masking)
    if summary:
        lines.append(
            f"Among jointly active stem preview frames, '{summary['lowest_visibility_stem']}' "
            f"has the lowest relative ERB preview visibility ({summary['lowest_visibility']}). "
            "This uncalibrated relative-spectrum proxy suggests a listening check; "
            "it does not establish audible masking severity, a whole-song result, or an EQ repair."
        )
    elif masking is not None:
        # Legacy profiles cannot qualify from the enclosing mix's activity.
        lines.append("Stem visibility withheld: no qualifying jointly active real preview frames.")

    style = payload.get("style_classification") or {}
    if style.get("era_label"):
        lines.append(
            f"Loudness/dynamics profile reads as {style.get('era_label')}"
            + (f" ({style.get('loudness_war_participant') and 'loudness-war spec' or 'wide dynamic range'})." if "loudness_war_participant" in style else ".")
        )

    flags = payload.get("flags") or []
    if flags:
        lines.append("Open flags: " + ", ".join(flags) + ".")

    lines.append("Listening check: A/B against a trusted reference at matched loudness before acting on any of the above.")
    return "\n".join(lines).strip()


def _valid_llm_critique(text: str) -> bool:
    return bool(text) and len(text.strip()) >= 40 and len(text) < 4000


def generate_critique(
    report: dict,
    *,
    allow_llm: bool = True,
    provider: CritiqueLLMProvider | None = None,
    timeout: int = 20,
) -> dict:
    """Produce a mix-review critique, LLM-assisted when enabled, else deterministic.

    Returns ``{"mode": "llm"|"deterministic", "available": bool, "message": str, "text": str}``.
    ``text`` is always populated — callers can display it unconditionally.
    """
    payload = critique_metrics_payload(report)
    fallback = deterministic_critique(payload)

    # Mirrors kenn.core.chat_answer.make_answer's fixed gating: both the
    # caller's allow_llm flag AND the env var must be true. Checking only
    # one of the two was the historical bug in KENN's equivalent code path.
    if allow_llm and _critique_env_enabled():
        active_provider = provider or _default_provider()
        if active_provider is None:
            return {
                "mode": "deterministic",
                "available": False,
                "message": "No LLM provider available; using deterministic critique.",
                "text": fallback,
            }
        system = (
            "You are Audio_Too's mix review assistant. Write a concise, practical critique "
            "(120-200 words) using ONLY the supplied JSON metrics. Do not claim to hear the "
            "audio. ERB preview visibility is an uncalibrated relative-spectrum proxy, not audible "
            "masking severity or an EQ repair recommendation. Transient preservation is a matched-event proxy; "
            "it does not establish audible damage, limiter settings or repair choices. "
            "Do not invent instrumentation, genre, or causes not implied by the data. "
            "Cover: overall technical read, any section-to-section loudness-range inconsistency, "
            "stereo balance, transient preservation (if present), and stem masking (if present). "
            "End with one concrete, actionable next step."
        )
        import json
        user = "Mix review metrics:\n" + json.dumps(payload, indent=2, default=str)
        try:
            result = active_provider.generate(
                [
                    {"role": "system", "content": system},
                    {"role": "user", "content": user},
                ],
                timeout=timeout,
            )
            text = (getattr(result, "content", None) or "").strip()
        except Exception as exc:
            return {
                "mode": "deterministic",
                "available": False,
                "message": f"LLM critique unavailable ({exc.__class__.__name__}); using deterministic critique.",
                "text": fallback,
            }
        if not _valid_llm_critique(text):
            return {
                "mode": "deterministic",
                "available": False,
                "message": "LLM critique returned an unusable response; using deterministic critique.",
                "text": fallback,
            }
        return {
            "mode": "llm",
            "available": True,
            "message": "LLM critique generated.",
            "text": text,
        }

    return {
        "mode": "deterministic",
        "available": False,
        "message": "Mix Review AI critique off; set MIX_REVIEW_CRITIQUE_ENABLED=1 and pass allow_llm=True to enable.",
        "text": fallback,
    }
