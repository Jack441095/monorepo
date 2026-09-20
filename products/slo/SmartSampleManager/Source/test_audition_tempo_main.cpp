#include "AuditionTempo.h"
#include <cmath>
#include <iostream>
#include <limits>

int main()
{
    int failures = 0;
    const auto expectRate = [&](double source, double sample, double host,
                                double expected, const char* label) {
        const double actual = slo::auditionSourceRate(source, sample, host);
        if (!std::isfinite(actual) || std::abs(actual - expected) > 1.0e-8) {
            std::cerr << "FAIL: " << label << " expected=" << expected
                      << " actual=" << actual << '\n';
            ++failures;
        }
    };
    expectRate(48000, 120, 150, 60000, "faster host speeds up sample");
    expectRate(48000, 120, 90, 36000, "slower host slows sample");
    expectRate(44100, 128, 128, 44100, "equal tempo preserves rate");
    // A four-beat 120 BPM loop is two seconds long; at 150 BPM it lasts 1.6s.
    const double duration = 96000.0 / slo::auditionSourceRate(48000, 120, 150);
    if (std::abs(duration - 1.6) > 1.0e-10) {
        std::cerr << "FAIL: four-beat loop duration is " << duration << '\n';
        ++failures;
    }
    const double nan = std::numeric_limits<double>::quiet_NaN();
    const double inf = std::numeric_limits<double>::infinity();
    for (double invalid : {0.0, -120.0, 20.0, nan, inf, -inf}) {
        expectRate(48000, invalid, 120, 48000, "unknown sample tempo preserves native rate");
        expectRate(48000, 120, invalid, 48000, "unknown host tempo preserves native rate");
    }
    for (double invalid : {0.0, -48000.0, nan, inf, -inf})
        expectRate(invalid, 120, 150, 0, "invalid source rate rejected");
    expectRate(48000, 120, std::numeric_limits<double>::max(), 48000,
               "overflow falls back to native rate");
    if (!failures) std::cout << "Audition tempo tests passed\n";
    return failures ? 1 : 0;
}
