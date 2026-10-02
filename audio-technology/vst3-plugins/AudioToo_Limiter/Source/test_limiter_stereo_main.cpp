// Regression harness for the stereo-linked streaming limiter kernel.
//
// AudioToo_Limiter used to call the mono batch limiter_gain_envelope once per
// channel per processBlock. Two things were wrong with that and both are audible:
//   - L and R were ducked by independent envelopes, so the stereo image decoupled
//     and the channels pumped apart under gain reduction.
//   - the batch entry point is stateless and starts its release one-pole at 1.0,
//     so every block boundary snapped an in-progress release back to unity, which
//     pumps at the block rate (128 samples on a typical host).
//
// The third test is the load-bearing one: the one-shot reference is the UNCHANGED
// mono batch kernel run over the stereo-linked magnitude max(|L|,|R|), which is
// the same kernel the Python tests in audio-analysis/tests/test_native_limiter.py
// already hold to bit-parity against StreamingLimiter and the offline
// dynamics.Limiter. So agreement here means the new stateful path did not drift
// from the algorithm those tests certified.
//
// Build (no JUCE needed -- the kernel is standalone C++):
//   clang++ -std=c++17 -O2 -Wall -Wextra -o test_limiter_stereo_main \
//       test_limiter_stereo_main.cpp \
//       ../../../audio-analysis/audio_analysis/dsp_engine/native/limiter_kernel.cpp
// Run: exits 0 on pass, 1 on failure, printing the measured numbers either way.

#include <algorithm>
#include <cmath>
#include <cstdarg>
#include <cstddef>
#include <cstdio>
#include <string>
#include <vector>

extern "C" {
struct LimiterStereoState;

LimiterStereoState* limiter_stereo_state_create(void);
void limiter_stereo_state_destroy(LimiterStereoState* state);
void limiter_stereo_state_reset(LimiterStereoState* state);

std::size_t limiter_gain_envelope_stereo(
    LimiterStereoState* state,
    const double* left, const double* right, std::size_t n,
    double input_gain, double ceiling_lin, double alpha_rel, int L,
    double* gain_out, double* out_left, double* out_right);

std::size_t limiter_stereo_state_flush(
    LimiterStereoState* state,
    double* gain_out, double* out_left, double* out_right);

// The unchanged mono batch kernel, used here as the one-shot reference.
void limiter_gain_envelope(
    const double* x, std::size_t n,
    double input_gain, double ceiling_lin, double alpha_rel, int L,
    double* gain_out, double* audio_out);
}

