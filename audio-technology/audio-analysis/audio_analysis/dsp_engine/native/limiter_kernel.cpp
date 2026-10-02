// C++ compute kernel for the look-ahead brickwall limiter.
//
// WHY THIS EXISTS
// ---------------
// The streaming limiter (dsp_engine/streaming.py::StreamingLimiter) is the one
// processor whose per-block cost is a pure-Python per-sample loop (monotonic
// deque + release one-pole) — the budget benchmark flagged it as the flattest
// margin and therefore the clearest candidate for a native port. This is that
// port: the identical algorithm in C++, so we can MEASURE what a compiled
// kernel buys (compute only — the look-ahead LATENCY is inherent and unchanged;
// see StreamingLimiter.latency_samples).
//
// It computes the exact same result as the offline dynamics.Limiter's
// gain_down envelope: a forward sliding-window maximum of |x * input_gain|
// over L samples, converted to a target gain (ceiling/peak when peak >
// ceiling, else 1.0), then an instant-attack / smoothed-release one-pole with
// coefficient alpha_rel. All arithmetic is IEEE 754 double in the same
// operation order as the Python/numpy (scipy.ndimage.maximum_filter1d +
// _smooth_attack_release) path, so the result is bit-identical (asserted in
// tests). This step is identical whether or not the caller pre-upsampled the
// input 4x for true-peak detection (true_peak=True just means a bigger L and
// a different alpha_rel, computed at 4x the sample rate) -- Limiter.apply()
// wires this kernel into both true_peak modes, not only true_peak=False.

#include <algorithm>
#include <cmath>
#include <cstddef>
#include <deque>
#include <utility>
#include <vector>

// Stereo-linked streaming limiter: the fix for two defects in how
// AudioToo_Limiter drove the mono kernel above. It called
// limiter_gain_envelope once per channel, so L and R were ducked by
// independent envelopes and the image decoupled under gain reduction;
// and because that batch entry point starts its release one-pole at
// 1.0, every processBlock snapped an in-progress release back to
// unity -- pumping at the block rate, i.e. every 128 samples.
//
// One envelope driven by max(|L|,|R|) per sample fixes the first; the
// release and the look-ahead window have to survive the call boundary
// to fix the second. Stereo linking follows
// master_bus.py::lookahead_limiter_mono_gain, block-to-block state
// follows StreamingLimiter in dsp_engine/streaming.py.
struct LimiterStereoState
{
    // (index, |x_g|) monotonic-decreasing deque feeding the sliding-window
    // maximum, fed max(|L_g|, |R_g|) rather than one channel at a time.
    std::deque<std::pair<long, double>> mono;

    // Real samples whose gain is not final yet, in arrival order. gain[i] needs
    // the window [i, i+L-1], so the newest L-1 samples always sit here and
    // that deficit IS the look-ahead latency (L-1 samples, matching
    // StreamingLimiter.latency_samples).
    struct Pending
    {
        long index;
        double left_g;
        double right_g;
    };
    std::deque<Pending> pending;

    // Carried across calls: the release smoothing is recursive, so restarting
    // it at 1.0 per block is the pumping this struct exists to prevent.
    double release_state = 1.0;
    long n_in = 0;  // real + pad samples fed so far

    // Finalisation reads these for samples staged by an earlier block, so they
    // live here rather than arriving per call. input_gain does NOT: we scale to
    // x_g once at feed time, because re-scaling a sample already sitting in the
    // look-ahead window would apply a threshold move twice to it.
    double ceiling_lin = 1.0;
    double alpha_rel = 0.0;
    int lookahead = 1;
};

namespace {

// Feed one sample's stereo-linked magnitude, then emit every sample whose full
// look-ahead window has arrived. out_* are written from index 0 upward, so the
// caller advances its own write cursor by the return value and the whole
// sequence stays on the input timeline -- that alignment is what
// StreamingLimiter.process_stream returns too.
void limiter_stereo_feed(LimiterStereoState* state,
                         double left_g, double right_g, bool is_pad,
                         double* gain_out, double* out_left, double* out_right,
                         std::size_t* written)
{
    const long j = state->n_in;
    // Pad magnitude is 0 so it extends the window without extending the peak,
    // exactly as the offline max-filter's zero padding does.
    const double magnitude = is_pad ? 0.0
                                    : std::max(std::fabs(left_g), std::fabs(right_g));
    if (!is_pad)
        state->pending.push_back(LimiterStereoState::Pending{j, left_g, right_g});

    while (!state->mono.empty() && state->mono.back().second <= magnitude)
        state->mono.pop_back();
    state->mono.emplace_back(j, magnitude);
    state->n_in = j + 1;

    // Index-driven, not count-driven: sample i is final once i+L-1 has arrived.
    // Stating it as an index rather than "emit one per sample" keeps this right
    // when the look-ahead knob moves mid-stream, where the backlog simply holds
    // a few more or fewer samples.
    while (!state->pending.empty()
           && state->pending.front().index + state->lookahead - 1 < state->n_in)
    {
        const long index = state->pending.front().index;
        // This cannot run dry: the entry for n_in-1 was just pushed above and
        // index <= n_in-1 always, so at least one entry survives the eviction.
        while (state->mono.front().first < index)
            state->mono.pop_front();
        const double window_max = state->mono.front().second;
        const double target = (window_max > state->ceiling_lin)
                                  ? (state->ceiling_lin / window_max)
                                  : 1.0;
        if (target <= state->release_state) {
            state->release_state = target;  // instant attack (offline alpha_att = 0)
        } else {
            state->release_state = state->alpha_rel * state->release_state
                                 + (1.0 - state->alpha_rel) * target;
        }
        // One value drives both channels: that is the whole point, and it is why
        // the image survives gain reduction instead of the two sides drifting.
        const LimiterStereoState::Pending& p = state->pending.front();
        const std::size_t slot = *written;
        if (gain_out != nullptr)
            gain_out[slot] = state->release_state;
        if (out_left != nullptr)
            out_left[slot] = p.left_g * state->release_state;
        if (out_right != nullptr)
            out_right[slot] = p.right_g * state->release_state;
        ++*written;
        state->pending.pop_front();
    }
}

}  // namespace

