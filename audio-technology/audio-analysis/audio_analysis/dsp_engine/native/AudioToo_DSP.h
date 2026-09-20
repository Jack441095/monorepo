/*
 * AudioToo_DSP.h — Consolidated C++ Native DSP Processing Header.
 * Zero-allocation audio processing algorithms for real-time audio analysis,
 * mastering, and JUCE VST3/AU audio plugin wrappers.
 */

#ifndef AUDIOTOO_DSP_H
#define AUDIOTOO_DSP_H

#include <cstddef>

#ifdef __cplusplus
extern "C" {
#endif

/*
 * Schroeder-Moorer Reverb
 * Evaluates pre-delay, 4 parallel LBCF comb filters, 2 series allpass filters,
 * stereo decorrelation, and wet/dry blend in a single pass.
 */
void schroeder_reverb(
    const double* left, const double* right, std::size_t n,
    int pre_delay_samples, double room_size, double decay_time, double damping, double wet_dry, double sample_rate,
    double* out_l, double* out_r
);

/*
 * Look-ahead Brickwall Limiter (gain envelope)
 * x: input samples (already gain-staged by input_gain upstream).
 * gain_out: per-sample gain reduction; audio_out: (x*input_gain)*gain.
 * Corrected 2026-08-01: this header previously declared a same-purpose but
 * differently-named/differently-signatured `apply_limiter(...)` that does
 * not exist in limiter_kernel.cpp -- harmless while unreferenced (only
 * schroeder_reverb below is currently called from AudioToo_PluginWrapper.cpp),
 * but would have failed to link the moment a Limiter plugin wrapper tried
 * to call it. Matches limiter_kernel.cpp's real exported symbol/signature.
 */
void limiter_gain_envelope(
    const double* x, std::size_t n,
    double input_gain, double ceiling_lin, double alpha_rel, int L,
    double* gain_out, double* audio_out
);

/*
 * Tape Saturation (waveshaper)
 * x_up/n: the (optionally oversampled) signal to shape; x_orig/n_orig: the
 * un-oversampled signal used for the dry side of the wet/dry mix.
 * Corrected 2026-08-01 alongside limiter_gain_envelope above -- matches
 * saturator_kernel.cpp's real exported symbol/signature (previously
 * declared here as a nonexistent `apply_tape_saturation(...)`).
 */
void saturator_waveshape(
    const double* x_up, std::size_t n,
    double drive_linear, double even_harmonics_a, double mix,
    const double* x_orig, std::size_t n_orig,
    double* y_out
);

/*
 * Direct Cross-Correlation (stereo phase/lag detection)
 * Corrected 2026-08-01 alongside the two above -- matches
 * phase_correlation_kernel.cpp's real exported symbol/signature (previously
 * declared here as a nonexistent `compute_phase_correlation(...)`).
 */
void direct_cross_correlation(
    const double* a, const double* b, std::size_t n, int max_lag,
    double* out_best_corr, int* out_best_lag
);

#ifdef __cplusplus
}
#endif

#endif /* AUDIOTOO_DSP_H */
