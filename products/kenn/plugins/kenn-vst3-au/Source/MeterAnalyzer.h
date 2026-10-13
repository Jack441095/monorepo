#pragma once

#include <JuceHeader.h>
#include "../../../packages/common/AudioTooRealtimeCore.h"

// Plug-in-facing meter shape. ContinuousAnalysis publishes these values from
// complete worker windows; the audio callback only enqueues its own input.
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
