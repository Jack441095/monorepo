// Regression harness for the streaming Schroeder-Moorer reverb.
//
// AudioToo_Reverb used to call the stateless batch kernel once per processBlock.
// That kernel treats [left, right) as a complete signal: it zeroes the first
// pre_delay_samples of the buffer and skips every filter whose delay does not
// fit inside n. At the block sizes a DAW actually uses that removes the whole
// wet path -- the shortest comb delay is 558 samples at room_size 0 and 1395 at
// the 0.5 default, i.e. 12.7 ms to 31.6 ms of look-back that no 128-sample block
// contains. What reached the output was (1 - wet_dry) * dry, a flat 3.74 dB cut
// at the default wet_dry 0.35 with no reverb at all.
//
// The fix feeds the same recursion from SchroederReverbState, which carries the
// comb, all-pass, pre-delay and spread rings across calls. The load-bearing test
// is test 3: the one-shot reference is the UNCHANGED batch kernel, the same
// entry point the numpy/ctypes bridge in audio-analysis uses and the one the
// Python parity tests in tests/test_numba_fallback_parity.py already hold to
// the reference implementation. Agreement there means the streaming path did not
// drift from the algorithm the offline side was certified against.
//
// Each behavioural test also runs the old per-block batch path and asserts it
// FAILS, so none of them can pass vacuously.
//
// Build (no JUCE needed -- the kernel is standalone C++):
//   clang++ -std=c++17 -O2 -Wall -Wextra -o test_reverb_streaming_main \
//       test_reverb_streaming_main.cpp \
//       ../../../audio-analysis/audio_analysis/dsp_engine/native/reverb_full_kernel.cpp
// Run: exits 0 on pass, 1 on failure, printing the measured numbers either way.

#include <algorithm>
#include <cmath>
#include <cstdarg>
#include <cstddef>
#include <cstdio>
#include <string>
#include <vector>

#include "../../../audio-analysis/audio_analysis/dsp_engine/native/reverb_full_kernel.h"

namespace {

// The plugin's factory settings from createParameterLayout(), so the numbers in
// the assertions below are the numbers a user hears on loading the plugin.
constexpr double kSampleRate = 48000.0;
constexpr double kRoomSize = 0.5;
constexpr double kDecayTime = 2.0;
constexpr double kDamping = 0.3;
constexpr double kPreDelayMs = 10.0;
constexpr double kWetDry = 0.35;
constexpr std::size_t kBlockSize = 128;

// scale = 0.5 + room_size * 1.5 = 1.25 at the default, giving comb delays
// 1395 / 1485 / 1596 / 1695 and all-pass delays 281 / 426, and spread delays of
// 23 ms and 29 ms at 44.1 kHz-scaled 48 kHz rates: 1104 and 1392 samples.
constexpr double kScale = 0.5 + kRoomSize * 1.5;
constexpr int kMinCombDelay = static_cast<int>(1116.0 * kScale);
constexpr int kPreDelaySamples = static_cast<int>((kPreDelayMs / 1000.0) * kSampleRate);
constexpr int kSpreadL = static_cast<int>(kSampleRate * 0.023);
constexpr int kSpreadR = static_cast<int>(kSampleRate * 0.029);

// An impulse at sample 0 can only reach the output after the pre-delay, one
// comb delay and one spread delay. Naming the expected onset pins the ring
// bookkeeping down to the sample: an off-by-one in any wrap modulus shows up
// here as a shift, not as a rounding wobble.
constexpr int kExpectedOnsetL = kPreDelaySamples + kMinCombDelay + kSpreadL;
constexpr int kExpectedOnsetR = kPreDelaySamples + kMinCombDelay + kSpreadR;

int failures = 0;

void report(const std::string& name, bool ok, const std::string& detail)
{
    std::printf("  [%s] %s -- %s\n", ok ? "PASS" : "FAIL", name.c_str(), detail.c_str());
    if (!ok)
        ++failures;
}

std::string format(const char* fmt, ...)
{
    char buffer[512];
    va_list args;
    va_start(args, fmt);
    vsnprintf(buffer, sizeof(buffer), fmt, args);
    va_end(args);
    return std::string(buffer);
}

struct Signal
{
    std::vector<double> left;
    std::vector<double> right;
};

// Deterministic noise, so a failure is reproducible and does not depend on the
// platform's rand(). xorshift64* is cheap and has no library dependency.
struct Noise
{
    unsigned long long s;

