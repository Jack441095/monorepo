// C++ compute kernel for cascaded biquad (Second-Order Sections) IIR filter.
//
// Direct Form II Transposed topology matching scipy.signal.sosfilt operation.
// IEEE 754 double precision operation order matches python reference for bit-exactness.

#include <cstddef>

extern "C" {

// Apply cascaded Second-Order Sections (SOS) filter to input signal x.
//   sos       : SOS matrix as flattened array of size n_sections * 6.
//               Each row contains [b0, b1, b2, 1.0, a1, a2].
//   n_sections: Number of biquad sections.
//   x         : Input audio samples (length n_samples).
//   n_samples : Number of audio samples.
//   y_out     : [out] Filtered audio samples (length n_samples).
void biquad_sos_filter(
    const double* sos, std::size_t n_sections,
    const double* x, std::size_t n_samples,
    double* y_out)
{
    if (n_sections == 0 || n_samples == 0 || !sos || !x || !y_out) return;

    for (std::size_t i = 0; i < n_samples; ++i) {
        y_out[i] = x[i];
    }

    for (std::size_t s = 0; s < n_sections; ++s) {
        const std::size_t offset = s * 6;
        const double b0 = sos[offset + 0];
        const double b1 = sos[offset + 1];
        const double b2 = sos[offset + 2];
        const double a1 = sos[offset + 4];
        const double a2 = sos[offset + 5];

        double z1 = 0.0;
        double z2 = 0.0;

        for (std::size_t i = 0; i < n_samples; ++i) {
            const double xi = y_out[i];
            const double yi = b0 * xi + z1;
            z1 = b1 * xi - a1 * yi + z2;
            z2 = b2 * xi - a2 * yi;
            y_out[i] = yi;
        }
    }
}

}  // extern "C"
