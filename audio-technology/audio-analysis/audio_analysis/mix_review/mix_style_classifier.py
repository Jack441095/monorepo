"""Stage 10 — deterministic mix style classifier.

Classifies a mix's era, loudness-war participation, and vintage-vs-modern
mastering character directly from measured metrics (LUFS, dynamic
range/crest factor, spectral tilt). Genre is delegated to the existing
spectral-fingerprint matcher in
:mod:`audio_analysis.analysis_core.genre_profiles`
(``classify_reference_profile``) rather than reimplemented here.

Deterministic, rule-based classification is used throughout (no LLM call)
because these are exactly the kind of judgments a mixing/mastering
engineer would want to be able to trust and audit — "why did it say
loudness-war?" should have a one-line numeric answer, not a model's
best guess. Every threshold below is documented with its reasoning.
"""

from __future__ import annotations



def _metric_float(value: object, fallback: float = 0.0) -> float:
    try:
        return float(value)
    except (TypeError, ValueError):
        return fallback


# ---------------------------------------------------------------------------
# Loudness-war participation
# ---------------------------------------------------------------------------
#
# Reference points used to set thresholds:
#  - The TT DR Meter / Pleasurize Music Foundation's published DR rating
#    scale treats DR14+ as "excellent" dynamic range, DR8-11 as typical of
#    a competently mastered modern commercial release, and DR7 or below as
#    the "loudness war" zone associated with audible pumping and fatigue
#    (Ian Shepherd's "Dynamic Range Day" campaign popularized this scale;
#    it's also the basis of the dr.loudness-war.info database).
#  - This codebase measures crest factor (peak-to-RMS, dB) rather than the
#    TT DR algorithm's RMS-of-loudest-20%-vs-peak measure, but the two
#    correlate closely on full-mix material and use the same rough
#    numeric range, so the same cutoffs are reused here rather than
#    inventing new ones.
#  - Streaming loudness normalization (Spotify ~-14 LUFS, Apple Music
#    ~-16 LUFS, YouTube ~-14 LUFS) means a track mastered louder than
#    roughly -10 to -9 LUFS integrated gets turned down on playback with
#    no audible loudness benefit — so a release still mastered that hot
#    is a strong, purpose-built signal of loudness-war mastering rather
#    than an accident. -9 LUFS is used as the integrated-loudness cutoff.
LOUDNESS_WAR_LUFS_THRESHOLD = -9.0
LOUDNESS_WAR_CREST_THRESHOLD_DB = 8.0
LOUDNESS_WAR_SEVERE_CREST_DB = 5.0


def classify_loudness_war(metrics: dict) -> dict:
    lufs = metrics.get("integrated_lufs")
    lufs_val = _metric_float(lufs, fallback=None) if lufs not in (None, "", "n/a") else None
    crest = _metric_float(metrics.get("crest_factor_db"), fallback=None)

    if lufs_val is None or crest is None:
        return {
            "participant": False,
            "severity": "unknown",
            "confidence": 0.0,
            "reasoning": "Insufficient loudness/crest-factor data to classify.",
        }

    loud_enough = lufs_val > LOUDNESS_WAR_LUFS_THRESHOLD
    squashed = crest < LOUDNESS_WAR_CREST_THRESHOLD_DB
    participant = loud_enough and squashed

    if participant and crest < LOUDNESS_WAR_SEVERE_CREST_DB:
        severity = "severe"
    elif participant:
        severity = "moderate"
    elif loud_enough or squashed:
        severity = "borderline"
    else:
        severity = "none"

    reasoning = (
        f"Integrated loudness {lufs_val:.1f} LUFS "
        f"({'above' if loud_enough else 'at/below'} the {LOUDNESS_WAR_LUFS_THRESHOLD:.0f} LUFS "
        "streaming-normalization-defeating threshold), "
        f"crest factor {crest:.1f} dB "
        f"({'below' if squashed else 'at/above'} the {LOUDNESS_WAR_CREST_THRESHOLD_DB:.0f} dB "
        "DR-meter loudness-war cutoff)."
    )
    return {
        "participant": participant,
        "severity": severity,
        "confidence": 0.9 if (loud_enough == squashed) else 0.55,
        "reasoning": reasoning,
        "integrated_lufs": lufs_val,
        "crest_factor_db": crest,
    }


# ---------------------------------------------------------------------------
# Vintage vs. modern mastering character
# ---------------------------------------------------------------------------
#
# Vintage/analogue-era masters (pre-~1990s, before widespread digital
# brickwall limiting) characteristically have:
#  - Wide dynamic range: crest factor comfortably above the loudness-war
#    cutoff, typically DR12+ per the TT DR scale.
#  - A darker top end relative to modern masters: tape/vinyl mastering
#    chains and pre-digital mic/preamp/EQ choices roll off high frequencies
#    more than contemporary digital chains tuned for earbuds/phone
#    speakers, so the "air" (8-16kHz) spectral-band share is comparatively
#    low. 3% is used as the cutoff for "low air share" based on this
#    codebase's BANDS split, where a bright modern master typically shows
#    5-8%+ in the air band and a warm/vintage one commonly sits under 3%.
# Modern masters are the inverse: high loudness, compressed dynamics,
# brighter top end (tuned for translation on small speakers/earbuds).
VINTAGE_CREST_THRESHOLD_DB = 12.0
VINTAGE_AIR_SHARE_THRESHOLD = 0.03


