// C++ end-to-end Schroeder-Moorer Reverb compute kernel.
//
// Evaluates pre-delay, 4 parallel LBCF comb filters, 2 series allpass filters,
// stereo decorrelation, and wet/dry blend in a single C++ execution pass.

#include <algorithm>
#include <cstddef>
#include <vector>
#include <cmath>
#include <utility>

#include "reverb_full_kernel.h"

extern "C" {

void schroeder_reverb(
    const double* left, const double* right, std::size_t n,
    int pre_delay_samples, double room_size, double decay_time, double damping, double wet_dry, double sample_rate,
    double* out_l, double* out_r)
{
    if (n == 0 || !left || !out_l || !out_r) return;

    const double fs = (sample_rate > 0.0) ? sample_rate : 44100.0;
    const double scale = 0.5 + room_size * 1.5;

    const int comb_delays[4] = {
        static_cast<int>(1116.0 * scale),
        static_cast<int>(1188.0 * scale),
        static_cast<int>(1277.0 * scale),
        static_cast<int>(1356.0 * scale)
    };
    const int ap_delays[2] = {
        static_cast<int>(225.0 * scale),
        static_cast<int>(341.0 * scale)
    };

    const double decay_t = (decay_time < 0.1) ? 0.1 : decay_time;
    double comb_g[4];
    for (int k = 0; k < 4; ++k) {
        comb_g[k] = std::pow(10.0, -3.0 * comb_delays[k] / (decay_t * fs));
    }

    const double* right_src = right ? right : left;

    // Thread-local scratch buffers to guarantee zero heap allocation churn on repeated passes
    thread_local std::vector<double> mono_input;
    thread_local std::vector<double> combs_out;
    thread_local std::vector<double> comb_y;
    thread_local std::vector<double> ap_out;
    thread_local std::vector<double> next_ap;

    if (mono_input.capacity() < n) mono_input.reserve(n);
    mono_input.resize(n);
    if (combs_out.capacity() < n) combs_out.reserve(n);
    combs_out.assign(n, 0.0);

    // 1. Pre-delay & mono mix
    for (std::size_t i = 0; i < n; ++i) {
        double xl_delayed = left[i];
        double xr_delayed = right_src[i];
        if (pre_delay_samples > 0) {
            if (static_cast<long>(i) >= pre_delay_samples) {
                xl_delayed = left[i - pre_delay_samples];
                xr_delayed = right_src[i - pre_delay_samples];
            } else {
                xl_delayed = 0.0;
                xr_delayed = 0.0;
            }
        }
        mono_input[i] = 0.5 * (xl_delayed + xr_delayed);
    }

    // 2. Parallel Comb Filters
    if (comb_y.capacity() < n) comb_y.reserve(n);
    comb_y.resize(n);

    for (int k = 0; k < 4; ++k) {
        const int d = comb_delays[k];
        if (d >= static_cast<long>(n)) continue;
        const double g = comb_g[k];
        const double g1 = g * (1.0 - damping);
        const double g2 = g * damping;

        std::fill(comb_y.begin(), comb_y.begin() + n, 0.0);
        for (std::size_t i = 0; i < n; ++i) {
            double acc = 0.0;
            if (static_cast<long>(i) >= d) {
                acc = mono_input[i - d] + g1 * comb_y[i - d];
                if (static_cast<long>(i) >= d + 1) {
                    acc += g2 * comb_y[i - d - 1];
                }
            }
            comb_y[i] = acc;
            combs_out[i] += acc;
        }
    }

    for (std::size_t i = 0; i < n; ++i) {
        combs_out[i] *= 0.25;
    }

    // 3. Series All-Pass Filters
    if (ap_out.capacity() < n) ap_out.reserve(n);
    ap_out.assign(combs_out.begin(), combs_out.begin() + n);

    if (next_ap.capacity() < n) next_ap.reserve(n);
    next_ap.resize(n);

    for (int k = 0; k < 2; ++k) {
        const int d = ap_delays[k];
        if (d >= static_cast<long>(n)) continue;
        const double g_ap = 0.7;
        std::fill(next_ap.begin(), next_ap.begin() + n, 0.0);
        for (std::size_t i = 0; i < n; ++i) {
            double acc = -g_ap * ap_out[i];
            if (static_cast<long>(i) >= d) {
                acc += ap_out[i - d] + g_ap * next_ap[i - d];
            }
            next_ap[i] = acc;
        }
        ap_out.assign(next_ap.begin(), next_ap.begin() + n);
    }

    // 4. Stereo spread (delay left by 23ms, right by 29ms)
    const int delay_l = static_cast<int>(fs * 0.023);
    const int delay_r = static_cast<int>(fs * 0.029);

    // Matches numpy's np.pad(ap_out, (delay, 0))[:-delay] semantics: when the
    // delay fits inside the signal, samples before the delay has "arrived"
    // are zero (a real causal delay), not the undelayed ap_out[i] -- that was
    // a real bug here (up to ~0.3 linear-amplitude divergence for small
    // room_size, where the comb filters' own onset latency is shorter than
    // delay_l/delay_r and ap_out[i] is genuinely non-zero in that window).
    // Only when the delay is >= the whole signal length does Python fall
    // back to the unshifted ap_out array (see spatial.py's Reverb.apply).
    const bool l_fits = delay_l < static_cast<long>(n);
    const bool r_fits = delay_r < static_cast<long>(n);
    for (std::size_t i = 0; i < n; ++i) {
        double wl, wr;
        if (l_fits) {
            wl = (static_cast<long>(i) >= delay_l) ? ap_out[i - delay_l] : 0.0;
        } else {
            wl = ap_out[i];
        }
        if (r_fits) {
            wr = (static_cast<long>(i) >= delay_r) ? ap_out[i - delay_r] : 0.0;
        } else {
            wr = ap_out[i];
        }

        out_l[i] = (1.0 - wet_dry) * left[i] + wet_dry * wl;
        out_r[i] = (1.0 - wet_dry) * right_src[i] + wet_dry * wr;
    }
}

}  // extern "C"

