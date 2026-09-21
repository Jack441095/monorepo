"""KENN-owned masking-risk analysis across two or more time-aligned stems.

This closes part of ``local_engine.NOT_EVALUATED_FAULT_FAMILIES``'s
``"masking"`` entry -- but deliberately as a separate tool with its own input
shape, not a silent addition to ``analyze_wav``. Masking is fundamentally a
question about *multiple isolated sources* competing for the same frequency
space at the same time; a single finished stereo mixdown alone cannot answer
it, so this module takes a list of separately uploaded stems instead of one
mixed file.

What this measures: for each pair of stems and each frequency band, the
fraction of overlapping time frames where both stems have audible energy
(above a floor) and are within a few dB of each other in that band -- i.e.
genuinely competing for the same frequency space, not just both non-silent.

What this does NOT claim: this is not a perceptual/psychoacoustic masking
model (no ITU/ISO masking-threshold curves, no critical-band weighting
beyond simple fixed Hz ranges). Real audible masking also depends on
transient timing, relative mix levels chosen deliberately by the engineer,
stereo placement, and listener perception -- none of which this measures.
Treat every finding here as "worth checking by ear", never as a certified
masking diagnosis. See docs/KENN_BETA_GAP_MATRIX.md for the qualification
status of this and the other explicitly-not-evaluated fault families.
"""

from __future__ import annotations

from typing import Any

try:
    # Package-relative import: used when this module is reached as
    # `core.masking_analysis` (this package's own __init__.py, and every
    # test file, both put `mix-review/` on sys.path).
    from .local_engine import (
        MIN_DURATION_SECONDS,
        UnsupportedAudioError,
        _decode_channels,
        validate_wav_upload,
    )
except ImportError:
    # Bare import: scripts/start_server.sh puts `mix-review/core` itself
    # directly on sys.path (matching local_engine.py's own zero-sibling-
    # import convention), so this module has no parent package in that
    # context and a relative import raises ImportError rather than
    # ModuleNotFoundError.
    from local_engine import (  # type: ignore[import-not-found, no-redef]
        MIN_DURATION_SECONDS,
        UnsupportedAudioError,
        _decode_channels,
        validate_wav_upload,
    )

try:
    import numpy as _np
except ImportError:  # pragma: no cover - exercised only in minimal environments.
    _np = None

SCHEMA = "kenn.mix_review_masking_analysis.v1"

# Named per common mixing-engineer vocabulary, not a psychoacoustic Bark/ERB
# scale -- this is a measured-energy proxy, not a perceptual model (see the
# module docstring).
MASKING_BANDS: tuple[tuple[str, int, int], ...] = (
    ("sub_bass", 20, 80),
    ("bass", 80, 250),
    ("low_mid", 250, 500),
    ("mid", 500, 2000),
    ("upper_mid", 2000, 4000),
    ("presence", 4000, 8000),
    ("brilliance", 8000, 16000),
)
FFT_WINDOW = 4096
FFT_HOP = 2048
ACTIVE_FLOOR_DBFS = -50.0
COMPETING_WITHIN_DB = 6.0
COMPETING_FRACTION_FLAG = 0.20
MAX_STEMS = 12


def _evidence_packet(
    labels: list[str],
    *,
    framerate: int,
    overlap_seconds: float,
    findings: list[dict[str, Any]],
    limitations: list[str],
) -> dict[str, Any]:
    """Expose masking candidates through KENN's shared evidence contract."""
    facts: list[dict[str, Any]] = [
        {"name": "stem_count", "value": len(labels), "unit": "stems", "source": "stem_masking_analysis", "confidence": "measured"},
        {"name": "sample_rate", "value": framerate, "unit": "Hz", "source": "stem_masking_analysis", "confidence": "measured"},
        {"name": "analyzed_seconds", "value": float(round(overlap_seconds, 2)), "unit": "seconds", "source": "stem_masking_analysis", "confidence": "measured"},
        {"name": "masking_candidate_count", "value": len(findings), "unit": "candidates", "source": "stem_masking_analysis", "confidence": "measured_proxy"},
    ]
    strongest = max(
        (
            item for item in findings
            if isinstance(item, dict)
            and isinstance((item.get("evidence") or {}).get("competing_frame_fraction"), (int, float))
        ),
        key=lambda item: float(item["evidence"]["competing_frame_fraction"]),
        default=None,
    )
    if strongest is not None:
        fraction = float(strongest["evidence"]["competing_frame_fraction"])
        facts.extend([
            {"name": "masking_highest_competing_frame_fraction", "value": fraction, "unit": "ratio", "source": "stem_masking_analysis", "confidence": "measured_proxy"},
            {"name": "masking_highest_pair", "value": " + ".join(str(value)[:96] for value in strongest.get("stems", [])[:2]), "unit": "", "source": "stem_masking_analysis", "confidence": "measured_proxy"},
            {"name": "masking_highest_band", "value": str(strongest.get("band") or "")[:64], "unit": "", "source": "stem_masking_analysis", "confidence": "measured_proxy"},
        ])
    return {
        "schema": "kenn.evidence.v1",
        "source": "stem_masking_analysis",
        "captured_at_age_seconds": None,
        "observed_at_epoch": None,
        "facts": facts,
        "limitations": [str(item)[:512] for item in limitations[:8] if str(item).strip()],
    }


