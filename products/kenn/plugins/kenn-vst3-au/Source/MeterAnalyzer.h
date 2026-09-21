#pragma once

#include <JuceHeader.h>
#include "../../../packages/common/AudioTooRealtimeCore.h"

// This analyser is deliberately allocation-free in processBlock.  Values are
// published atomically for the editor and handoff exporter; it never sends
// network traffic from the audio thread.
struct KENNMeterSnapshot
{
    float peakDb = -100.0f;
    float rmsDb = -100.0f;
    float correlation = 1.0f;
    float stereoWidth = 0.0f;
    float crestDb = 0.0f;
    float transientRatio = 0.0f;
    int clippedSamples = 0;
    double sampleRate = 0.0;
    juce::int64 analysedSamples = 0;
};

// The plugin's single realtime owner is AudioTooRealtimeCore in the shared
// package. This snapshot remains as the plugin-facing evidence shape; the old
// duplicate KENNMeterAnalyzer implementation was removed so the callback has
// one authoritative DSP path.
