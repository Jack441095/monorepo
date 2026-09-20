// C++ compute kernel for state-dependent attack/release one-pole envelope smoothing and noise gate.
//
// Matches operation order of dynamics.py's _smooth_attack_release_py and _gate_envelope_py for bit-exactness.

#include <cstddef>

extern "C" {

void smooth_attack_release(
    const double* values, std::size_t n,
    double alpha_att, double alpha_rel, double init,
    bool attack_when_less, double* out)
{
    if (n == 0 || !values || !out) return;

    double current = init;
    for (std::size_t i = 0; i < n; ++i) {
        const double target = values[i];
        const bool attacking = attack_when_less ? (target < current) : (target <= current);
        if (attacking) {
            current = alpha_att * current + (1.0 - alpha_att) * target;
        } else {
            current = alpha_rel * current + (1.0 - alpha_rel) * target;
        }
        out[i] = current;
    }
}

void gate_envelope(
    const double* level_db, std::size_t n,
    double threshold, double alpha_att, double alpha_rel,
    int hold_samples, double target_gain_open, double target_gain_closed,
    double* g_out)
{
    if (n == 0 || !level_db || !g_out) return;

    bool gate_open = false;
    int hold_counter = 0;
    double current_gain = target_gain_closed;

    for (std::size_t i = 0; i < n; ++i) {
        const double level = level_db[i];
        if (level > threshold) {
            gate_open = true;
            hold_counter = hold_samples;
        } else {
            if (hold_counter > 0) {
                hold_counter--;
            } else {
                gate_open = false;
            }
        }
        const double target = gate_open ? target_gain_open : target_gain_closed;
        if (target > current_gain) {
            current_gain = alpha_att * current_gain + (1.0 - alpha_att) * target;
        } else {
            current_gain = alpha_rel * current_gain + (1.0 - alpha_rel) * target;
        }
        g_out[i] = current_gain;
    }
}

}  // extern "C"