namespace {

// Make a delay-line ring able to hold `needed` samples. Deliberately
// grow-only: the kernel wraps each index at the *active* delay, so a ring
// that kept its high-water mark never reallocates and never re-zeros while
// a host automates room_size. A ring sized to the live delay instead would
// zero the comb bank on every block of a sweep, gating the wet path 32
// times a second -- reverb.py sizes for max_comb for the same reason.
// Freshly grown slots are zeroed, which is what makes an opening ring
// reproduce the batch kernel's implicit pre-buffer silence.
void grow_delay_ring(std::vector<double>& ring, std::size_t needed)
{
    if (ring.size() < needed)
        ring.resize(needed, 0.0);
}

// Wipe a ring's contents but keep its allocation, so prepareToPlay does not
// hand the first processBlock after it a set of fresh allocations.
void flush_delay_ring(std::vector<double>& ring, std::size_t& index)
{
    std::fill(ring.begin(), ring.end(), 0.0);
    index = 0;
}

}  // namespace

extern "C" {

void schroeder_reverb_stream(
    SchroederReverbState* state,
    const double* left, const double* right, std::size_t n,
    int pre_delay_samples, double room_size, double decay_time, double damping, double wet_dry, double sample_rate,
    double* out_l, double* out_r)
{
    if (state == nullptr || n == 0 || !left || !out_l || !out_r) return;

    const double fs = (sample_rate > 0.0) ? sample_rate : 44100.0;
    // room_size below 0 has no defined batch behaviour either (negative
    // comb delays index past the buffer there), so clamp instead of
    // letting a stray value turn a ring length negative.
    const double clamped_room = (room_size < 0.0) ? 0.0 : room_size;
    const double scale = 0.5 + clamped_room * 1.5;

    const int comb_delays[4] = {
        static_cast<int>(1116.0 * scale),
        static_cast<int>(1188.0 * scale),
        static_cast<int>(1277.0 * scale),
        static_cast<int>(1356.0 * scale)
    };
    const int ap_delays[2] = {
        static_cast<int>(225.0 * scale),
        static_cast<int>(341.0 * scale)
    };

    const double decay_t = (decay_time < 0.1) ? 0.1 : decay_time;
    double comb_g[4];
    for (int k = 0; k < 4; ++k) {
        comb_g[k] = std::pow(10.0, -3.0 * comb_delays[k] / (decay_t * fs));
    }

    const double* right_src = right ? right : left;

    const std::size_t pre_delay = (pre_delay_samples > 0)
        ? static_cast<std::size_t>(pre_delay_samples)
        : static_cast<std::size_t>(0);
    grow_delay_ring(state->pre_delay_history, pre_delay);

    for (int k = 0; k < 4; ++k) {
        // y_history needs one slot more than the comb delay because the
        // damping term reaches y[i-d] and y[i-d-1], which are consecutive
        // samples in a ring wrapping at d + 1.
        grow_delay_ring(state->combs[k].x_history, static_cast<std::size_t>(comb_delays[k]));
        grow_delay_ring(state->combs[k].y_history, static_cast<std::size_t>(comb_delays[k]) + 1);
    }

    for (int k = 0; k < 2; ++k) {
        const std::size_t d = static_cast<std::size_t>(ap_delays[k]);
        grow_delay_ring(state->allpasses[k].x_history, d);
        grow_delay_ring(state->allpasses[k].y_history, d);
    }

    // The spread delays are 23 ms and 29 ms, so both exceed 1000 samples at
    // any real rate; the clamp only stops a nonsense rate (< 44 Hz) from
    // wrapping an index modulo zero.
    const double spread_l = fs * 0.023;
    const double spread_r = fs * 0.029;
    const std::size_t delay_l = (spread_l < 1.0) ? static_cast<std::size_t>(1) : static_cast<std::size_t>(spread_l);
    const std::size_t delay_r = (spread_r < 1.0) ? static_cast<std::size_t>(1) : static_cast<std::size_t>(spread_r);
    grow_delay_ring(state->spread_l_history, delay_l);
    grow_delay_ring(state->spread_r_history, delay_r);

    const double g_ap = 0.7;

    for (std::size_t i = 0; i < n; ++i) {
        // 1. Pre-delay & mono mix. Reading the ring yields the mix from
        // pre_delay samples ago, exactly what the batch kernel computes
        // by shifting each channel before mixing.
        double mono_delayed;
        if (pre_delay > 0) {
            mono_delayed = state->pre_delay_history[state->pre_delay_index];
            state->pre_delay_history[state->pre_delay_index] = 0.5 * (left[i] + right_src[i]);
            state->pre_delay_index = (state->pre_delay_index + 1) % pre_delay;
        }
        else {
            mono_delayed = 0.5 * (left[i] + right_src[i]);
        }

        // 2. Parallel comb filters. The batch kernel skips a comb
        // entirely when d >= n; a 128-sample block never reaches even
        // the shortest comb (558 samples at room_size 0, 1395 at the
        // 0.5 default), which is why the per-block call silenced the
        // wet path. The rings carry the missing 12.7-31.6 ms of
        // history across calls.
        double combs_acc = 0.0;
        for (int k = 0; k < 4; ++k) {
            SchroederReverbState::Comb& comb = state->combs[k];
            const std::size_t d = static_cast<std::size_t>(comb_delays[k]);
            const std::size_t dy = d + 1;
            const double g = comb_g[k];
            const double g1 = g * (1.0 - damping);
            const double g2 = g * damping;

            const double x_delayed = comb.x_history[comb.x_index];
            const double y_delayed = comb.y_history[(comb.y_index + 1) % dy];
            const double y_prev = comb.y_history[comb.y_index];
            const double acc = x_delayed + g1 * y_delayed;
            const double with_prev = acc + g2 * y_prev;

            comb.x_history[comb.x_index] = mono_delayed;
            comb.x_index = (comb.x_index + 1) % d;
            comb.y_history[comb.y_index] = with_prev;
            comb.y_index = (comb.y_index + 1) % dy;

            combs_acc += with_prev;
        }

        const double combs_out = 0.25 * combs_acc;

        // 3. Series all-pass filters. The association below matches the
        // batch kernel's (-g*x) + (x_d + g*y_d) so streaming and one-shot
        // calls agree bit for bit.
        double ap_out = combs_out;
        for (int k = 0; k < 2; ++k) {
            SchroederReverbState::Allpass& ap = state->allpasses[k];
            const std::size_t d = static_cast<std::size_t>(ap_delays[k]);

            const double x_delayed = ap.x_history[ap.x_index];
            const double y_delayed = ap.y_history[ap.y_index];
            const double feedback = x_delayed + g_ap * y_delayed;
            const double y = (-g_ap * ap_out) + feedback;

            ap.x_history[ap.x_index] = ap_out;
            ap.x_index = (ap.x_index + 1) % d;
            ap.y_history[ap.y_index] = y;
            ap.y_index = (ap.y_index + 1) % d;

            ap_out = y;
        }

        // 4. Stereo spread (delay left by 23ms, right by 29ms)
        const double wl = state->spread_l_history[state->spread_l_index];
        state->spread_l_history[state->spread_l_index] = ap_out;
        state->spread_l_index = (state->spread_l_index + 1) % delay_l;

        const double wr = state->spread_r_history[state->spread_r_index];
        state->spread_r_history[state->spread_r_index] = ap_out;
        state->spread_r_index = (state->spread_r_index + 1) % delay_r;

        out_l[i] = (1.0 - wet_dry) * left[i] + wet_dry * wl;
        out_r[i] = (1.0 - wet_dry) * right_src[i] + wet_dry * wr;
    }
}

void schroeder_reverb_state_reset(SchroederReverbState* state)
{
    if (state == nullptr) return;

    flush_delay_ring(state->pre_delay_history, state->pre_delay_index);

    for (int k = 0; k < 4; ++k) {
        flush_delay_ring(state->combs[k].x_history, state->combs[k].x_index);
        flush_delay_ring(state->combs[k].y_history, state->combs[k].y_index);
    }

    for (int k = 0; k < 2; ++k) {
        flush_delay_ring(state->allpasses[k].x_history, state->allpasses[k].x_index);
        flush_delay_ring(state->allpasses[k].y_history, state->allpasses[k].y_index);
    }

    flush_delay_ring(state->spread_l_history, state->spread_l_index);
    flush_delay_ring(state->spread_r_history, state->spread_r_index);
}

}  // extern "C"