    explicit Noise(unsigned long long seed)
        : s(seed == 0 ? 0x9E3779B97F4A7C15ull : seed)
    {
    }

    double next()
    {
        s ^= s >> 12;
        s ^= s << 25;
        s ^= s >> 27;
        const unsigned long long v = s * 0x2545F4914F6CDD1Dull;
        // Map to [-1, 1) with 53 bits of mantissa.
        return static_cast<double>(v >> 11) / 4503599627370496.0 * 2.0 - 1.0;
    }
};

// Stereo noise, uncorrelated per channel, optionally decorrelated between the
// channels by giving each side its own seed. Correlated input would make the
// mono mix at the head of the kernel trivial to get right.
Signal stereoNoise(std::size_t n, double amplitude, unsigned long long seed)
{
    Signal signal;
    signal.left.resize(n);
    signal.right.resize(n);
    Noise l(seed);
    Noise r(seed ^ 0xD1B54A32D192ED03ull);
    for (std::size_t i = 0; i < n; ++i)
    {
        signal.left[i] = amplitude * l.next();
        signal.right[i] = amplitude * r.next();
    }
    return signal;
}

// A single full-scale impulse on both channels at sample 0.
Signal impulse(std::size_t n)
{
    Signal signal;
    signal.left.assign(n, 0.0);
    signal.right.assign(n, 0.0);
    signal.left[0] = 1.0;
    signal.right[0] = 1.0;
    return signal;
}

// One knob setting held constant for the whole run, which is what the streaming
// path is being compared against.
struct Params
{
    int preDelaySamples = kPreDelaySamples;
    double roomSize = kRoomSize;
    double decayTime = kDecayTime;
    double damping = kDamping;
    double wetDry = kWetDry;
    double sampleRate = kSampleRate;
};

Signal runBlocked(const Signal& in, const Params& params, std::size_t blockSize)
{
    const std::size_t n = in.left.size();
    Signal out;
    out.left.assign(n, 0.0);
    out.right.assign(n, 0.0);

    SchroederReverbState state;
    for (std::size_t start = 0; start < n; start += blockSize)
    {
        const std::size_t count = std::min(blockSize, n - start);
        schroeder_reverb_stream(
            &state,
            in.left.data() + start, in.right.data() + start, count,
            params.preDelaySamples, params.roomSize, params.decayTime,
            params.damping, params.wetDry, params.sampleRate,
            out.left.data() + start, out.right.data() + start);
    }
    return out;
}

// One call over the whole buffer: the offline batch entry point, used as the
// reference the streaming path has to reproduce.
Signal runOneShot(const Signal& in, const Params& params)
{
    const std::size_t n = in.left.size();
    Signal out;
    out.left.assign(n, 0.0);
    out.right.assign(n, 0.0);
    schroeder_reverb(
        in.left.data(), in.right.data(), n,
        params.preDelaySamples, params.roomSize, params.decayTime,
        params.damping, params.wetDry, params.sampleRate,
        out.left.data(), out.right.data());
    return out;
}

// What PluginProcessor.cpp did before the fix: one stateless batch call per
// host block. Reproduced here so each test can prove it fails this path.
Signal legacyPerBlock(const Signal& in, const Params& params, std::size_t blockSize)
{
    const std::size_t n = in.left.size();
    Signal out;
    out.left.assign(n, 0.0);
    out.right.assign(n, 0.0);
    for (std::size_t start = 0; start < n; start += blockSize)
    {
        const std::size_t count = std::min(blockSize, n - start);
        schroeder_reverb(
            in.left.data() + start, in.right.data() + start, count,
            params.preDelaySamples, params.roomSize, params.decayTime,
            params.damping, params.wetDry, params.sampleRate,
            out.left.data() + start, out.right.data() + start);
    }
    return out;
}

// First index whose magnitude clears `threshold`, or n if there is none.
std::size_t firstAudible(const std::vector<double>& v, double threshold)
{
    for (std::size_t i = 0; i < v.size(); ++i)
        if (std::fabs(v[i]) > threshold)
            return i;
    return v.size();
}

double rms(const std::vector<double>& v, std::size_t start, std::size_t count)
{
    double sum = 0.0;
    for (std::size_t i = start; i < start + count && i < v.size(); ++i)
        sum += v[i] * v[i];
    return (count == 0) ? 0.0 : std::sqrt(sum / static_cast<double>(count));
}

double rms(const Signal& s, std::size_t start, std::size_t count)
{
    const double l = rms(s.left, start, count);
    const double r = rms(s.right, start, count);
    return std::sqrt(0.5 * (l * l + r * r));
}

double maxAbsDiff(const Signal& a, const Signal& b)
{
    double worst = 0.0;
    for (std::size_t i = 0; i < a.left.size(); ++i)
    {
        worst = std::max(worst, std::fabs(a.left[i] - b.left[i]));
        worst = std::max(worst, std::fabs(a.right[i] - b.right[i]));
    }
    return worst;
}

double db(double linear)
{
    return 20.0 * std::log10(std::max(linear, 1e-300));
}

// Test 1a: an impulse has to come out of the wet path at the analytically
// expected sample. Reading the wet signal alone means wet_dry = 1.0, which
// makes the kernel's output the wet signal with no dry mixed in -- no new
// kernel API needed to look at it.
void test_impulse_reaches_the_wet_path()
{
    std::printf("test_impulse_reaches_the_wet_path_at_the_expected_sample\n");
    const std::size_t n = 65536;
    const Signal in = impulse(n);

    Params wet;
    wet.wetDry = 1.0;
    const Signal streaming = runBlocked(in, wet, kBlockSize);
    const Signal legacy = legacyPerBlock(in, wet, kBlockSize);

    const std::size_t onsetL = firstAudible(streaming.left, 1e-12);
    const std::size_t onsetR = firstAudible(streaming.right, 1e-12);
    const std::size_t legacyOnsetL = firstAudible(legacy.left, 1e-12);

    report("wet output starts at pre-delay + shortest comb + 23 ms spread",
           onsetL == static_cast<std::size_t>(kExpectedOnsetL)
               && onsetR == static_cast<std::size_t>(kExpectedOnsetR),
           format("expected onset L %d, R %d; measured L %zu, R %zu "
                  "(pre-delay %d + shortest comb %d + spread %d/%d)",
                  kExpectedOnsetL, kExpectedOnsetR, onsetL, onsetR,
                  kPreDelaySamples, kMinCombDelay, kSpreadL, kSpreadR));

    // The onset is far past the first block, which is the whole point: no
    // single 128-sample block contains the comb's look-back.
    report("onset lands well beyond the first processBlock",
           onsetL > 16 * kBlockSize,
           format("onset at sample %zu = block %zu at %zu samples per block",
                  onsetL, onsetL / kBlockSize, kBlockSize));

    // Silent until then, with no onset jitter: an off-by-one in any ring wrap
    // would put energy one sample early or late.
    double worstBeforeOnset = 0.0;
    for (std::size_t i = 0; i < onsetL; ++i)
        worstBeforeOnset = std::max(worstBeforeOnset, std::fabs(streaming.left[i]));
    report("nothing leaks out before the onset sample",
           worstBeforeOnset == 0.0,
           format("worst |wet| below the onset %.3e", worstBeforeOnset));

    report("legacy per-block batch path never produces wet output",
           legacyOnsetL == n,
           format("legacy first audible sample %zu of %zu (wet path silent for "
                  "the whole run)", legacyOnsetL, n));
}

// Test 1b: decaying wet energy. Noise for the first half, silence after, so
// everything past the midpoint is reverb tail fed by state the kernel carried
// over rather than signal arriving on the wire.
void test_wet_energy_rings_and_decays()
{
    std::printf("test_wet_energy_rings_down_after_the_dry_signal_stops\n");
    const std::size_t n = 72000;  // 1.5 s at 48 kHz
    const std::size_t dryEnd = 24000;
    Signal in = stereoNoise(n, 0.5, 42ull);
    for (std::size_t i = dryEnd; i < n; ++i)
    {
        in.left[i] = 0.0;
        in.right[i] = 0.0;
    }

    Params wet;
    wet.wetDry = 1.0;
    const Signal streaming = runBlocked(in, wet, kBlockSize);
    const Signal legacy = legacyPerBlock(in, wet, kBlockSize);

    // Windows across the whole second, so the build-up, the tail and the decay
    // are all visible in one printout.
    const std::size_t window = 2400;
    std::vector<double> streamingRms;
    std::vector<double> legacyRms;
    for (std::size_t start = 0; start + window <= n; start += window)
    {
        streamingRms.push_back(rms(streaming, start, window));
        legacyRms.push_back(rms(legacy, start, window));
    }

    double peak = 0.0;
    std::size_t peakWindow = 0;
    for (std::size_t w = 0; w < streamingRms.size(); ++w)
        if (streamingRms[w] > peak)
        {
            peak = streamingRms[w];
            peakWindow = w;
        }

    report("wet output is audible in windows past the first block",
           peak > 0.0 && peakWindow > 0,
           format("peak window RMS %.6f (%.2f dB) at window %zu of %zu",
                  peak, db(peak), peakWindow, streamingRms.size()));

    // The dry signal stopped at sample 24000, so every window from index 10 on
    // is tail only.
    const std::size_t tailFirstWindow = dryEnd / window;
    double tailPeak = 0.0;
    for (std::size_t w = tailFirstWindow; w < streamingRms.size(); ++w)
        tailPeak = std::max(tailPeak, streamingRms[w]);
    report("wet tail is still running after the dry signal stops",
           tailPeak > 1e-4,
           format("tail windows from %zu: peak RMS %.6f (%.2f dB), last window "
                  "RMS %.6f (%.2f dB)", tailFirstWindow, tailPeak, db(tailPeak),
                  streamingRms.back(), db(streamingRms.back())));

    // The tail has to fall at the rate RT60 2.0 s names, not merely fall. One
    // comb pass of d samples costs 60*d/(T*fs) dB, so the wet level should drop
    // 60/(T*fs) dB per sample whatever the excitation is. Fitting that slope is
    // a real assertion about the feedback coefficient; a threshold like "under
    // 2% of peak" only says something for one signal length, and at RT60 2 s it
    // needs several seconds of tail to become meaningful at all.
    //
    // Fit over the last 60% of the tail: the first tail windows are still
    // filling, because the comb taps land up to 1695 samples after the dry
    // signal stops.
    const double analyticDbPerSample = 60.0 / (kDecayTime * kSampleRate);
    const std::size_t fitFirst = tailFirstWindow + (streamingRms.size() - tailFirstWindow) * 2 / 5;
    std::size_t fitCount = 0;
    double sumX = 0.0, sumY = 0.0, sumXX = 0.0, sumXY = 0.0;
    for (std::size_t w = fitFirst; w < streamingRms.size(); ++w)
    {
        if (streamingRms[w] <= 0.0)
            continue;
        const double x = static_cast<double>(w);
        const double y = db(streamingRms[w]);
        sumX += x;
        sumY += y;
        sumXX += x * x;
        sumXY += x * y;
        ++fitCount;
    }
    // Ordinary least squares of window RMS in dB against window index, so the
    // slope comes out in dB per window.
    const double meanX = sumX / static_cast<double>(fitCount);
    const double meanY = sumY / static_cast<double>(fitCount);
    const double slopeDbPerWindow = (sumXY - static_cast<double>(fitCount) * meanX * meanY)
                                  / (sumXX - static_cast<double>(fitCount) * meanX * meanX);
    const std::size_t spanWindows = streamingRms.size() - 1 - fitFirst;
    const std::size_t spanSamples = spanWindows * window;
    const double measuredDrop = -slopeDbPerWindow * static_cast<double>(spanWindows);
    const double expectedDrop = analyticDbPerSample * static_cast<double>(spanSamples);

    report("tail decays at the rate RT60 2.0 s specifies",
           std::fabs(measuredDrop - expectedDrop) < 2.0,
           format("measured %.2f dB over the last %zu samples (%zu windows), "
                  "RT60 %.1f s predicts %.2f dB, error %.3f dB; fitted slope "
                  "%.4f dB per window against %.4f expected",
                  measuredDrop, spanSamples, spanWindows, kDecayTime,
                  expectedDrop, measuredDrop - expectedDrop, slopeDbPerWindow,
                  -analyticDbPerSample * static_cast<double>(window)));

    // And the trend has to be down, not level: every window in the final third
    // sits below the first tail window.
    const std::size_t lastThird = tailFirstWindow + (streamingRms.size() - tailFirstWindow) * 2 / 3;
    double lastThirdMax = 0.0;
    for (std::size_t w = lastThird; w < streamingRms.size(); ++w)
        lastThirdMax = std::max(lastThirdMax, streamingRms[w]);
    report("final third of the tail is well below the first tail window",
           lastThirdMax < 0.5 * streamingRms[tailFirstWindow],
           format("first tail window RMS %.6f (%.2f dB), highest window in the "
                  "final third %.6f (%.2f dB)", streamingRms[tailFirstWindow],
                  db(streamingRms[tailFirstWindow]), lastThirdMax,
                  db(lastThirdMax)));

    double legacyTailPeak = 0.0;
    for (std::size_t w = tailFirstWindow; w < legacyRms.size(); ++w)
        legacyTailPeak = std::max(legacyTailPeak, legacyRms[w]);
    report("legacy per-block batch path produces no tail at all",
           legacyTailPeak == 0.0,
           format("legacy tail peak RMS %.3e (dry silence in, dry silence out)",
                  legacyTailPeak));
}

// Test 2: blocked streaming output must equal the one-shot batch kernel on the
// same signal. The buffer is comfortably longer than the longest delay in the
// network (1695 samples) and the spread (1392), so the batch kernel skips
// nothing and takes its causal-spread branch -- the only branch where the two
// are meant to agree.
void test_blocked_matches_one_shot()
{
    std::printf("test_blocked_streaming_matches_one_shot_batch\n");
    const std::size_t n = 16384;
    const Signal in = stereoNoise(n, 0.5, 7ull);

    const Signal reference = runOneShot(in, Params{});
    const Signal blocked = runBlocked(in, Params{}, kBlockSize);

    const double diff = maxAbsDiff(blocked, reference);
    report("128-sample blocks reproduce the one-shot batch kernel",
           diff < 1e-9,
           format("max |blocked - one-shot| %.3e over %zu samples (%.2f dBFS)",
                  diff, n, db(diff)));

    // Every block size a host might pick, including one-sample blocks, which is
    // the tightest possible check on the wrap arithmetic.
    const std::size_t sizes[] = {1, 2, 7, 64, 128, 256, 512, 4096};
    double worst = 0.0;
    std::size_t worstSize = 0;
    for (const std::size_t blockSize : sizes)
    {
        const double d = maxAbsDiff(runBlocked(in, Params{}, blockSize), reference);
        if (d > worst)
        {
            worst = d;
            worstSize = blockSize;
        }
    }
    report("result does not depend on the host block size",
           worst < 1e-9,
           format("worst deviation %.3e at %zu-sample blocks, across 1 / 2 / 7 / "
                  "64 / 128 / 256 / 512 / 4096", worst, worstSize));

    // The reference must be doing real work, otherwise "agrees" means nothing.
    double referencePeak = 0.0;
    for (std::size_t i = 0; i < reference.left.size(); ++i)
        referencePeak = std::max(referencePeak, std::fabs(reference.left[i]));
    const Signal legacy = legacyPerBlock(in, Params{}, kBlockSize);
    const double legacyDiff = maxAbsDiff(legacy, reference);
    report("legacy per-block batch path diverges from the one-shot kernel",
           legacyDiff > 1e-3,
           format("legacy vs one-shot %.3e (%.2f dBFS); one-shot peak %.6f",
                  legacyDiff, db(legacyDiff), referencePeak));
}

// A flush in the middle of a stream is audible as a hole in the tail, so
// schroeder_reverb_state_reset has to actually clear the rings. A reset that
// dropped the reset would silently keep the previous take's reverb alive.
void test_state_reset_flushes_the_tail()
{
    std::printf("test_state_reset_flushes_the_tail\n");
    const std::size_t n = 24000;
    const Signal in = stereoNoise(n, 0.5, 99ull);

    Params wet;
    wet.wetDry = 1.0;

    // Drive the state hard, reset it, then run silence: a flushed state must
    // produce nothing at all.
    SchroederReverbState state;
    std::vector<double> driveL(n, 0.0);
    std::vector<double> driveR(n, 0.0);
    schroeder_reverb_stream(&state, in.left.data(), in.right.data(), n,
                            wet.preDelaySamples, wet.roomSize, wet.decayTime,
                            wet.damping, wet.wetDry, wet.sampleRate,
                            driveL.data(), driveR.data());
    schroeder_reverb_state_reset(&state);

    double drivenPeak = 0.0;
    for (std::size_t i = 0; i < n; ++i)
    {
        drivenPeak = std::max(drivenPeak, std::fabs(driveL[i]));
        drivenPeak = std::max(drivenPeak, std::fabs(driveR[i]));
    }

    std::vector<double> afterL(n, 0.0);
    std::vector<double> afterR(n, 0.0);
    const std::vector<double> silenceL(n, 0.0);
    const std::vector<double> silenceR(n, 0.0);
    schroeder_reverb_stream(&state, silenceL.data(), silenceR.data(), n,
                            wet.preDelaySamples, wet.roomSize, wet.decayTime,
                            wet.damping, wet.wetDry, wet.sampleRate,
                            afterL.data(), afterR.data());

    double peakAfterReset = 0.0;
    for (std::size_t i = 0; i < n; ++i)
    {
        peakAfterReset = std::max(peakAfterReset, std::fabs(afterL[i]));
        peakAfterReset = std::max(peakAfterReset, std::fabs(afterR[i]));
    }
    report("reset state emits silence on the next block",
           peakAfterReset == 0.0 && drivenPeak > 1e-3,
           format("wet peak before the reset %.6f, after it on silence %.3e",
                  drivenPeak, peakAfterReset));
}

// Test 3: the reason the bug was audible. At the default wet_dry 0.35 the old
// path emitted (1 - 0.35) * dry = 0.65 * dry and nothing else, so the plugin
// subtracted a flat 3.74 dB from everything and added no reverb.
void test_default_mix_is_no_longer_a_flat_dry_cut()
{
    std::printf("test_default_wet_dry_is_not_a_flat_dry_only_cut\n");
    const std::size_t n = 48000;
    const std::size_t dryEnd = 24000;
    Signal in = stereoNoise(n, 0.5, 2026ull);
    for (std::size_t i = dryEnd; i < n; ++i)
    {
        in.left[i] = 0.0;
        in.right[i] = 0.0;
    }

    const Params params;  // wet_dry 0.35, the factory default
    const Signal streaming = runBlocked(in, params, kBlockSize);
    const Signal legacy = legacyPerBlock(in, params, kBlockSize);

    const double dryRms = rms(in, 0, dryEnd);
    const double streamingRms = rms(streaming, 0, dryEnd);
    const double legacyRms = rms(legacy, 0, dryEnd);

    // Exactly 0.65 before the fix: the output was a scaled copy of the input.
    report("legacy path was a flat 0.65 * dry cut with no reverb",
           std::fabs(legacyRms - 0.65 * dryRms) < 1e-12 && db(legacyRms) - db(dryRms) < -3.73,
           format("legacy RMS %.6f vs dry %.6f = %.6f * dry (%.2f dB), i.e. a "
                  "flat %.2f dB cut", legacyRms, dryRms,
                  legacyRms / dryRms, db(legacyRms) - db(dryRms),
                  db(dryRms) - db(legacyRms)));

    // Now the wet signal contributes, so the wet path must carry real energy
    // past the point the dry signal goes silent.
    const double tailRms = rms(streaming, dryEnd, n - dryEnd);
    const double legacyTailRms = rms(legacy, dryEnd, n - dryEnd);
    report("tail past the dry signal is no longer silent",
           tailRms > 1e-4 && legacyTailRms == 0.0,
           format("streaming tail RMS %.6f (%.2f dB) over samples %zu-%zu; "
                  "legacy %.3e", tailRms, db(tailRms), dryEnd, n, legacyTailRms));

    report("wet path now adds energy over the dry signal itself",
           streamingRms > legacyRms,
           format("RMS over the dry region %.6f (%.2f dB) vs legacy %.6f "
                  "(%.2f dB) and dry %.6f (%.2f dB)", streamingRms,
                  db(streamingRms), legacyRms, db(legacyRms), dryRms,
                  db(dryRms)));

    // And the wet path must not simply be a scaled copy of the dry any more.
    // Measuring the dry-signal gain in a window that is entirely inside the dry
    // but also inside the reverb response shows the mix is not a constant.
    double minRatio = 1e300;
    double maxRatio = 0.0;
    for (std::size_t i = kExpectedOnsetL; i < 12000; ++i)
    {
        const double dry = 0.5 * (std::fabs(in.left[i]) + std::fabs(in.right[i]));
        if (dry < 0.05)
            continue;  // a ratio against a near-zero dry sample is meaningless
        const double got = rms(streaming, i, 1) / dry;
        minRatio = std::min(minRatio, got);
        maxRatio = std::max(maxRatio, got);
    }
    report("output is not a constant multiple of the dry signal",
           maxRatio - minRatio > 0.05,
           format("output/dry ratio ranges %.3f to %.3f over the first 12000 "
                  "samples (a flat cut would be 0.650 everywhere)", minRatio,
                  maxRatio));

    double streamPeak = 0.0;
    for (std::size_t i = 0; i < streaming.left.size(); ++i)
    {
        streamPeak = std::max(streamPeak, std::fabs(streaming.left[i]));
        streamPeak = std::max(streamPeak, std::fabs(streaming.right[i]));
    }
    report("no runaway: output stays bounded under unit input noise",
           streamPeak < 4.0,
           format("peak %.4f (%.2f dBFS) from 0.5-amplitude noise", streamPeak,
                  db(streamPeak)));
}

// Test 4: a room_size sweep must not flush the delay lines. The rings are
// deliberately kept at their high-water mark and wrap at the live delay, so
// moving the knob changes which sample each comb taps and nothing else. A ring
// sized to the live delay would be re-zeroed on every block of a sweep and gate
// the wet path at the automation rate.
void test_room_size_sweep_does_not_flush_the_tail()
{
    std::printf("test_room_size_sweep_keeps_the_tail_running\n");
    const std::size_t n = 48000;
    const std::size_t dryEnd = 24000;
    Signal in = stereoNoise(n, 0.5, 512ull);

    // Noise for the first half, then silence, so the knob move lands in the
    // tail where it actually has something to destroy. Moving room_size while
    // the dry signal is still running hides the defect: the comb bank refills
    // from live input within one comb period and the 23/29 ms spread rings
    // carry pre-move history over the flush. A flush during the tail kills the
    // reverb outright, because there is no live input left to refill it from.
    for (std::size_t i = dryEnd; i < n; ++i)
    {
        in.left[i] = 0.0;
        in.right[i] = 0.0;
    }

    Params params;
    params.wetDry = 1.0;

    // room_size 1.0 gives the longest delays in the parameter range, so the
    // rings have to grow to fit; 0.2 then shrinks the live delay without
    // shrinking the rings.
    SchroederReverbState state;
    std::vector<double> outL(n, 0.0);
    std::vector<double> outR(n, 0.0);
    const std::size_t moveAt = 36000;  // 0.5 s into the tail

    for (std::size_t start = 0; start < n; start += kBlockSize)
    {
        const std::size_t count = std::min(kBlockSize, n - start);
        const double room = (start < moveAt) ? 1.0 : 0.2;
        schroeder_reverb_stream(
            &state, in.left.data() + start, in.right.data() + start, count,
            params.preDelaySamples, room, params.decayTime,
            params.damping, params.wetDry, params.sampleRate,
            outL.data() + start, outR.data() + start);
    }

    Signal streamed;
    streamed.left = outL;
    streamed.right = outR;

    // Probe across the move, with the window longer than the 23 ms spread delay
    // (1104 samples) so a flush cannot hide behind the spread rings. The tail
    // is already 3.75 dB down where the move lands and RT60 2.0 s predicts a
    // further 1.0 dB per 1600 samples, so the honest answer is close to the
    // before level, not above it.
    const std::size_t probe = 2048;
    const double before = rms(streamed, moveAt - probe, probe);
    const double after = rms(streamed, moveAt, probe);
    const double later = rms(streamed, moveAt + probe, probe);
    report("moving room_size during the tail leaves the reverb running",
           before > 1e-3 && after > 0.7 * before && later > 0.5 * before,
           format("wet RMS over %zu samples before the move %.6f, the %zu "
                  "starting at it %.6f (%.0f%%), the %zu after that %.6f "
                  "(%.0f%%); a flushed ring reads ~0 from here on",
                  probe, before, probe, after,
                  100.0 * after / std::max(before, 1e-300), probe, later,
                  100.0 * later / std::max(before, 1e-300)));

    // And the rings must not have been reallocated per block, which is what a
    // live-sized ring would do 375 times over.
    const std::size_t xRing = state.combs[3].x_history.size();
    report("rings hold the high-water mark, not the live delay",
           xRing >= 2712,
           format("comb 3 ring holds %zu slots; the live delay after the move "
                  "is %d and the high-water mark is 2712", xRing, 1085));
}

}  // namespace

