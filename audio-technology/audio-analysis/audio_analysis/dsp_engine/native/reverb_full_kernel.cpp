// C++ end-to-end Schroeder-Moorer Reverb compute kernel.
//
// Evaluates pre-delay, 4 parallel LBCF comb filters, 2 series allpass filters,
// stereo decorrelation, and wet/dry blend in a single C++ execution pass.

#include <cstddef>
#include <vector>
#include <cmath>
#include <utility>

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
