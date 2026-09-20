"""Stage 10 — Mix Review Enhancements: tests for new metrics, AI critique,
style classifier, and stem solo.

Uses synthetic signals with known properties rather than real commercial
audio (none is available in this environment), so these tests verify the
math does what it claims on controlled inputs — not the master plan's
80%-agreement-with-commercial-references benchmark, which requires real
reference tracks this environment doesn't have.
"""

from __future__ import annotations

import math
import os
import sys
from pathlib import Path

import numpy as np
import pytest

ROOT = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(ROOT / "studio" / "audio_analysis"))
sys.path.insert(0, str(ROOT))

from audio_analysis.analysis_core.analysis_features import stereo_asymmetry
from audio_analysis.analysis_core.loudness import loudness_range_by_section, loudness_range_for_span
from audio_analysis.analysis_core.transient_groove import transient_preservation
from audio_analysis.analysis_core.analysis_core import compare_transient_preservation, stem_frequency_masking
from audio_analysis.mix_review import mix_review_critique
from audio_analysis.mix_review import mix_style_classifier
from audio_analysis.mixdown import stem_solo


SR = 44100


def _sine(freq: float, duration_s: float, sample_rate: int = SR, amp: float = 0.5) -> list[float]:
    n = int(duration_s * sample_rate)
    return [amp * math.sin(2 * math.pi * freq * i / sample_rate) for i in range(n)]


def _white_noise(duration_s: float, sample_rate: int = SR, amp: float = 0.3, seed: int = 42) -> list[float]:
    import random
    rng = random.Random(seed)
    n = int(duration_s * sample_rate)
    return [amp * (2 * rng.random() - 1) for _ in range(n)]


# ---------------------------------------------------------------------------
# 1a. Stereo asymmetry
# ---------------------------------------------------------------------------


def test_stereo_asymmetry_detects_balanced_signal() -> None:
    left = _sine(440.0, 2.0)
    right = _sine(440.0, 2.0)
    result = stereo_asymmetry(left, right, SR)
    assert abs(result["level_asymmetry_db"]) < 0.1
    assert result["asymmetric"] is False
    assert result["louder_channel"] == "none"


def test_stereo_asymmetry_detects_persistent_right_bias() -> None:
    left = _sine(440.0, 2.0, amp=0.2)
    right = _sine(440.0, 2.0, amp=0.5)  # ~8 dB louder than left
    result = stereo_asymmetry(left, right, SR)
    assert result["level_asymmetry_db"] > 5.0
    assert result["asymmetric"] is True
    assert result["louder_channel"] == "right"
    assert result["mean_balance"] > 0.15


def test_stereo_asymmetry_distinguishes_from_pure_width() -> None:
    # Wide but balanced: independent noise per channel, same RMS level.
    # This should NOT be flagged as asymmetric even though the side/mid
    # energy ratio is high (that's width, not asymmetry).
    left = _white_noise(2.0, seed=1)
    right = _white_noise(2.0, seed=2)
    result = stereo_asymmetry(left, right, SR)
    assert result["asymmetric"] is False
    assert abs(result["level_asymmetry_db"]) < 1.0


# ---------------------------------------------------------------------------
# 1b. LRA (loudness range) per structural section
# ---------------------------------------------------------------------------


def test_loudness_range_by_section_detects_dynamic_contrast() -> None:
    # Section 1: constant loud tone (low LRA expected)
    # Section 2: alternating loud/quiet bursts (higher LRA expected)
    sr = 48000
    loud_section = _sine(200.0, 10.0, sample_rate=sr, amp=0.6)
    dynamic_section = []
    for burst in range(10):
        amp = 0.6 if burst % 2 == 0 else 0.05
        dynamic_section.extend(_sine(200.0, 1.0, sample_rate=sr, amp=amp))

    left = loud_section + dynamic_section
    right = list(left)
    sections = [
        {"index": 0, "label": "Loud section", "start_seconds": 0.0, "end_seconds": 10.0},
        {"index": 1, "label": "Dynamic section", "start_seconds": 10.0, "end_seconds": 20.0},
    ]
    results = loudness_range_by_section(left, right, sr, sections)
    assert len(results) == 2
    loud_lra = results[0]["loudness_range_lu"]
    dynamic_lra = results[1]["loudness_range_lu"]
    assert loud_lra is not None and dynamic_lra is not None
    assert dynamic_lra > loud_lra, (
        f"Expected the bursty section to show more loudness range than the constant one "
        f"(got loud={loud_lra}, dynamic={dynamic_lra})"
    )