int main()
{
    std::printf("AudioToo_Reverb streaming reverb harness\n");
    std::printf("48 kHz, room_size %.2f (comb delays %d/%d/%d/%d), RT60 %.1f s, "
                "damping %.2f, pre-delay %.0f ms (%d samples), wet_dry %.2f, "
                "%zu-sample blocks\n\n",
                kRoomSize, static_cast<int>(1116.0 * kScale),
                static_cast<int>(1188.0 * kScale), static_cast<int>(1277.0 * kScale),
                static_cast<int>(1356.0 * kScale), kDecayTime, kDamping, kPreDelayMs,
                kPreDelaySamples, kWetDry, kBlockSize);

    test_impulse_reaches_the_wet_path();
    std::printf("\n");
    test_wet_energy_rings_and_decays();
    std::printf("\n");
    test_blocked_matches_one_shot();
    std::printf("\n");
    test_state_reset_flushes_the_tail();
    std::printf("\n");
    test_default_mix_is_no_longer_a_flat_dry_cut();
    std::printf("\n");
    test_room_size_sweep_does_not_flush_the_tail();

    std::printf("\n%s (%d failure%s)\n", failures == 0 ? "PASSED" : "FAILED",
                failures, failures == 1 ? "" : "s");
    return failures == 0 ? 0 : 1;
}