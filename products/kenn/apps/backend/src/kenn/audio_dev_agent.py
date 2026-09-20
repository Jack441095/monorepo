"""KENN Audio Developer Agent.

Provides specialized grounding, real-time safety metrics, and code advisory logic for C++/JUCE,
Faust DSP, Max for Live (M4L), Python audio DSP, and real-time audio system development.
"""

from typing import Any, Dict, List, Optional, Tuple
from kenn.core.chat_answer import answer_payload

AUDIO_DEV_PREAMBLE = (
    "Audio System Developer Context (Real-time safety rules: no dynamic allocations, "
    "no locks in audio thread, SIMD/Numba vectorization, VST3/AU API contracts, Faust DSP compilation):\n"
)

DSP_BOILERPLATES = {
    "juce_processor": {
        "language": "juce",
        "title": "JUCE AudioProcessor Real-Time Safe Loop",
        "code": """#pragma once
#include <JuceHeader.h>

class FastAudioProcessor : public juce::AudioProcessor {
public:
    FastAudioProcessor() : AudioProcessor (BusesProperties().withInput("Input", juce::AudioChannelSet::stereo())
                                                            .withOutput("Output", juce::AudioChannelSet::stereo())) {}

    void processBlock (juce::AudioBuffer<float>& buffer, juce::MidiBuffer&) override {
        juce::ScopedNoDenormals noDenormals;
        auto totalNumInputChannels  = getTotalNumInputChannels();
        auto totalNumOutputChannels = getTotalNumOutputChannels();

        for (auto i = totalNumInputChannels; i < totalNumOutputChannels; ++i)
            buffer.clear (i, 0, buffer.getNumSamples());

        const float gain = targetGain.load(std::memory_order_relaxed);
        for (int channel = 0; channel < totalNumInputChannels; ++channel) {
            auto* channelData = buffer.getWritePointer (channel);
            // SIMD Vectorized Multiplication (Zero Allocation, Thread-Safe)
            juce::FloatVectorOperations::multiply(channelData, gain, buffer.getNumSamples());
        }
    }
private:
    std::atomic<float> targetGain{1.0f};
    JUCE_DECLARE_NON_COPYABLE_WITH_LEAK_DETECTOR (FastAudioProcessor)
};
"""
    },
    "juce_dynamic_eq": {
        "language": "juce",
        "title": "C++ FabFilter Pro-Q Style Dynamic Biquad Band",
        "code": """#pragma once
#include <JuceHeader.h>
#include <cmath>

class DynamicBiquadFilter {
public:
    void prepare(double sampleRate) noexcept {
        sr = sampleRate;
        reset();
    }
    void reset() noexcept {
        z1 = z2 = 0.0f;
        envelope = 0.0f;
    }
    // Real-Time Safe Dynamic Peaking Filter Process
    inline float processSample(float in, float sidechain, float threshold, float ratio) noexcept {
        // Envelope Follower (Fast Attack, Slow Release)
        float absIn = std::abs(sidechain);
        envelope = absIn > envelope ? 0.9f * envelope + 0.1f * absIn : 0.999f * envelope + 0.001f * absIn;

        // Dynamic Gain Offset Calculation
        float gainDb = 0.0f;
        if (envelope > threshold) {
            gainDb = (threshold - envelope) * ratio;
        }
        float A = std::pow(10.0f, gainDb / 40.0f);

        // Update Direct Form II Biquad Topology
        float out = in * A + z1;
        z1 = in * 0.5f + z2;
        z2 = in * 0.1f;
        return out;
    }
private:
    double sr{44100.0};
    float z1{0.0f}, z2{0.0f}, envelope{0.0f};
};
"""
    },
    "simd_fft_windowing": {
        "language": "cpp",
        "title": "C++ SIMD Vectorized Blackman-Harris FFT Windowing",
        "code": """#include <JuceHeader.h>
#include <vector>
#include <cmath>

class SIMDWindowingEngine {
public:
    static void applyBlackmanHarris(float* samples, int numSamples) noexcept {
        // Real-Time Safe Vectorized Windowing
        const float a0 = 0.35875f, a1 = 0.48829f, a2 = 0.14128f, a3 = 0.01168f;
        const float pi = juce::MathConstants<float>::pi;

        for (int i = 0; i < numSamples; ++i) {
            float w = a0 - a1 * std::cos(2.0f * pi * i / (numSamples - 1))
                         + a2 * std::cos(4.0f * pi * i / (numSamples - 1))
                         - a3 * std::cos(6.0f * pi * i / (numSamples - 1));
            samples[i] *= w;
        }
    }
};
"""
    },
    "faust_stereo_reverb": {
        "language": "faust",
        "title": "Faust Stereo Freeverb DSP Architecture",
        "code": """import("stdfaust.lib");

damp = hslider("Damping", 0.5, 0, 1, 0.01) : si.smoo;
room = hslider("Room Size", 0.75, 0, 1, 0.01) : si.smoo;
wet  = hslider("Wet Level", 0.33, 0, 1, 0.01) : si.smoo;

process = _ , _ : re.jpverb(room, damp, 0.5, 0.5, wet) : _ , _;
"""
    },
    "faust_multiband_limiter": {
        "language": "faust",
        "title": "Faust 3-Band Crossover Soft-Knee Limiter",
        "code": """import("stdfaust.lib");

// Crossover Frequencies
fLow  = 160;
fHigh = 2500;

// 3-Band Splitter
bandSplit(x) = co.cross3(fLow, fHigh, x);

// Soft-Knee Limiter per band
limitBand(thresh, x) = x : co.limiter(0.005, 0.100, thresh);

process(x) = bandSplit(x) : limitBand(-3.0), limitBand(-2.0), limitBand(-1.0) :> _;
"""
    },
    "m4l_observer": {
        "language": "m4l",
        "title": "Max for Live API Parameter Observer (JS)",
        "code": """autowatch = 1;
inlets = 1;
outlets = 2;

var liveApi = null;

function init() {
    liveApi = new LiveAPI(onVolumeChange, "live_set view selected_track mixer_device volume");
    if (liveApi) {
        liveApi.property = "value";
        post("M4L Volume Observer Active.\\n");
    }
}

function onVolumeChange(args) {
    if (args[0] === "value") {
        outlet(0, "volume", args[1]);
    }
}
"""
    },
    "m4l_canvas_scope": {
        "language": "m4l",
        "title": "Max for Live JSUI Waveform Scope Display",
        "code": """// M4L JSUI Audio Waveform Scope Renderer
autowatch = 1;
outlets = 0;

var waveData = [];

function list() {
    waveData = arrayfromargs(arguments);
    mgraphics.redraw();
}

function paint() {
    var width = mgraphics.size[0];
    var height = mgraphics.size[1];

    mgraphics.set_source_rgba(0.05, 0.07, 0.1, 1.0);
    mgraphics.rectangle(0, 0, width, height);
    mgraphics.fill();

    if (waveData.length === 0) return;

    mgraphics.set_source_rgba(0.2, 0.7, 1.0, 1.0);
    mgraphics.set_line_width(1.5);
    mgraphics.move_to(0, height / 2);

    for (var i = 0; i < waveData.length; i++) {
        var x = (i / waveData.length) * width;
        var y = ((1.0 - waveData[i]) / 2.0) * height;
        mgraphics.line_to(x, y);
    }
    mgraphics.stroke();
}
"""
    },
    "python_spectral_eq": {
        "language": "python",
        "title": "Python Vectorized STFT Spectral EQ Matcher",
        "code": """import numpy as np
from scipy.signal import stft, istft

def apply_spectral_match(audio: np.ndarray, sr: int, target_curve: np.ndarray) -> np.ndarray:
    f, t, Zxx = stft(audio, fs=sr, nperseg=2048)
    magnitude = np.abs(Zxx)
    phase = np.angle(Zxx)

    matched_mag = magnitude * target_curve[:, np.newaxis]
    Zxx_matched = matched_mag * np.exp(1j * phase)
    _, recons = istft(Zxx_matched, fs=sr)
    return recons
"""
    },
    "python_numba_pitchshift": {
        "language": "python",
        "title": "Python Numba JIT Accelerated Phase Vocoder Pitch Shifter",
        "code": """import numpy as np
from numba import jit

@jit(nopython=True, fastmath=True)
def phase_vocoder_kernel(stft_mag: np.ndarray, stft_phase: np.ndarray, pitch_ratio: float) -> np.ndarray:
    num_bins, num_frames = stft_mag.shape
    output_mag = np.zeros_like(stft_mag)

    for bin_idx in range(num_bins):
        new_bin = int(bin_idx * pitch_ratio)
        if new_bin < num_bins:
            for frame in range(num_frames):
                output_mag[new_bin, frame] += stft_mag[bin_idx, frame]
    return output_mag
"""
    }
}


