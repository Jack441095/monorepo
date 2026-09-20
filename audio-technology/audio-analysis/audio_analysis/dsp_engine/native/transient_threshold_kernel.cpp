// C++ compute kernel for the per-frame rolling median/MAD adaptive threshold
// used by transient_groove.py's detect_transient_onsets.
//
// Matches this exact Python loop for bit-exactness:
//   radius = 8
//   for index in range(len(flux)):
//       local = flux[max(0, index-radius):min(len(flux), index+radius+1)]
//       median = float(np.median(local))
//       mad = float(np.median(np.abs(local - median)))
//       threshold[index] = median + max(0.015, 3.0*mad)
//
// The window is at most 2*radius+1 elements (truncated, not padded, at the
// signal edges) -- np.median's own definition (sorted middle element, or the
// mean of the two middle elements for an even-length window) is replicated
// exactly via a full sort of the (tiny, <=2*radius+1) window per index. This
// was a Python-level np.median() call twice per index (measured 282K calls
// for a real render) -- the per-call Python/numpy dispatch overhead, not the
// O(w log w) work itself, was the actual cost on a window this small.

#include <algorithm>
#include <cstddef>
#include <vector>

extern "C" {

namespace {

// np.median() on a sorted buffer of length w: middle element for odd w, mean
// of the two middle elements for even w.
inline double median_of_sorted(const double* buf, int w) {
    if (w % 2 == 1) {
        return buf[w / 2];
    }
    return (buf[w / 2 - 1] + buf[w / 2]) / 2.0;
}

}  // namespace

void rolling_median_mad_threshold(
    const double* flux, std::size_t n, int radius,
    double min_floor, double mad_multiplier,
    double* threshold_out)
{
    if (n == 0 || !flux || !threshold_out) return;

    const int max_window = 2 * radius + 1;
    std::vector<double> window_buf(max_window > 0 ? max_window : 1);
    std::vector<double> dev_buf(max_window > 0 ? max_window : 1);

    for (std::size_t i = 0; i < n; ++i) {
        const long lo = std::max(0L, static_cast<long>(i) - radius);
        const long hi = std::min(static_cast<long>(n), static_cast<long>(i) + radius + 1);
        const int w = static_cast<int>(hi - lo);

        for (int k = 0; k < w; ++k) {
            window_buf[k] = flux[lo + k];
        }
        std::sort(window_buf.begin(), window_buf.begin() + w);
        const double median = median_of_sorted(window_buf.data(), w);

        for (int k = 0; k < w; ++k) {
            const double d = flux[lo + k] - median;
            dev_buf[k] = (d < 0.0) ? -d : d;
        }
        std::sort(dev_buf.begin(), dev_buf.begin() + w);
        const double mad = median_of_sorted(dev_buf.data(), w);

        const double scaled_mad = mad_multiplier * mad;
        threshold_out[i] = median + (min_floor > scaled_mad ? min_floor : scaled_mad);
    }
}

}  // extern "C"
