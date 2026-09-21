# KENN Mix Review Qualification & Evaluation Report

**Date**: 2026-09-21

**Engine**: `mix-review/core/local_engine.py` (`ANALYSIS_VERSION = "kenn.mix_review.local_engine.v1"`)

**Status**: Qualified for the documented synthetic benchmark scope


---

## 1. Executive Summary

This report documents the evaluation of KENN's local Mix Review analysis engine across all 9 qualified audio fault families. Testing was conducted on synthetic-but-clearly-labelled 16-bit PCM WAV audio material representing ground-truth studio mix defects.

All documented release thresholds pass.

---

## 2. Release Threshold Compliance Matrix

| Metric | Target / Release Threshold | Measured Value | Qualification Status |
| :--- | :--- | :--- | :--- |
| **Precision** | $\ge 98.0\%$ | **100.0%** | **PASSED** |
| **Recall** | $\ge 98.0\%$ | **100.0%** | **PASSED** |
| **F1 Score** | $\ge 98.0\%$ | **100.0%** | **PASSED** |
| **False-Positive Rate** | $\le 1.0\%$ | **0.0%** | **PASSED** |
| **Steady-State Mean Analysis Latency** | $< 100.0\text{ ms}$ | **4.39 ms** | **PASSED** |
| **Cold Start Analysis Latency** | $< 500.0\text{ ms}$ | **6.10 ms** | **PASSED** |
| **Cold-Inclusive Max Analysis Latency** | $< 500.0\text{ ms}$ | **13.51 ms** | **PASSED** |
| **Corrupted-Input Recovery** | **100.0%** (0 crashes) | **100.0%** | **PASSED** |

---

## 3. Detailed Test Case Results

| Test Case Name | Expected Faults | Detected Faults | Latency | Status |
| :--- | :--- | :--- | :--- | :--- |
| **Clean Reference Track** | None (Clean) | None (Clean) | 3.1 ms | **PASSED** |
| **Hard Digital Clipping Fault** | headroom, clipping, loudness_estimate, true_peak_intersample, calibrated_lufs_bs1770 | headroom, clipping, loudness_estimate, true_peak_intersample, calibrated_lufs_bs1770 | 3.19 ms | **PASSED** |
| **Low Headroom Peak Hot Fault** | headroom, clipping, loudness_estimate, true_peak_intersample, calibrated_lufs_bs1770 | headroom, clipping, loudness_estimate, true_peak_intersample, calibrated_lufs_bs1770 | 3.11 ms | **PASSED** |
| **Silence Truncation Fault** | silence_or_truncation | silence_or_truncation | 13.51 ms | **PASSED** |
| **Channel Imbalance (L/R RMS offset)** | calibrated_lufs_bs1770, phase_polarity_mono_compatibility, channel_imbalance, loudness_estimate | calibrated_lufs_bs1770, phase_polarity_mono_compatibility, channel_imbalance, loudness_estimate | 3.02 ms | **PASSED** |
| **180-deg Phase Polarity Inversion** | calibrated_lufs_bs1770, phase_polarity_mono_compatibility, loudness_estimate | calibrated_lufs_bs1770, phase_polarity_mono_compatibility, loudness_estimate | 3.02 ms | **PASSED** |
| **DC Offset Shift (+0.08 bias)** | calibrated_lufs_bs1770, loudness_estimate, dc_offset | calibrated_lufs_bs1770, loudness_estimate, dc_offset | 3.03 ms | **PASSED** |
| **Hot Loudness Proxy Overflow** | calibrated_lufs_bs1770, loudness_estimate | calibrated_lufs_bs1770, loudness_estimate | 3.1 ms | **PASSED** |

---

## 4. Corrupted & Invalid Input Recovery Matrix

| Input Scenario | Payload Type | Handled Exception | Recovery Status |
| :--- | :--- | :--- | :--- |
| **Truncated Header** | 10-byte truncated WAV header | `Could not decode audio` | **PASSED** |
| **Mismatched Format** | MP3 header with `.wav` extension | `Could not decode audio` | **PASSED** |
| **Zero-Byte File** | 0-byte payload | `Could not decode audio` | **PASSED** |
| **Random Garbage Bytes** | Random non-audio stream | `Could not decode audio` | **PASSED** |

---

## 5. Sign-Off & Verification

* **QA verification**: all documented thresholds passed.
* **Release recommendation**: Qualified for the documented synthetic benchmark scope only.
