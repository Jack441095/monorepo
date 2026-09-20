# Audio_Too JUCE VST3 & Audio Unit (AU) Plugin Suite

This directory contains native JUCE C++ audio plugin projects that wrap the high-fidelity C++ DSP kernels developed for **Audio_Too** into standalone **VST3** (`.vst3`) and **Audio Unit** (`.component`) audio plugins for standard Digital Audio Workstations (Ableton Live 12, Logic Pro, Pro Tools, Reaper).

---

## Plugins Included

### 1. AudioToo Reverb (`AudioToo_Reverb/`)
- **Engine:** End-to-end Schroeder-Moorer Reverb C++ kernel (`reverb_full_kernel.cpp`).
- **Parameters:**
  - **Room Size:** `0.0` to `1.0` (room dimension scaling factor)
  - **Decay Time:** `0.1s` to `10.0s` (reverb tail decay time)
  - **Damping:** `0.0` to `1.0` (high-frequency absorption)
  - **Pre-Delay:** `0ms` to `200ms`
  - **Wet/Dry Blend:** `0%` to `100%`

### 2. AudioToo Limiter (`AudioToo_Limiter/`)
- **Engine:** Look-ahead brickwall limiter C++ kernel (`limiter_kernel.cpp`).
- **Parameters:**
  - **Threshold:** `-30.0 dB` to `0.0 dB` (input drive & threshold)
  - **Ceiling:** `-12.0 dB` to `0.0 dB` (peak ceiling target)
  - **Release:** `1.0 ms` to `500.0 ms` (smoothed release curve)
  - **Look-Ahead:** `0.5 ms` to `10.0 ms` (sliding window look-ahead with sample-accurate DAW latency reporting)

---

## Building the Plugins (CMake & JUCE)

### Requirements
- **CMake** 3.22 or higher (`brew install cmake`)
- **Clang / GCC / MSVC** supporting C++20
- **JUCE Framework** (cloned as a submodule under `JUCE/` or installed system-wide)

### Build Instructions (macOS / Linux)

```bash
# Clone JUCE framework if needed
git clone https://github.com/juce-framework/JUCE.git studio/vst3_plugins/AudioToo_Reverb/JUCE
git clone https://github.com/juce-framework/JUCE.git studio/vst3_plugins/AudioToo_Limiter/JUCE

# 1. Build AudioToo Reverb
cd studio/vst3_plugins/AudioToo_Reverb
cmake -B build -DCMAKE_BUILD_TYPE=Release
cmake --build build --config Release

# 2. Build AudioToo Limiter
cd ../AudioToo_Limiter
cmake -B build -DCMAKE_BUILD_TYPE=Release
cmake --build build --config Release
```

---

## Default Installation Paths

When `COPY_PLUGIN_AFTER_BUILD` is enabled, CMake automatically installs compiled plugins to:

- **macOS VST3:** `~/Library/Audio/Plug-Ins/VST3/`
- **macOS AU (Audio Unit):** `~/Library/Audio/Plug-Ins/Components/`
- **Windows VST3:** `C:\Program Files\Common Files\VST3\`
- **Linux VST3:** `~/.vst3/`

Open **Ableton Live 12**, rescan plug-ins, and look for **Audio Engineering Company** under VST3 / Audio Units.