namespace {

constexpr double kSampleRate = 48000.0;
constexpr double kInputGain = 1.0;         // 0 dBFS threshold
constexpr double kCeilingLin = 0.891251;   // -1.0 dBFS
constexpr double kAlphaRel = 0.999583;     // 50 ms release at 48 kHz
constexpr int kLookahead = 64;
constexpr std::size_t kBlockSize = 128;

int failures = 0;

void report(const std::string& name, bool ok, const std::string& detail)
{
    std::printf("  [%s] %s -- %s\n", ok ? "PASS" : "FAIL", name.c_str(), detail.c_str());
    if (!ok)
        ++failures;
}

std::string format(const char* fmt, ...)
{
    char buffer[256];
    va_list args;
    va_start(args, fmt);
    vsnprintf(buffer, sizeof(buffer), fmt, args);
    va_end(args);
    return std::string(buffer);
}

struct StereoBlock
{
    std::vector<double> left;
    std::vector<double> right;
};

struct StereoResult
{
    std::vector<double> gain;
    std::vector<double> left;
    std::vector<double> right;
    std::vector<std::size_t> producedPerBlock;
};

// Correlated stereo with a single transient.
StereoBlock correlatedTransient(std::size_t n)
{
    StereoBlock block;
    block.left.resize(n);
    block.right.resize(n);
    for (std::size_t i = 0; i < n; ++i)
    {
        const double t = static_cast<double>(i) / kSampleRate;
        double v = 0.8 * std::sin(2.0 * M_PI * 220.0 * t)
                 + 0.3 * std::sin(2.0 * M_PI * 3100.0 * t);
        if (i >= 400 && i < 412)
            v += 2.5;  // +8 dB transient, identical in both channels
        block.left[i] = v;
        block.right[i] = v;
    }
    return block;
}

// The case that actually catches independent per-channel envelopes: the transient
// lives in one channel only, and the other is 40 dB down. A per-channel limiter
// sees nothing to do on the quiet channel and leaves it at unity, which is the
// image collapse we fixed.
StereoBlock transientOnLeftOnly(std::size_t n)
{
    StereoBlock block = correlatedTransient(n);
    const double quiet = 0.01;
    for (std::size_t i = 0; i < n; ++i)
        block.right[i] = quiet * block.left[i];
    return block;
}

// The same signal with the roles swapped. Needed because transientOnLeftOnly
// alone cannot catch an envelope driven by |L| alone: there R is a 1% copy of L,
// so max(|L|,|R|) is always |L| and the mutant computes the correct answer by
// accident. Swapping the channels is what makes the link direction observable.
StereoBlock transientOnRightOnly(std::size_t n)
{
    StereoBlock block = correlatedTransient(n);
    for (std::size_t i = 0; i < n; ++i)
    {
        const double hot = block.right[i];
        block.left[i] = 0.01 * hot;
        block.right[i] = hot;
    }
    return block;
}

// Genuinely decorrelated: different partials per side and transients at different
// times, so which channel is the louder one changes throughout. Used for the
// one-shot comparison, because a reference built from max(|L|,|R|) over a
// correlated signal is just |L| and would not notice an envelope that ignored R.
StereoBlock decorrelatedStereo(std::size_t n)
{
    StereoBlock block;
    block.left.resize(n);
    block.right.resize(n);
    for (std::size_t i = 0; i < n; ++i)
    {
        const double t = static_cast<double>(i) / kSampleRate;
        double l = 0.8 * std::sin(2.0 * M_PI * 220.0 * t)
                 + 0.3 * std::sin(2.0 * M_PI * 3100.0 * t);
        double r = 0.7 * std::sin(2.0 * M_PI * 330.0 * t)
                 + 0.2 * std::sin(2.0 * M_PI * 5100.0 * t);
        if (i >= 400 && i < 412)
            l += 2.5;
        if (i >= 900 && i < 914)
            r += 2.2;
        block.left[i] = l;
        block.right[i] = r;
    }
    return block;
}

// Run the stateful kernel over the whole signal in fixed blocks, then drain the
// look-ahead tail. The kernel writes from index 0 of each call, so we advance a
// write cursor rather than indexing by input position -- that cursor is what
// keeps the result on the input timeline, which is what makes it comparable to
// the one-shot reference.
StereoResult runBlocked(const StereoBlock& block, std::size_t blockSize)
{
    const std::size_t n = block.left.size();
    StereoResult result;
    result.gain.assign(n, 0.0);
    result.left.assign(n, 0.0);
    result.right.assign(n, 0.0);

    LimiterStereoState* state = limiter_stereo_state_create();
    std::vector<double> gain(n, 0.0);
    std::vector<double> outL(n, 0.0);
    std::vector<double> outR(n, 0.0);
    std::size_t cursor = 0;

    for (std::size_t start = 0; start < n; start += blockSize)
    {
        const std::size_t count = std::min(blockSize, n - start);
        const std::size_t produced = limiter_gain_envelope_stereo(
            state, block.left.data() + start, block.right.data() + start, count,
            kInputGain, kCeilingLin, kAlphaRel, kLookahead,
            gain.data() + cursor, outL.data() + cursor, outR.data() + cursor);
        result.producedPerBlock.push_back(produced);
        cursor += produced;
    }

    if (cursor != n)
        std::printf("  note: %zu samples owed after the last block, draining\n", n - cursor);

    limiter_stereo_state_flush(state, gain.data() + cursor,
                               outL.data() + cursor, outR.data() + cursor);
    limiter_stereo_state_destroy(state);

    result.gain = gain;
    result.left = outL;
    result.right = outR;
    return result;
}

// The old code path, reproduced so we can prove these tests actually catch the
// defect rather than passing vacuously. Two stateless per-channel calls, exactly
// as PluginProcessor.cpp did before the fix.
void legacyPerChannel(const StereoBlock& block, std::size_t blockSize,
                      std::vector<double>& gainL, std::vector<double>& outL,
                      std::vector<double>& gainR, std::vector<double>& outR)
{
    const std::size_t n = block.left.size();
    gainL.assign(n, 0.0);
    outL.assign(n, 0.0);
    gainR.assign(n, 0.0);
    outR.assign(n, 0.0);

    for (std::size_t start = 0; start < n; start += blockSize)
    {
        const std::size_t count = std::min(blockSize, n - start);
        limiter_gain_envelope(block.left.data() + start, count,
                              kInputGain, kCeilingLin, kAlphaRel, kLookahead,
                              gainL.data() + start, outL.data() + start);
        limiter_gain_envelope(block.right.data() + start, count,
                              kInputGain, kCeilingLin, kAlphaRel, kLookahead,
                              gainR.data() + start, outR.data() + start);
    }
}

StereoResult oneShotReference(const StereoBlock& block)
{
    // Window maximum of max(|L|,|R|) over [i, i+L-1] equals the larger of the two
    // per-channel window maxima, so a single mono pass over the linked magnitude
    // yields the same envelope the streaming path must produce.
    const std::size_t n = block.left.size();
    std::vector<double> linked(n, 0.0);
    for (std::size_t i = 0; i < n; ++i)
    {
        linked[i] = std::max(std::fabs(block.left[i] * kInputGain),
                             std::fabs(block.right[i] * kInputGain));
    }

    StereoResult reference;
    reference.gain.assign(n, 0.0);
    reference.left.assign(n, 0.0);
    reference.right.assign(n, 0.0);
    limiter_gain_envelope(linked.data(), n, 1.0, kCeilingLin, kAlphaRel,
                          kLookahead, reference.gain.data(), reference.left.data());
    for (std::size_t i = 0; i < n; ++i)
    {
        reference.left[i] = (block.left[i] * kInputGain) * reference.gain[i];
        reference.right[i] = (block.right[i] * kInputGain) * reference.gain[i];
    }
    return reference;
}

double maxAbsDiff(const std::vector<double>& a, const std::vector<double>& b)
{
    double worst = 0.0;
    for (std::size_t i = 0; i < a.size(); ++i)
        worst = std::max(worst, std::fabs(a[i] - b[i]));
    return worst;
}

// Gain implied by a channel's output, ignoring zero crossings where recovering
// a ratio is meaningless.
double impliedGainSpread(const StereoBlock& block, const StereoResult& result)
{
    double worst = 0.0;
    for (std::size_t i = 0; i < block.left.size(); ++i)
    {
        const double lIn = block.left[i] * kInputGain;
        const double rIn = block.right[i] * kInputGain;
        if (std::fabs(lIn) < 1e-3 || std::fabs(rIn) < 1e-3)
            continue;
        worst = std::max(worst, std::fabs(result.left[i] / lIn - result.right[i] / rIn));
    }
    return worst;
}

double deepestGain(const std::vector<double>& gain)
{
    double lowest = 1.0;
    for (const double g : gain)
        lowest = std::min(lowest, g);
    return lowest;
}

// Test 1a: correlated stereo with a transient. Both channels must see the same
// gain at every sample. Note this alone does NOT catch the old defect -- with
// L identical to R, two independent envelopes are trivially equal -- so it only
// guards against the new path decorrelating something that should be linked.
void test_correlated_stereo_shares_gain()
{
    std::printf("test_correlated_stereo_shares_one_gain_envelope\n");
    const StereoBlock block = correlatedTransient(2048);
    const StereoResult result = runBlocked(block, kBlockSize);

    const double spread = impliedGainSpread(block, result);
    const double lowest = deepestGain(result.gain);

    report("L and R see identical gain through the transient",
           spread < 1e-12 && lowest < 0.7,
           format("worst L/R implied-gain spread %.3e, lowest gain %.6f (%.2f dB)",
                  spread, lowest, 20.0 * std::log10(lowest)));
}

// Test 1b: transient in one channel only, the other 40 dB down. This is the check
// that catches independent per-channel envelopes: the quiet channel must be
// ducked by the same gain as the hot one. Run with the hot channel on each side,
// because a one-sided mutant can otherwise satisfy the first half of this test.
void test_asymmetric_stereo_is_linked()
{
    std::printf("test_one_sided_transient_ducks_the_quiet_channel\n");

    struct Case
    {
        const char* name;
        StereoBlock block;
        int hotChannel;
    };

    const std::vector<Case> cases{
        {"transient on L", transientOnLeftOnly(2048), 0},
        {"transient on R", transientOnRightOnly(2048), 1},
    };

    for (const Case& testCase : cases)
    {
        const StereoResult result = runBlocked(testCase.block, kBlockSize);
        const double spread = impliedGainSpread(testCase.block, result);
        const double lowest = deepestGain(result.gain);

        std::size_t deepestIndex = 0;
        for (std::size_t i = 0; i < result.gain.size(); ++i)
            if (result.gain[i] < result.gain[deepestIndex])
                deepestIndex = i;
        const double lIn = testCase.block.left[deepestIndex] * kInputGain;
        const double rIn = testCase.block.right[deepestIndex] * kInputGain;

        report(testCase.name,
               spread < 1e-12 && lowest < 0.7,
               format("worst implied-gain spread %.3e, lowest gain %.6f at sample "
                      "%zu (L %.3f -> %.6f, R %.3f -> %.6f)",
                      spread, lowest, deepestIndex, lIn, result.left[deepestIndex],
                      rIn, result.right[deepestIndex]));

        std::vector<double> gainL, outL, gainR, outR;
        legacyPerChannel(testCase.block, kBlockSize, gainL, outL, gainR, outR);
        StereoResult legacy{gainL, outL, outR, {}};
        const double legacySpread = impliedGainSpread(testCase.block, legacy);
        const double legacyQuietGain =
            deepestGain(testCase.hotChannel == 0 ? gainR : gainL);

        report("  legacy per-channel path fails this",
               legacySpread > 0.1 && legacyQuietGain > 0.999,
               format("legacy spread %.3e, legacy lowest quiet-channel gain %.6f "
                      "(quiet channel never ducked)", legacySpread, legacyQuietGain));
    }
}

// Test 2: the envelope must be continuous across block boundaries. Sustained
// hot input in 128-sample blocks, the case a DAW actually runs. The first 16
// blocks are hot; the remaining tail sits below the ceiling, where the target
// becomes 1.0 and the envelope runs a smoothed release. That release is what a
// stateless per-channel call used to reset to unity every 128 samples.
void test_gain_continuous_across_blocks()
{
    std::printf("test_gain_continuous_across_block_boundaries\n");
    const std::size_t n = kBlockSize * 64;
    const std::size_t hotBlocks = 16;

    StereoBlock block;
    block.left.resize(n);
    block.right.resize(n);
    for (std::size_t i = 0; i < n; ++i)
    {
        const double amp = (i < hotBlocks * kBlockSize) ? 1.0 : 0.5;
        block.left[i] = amp;
        block.right[i] = amp;
    }

    const StereoResult result = runBlocked(block, kBlockSize);

    // Continuity means the boundary is not a special event: the step across it
    // must be no bigger than an ordinary step between neighbouring samples. The
    // release is a one-pole, so gain legitimately changes every sample in the
    // tail and an exact-equality test would just be measuring that.
    double worstBoundaryRatio = 0.0;
    std::size_t worstBoundaryBlock = 0;
    for (std::size_t b = 1; b < result.producedPerBlock.size(); ++b)
    {
        const std::size_t start = b * kBlockSize;
        const double step = std::fabs(result.gain[start] - result.gain[start - 1]);

        double neighbourhoodMax = 0.0;
        const std::size_t lo = (start >= kBlockSize) ? start - kBlockSize : 0;
        for (std::size_t i = lo + 1; i < std::min(start + kBlockSize, n); ++i)
            neighbourhoodMax = std::max(neighbourhoodMax, std::fabs(result.gain[i] - result.gain[i - 1]));

        const double ratio = step / std::max(neighbourhoodMax, 1e-300);
        if (ratio > worstBoundaryRatio)
        {
            worstBoundaryRatio = ratio;
            worstBoundaryBlock = b;
        }
    }

    report("no block boundary is a discontinuity in the envelope",
           worstBoundaryRatio <= 1.05,
           format("worst boundary step is %.2fx the largest ordinary neighbouring "
                  "step (at block %zu); first block produced %zu of %zu samples, "
                  "look-ahead latency %d",
                  worstBoundaryRatio, worstBoundaryBlock,
                  result.producedPerBlock[0], kBlockSize, kLookahead - 1));

    // The decisive anti-snap check. 48 block boundaries cross the tail; if the
    // release restarted at 1.0 each time it could never climb as one continuous
    // one-pole to the analytic value 1 - (1-g_hot)*alpha^tail. Matching that to
    // 1e-9 means the state really did survive every boundary.
    const std::size_t tailStart = hotBlocks * kBlockSize;
    const double tailSamples = static_cast<double>(n - 1 - tailStart);
    // alpha^k on the coefficient we actually handed the kernel, not
    // exp(-k/2400): kAlphaRel is a rounded literal, and the two differ by ~2e-5
    // over this many samples, which is exactly the size of error we are testing.
    const double expectedEnd = 1.0 - (1.0 - result.gain[tailStart])
                                       * std::pow(kAlphaRel, tailSamples);
    const double endError = std::fabs(result.gain[n - 1] - expectedEnd);

    report("release runs as one continuous one-pole across all 48 boundaries",
           endError < 1e-9 && result.gain[n - 1] > 0.99,
           format("tail gain %.9f -> %.9f, continuous-release prediction %.9f, "
                  "error %.3e", result.gain[tailStart], result.gain[n - 1],
                  expectedEnd, endError));

    double worstDecrease = 0.0;
    for (std::size_t i = tailStart + 1; i < n; ++i)
        worstDecrease = std::max(worstDecrease, result.gain[i - 1] - result.gain[i]);
    report("release tail never steps backwards",
           worstDecrease <= 1e-15,
           format("worst backward step through the tail %.3e", worstDecrease));

    std::vector<double> gainL, outL, gainR, outR;
    legacyPerChannel(block, kBlockSize, gainL, outL, gainR, outR);
    double legacyWorstStep = 0.0;
    double legacyHottestTailStart = 0.0;
    for (std::size_t b = 1; b < 64; ++b)
        legacyWorstStep = std::max(legacyWorstStep,
                                   std::fabs(gainL[b * kBlockSize] - gainL[b * kBlockSize - 1]));
    for (std::size_t b = hotBlocks; b < 64; ++b)
        legacyHottestTailStart = std::max(legacyHottestTailStart, gainL[b * kBlockSize]);

    report("legacy stateless reset fails this check",
           legacyWorstStep > 1e-3 && legacyHottestTailStart > 0.999,
           format("legacy worst boundary step %.3e, legacy highest tail block "
                  "start %.6f (snapped to unity 48 times)",
                  legacyWorstStep, legacyHottestTailStart));
}

// Test 3: blocked stateful output must equal the one-shot batch kernel on the
// same signal. This is what keeps the new path honest against the algorithm the
// Python bit-parity tests already certified.
void test_blocked_matches_one_shot()
{
    std::printf("test_blocked_matches_one_shot_reference\n");
    // Decorrelated on purpose. Over correlated input the one-shot reference is
    // just |L|, so it cannot tell a correctly linked envelope from one that
    // ignores the right channel outright.
    const StereoBlock block = decorrelatedStereo(4096);

    const StereoResult blocked = runBlocked(block, kBlockSize);
    const StereoResult reference = oneShotReference(block);

    const double gainDiff = maxAbsDiff(blocked.gain, reference.gain);
    const double leftDiff = maxAbsDiff(blocked.left, reference.left);
    const double rightDiff = maxAbsDiff(blocked.right, reference.right);

    report("128-sample blocks reproduce the one-shot envelope and audio",
           gainDiff < 1e-12 && leftDiff < 1e-12 && rightDiff < 1e-12,
           format("max |gain| %.3e, |left| %.3e, |right| %.3e over %zu samples",
                  gainDiff, leftDiff, rightDiff, block.left.size()));

    // 256- and 512-sample blocks must land on the same samples, or the result
    // still depends on whatever buffer size the host picked.
    const StereoResult blocked256 = runBlocked(block, 256);
    const StereoResult blocked512 = runBlocked(block, 512);
    const double sizeDiff = std::max(maxAbsDiff(blocked.gain, blocked256.gain),
                                     maxAbsDiff(blocked.gain, blocked512.gain));
    report("result does not depend on the host block size",
           sizeDiff < 1e-12,
           format("max |gain| vs 256- and 512-sample blocks %.3e", sizeDiff));

    double peak = 0.0;
    for (std::size_t i = 0; i < blocked.left.size(); ++i)
        peak = std::max(peak, std::max(std::fabs(blocked.left[i]),
                                       std::fabs(blocked.right[i])));
    report("output stays under the -1 dBFS ceiling",
           peak <= kCeilingLin + 1e-12,
           format("output peak %.6f, ceiling %.6f", peak, kCeilingLin));
}

}  // namespace

int main()
{
    std::printf("AudioToo_Limiter stereo-linked limiter harness\n");
    std::printf("48 kHz, -1 dBFS ceiling, 50 ms release (alpha_rel %.6f), "
                "%d-sample look-ahead\n\n",
                kAlphaRel, kLookahead);

    test_correlated_stereo_shares_gain();
    std::printf("\n");
    test_asymmetric_stereo_is_linked();
    std::printf("\n");
    test_gain_continuous_across_blocks();
    std::printf("\n");
    test_blocked_matches_one_shot();

    std::printf("\n%s (%d failure%s)\n", failures == 0 ? "PASSED" : "FAILED",
                failures, failures == 1 ? "" : "s");
    return failures == 0 ? 0 : 1;
}