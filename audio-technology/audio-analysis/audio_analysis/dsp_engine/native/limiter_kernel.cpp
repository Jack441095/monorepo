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

#include <cmath>
#include <cstddef>
#include <deque>
#include <utility>
#include <vector>

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

}  // extern "C"