def test_loudness_range_by_section_accepts_numpy_array_input() -> None:
    """analysis_core.py's LUFS-accuracy re-read (2026-08-01) started passing
    numpy arrays here instead of lists to skip a redundant list<->array
    round trip. `not left`/`not right`'s old truthiness check would raise
    ValueError on a multi-element ndarray ("truth value of an array is
    ambiguous") -- this locks in the fix (a length check instead) and that
    list vs. ndarray input produce identical results."""
    sr = 48000
    rng = np.random.default_rng(9)
    left_list = (0.1 * rng.standard_normal(sr * 20)).tolist()
    right_list = list(left_list)
    sections = [
        {"index": 0, "label": "A", "start_seconds": 0.0, "end_seconds": 10.0},
        {"index": 1, "label": "B", "start_seconds": 10.0, "end_seconds": 20.0},
    ]

    result_list = loudness_range_by_section(left_list, right_list, sr, sections)
    result_array = loudness_range_by_section(
        np.asarray(left_list, dtype=np.float64), np.asarray(right_list, dtype=np.float64), sr, sections,
    )
    assert result_list == result_array

    # The empty-input guard must also not crash on an empty ndarray.
    empty = np.asarray([], dtype=np.float64)
    assert loudness_range_by_section(empty, empty, sr, sections) == []


def test_loudness_range_for_span_short_audio_returns_none() -> None:
    short = _sine(200.0, 0.5)  # well under the ~4s minimum for two 3s short-term windows
    assert loudness_range_for_span(short, short, SR) is None


# ---------------------------------------------------------------------------
# 1c. Transient preservation (pre/post limiting comparison)
# ---------------------------------------------------------------------------


def _click_track(n_clicks: int, sample_rate: int, spacing_s: float = 0.5, click_amp: float = 0.9) -> list[float]:
    """Synthetic percussive click train: sharp attacks with silence between."""
    spacing = int(spacing_s * sample_rate)
    signal = [0.0] * (n_clicks * spacing)
    click_len = int(0.01 * sample_rate)
    for c in range(n_clicks):
        start = c * spacing
        for i in range(click_len):
            if start + i < len(signal):
                # Sharp exponential-decay click = fast attack, clear transient.
                signal[start + i] = click_amp * math.exp(-i / (click_len * 0.15))
    return signal


def _simple_limiter(samples: list[float], ceiling: float = 0.3, window_ms: float = 6.0, sample_rate: int = SR) -> list[float]:
    """A crude but real transient-smearing processor: a moving-average
    lowpass (simulating the reconstruction/lookahead filter response of a
    real limiter/brickwall stage) followed by makeup-gain scaling toward
    ``ceiling``. Physically softening a signal's leading edge by removing
    high-frequency content is exactly what broadens measured attack time
    and reduces peak/sustain contrast — the fingerprint
    :func:`transient_preservation` is designed to detect — and is more
    representative of a real over-limited chain than a pure sample-domain
    gain-reduction curve, which (for very short percussive material) can
    scale a transient down uniformly without changing its *shape* at all.
    """
    if not samples:
        return []
    window = max(1, int(sample_rate * window_ms / 1000.0))
    from collections import deque
    dq: "deque[float]" = deque(maxlen=window)
    smoothed = []
    for value in samples:
        dq.append(value)
        smoothed.append(sum(dq) / len(dq))
    peak = max(abs(v) for v in smoothed) or 1e-9
    makeup = ceiling / peak
    return [v * makeup for v in smoothed]


def test_transient_preservation_detects_smearing_from_limiter() -> None:
    pre = _click_track(6, SR, spacing_s=0.4, click_amp=0.95)
    post = _simple_limiter(pre, ceiling=0.25)

    result = transient_preservation(pre, post, SR)
    assert result["matched_event_count"] >= 2, f"Expected matched transients, got {result}"
    assert result["preservation_score"] is not None
    assert result["preservation_score"] < 0.9, (
        f"Expected the limiter to measurably reduce the preservation score, got {result['preservation_score']}"
    )
    assert result["mean_attack_ratio_loss_db"] >= 0.0