extern "C" {

// Compute per-sample limiter gain envelope and limited output.
//   x            : input samples (length n)
//   n            : sample count
//   input_gain   : 10^(-threshold_db/20)
//   ceiling_lin  : 10^(ceiling_db/20)
//   alpha_rel    : release one-pole coefficient
//   L            : look-ahead window length in samples (>= 1)
//   gain_out     : [out] per-sample gain (length n) == offline gain_down
//   audio_out    : [out] limited signal (length n) == (x*input_gain) * gain
void limiter_gain_envelope(
    const double* x, std::size_t n,
    double input_gain, double ceiling_lin, double alpha_rel, int L,
    double* gain_out, double* audio_out)
{
    if (n == 0 || L < 1) return;

    // Monotonic-decreasing deque of (index, |x_g|) giving the sliding-window
    // maximum over [i, i+L-1]. We feed real samples 0..n-1 then L-1 zero pads
    // (matching the offline max-filter's end zero padding), finalising gain[i]
    // once its full forward window has arrived.
    // Thread-local array deque for zero-allocation look-ahead maximum tracking
    thread_local std::vector<std::pair<long, double>> mono;
    const long nn = static_cast<long>(n);
    const long total = nn + (L - 1);

    if (mono.capacity() < static_cast<std::size_t>(total + 1)) {
        mono.reserve(total + 1);
    }
    mono.clear();

    double release_state = 1.0;
    std::size_t head = 0;

    for (long j = 0; j < total; ++j) {
        const double a = (j < nn) ? std::fabs(x[j] * input_gain) : 0.0;
        while (mono.size() > head && mono.back().second <= a) {
            mono.pop_back();
        }
        mono.emplace_back(j, a);

        const long i = j - (L - 1);
        if (i >= 0) {
            while (head < mono.size() && mono[head].first < i) {
                head++;
            }
            const double window_max = mono[head].second;
            const double target = (window_max > ceiling_lin)
                                      ? (ceiling_lin / window_max)
                                      : 1.0;
            if (target <= release_state) {
                release_state = target;  // instant attack (alpha_att = 0)
            } else {
                release_state = alpha_rel * release_state
                              + (1.0 - alpha_rel) * target;
            }
            gain_out[i] = release_state;
            audio_out[i] = (x[i] * input_gain) * release_state;
        }
    }
}

// Allocate a streaming stereo state. Call from prepareToPlay, never from
// processBlock -- the deque storage has to grow on a non-audio thread or we
// allocate while the audio thread runs.
LimiterStereoState* limiter_stereo_state_create(void)
{
    return new LimiterStereoState();
}

void limiter_stereo_state_destroy(LimiterStereoState* state)
{
    delete state;
}

// Drop the window, the backlog and the release one-pole. Required after a
// discontinuity (transport stop/start, sample-rate change); the envelope has
// no way to know the silence in between was not part of the signal.
void limiter_stereo_state_reset(LimiterStereoState* state)
{
    if (state == nullptr)
        return;
    state->mono.clear();
    state->pending.clear();
    state->release_state = 1.0;
    state->n_in = 0;
}

// Limit one stereo block. Writes gain_out, out_left and out_right from index 0
// and returns how many samples that was: n-(L-1) on the first call, n once the
// window is primed. The missing L-1 on the first call is the look-ahead delay
// the host compensates via setLatencySamples, not lost audio. Any of the three
// output pointers may be null if the caller does not want that signal.
//
// Returns 0 if state is null or n is 0.
std::size_t limiter_gain_envelope_stereo(
    LimiterStereoState* state,
    const double* left, const double* right, std::size_t n,
    double input_gain, double ceiling_lin, double alpha_rel, int L,
    double* gain_out, double* out_left, double* out_right)
{
    if (state == nullptr || n == 0)
        return 0;

    state->ceiling_lin = ceiling_lin;
    state->alpha_rel = alpha_rel;
    state->lookahead = (L < 1) ? 1 : L;

    std::size_t written = 0;
    for (std::size_t i = 0; i < n; ++i) {
        limiter_stereo_feed(state, left[i] * input_gain, right[i] * input_gain,
                            false, gain_out, out_left, out_right, &written);
    }
    return written;
}

// Drain the look-ahead tail at end-of-stream by feeding L-1 zero pads, which is
// the most that can ever be owed. Call once when the stream ends; a live plugin
// never does, since the next processBlock supplies the future samples instead.
// Returns the number of samples written.
std::size_t limiter_stereo_state_flush(
    LimiterStereoState* state,
    double* gain_out, double* out_left, double* out_right)
{
    if (state == nullptr)
        return 0;

    std::size_t written = 0;
    const int pads = (state->lookahead > 1) ? state->lookahead - 1 : 0;
    for (int i = 0; i < pads; ++i) {
        limiter_stereo_feed(state, 0.0, 0.0, true,
                            gain_out, out_left, out_right, &written);
    }
    return written;
}

}  // extern "C"
