#include "automix_bindings.hpp"

#include <algorithm>
#include <cmath>
#include <cstddef>
#include <string>
#include <vector>

#include <nanobind/ndarray.h>
#include <nanobind/nanobind.h>

#include "AudioToo_DSP.h"

namespace nb = nanobind;

using DoubleInput = nb::ndarray<nb::numpy, const double, nb::ndim<1>, nb::c_contig, nb::device::cpu>;
using DoubleMatrixInput = nb::ndarray<nb::numpy, const double, nb::ndim<2>, nb::c_contig, nb::device::cpu>;
using DoubleOutput = nb::ndarray<nb::numpy, double, nb::shape<-1>, nb::device::cpu>;

extern "C" {
void biquad_sos_filter(const double*, std::size_t, const double*, std::size_t, double*);
void smooth_attack_release(
    const double*, std::size_t, double, double, double, bool, double*);
void gate_envelope(
    const double*, std::size_t, double, double, double, int, double, double, double*);
void rolling_median_mad_threshold(
    const double*, std::size_t, int, double, double, double*);
}

namespace {

DoubleOutput make_output(const std::vector<double>& values)
{
    auto* data = new double[values.size()];
    std::copy(values.begin(), values.end(), data);
    nb::capsule owner(data, [](void* pointer) noexcept { delete[] static_cast<double*>(pointer); });
    return DoubleOutput(data, { values.size() }, owner);
}

void require_nonempty_finite(const DoubleInput& values, const char* name)
{
    if (values.ndim() != 1 || values.shape(0) == 0)
    {
        const std::string message = std::string(name) +
                                    " must be a non-empty one-dimensional float64 NumPy array";
        throw nb::value_error(message.c_str());
    }
    const double* ptr = values.data();
    const std::size_t count = values.shape(0);
    for (std::size_t i = 0; i < count; ++i)
    {
        if (!std::isfinite(ptr[i]))
        {
            const std::string message = std::string(name) + " contains NaN or infinite samples";
            throw nb::value_error(message.c_str());
        }
    }
}

void require_finite_scalar(double value, const char* name)
{
    if (!std::isfinite(value))
    {
        const std::string message = std::string(name) + " must be finite";
        throw nb::value_error(message.c_str());
    }
}

void require_smoothing_alpha(double alpha, const char* name)
{
    if (!std::isfinite(alpha) || alpha < 0.0 || alpha > 1.0)
    {
        const std::string message = std::string(name) + " must be in [0.0, 1.0]";
        throw nb::value_error(message.c_str());
    }
}

nb::dict limiter(DoubleInput input, double input_gain, double ceiling_lin, double alpha_rel, int lookahead)
{
    require_nonempty_finite(input, "input");
    if (!std::isfinite(input_gain) || input_gain <= 0.0)
        throw nb::value_error("input_gain must be positive and finite");
    if (!std::isfinite(ceiling_lin) || ceiling_lin <= 0.0)
        throw nb::value_error("ceiling_lin must be positive and finite");
    if (!std::isfinite(alpha_rel) || alpha_rel < 0.0 || alpha_rel >= 1.0)
        throw nb::value_error("alpha_rel must be in [0.0, 1.0)");
    if (lookahead < 1)
        throw nb::value_error("lookahead must be positive");

    // Zero-padding beyond the buffer length cannot increase the sliding-window
    // maximum of |x_g| >= 0, so clamping lookahead to input.shape(0) preserves
    // bit-exactness while avoiding unbounded reserve/loop work on huge L.
    const int effective_lookahead = static_cast<int>(
        std::min<std::size_t>(static_cast<std::size_t>(lookahead), input.shape(0)));

    std::vector<double> audio(input.shape(0));
    std::vector<double> gain(input.shape(0));
    {
        nb::gil_scoped_release release;
        limiter_gain_envelope(input.data(), input.shape(0), input_gain, ceiling_lin, alpha_rel,
                              effective_lookahead, gain.data(), audio.data());
    }
    nb::dict output;
    output["gain"] = make_output(gain);
    output["audio"] = make_output(audio);
    return output;
}

DoubleOutput biquad(DoubleMatrixInput sos, DoubleInput input)
{
    if (sos.ndim() != 2 || sos.shape(0) == 0 || sos.shape(1) != 6)
        throw nb::value_error("sos must have shape (sections, 6) with at least one section");
    require_nonempty_finite(input, "input");

    const std::size_t sections = sos.shape(0);
    const double* sos_ptr = sos.data();
    std::vector<double> normalized_sos;
    bool needs_normalization = false;
    for (std::size_t s = 0; s < sections; ++s)
    {
        const std::size_t offset = s * 6;
        for (std::size_t k = 0; k < 6; ++k)
        {
            if (!std::isfinite(sos_ptr[offset + k]))
                throw nb::value_error("sos contains NaN or infinite coefficients");
        }
        const double a0 = sos_ptr[offset + 3];
        if (std::abs(a0) <= 1e-15)
            throw nb::value_error("sos section a0 coefficient must be non-zero");
        if (a0 != 1.0)
            needs_normalization = true;
    }

    if (needs_normalization)
    {
        normalized_sos.resize(sections * 6);
        for (std::size_t s = 0; s < sections; ++s)
        {
            const std::size_t offset = s * 6;
            const double inv_a0 = 1.0 / sos_ptr[offset + 3];
            normalized_sos[offset + 0] = sos_ptr[offset + 0] * inv_a0;
            normalized_sos[offset + 1] = sos_ptr[offset + 1] * inv_a0;
            normalized_sos[offset + 2] = sos_ptr[offset + 2] * inv_a0;
            normalized_sos[offset + 3] = 1.0;
            normalized_sos[offset + 4] = sos_ptr[offset + 4] * inv_a0;
            normalized_sos[offset + 5] = sos_ptr[offset + 5] * inv_a0;
        }
        sos_ptr = normalized_sos.data();
    }

    std::vector<double> output(input.shape(0));
    {
        nb::gil_scoped_release release;
        biquad_sos_filter(sos_ptr, sections, input.data(), input.shape(0), output.data());
    }
    for (double sample : output)
    {
        if (!std::isfinite(sample))
            throw nb::value_error("biquad filter output became non-finite");
    }
    return make_output(output);
}

nb::dict correlation(DoubleInput left, DoubleInput right, int max_lag)
{
    require_nonempty_finite(left, "left");
    require_nonempty_finite(right, "right");
    if (left.shape(0) != right.shape(0))
        throw nb::value_error("left and right must have equal lengths");
    if (max_lag < 1)
        throw nb::value_error("max_lag must be positive");

    // Lags >= N have zero overlap (start_i >= end_i in direct_cross_correlation),
    // so clamping max_lag to max(1, N - 1) avoids spinning on empty lag windows.
    const std::size_t max_useful_lag = left.shape(0) > 1 ? left.shape(0) - 1 : 1;
    const int effective_lag = static_cast<int>(
        std::min<std::size_t>(static_cast<std::size_t>(max_lag), max_useful_lag));

    double value = 0.0;
    int lag = 0;
    {
        nb::gil_scoped_release release;
        direct_cross_correlation(left.data(), right.data(), left.shape(0), effective_lag, &value, &lag);
    }
    nb::dict output;
    output["correlation"] = value;
    output["lag"] = lag;
    return output;
}

DoubleOutput smooth(DoubleInput values, double alpha_att, double alpha_rel, double init, bool attack_when_less)
{
    require_nonempty_finite(values, "values");
    require_smoothing_alpha(alpha_att, "alpha_att");
    require_smoothing_alpha(alpha_rel, "alpha_rel");
    require_finite_scalar(init, "init");
    std::vector<double> output(values.shape(0));
    {
        nb::gil_scoped_release release;
        smooth_attack_release(values.data(), values.shape(0), alpha_att, alpha_rel, init, attack_when_less, output.data());
    }
    return make_output(output);
}

DoubleOutput gate(DoubleInput levels, double threshold, double alpha_att, double alpha_rel,
                  int hold_samples, double target_gain_open, double target_gain_closed)
{
    require_nonempty_finite(levels, "levels");
    require_finite_scalar(threshold, "threshold");
    require_smoothing_alpha(alpha_att, "alpha_att");
    require_smoothing_alpha(alpha_rel, "alpha_rel");
    if (hold_samples < 0)
        throw nb::value_error("hold_samples must be non-negative");
    require_finite_scalar(target_gain_open, "target_gain_open");
    require_finite_scalar(target_gain_closed, "target_gain_closed");
    std::vector<double> output(levels.shape(0));
    {
        nb::gil_scoped_release release;
        gate_envelope(levels.data(), levels.shape(0), threshold, alpha_att, alpha_rel,
                      hold_samples, target_gain_open, target_gain_closed, output.data());
    }
    return make_output(output);
}

DoubleOutput threshold(DoubleInput flux, int radius, double min_floor, double mad_multiplier)
{
    require_nonempty_finite(flux, "flux");
    if (radius < 0)
        throw nb::value_error("radius must be non-negative");
    require_finite_scalar(min_floor, "min_floor");
    if (!std::isfinite(mad_multiplier) || mad_multiplier < 0.0)
        throw nb::value_error("mad_multiplier must be non-negative and finite");

    // A window radius larger than flux.shape(0) already covers the entire array
    // [0, N) for every index; clamping bounds the scratch allocation to 2*N + 1.
    const int effective_radius = static_cast<int>(
        std::min<std::size_t>(static_cast<std::size_t>(radius), flux.shape(0)));

    std::vector<double> output(flux.shape(0));
    {
        nb::gil_scoped_release release;
        rolling_median_mad_threshold(flux.data(), flux.shape(0), effective_radius, min_floor, mad_multiplier, output.data());
    }
    return make_output(output);
}

} // namespace

void init_automix_bindings(nb::module_& module)
{
    auto automix = module.def_submodule("automix", "Optional native AutoMix DSP kernels.");
    automix.def("limiter", &limiter, nb::arg("input"), nb::arg("input_gain"),
                 nb::arg("ceiling_lin"), nb::arg("alpha_rel"), nb::arg("lookahead"));
    automix.def("biquad", &biquad, nb::arg("sos"), nb::arg("input"));
    automix.def("correlation", &correlation, nb::arg("left"), nb::arg("right"), nb::arg("max_lag"));
    automix.def("smooth", &smooth, nb::arg("values"), nb::arg("alpha_att"), nb::arg("alpha_rel"),
                nb::arg("init"), nb::arg("attack_when_less"));
    automix.def("gate", &gate, nb::arg("levels"), nb::arg("threshold"), nb::arg("alpha_att"),
                nb::arg("alpha_rel"), nb::arg("hold_samples"), nb::arg("target_gain_open"),
                nb::arg("target_gain_closed"));
    automix.def("threshold", &threshold, nb::arg("flux"), nb::arg("radius"),
                nb::arg("min_floor"), nb::arg("mad_multiplier"));
}