def test_transient_preservation_identical_signal_scores_high() -> None:
    pre = _click_track(6, SR, spacing_s=0.4, click_amp=0.7)
    post = list(pre)  # unprocessed passthrough
    result = transient_preservation(pre, post, SR)
    assert result["preservation_score"] is not None
    assert result["preservation_score"] > 0.95


def test_compare_transient_preservation_wrapper_matches_direct_call() -> None:
    pre = _click_track(4, SR, spacing_s=0.4)
    post = _simple_limiter(pre, ceiling=0.3)
    direct = transient_preservation(pre, post, SR)
    wrapped = compare_transient_preservation(pre, post, SR)
    assert wrapped["matched_event_count"] == direct["matched_event_count"]
    assert wrapped["preservation_score"] == direct["preservation_score"]


# ---------------------------------------------------------------------------
# 1d. Frequency-band masking between stems
# ---------------------------------------------------------------------------


def test_stem_frequency_masking_requires_two_stems() -> None:
    result = stem_frequency_masking([{"name": "solo_stem", "file_bytes": b""}])
    assert result["ok"] is False


def test_stem_frequency_masking_reports_matrix_for_two_stems() -> None:
    import io
    import struct
    import wave

    def _wav_bytes(samples: list[float], sample_rate: int = SR) -> bytes:
        buf = io.BytesIO()
        with wave.open(buf, "wb") as wav:
            wav.setnchannels(1)
            wav.setsampwidth(2)
            wav.setframerate(sample_rate)
            frames = b"".join(struct.pack("<h", int(max(-1.0, min(1.0, s)) * 32767)) for s in samples)
            wav.writeframes(frames)
        return buf.getvalue()

    bass = _sine(80.0, 1.0, amp=0.6)
    lead = _sine(2000.0, 1.0, amp=0.4)
    stems = [
        {"name": "bass", "file_bytes": _wav_bytes(bass)},
        {"name": "lead", "file_bytes": _wav_bytes(lead)},
    ]
    result = stem_frequency_masking(stems)
    assert result["ok"] is True
    assert "masking_matrix" in result
    assert "bass" in result["masking_matrix"]
    assert "lead" in result["masking_matrix"]["bass"]


# ---------------------------------------------------------------------------
# 2. AI critique — env gating and both paths
# ---------------------------------------------------------------------------


def _sample_report() -> dict:
    return {
        "summary": "Solid technical pass.",
        "metrics": {
            "technical_rating": "Clean technical pass",
            "technical_score": 82,
            "integrated_lufs": -12.4,
            "crest_factor_db": 9.5,
            "loudness_range_lu": 6.0,
            "loudness_range_by_section": [
                {"label": "Section 1", "loudness_range_lu": 3.0, "method": "momentary_400ms"},
                {"label": "Section 2", "loudness_range_lu": 7.5, "method": "momentary_400ms"},
            ],
            "stereo_asymmetry": {
                "asymmetric": True,
                "summary": "Persistent right-channel bias: +2.10 dB level difference.",
            },
        },
        "flags": [{"label": "Low headroom", "severity": "medium"}],
    }


def test_critique_disabled_by_default_returns_deterministic() -> None:
    os.environ.pop("MIX_REVIEW_CRITIQUE_ENABLED", None)
    result = mix_review_critique.generate_critique(_sample_report())
    assert result["mode"] == "deterministic"
    assert result["available"] is False
    assert result["text"].strip() != ""
    assert "Overall:" in result["text"]


def test_critique_allow_llm_false_blocks_even_when_env_set(monkeypatch) -> None:
    monkeypatch.setenv("MIX_REVIEW_CRITIQUE_ENABLED", "1")
    result = mix_review_critique.generate_critique(_sample_report(), allow_llm=False)
    assert result["mode"] == "deterministic"
    assert result["text"].strip() != ""


def test_critique_env_gate_combined_with_allow_llm(monkeypatch) -> None:
    """Mirrors KENN's `allow_llm and env_check` bug-fix pattern: both the
    env var AND allow_llm must be true together for the LLM path to even
    be attempted."""
    monkeypatch.delenv("MIX_REVIEW_CRITIQUE_ENABLED", raising=False)
    # allow_llm True but env off -> deterministic
    result = mix_review_critique.generate_critique(_sample_report(), allow_llm=True)
    assert result["mode"] == "deterministic"

    monkeypatch.setenv("MIX_REVIEW_CRITIQUE_ENABLED", "1")
    # allow_llm False but env on -> still deterministic (allow_llm wins as a hard "no")
    result = mix_review_critique.generate_critique(_sample_report(), allow_llm=False)
    assert result["mode"] == "deterministic"


