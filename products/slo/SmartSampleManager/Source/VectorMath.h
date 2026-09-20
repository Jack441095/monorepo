#pragma once

// Small vectorized math helpers. Deliberately kept free of any JUCE include:
// on this SDK, <Accelerate/Accelerate.h> transitively pulls in
// CoreServices/CarbonCore, whose legacy global `Point`/`Component` C typedefs
// become ambiguous with juce::Point/juce::Component as soon as
// `using namespace juce;` is in scope (which JuceHeader.h does). Confining
// Accelerate.h to VectorMath.cpp, which never includes JUCE, avoids that clash
// entirely rather than fighting it with include-order tricks.
namespace VectorMath {
    // out[i] = a[i] * b[i] for i in [0, n)
    void multiply(const float* a, const float* b, float* out, int n);

    // returns sum(a[i] * b[i]) for i in [0, n)
    float dotProduct(const float* a, const float* b, int n);
}
