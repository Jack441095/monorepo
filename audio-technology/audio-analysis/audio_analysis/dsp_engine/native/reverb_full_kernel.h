/*
 * reverb_full_kernel.h — Schroeder-Moorer reverb kernel declarations.
 *
 * Shared by the offline audio-analysis path (one-shot batch calls via
 * the ctypes bridge in native/__init__.py) and the realtime VST3/AU
 * plugin (streaming calls from processBlock). Deliberately free of
 * JUCE and other project headers: the Python bridge compiles
 * reverb_full_kernel.cpp on its own with nothing but a C++17 compiler.
 */

#ifndef REVERB_FULL_KERNEL_H
#define REVERB_FULL_KERNEL_H

#include <cstddef>
#include <vector>

/*
 * Delay-line state carried across streaming calls.
 *
 * schroeder_reverb() below starts every call from silence, which is
 * correct for offline whole-signal renders but wrong for a host that
 * hands the kernel one processBlock at a time: at the usual 128-512
 * sample block sizes every comb filter is skipped outright (the
 * shortest comb delay is 558 samples at room_size 0 and 1395 at the
 * 0.5 default, i.e. 12.7 ms to 31.6 ms of look-back no single block
 * contains) and the pre-delay zeroes the whole block, so the wet path
 * never sounds. schroeder_reverb_stream() feeds the same recursion
 * from this state instead.
 *
 * Every ring is at least as long as the delay it serves, so the modulo
 * arithmetic in the kernel cannot index past the buffer. A ring only ever
 * grows: it holds the high-water mark of the delays it has been asked for
 * and the kernel wraps the index at the *current* delay, leaving the spare
 * slots untouched. That is what keeps a moving room_size knob from wiping
 * the tail -- a host sweeps it every block, and a ring that re-sized to
 * the live delay would zero the comb bank 32 times a second and gate the
 * wet path. reverb.py avoids the same trap by allocating for max_comb and
 * only moving the wrap point.
 *
 * Newly grown slots are zero-filled, which is what makes a freshly opened
 * ring reproduce the batch kernel's implicit pre-buffer silence.
 */
struct SchroederReverbState
{
    // One damped comb filter: y[i] = x[i-d] + g1*y[i-d] + g2*y[i-d-1].
    // x_history keeps the last d input samples; y_history keeps d + 1
    // output samples so the recursion can reach both y[i-d] and
    // y[i-d-1]. buf[index] is the sample from d (or d+1) samples back,
    // and buf[(index + 1) % len] is one sample newer than that.
    struct Comb
    {
        std::vector<double> x_history;
        std::vector<double> y_history;
        std::size_t x_index = 0;
        std::size_t y_index = 0;
    };

    // One Schroeder all-pass filter: y[i] = -g*x[i] + x[i-d] + g*y[i-d].
    struct Allpass
    {
        std::vector<double> x_history;
        std::vector<double> y_history;
        std::size_t x_index = 0;
        std::size_t y_index = 0;
    };

    // Pre-delay over the mono mix. The mix commutes with the delay
    // (0.5 is a power of two, so it scales exactly in IEEE double), so
    // one ring over 0.5*(l+r) reproduces the batch kernel's per-channel
    // pre-delay followed by mix exactly.
    std::vector<double> pre_delay_history;
    std::size_t pre_delay_index = 0;

    Comb combs[4];
    Allpass allpasses[2];

    // Stereo spread: 23 ms on the left, 29 ms on the right at 44.1 kHz.
    std::vector<double> spread_l_history;
    std::size_t spread_l_index = 0;
    std::vector<double> spread_r_history;
    std::size_t spread_r_index = 0;
};

#ifdef __cplusplus
extern "C" {
#endif

/*
 * Offline batch reverb. Treats [left, right) as one complete signal:
 * all delay lines start empty and every filter whose delay does not fit
 * in n is skipped. Callers that stream audio in blocks must use
 * schroeder_reverb_stream() instead.
 */
void schroeder_reverb(
    const double* left, const double* right, std::size_t n,
    int pre_delay_samples, double room_size, double decay_time, double damping, double wet_dry, double sample_rate,
    double* out_l, double* out_r
);

/*
 * Streaming reverb: same recursion and parameters as schroeder_reverb,
 * but delay lines live in state and survive across calls, so blocks of
 * any size (down to 1 sample) produce exactly what one batch call over
 * the concatenated blocks produces.
 *
 * A knob move only moves each ring's wrap point, never reallocates and
 * never zeroes, so the tail runs on through an automation sweep.
 *
 * Matches the batch kernel's causal stereo spread; the batch kernel's
 * fallback for one-shot buffers shorter than the 29 ms spread delay
 * (undelayed passthrough) has no streaming meaning, so the two differ for
 * buffers shorter than the spread delay.
 *
 * state is owned by the caller and touched only on the calling thread;
 * a ring allocates only the first time a delay needs more room than it
 * has, never per sample.
 */
void schroeder_reverb_stream(
    SchroederReverbState* state,
    const double* left, const double* right, std::size_t n,
    int pre_delay_samples, double room_size, double decay_time, double damping, double wet_dry, double sample_rate,
    double* out_l, double* out_r
);

/* Flush every delay line in state. Call from prepareToPlay(): the
 * 23/29 ms spread delays depend on the sample rate, so a rate change
 * must not carry old history across. */
void schroeder_reverb_state_reset(SchroederReverbState* state);

#ifdef __cplusplus
}
#endif

#endif /* REVERB_FULL_KERNEL_H */