def test_critique_llm_path_with_fake_provider(monkeypatch) -> None:
    """Exercise the LLM-enabled path with a fake provider (no real network
    call) to confirm the generate()/content plumbing and validation work."""
    monkeypatch.setenv("MIX_REVIEW_CRITIQUE_ENABLED", "1")

    class _FakeResult:
        content = (
            "Main read: solid technical pass with balanced low end and controlled dynamics "
            "across both sections of this otherwise clean mix."
        )

    class _FakeProvider:
        def generate(self, messages, timeout=10):
            return _FakeResult()

    monkeypatch.setattr(mix_review_critique, "_default_provider", lambda: _FakeProvider())
    result = mix_review_critique.generate_critique(_sample_report(), allow_llm=True)
    assert result["mode"] == "llm"
    assert result["available"] is True
    assert result["text"].strip() != ""


def test_critique_llm_failure_falls_back_to_deterministic(monkeypatch) -> None:
    monkeypatch.setenv("MIX_REVIEW_CRITIQUE_ENABLED", "1")

    class _FailingProvider:
        def generate(self, messages, timeout=10):
            raise RuntimeError("connection refused")

    monkeypatch.setattr(mix_review_critique, "_default_provider", lambda: _FailingProvider())
    result = mix_review_critique.generate_critique(_sample_report(), allow_llm=True)
    assert result["mode"] == "deterministic"
    assert result["text"].strip() != ""


def test_critique_optionally_uses_live_ollama_if_reachable() -> None:
    """Best-effort real integration check: if Ollama is actually running
    locally, exercise the true end-to-end LLM path. Skips cleanly if not
    reachable so this suite doesn't depend on external state."""
    import httpx
    try:
        resp = httpx.get("http://127.0.0.1:11434/api/tags", timeout=1.0)
        reachable = resp.status_code == 200
    except Exception:
        reachable = False
    if not reachable:
        pytest.skip("Ollama not reachable at localhost:11434; skipping live LLM critique check.")

    old = os.environ.get("MIX_REVIEW_CRITIQUE_ENABLED")
    os.environ["MIX_REVIEW_CRITIQUE_ENABLED"] = "1"
    try:
        result = mix_review_critique.generate_critique(_sample_report(), allow_llm=True, timeout=20)
    finally:
        if old is None:
            os.environ.pop("MIX_REVIEW_CRITIQUE_ENABLED", None)
        else:
            os.environ["MIX_REVIEW_CRITIQUE_ENABLED"] = old
    assert result["text"].strip() != ""
    # Either the LLM produced a valid critique, or it failed validation/connection
    # and fell back — both are acceptable outcomes for this best-effort check.
    assert result["mode"] in {"llm", "deterministic"}


# ---------------------------------------------------------------------------
# 3. Style classifier — synthetic style-profile mixes
# ---------------------------------------------------------------------------


def test_style_classifier_detects_loudness_war_mix() -> None:
    metrics = {
        "integrated_lufs": -7.5,
        "crest_factor_db": 4.5,
        "bands": {"sub": 0.1, "bass": 0.15, "low_mids": 0.15, "mids": 0.3, "presence": 0.15, "sibilance": 0.08, "air": 0.07},
    }
    result = mix_style_classifier.classify_mix_style({"metrics": metrics})
    assert result["loudness_war"]["participant"] is True
    assert result["loudness_war"]["severity"] in {"moderate", "severe"}
    assert result["vintage_or_modern"]["label"] == "modern"


def test_style_classifier_detects_vintage_wide_dynamic_range_mix() -> None:
    metrics = {
        "integrated_lufs": -20.0,
        "crest_factor_db": 16.0,
        "bands": {"sub": 0.1, "bass": 0.2, "low_mids": 0.25, "mids": 0.3, "presence": 0.1, "sibilance": 0.03, "air": 0.02},
    }
    result = mix_style_classifier.classify_mix_style({"metrics": metrics})
    assert result["loudness_war"]["participant"] is False
    assert result["vintage_or_modern"]["label"] == "vintage-leaning"
    assert result["era"]["label"] == "classic / pre-loudness-war"


