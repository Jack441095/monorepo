"""Unit tests for KENN Audio Developer Agent & VS Code Extension backend."""

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent.parent
if str(ROOT / "studio" / "kenn") not in sys.path:
    sys.path.insert(0, str(ROOT / "studio" / "kenn"))

from kenn.audio_dev_agent import ask_audio_dev_agent


def test_ask_audio_dev_agent_cpp_warnings():
    """Verify Audio Dev Agent catches dynamic allocation and mutex locks in C++ code."""
    unsafe_code = """
    void processBlock(juce::AudioBuffer<float>& buffer) {
        float* mem = new float[1024]; // Unsafe allocation in audio thread
        std::mutex mtx;
        std::lock_guard<std::mutex> lock(mtx); // Unsafe lock in audio thread
    }
    """
    res = ask_audio_dev_agent("Is this audio processing code safe?", code_context=unsafe_code, language="cpp")
    assert "realtime_warnings" in res
    warnings = res["realtime_warnings"]
    assert len(warnings) >= 1
    assert any("allocation" in w.lower() or "new" in w.lower() for w in warnings)


def test_ask_audio_dev_agent_general_query():
    """Verify Audio Dev Agent responds to audio DSP programming queries."""
    res = ask_audio_dev_agent("How do I implement a 2-pole Biquad IIR Lowpass filter in C++?", language="cpp")
    assert "advice" in res
    assert res["advice"] is not None


def test_calculate_realtime_safety_score():
    """Verify safety score calculation penalizes allocations/locks and awards SIMD bonuses."""
    from kenn.audio_dev_agent import calculate_realtime_safety_score
    unsafe_code = "float* ptr = new float[512]; std::mutex mtx; std::lock_guard<std::mutex> lock(mtx);"
    score, breakdown = calculate_realtime_safety_score(unsafe_code, "cpp")
    assert score < 60
    assert len(breakdown) >= 2

    safe_simd_code = "juce::ScopedNoDenormals noDenormals; juce::FloatVectorOperations::multiply(data, gain, samples);"
    safe_score, safe_breakdown = calculate_realtime_safety_score(safe_simd_code, "cpp")
    assert safe_score == 100


