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


def critique_metrics_payload(report: dict) -> dict:
    """Extract the Stage 10 + core metrics a critique should reason about.

    Kept separate from the wider action-plan/comparison payload used by the
    pre-existing whole-report critique in ``analysis_interpretation.py`` —
    this one is scoped to the new richer diagnostics (per-section LRA,
    stereo asymmetry, transient preservation, stem masking) plus the small
    set of core numbers needed to make those readable in context.
    """
    metrics = report.get("metrics") or report
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
        "transient_preservation": metrics.get("transient_preservation"),
        "stem_masking": metrics.get("stem_masking"),
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

    tp_data = payload.get("transient_preservation") or {}
    score_tp = tp_data.get("preservation_score")
    if score_tp is not None:
        profile = tp_data.get("profile", "")
        lines.append(
            f"Transient preservation across the compared render is '{profile.lower()}' "
            f"(score {score_tp:.2f}/1.0); "
            + (
                "attacks are coming through largely intact."
                if score_tp >= 0.85
                else "some attack smearing is measurable — check limiter/compressor attack and lookahead settings if punch feels softened."
            )
        )

    masking = payload.get("stem_masking") or {}
    if masking.get("ok") and masking.get("stems"):
        low_vis = min(masking["stems"], key=lambda s: s.get("overall_visibility", 1.0))
        if low_vis.get("overall_visibility", 1.0) < 0.6:
            lines.append(
                f"Among the supplied stems, '{low_vis.get('name')}' has the lowest simultaneous-masking "
                f"visibility ({low_vis.get('overall_visibility')}) — it's the stem most likely getting "
                f"buried by the others; consider carving space for it."
            )

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
            "audio. Do not invent instrumentation, genre, or causes not implied by the data. "
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
