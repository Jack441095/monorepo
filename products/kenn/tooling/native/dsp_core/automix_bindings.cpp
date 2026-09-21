#include "automix_bindings.hpp"

#include <algorithm>
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

void require_nonempty(const DoubleInput& values, const char* name)
{
    if (values.ndim() != 1 || values.shape(0) == 0)
    {
        const std::string message = std::string(name) +
                                    " must be a non-empty one-dimensional float64 NumPy array";
        throw nb::value_error(message.c_str());
    }
}

nb::dict limiter(DoubleInput input, double input_gain, double ceiling_lin, double alpha_rel, int lookahead)
{
    require_nonempty(input, "input");
    if (lookahead < 1)
        throw nb::value_error("lookahead must be positive");
    std::vector<double> audio(input.shape(0));
    std::vector<double> gain(input.shape(0));
    {
        nb::gil_scoped_release release;
        limiter_gain_envelope(input.data(), input.shape(0), input_gain, ceiling_lin, alpha_rel,
                              lookahead, gain.data(), audio.data());
    }
    nb::dict output;
    output["gain"] = make_output(gain);
    output["audio"] = make_output(audio);
    return output;
}

DoubleOutput biquad(DoubleMatrixInput sos, DoubleInput input)
{
    if (sos.ndim() != 2 || sos.shape(1) != 6)
        throw nb::value_error("sos must have shape (sections, 6)");
    require_nonempty(input, "input");
    std::vector<double> output(input.shape(0));
    {
        nb::gil_scoped_release release;
        biquad_sos_filter(sos.data(), sos.shape(0), input.data(), input.shape(0), output.data());
    }
    return make_output(output);
}

nb::dict correlation(DoubleInput left, DoubleInput right, int max_lag)
{
    require_nonempty(left, "left");
    require_nonempty(right, "right");
    if (left.shape(0) != right.shape(0))
        throw nb::value_error("left and right must have equal lengths");
    if (max_lag < 1)
        throw nb::value_error("max_lag must be positive");
    double value = 0.0;
    int lag = 0;
    {
        nb::gil_scoped_release release;
        direct_cross_correlation(left.data(), right.data(), left.shape(0), max_lag, &value, &lag);
    }
    nb::dict output;
    output["correlation"] = value;
    output["lag"] = lag;
    return output;
}

DoubleOutput smooth(DoubleInput values, double alpha_att, double alpha_rel, double init, bool attack_when_less)
{
    require_nonempty(values, "values");
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
    require_nonempty(levels, "levels");
    if (hold_samples < 0)
        throw nb::value_error("hold_samples must be non-negative");
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
    require_nonempty(flux, "flux");
    if (radius < 0)
        throw nb::value_error("radius must be non-negative");
    std::vector<double> output(flux.shape(0));
    {
        nb::gil_scoped_release release;
        rolling_median_mad_threshold(flux.data(), flux.shape(0), radius, min_floor, mad_multiplier, output.data());
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