def test_style_classifier_handles_missing_data_gracefully() -> None:
    result = mix_style_classifier.classify_mix_style({"metrics": {}})
    assert result["loudness_war"]["participant"] is False
    assert result["loudness_war"]["severity"] == "unknown"
    assert result["genre"]["genre_name"] == "Uncategorised"


def test_style_classifier_accepts_bare_metrics_dict() -> None:
    metrics = {"integrated_lufs": -8.0, "crest_factor_db": 5.0, "bands": {}}
    result = mix_style_classifier.classify_mix_style(metrics)
    assert result["loudness_war"]["participant"] is True


# ---------------------------------------------------------------------------
# 4. Stem solo — frequency isolation and comparison
# ---------------------------------------------------------------------------


def test_solo_frequency_range_removes_out_of_band_energy() -> None:
    # Mix of a 100 Hz tone (bass) and an 8000 Hz tone (air); solo the bass
    # range only and confirm the high tone's energy is strongly attenuated.
    low_tone = _sine(100.0, 1.0, amp=0.5)
    high_tone = _sine(8000.0, 1.0, amp=0.5)
    mixed = [a + b for a, b in zip(low_tone, high_tone)]

    soloed = stem_solo.solo_frequency_range(mixed, SR, 20.0, 300.0)

    def _rms(sig: list[float]) -> float:
        return math.sqrt(sum(v * v for v in sig) / len(sig)) if sig else 0.0

    # Estimate the high-frequency content remaining by correlating against
    # a pure high-tone reference; a well-isolated bass band should have
    # near-zero correlation with the high tone.
    ref = high_tone
    n = min(len(soloed), len(ref))
    dot = sum(soloed[i] * ref[i] for i in range(n))
    norm = math.sqrt(sum(v * v for v in soloed[:n])) * math.sqrt(sum(v * v for v in ref[:n])) or 1e-9
    correlation = dot / norm
    assert abs(correlation) < 0.15, f"Expected the 8kHz tone to be filtered out, correlation={correlation}"
    assert _rms(soloed) > 0.05, "Expected the in-band 100Hz tone to survive the filter"


def test_solo_band_by_name_isolates_named_band() -> None:
    tone = _sine(3000.0, 1.0, amp=0.5)  # presence band (2000-6000)
    soloed = stem_solo.solo_band_by_name(tone, SR, "presence")
    rms_before = math.sqrt(sum(v * v for v in tone) / len(tone))
    rms_after = math.sqrt(sum(v * v for v in soloed) / len(soloed))
    assert rms_after > rms_before * 0.5, "In-band tone should survive with most of its energy"

    soloed_wrong_band = stem_solo.solo_band_by_name(tone, SR, "sub")
    rms_wrong = math.sqrt(sum(v * v for v in soloed_wrong_band) / len(soloed_wrong_band))
    assert rms_wrong < rms_after * 0.2, "Out-of-band solo should strongly attenuate the tone"


def test_solo_band_by_name_rejects_unknown_band() -> None:
    with pytest.raises(ValueError):
        stem_solo.solo_band_by_name([0.1, 0.2], SR, "not_a_band")


def test_stem_spectrum_comparison_identifies_low_end_dominant_stem() -> None:
    bass_stem = {"name": "bass", "samples": _sine(60.0, 1.0, amp=0.6), "sample_rate": SR}
    vocal_stem = {"name": "vocal", "samples": _sine(1200.0, 1.0, amp=0.6), "sample_rate": SR}
    result = stem_solo.stem_spectrum_comparison([bass_stem, vocal_stem])

    assert result["dominant_band"]["sub"]["stem"] == "bass"
    assert result["dominant_band"]["mids"]["stem"] == "vocal"
    ranked = result["low_end_summary"]["ranked"]
    assert ranked[0]["name"] == "bass"


def test_stem_spectrum_comparison_flags_low_end_overlap() -> None:
    kick = {"name": "kick", "samples": _sine(70.0, 1.0, amp=0.6), "sample_rate": SR}
    bass = {"name": "bass", "samples": _sine(90.0, 1.0, amp=0.6), "sample_rate": SR}
    result = stem_solo.stem_spectrum_comparison([kick, bass])
    assert result["low_end_summary"]["overlap_warning"] is not None