def _mono_from_wav(payload: bytes) -> tuple[Any, int]:
    channels, framerate, channel_count = _decode_channels(payload)
    if channel_count == 1:
        mono = channels[0]
    else:
        mono = sum(channels) / channel_count if _np is None else _np.mean(_np.stack(channels), axis=0)
    return mono, framerate


def _native_band_energy(signal: Any, framerate: int) -> tuple[Any, str] | None:
    """Use the optional KENN native kernel when it is loadable."""
    try:
        from kenn.core import native_fft

        result = native_fft.masking_band_energy(
            signal,
            framerate,
            fft_size=FFT_WINDOW,
            hop=FFT_HOP,
        )
    except (AttributeError, ImportError, OSError, RuntimeError, TypeError, ValueError):
        return None
    if not result or "energy" not in result:
        return None
    return (
        _np.asarray(result["energy"], dtype=float),
        str(result.get("backend") or "cpp-native"),
    )


def _band_energy_over_time_with_backend(signal: Any, framerate: int) -> tuple[Any, str]:
    """Return an (n_frames, n_bands) array of per-band RMS magnitude."""
    native = _native_band_energy(signal, framerate)
    if native is not None:
        return native

    n_frames = 1 + max(0, (len(signal) - FFT_WINDOW) // FFT_HOP)
    freqs = _np.fft.rfftfreq(FFT_WINDOW, 1.0 / framerate)
    band_index = [
        _np.where((freqs >= lo) & (freqs < hi))[0] for _name, lo, hi in MASKING_BANDS
    ]
    window = _np.hanning(FFT_WINDOW)
    out = _np.zeros((n_frames, len(MASKING_BANDS)))
    for i in range(n_frames):
        frame = signal[i * FFT_HOP : i * FFT_HOP + FFT_WINDOW]
        if len(frame) < FFT_WINDOW:
            break
        spectrum = _np.abs(_np.fft.rfft(frame * window))
        for band, idx in enumerate(band_index):
            out[i, band] = float(_np.sqrt(_np.mean(spectrum[idx] ** 2))) if len(idx) else 0.0
    return out, "python-numpy-reference"


def _band_energy_over_time(signal: Any, framerate: int) -> Any:
    """Return an (n_frames, n_bands) array of per-band RMS magnitude."""
    return _band_energy_over_time_with_backend(signal, framerate)[0]


def _to_dbfs(magnitude: Any) -> Any:
    return 20.0 * _np.log10(_np.maximum(magnitude, 1e-9))


def analyze_stem_masking(stems: list[tuple[str, bytes]]) -> dict[str, Any]:
    """Analyze frequency-band energy competition across 2+ time-aligned stems.

    ``stems`` is a list of ``(label, wav_bytes)`` pairs. Every stem must be a
    valid mono/stereo 16- or 24-bit PCM WAV at the same sample rate; stems of
    different lengths are compared over their shared overlapping duration
    only (the longer stem's extra tail is not analyzed, and this is recorded
    as a limitation on the receipt).
    """
    if _np is None:
        return {
            "schema": SCHEMA,
            "ok": False,
            "error": "Masking analysis requires the optional numpy dependency, which is not installed.",
        }
    if len(stems) < 2:
        return {"schema": SCHEMA, "ok": False, "error": "At least 2 stems are required to analyze masking between them."}
    if len(stems) > MAX_STEMS:
        return {
            "schema": SCHEMA,
            "ok": False,
            "error": f"At most {MAX_STEMS} stems are supported per analysis; split a larger session into groups.",
        }
    labels = [label for label, _payload in stems]
    if len(set(labels)) != len(labels):
        return {"schema": SCHEMA, "ok": False, "error": "Stem labels must be unique."}

    for label, payload in stems:
        validation = validate_wav_upload(payload, f"{label}.wav", label=label)
        if not validation["ok"]:
            return {"schema": SCHEMA, "ok": False, "error": validation["error"]}

    decoded: dict[str, tuple[Any, int]] = {}
    for label, payload in stems:
        try:
            mono, framerate = _mono_from_wav(payload)
        except UnsupportedAudioError as exc:
            return {"schema": SCHEMA, "ok": False, "error": f"Could not decode {label}: {exc}"}
        decoded[label] = (mono, framerate)

    framerates = {framerate for _mono, framerate in decoded.values()}
    if len(framerates) > 1:
        detail = ", ".join(f"{label}={framerate}Hz" for label, (_mono, framerate) in decoded.items())
        return {
            "schema": SCHEMA,
            "ok": False,
            "error": f"All stems must share one sample rate to compare them time-aligned; got: {detail}",
        }
    framerate = framerates.pop()

    shortest = min(len(mono) for mono, _framerate in decoded.values())
    overlap_seconds = shortest / framerate
    if overlap_seconds < MIN_DURATION_SECONDS:
        return {
            "schema": SCHEMA,
            "ok": False,
            "error": f"Shared overlapping duration ({overlap_seconds:.2f}s) is below the {MIN_DURATION_SECONDS}s minimum for a meaningful analysis.",
        }
    truncated_labels = [label for label, (mono, _fr) in decoded.items() if len(mono) > shortest]

    band_energy_with_backend = {
        label: _band_energy_over_time_with_backend(mono[:shortest], framerate)
        for label, (mono, _fr) in decoded.items()
    }
    band_energy = {label: item[0] for label, item in band_energy_with_backend.items()}
    implementations = {item[1] for item in band_energy_with_backend.values()}
    implementation = implementations.pop() if len(implementations) == 1 else "mixed"
    band_energy_db = {label: _to_dbfs(energy) for label, energy in band_energy.items()}

    findings: list[dict[str, Any]] = []
    for i, label_a in enumerate(labels):
        for label_b in labels[i + 1 :]:
            db_a, db_b = band_energy_db[label_a], band_energy_db[label_b]
            n_frames = db_a.shape[0]
            if n_frames == 0:
                continue
            for band_idx, (band_name, lo_hz, hi_hz) in enumerate(MASKING_BANDS):
                both_active = (db_a[:, band_idx] > ACTIVE_FLOOR_DBFS) & (db_b[:, band_idx] > ACTIVE_FLOOR_DBFS)
                competing = both_active & (_np.abs(db_a[:, band_idx] - db_b[:, band_idx]) < COMPETING_WITHIN_DB)
                fraction = float(competing.sum()) / n_frames
                if fraction < COMPETING_FRACTION_FLAG:
                    continue
                severity = "high" if fraction >= 0.5 else "medium" if fraction >= 0.35 else "low"
                findings.append(
                    {
                        "fault_family": "masking",
                        "detected": True,
                        "severity": severity,
                        "confidence": 0.6,
                        "stems": [label_a, label_b],
                        "band": band_name,
                        "frequency_range_hz": [lo_hz, hi_hz],
                        "evidence": {
                            "competing_frame_fraction": round(fraction, 3),
                            "active_floor_dbfs": ACTIVE_FLOOR_DBFS,
                            "competing_within_db": COMPETING_WITHIN_DB,
                        },
                        "explanation": (
                            f"'{label_a}' and '{label_b}' have comparable simultaneous energy "
                            f"(within {COMPETING_WITHIN_DB:.0f} dB of each other) in the {band_name} "
                            f"range ({lo_hz}-{hi_hz} Hz) for {fraction * 100:.0f}% of their shared "
                            "playing time -- worth listening for whether one is masking the other."
                        ),
                        "suggested_next_step": (
                            f"Listen to '{label_a}' and '{label_b}' together in this range; consider a "
                            "complementary EQ cut on one of them, or check whether this is an intentional "
                            "unison/layering choice rather than an unwanted conflict."
                        ),
                        "limitations": (
                            "A measured energy-competition proxy, not a perceptual masking model -- "
                            "does not account for transient timing, stereo placement, relative mix "
                            "levels, or listener perception."
                        ),
                    }
                )

    limitations = [
        "Measured energy-competition proxy only, not a perceptual/psychoacoustic masking model.",
        "Stems of different lengths are compared only over their shared overlapping duration.",
        "Requires stems that are already time-aligned (e.g. exported from the same session at the same start point).",
    ]
    return {
        "schema": SCHEMA,
        "ok": True,
        "stems": labels,
        "sample_rate_hz": framerate,
        "analyzed_seconds": round(overlap_seconds, 2),
        "truncated_stems": truncated_labels,
        "bands": [{"name": name, "low_hz": lo, "high_hz": hi} for name, lo, hi in MASKING_BANDS],
        "implementation": implementation,
        "findings": findings,
        "limitations": limitations,
        "evidence": _evidence_packet(
            labels,
            framerate=framerate,
            overlap_seconds=overlap_seconds,
            findings=findings,
            limitations=limitations,
        ),
    }
