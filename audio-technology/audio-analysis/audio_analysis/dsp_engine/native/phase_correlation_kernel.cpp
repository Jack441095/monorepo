// C++ compute kernel for direct lag-windowed stem cross-correlation.
//
// Computes Pearson correlation over a small lag window [-max_lag, +max_lag].
// O(N * max_lag) SIMD compute pass matching scipy.signal.correlate(a, b) sign convention.

#include <cstddef>
#include <cmath>
#include <vector>
#include <algorithm>

extern "C" {

void direct_cross_correlation(
    const double* a, const double* b, std::size_t n, int max_lag,
    double* out_best_corr, int* out_best_lag)
{
    if (n == 0 || max_lag < 1 || !a || !b || !out_best_corr || !out_best_lag) {
        if (out_best_corr) *out_best_corr = 0.0;
        if (out_best_lag) *out_best_lag = 0;
        return;
    }

    double sum_a = 0.0, sum_b = 0.0;
    for (std::size_t i = 0; i < n; ++i) {
        sum_a += a[i];
        sum_b += b[i];
    }
    const double mean_a = sum_a / static_cast<double>(n);
    const double mean_b = sum_b / static_cast<double>(n);

    double ss_a = 0.0, ss_b = 0.0;
    std::vector<double> a_c(n), b_c(n);
    for (std::size_t i = 0; i < n; ++i) {
        const double ac = a[i] - mean_a;
        const double bc = b[i] - mean_b;
        a_c[i] = ac;
        b_c[i] = bc;
        ss_a += ac * ac;
        ss_b += bc * bc;
    }

    const double norm = std::sqrt(ss_a * ss_b);
    if (norm < 1e-12) {
        *out_best_corr = 0.0;
        *out_best_lag = 0;
        return;
    }

    double max_abs_corr = -1.0;
    double best_corr = 0.0;
    int best_lag = 0;

    const long nn = static_cast<long>(n);
    for (int lag = -max_lag; lag <= max_lag; ++lag) {
        double dot = 0.0;
        const long start_i = std::max(0L, static_cast<long>(lag));
        const long end_i = std::min(nn, nn + static_cast<long>(lag));

        for (long i = start_i; i < end_i; ++i) {
            dot += a_c[i] * b_c[i - lag];
        }

        const double corr = dot / norm;
        const double abs_corr = std::abs(corr);
        if (abs_corr > max_abs_corr) {
            max_abs_corr = abs_corr;
            best_corr = corr;
            best_lag = lag;
        }
    }

    if (best_corr > 1.0) best_corr = 1.0;
    if (best_corr < -1.0) best_corr = -1.0;

    *out_best_corr = best_corr;
    *out_best_lag = best_lag;
}

}  // extern "C"