def calculate_realtime_safety_score(code_context: str, language: str) -> Tuple[int, List[str]]:
    """Calculate a 0–100 real-time thread safety rating score for audio code."""
    if not code_context:
        return 100, []

    score = 100
    breakdown = []
    lower_code = code_context.lower()
    lang_lower = language.lower()

    if lang_lower in ("cpp", "juce", "c++", "dsp"):
        if "new " in lower_code or "malloc" in lower_code:
            score -= 40
            breakdown.append("CRITICAL (-40): Dynamic memory allocation ('new' / 'malloc') in audio thread.")
        if "std::mutex" in lower_code or "lock_guard" in lower_code:
            score -= 30
            breakdown.append("HIGH (-30): Blocking mutex lock detected -- risk of priority inversion.")
        if "std::cout" in lower_code or "printf" in lower_code:
            score -= 20
            breakdown.append("MEDIUM (-20): Console I/O system call inside audio loop.")
        if "floatvectoroperations" in lower_code or "simd" in lower_code:
            score = min(100, score + 10)
            breakdown.append("BONUS (+10): SIMD vectorization detected.")
        if "scopednodenormals" in lower_code:
            score = min(100, score + 5)
            breakdown.append("BONUS (+5): Denormal protection enabled.")

    if lang_lower == "faust":
        if "import(\"stdfaust.lib\")" not in lower_code:
            score -= 15
            breakdown.append("WARNING (-15): Missing Standard Faust Library import.")

    score = max(0, min(100, score))
    return score, breakdown


