// C++ compute kernel for Schroeder-Moorer Reverb (LBCF Comb & Allpass filters).
//
// Operation order matches spatial.py's _lbcf_comb_py and _allpass_py for bit-exactness.

#include <cstddef>
#include <cmath>

extern "C" {

// Low-pass feedback comb filter:
// y[n] = x[n-d] + g * ((1-damping)*y[n-d] + damping*y[n-d-1])
void lbcf_comb_filter(
    const double* x, std::size_t n, int d, double g, double damping, double* y_out)
{
    if (n == 0 || d < 1 || !x || !y_out) return;
    const double g1 = g * (1.0 - damping);
    const double g2 = g * damping;

    for (std::size_t i = 0; i < n; ++i) {
        double acc = 0.0;
        if (static_cast<long>(i) >= d) {
            acc = x[i - d] + g1 * y_out[i - d];
            if (static_cast<long>(i) >= d + 1) {
                acc += g2 * y_out[i - d - 1];
            }
        }
        y_out[i] = acc;
    }
}

// All-pass filter:
// y[n] = -g*x[n] + x[n-d] + g*y[n-d]
void allpass_filter(
    const double* x, std::size_t n, int d, double g, double* y_out)
{
    if (n == 0 || d < 1 || !x || !y_out) return;

    for (std::size_t i = 0; i < n; ++i) {
        double acc = -g * x[i];
        if (static_cast<long>(i) >= d) {
            acc += x[i - d] + g * y_out[i - d];
        }
        y_out[i] = acc;
    }
}

}  // extern "C"