def classify_vintage_or_modern(metrics: dict) -> dict:
    crest = _metric_float(metrics.get("crest_factor_db"), fallback=None)
    bands = metrics.get("bands") or {}
    air_share = _metric_float(bands.get("air"), fallback=None)

    if crest is None:
        return {"label": "unknown", "confidence": 0.0, "reasoning": "No crest-factor data available."}

    wide_dynamics = crest >= VINTAGE_CREST_THRESHOLD_DB
    dark_top_end = air_share is not None and air_share < VINTAGE_AIR_SHARE_THRESHOLD

    if wide_dynamics and (dark_top_end or air_share is None):
        label = "vintage-leaning"
        confidence = 0.85 if dark_top_end else 0.6
    elif not wide_dynamics and air_share is not None and not dark_top_end:
        label = "modern"
        confidence = 0.85
    elif wide_dynamics:
        label = "vintage-leaning"
        confidence = 0.55
    else:
        label = "modern"
        confidence = 0.55

    reasoning = (
        f"Crest factor {crest:.1f} dB "
        f"({'wide/vintage-typical' if wide_dynamics else 'narrow/modern-typical'}, "
        f"cutoff {VINTAGE_CREST_THRESHOLD_DB:.0f} dB)"
    )
    if air_share is not None:
        reasoning += (
            f"; air-band (8-16kHz) share {air_share:.3f} "
            f"({'dark/vintage-typical' if dark_top_end else 'bright/modern-typical'}, "
            f"cutoff {VINTAGE_AIR_SHARE_THRESHOLD:.2f})."
        )
    else:
        reasoning += "; no spectral band data available for the top-end check."

    return {"label": label, "confidence": round(confidence, 2), "reasoning": reasoning}


# ---------------------------------------------------------------------------
# Era bucket
# ---------------------------------------------------------------------------
#
# Coarse era buckets derived from the same loudness/dynamics evidence,
# reflecting well-documented mastering-loudness trends over time:
#  - "classic/pre-loudness-war" — wide dynamics, moderate loudness
#    (roughly pre-1990s practice, or any era mastered conservatively).
#  - "loudness-war era" — the CD-loudness-war signature (roughly
#    mid-1990s to ~2013): very loud, heavily limited.
#  - "streaming-normalized era" — post ~2013, once Spotify/YouTube/Apple
#    began normalizing playback loudness, removing the incentive to
#    master hotter than the -14ish LUFS normalization targets; loudness
#    tends to settle around -8 to -14 LUFS with DR8-12 as engineers
#    stopped racing for peak loudness (widely discussed industry
#    shift, e.g. Ian Shepherd's "loudness war is over" commentary and
#    Spotify's own mastering-loudness FAQ).
def classify_era(metrics: dict, loudness_war: dict) -> dict:
    lufs = metrics.get("integrated_lufs")
    lufs_val = _metric_float(lufs, fallback=None) if lufs not in (None, "", "n/a") else None
    crest = _metric_float(metrics.get("crest_factor_db"), fallback=None)

    if lufs_val is None or crest is None:
        return {"label": "unknown", "confidence": 0.0, "reasoning": "Insufficient loudness data."}

    if crest >= VINTAGE_CREST_THRESHOLD_DB and lufs_val <= -14.0:
        label = "classic / pre-loudness-war"
        reasoning = f"Wide dynamics (crest {crest:.1f} dB) at conservative loudness ({lufs_val:.1f} LUFS)."
        confidence = 0.75
    elif loudness_war.get("participant") and lufs_val > -9.0:
        label = "loudness-war era"
        reasoning = f"Heavily limited ({crest:.1f} dB crest) and mastered very hot ({lufs_val:.1f} LUFS)."
        confidence = 0.8
    elif -14.0 <= lufs_val <= -8.0 and crest >= 7.0:
        label = "streaming-normalized era"
        reasoning = (
            f"Loudness ({lufs_val:.1f} LUFS) and dynamics ({crest:.1f} dB crest) both sit in the range "
            "typical of masters made after streaming loudness normalization removed the incentive to "
            "over-compress."
        )
        confidence = 0.6
    else:
        label = "indeterminate"
        reasoning = (
            f"Loudness ({lufs_val:.1f} LUFS) / dynamics ({crest:.1f} dB crest) don't cleanly match "
            "any single era signature."
        )
        confidence = 0.3

    return {"label": label, "confidence": confidence, "reasoning": reasoning}


def classify_genre(metrics: dict) -> dict:
    """Delegate genre classification to the existing spectral-fingerprint matcher."""
    log_bands = metrics.get("log_bands_40")
    if not log_bands or len(log_bands) != 40:
        return {"genre_key": "", "genre_name": "Uncategorised", "confidence": 0.0, "distance_db": None}
    from audio_analysis.analysis_core.genre_profiles import classify_reference_profile
    return classify_reference_profile(log_bands, metrics)


def classify_mix_style(report_or_metrics: dict) -> dict:
    """Classify era, genre, loudness-war participation, and vintage/modern
    character for a mix, from its measured metrics.

    Accepts either a full mix-review report (``{"metrics": {...}, ...}``)
    or a bare metrics dict — both are common call shapes elsewhere in this
    codebase.
    """
    metrics = report_or_metrics.get("metrics") if "metrics" in report_or_metrics else report_or_metrics
    metrics = metrics or {}

    loudness_war = classify_loudness_war(metrics)
    vintage_modern = classify_vintage_or_modern(metrics)
    era = classify_era(metrics, loudness_war)
    genre = classify_genre(metrics)

    return {
        "genre": genre,
        "era": era,
        "loudness_war": loudness_war,
        "vintage_or_modern": vintage_modern,
        "summary": (
            f"{genre.get('genre_name', 'Uncategorised')}-leaning, {era.get('label', 'unknown')} "
            f"({vintage_modern.get('label', 'unknown')} mastering character)"
            + (", loudness-war participant" if loudness_war.get("participant") else "")
            + "."
        ),
    }