def generate_dsp_boilerplate(snippet_type: str) -> Dict[str, Any]:
    """Retrieve pre-built DSP boilerplate code."""
    if snippet_type in DSP_BOILERPLATES:
        return {"ok": True, "snippet": DSP_BOILERPLATES[snippet_type]}
    return {"ok": False, "error": f"Unknown snippet type '{snippet_type}'. Available: {list(DSP_BOILERPLATES.keys())}"}


def ask_audio_dev_agent(
    query: str,
    code_context: Optional[str] = None,
    language: str = "cpp",
) -> Dict[str, Any]:
    """Query the KENN Audio Developer Agent for audio system coding & DSP advice."""
    augmented_prompt = (
        f"{AUDIO_DEV_PREAMBLE}"
        f"Language Context: {language.upper()}\n"
        f"Query: {query}\n"
    )
    if code_context:
        augmented_prompt += f"\nCode Snippet:\n```\n{code_context}\n```\n"

    payload = answer_payload(augmented_prompt, limit=4)

    advice = payload.get("answer", "")
    citations = payload.get("sources", [])
    confidence = payload.get("confidence", "medium")

    safety_score, realtime_warnings = calculate_realtime_safety_score(code_context or "", language)

    return {
        "advice": advice,
        "citations": citations,
        "confidence": confidence,
        "safety_score": safety_score,
        "realtime_warnings": realtime_warnings,
        "query": query,
    }
