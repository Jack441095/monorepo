// C++ compute kernel for tape/tube soft saturation waveshaping.
//
// Matches operation order of saturation.py's apply_saturation for bit-exactness.

#include <cstddef>
#include <cmath>

extern "C" {

void saturator_waveshape(
    const double* x_up, std::size_t n,
    double drive_linear, double even_harmonics_a, double mix,
    const double* x_orig, std::size_t n_orig,
    double* y_out)
{
    if (n == 0 || !x_up || !y_out) return;

    const double d = (drive_linear > 1e-9) ? drive_linear : 1.0;
    const double a = even_harmonics_a;

    for (std::size_t i = 0; i < n; ++i) {
        const double x_val = x_up[i];
        const double x_shape = (a > 0.0) ? (x_val + a * (x_val * x_val - 0.5)) : x_val;
        const double sat_val = std::tanh(x_shape * d) / d;

        if (x_orig && n_orig == n) {
            y_out[i] = (1.0 - mix) * x_orig[i] + mix * sat_val;
        } else {
            y_out[i] = sat_val;
        }
    }
}

}  // extern "C"
