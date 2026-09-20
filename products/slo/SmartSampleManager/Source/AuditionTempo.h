#pragma once

#include <cmath>

namespace slo {
// Rate-based audition changes pitch as well as duration (not time stretching).
// Missing/unreliable tempo retains native speed. Bounds match the existing
// >20 BPM eligibility threshold; invalid arithmetic must not reach JUCE.
inline double auditionSourceRate(double sourceRate, double sampleBpm, double hostBpm) noexcept
{
    if (!std::isfinite(sourceRate) || sourceRate <= 0.0) return 0.0;
    if (!std::isfinite(sampleBpm) || !std::isfinite(hostBpm)
        || sampleBpm <= 20.0 || hostBpm <= 20.0) return sourceRate;
    const double rate = sourceRate * (hostBpm / sampleBpm);
    return std::isfinite(rate) && rate > 0.0 ? rate : sourceRate;
}
} // namespace slo
