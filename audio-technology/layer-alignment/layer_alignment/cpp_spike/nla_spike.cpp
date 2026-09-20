// NITE DSP layer-alignment R&D — C++ proof spike
//
// Isolated numerical validation of the core alignment kernels:
//   - time-domain normalised cross-correlation (energy-normalised)
//   - GCC-PHAT (soft-whitened variant, gamma configurable)
//   - parabolic fractional refinement
//
// No JUCE, no external dependencies. Reads two raw float32 files and a
// config line from stdin/argv; prints one CSV result line.
//
// Build:  clang++ -O2 -std=c++17 nla_spike.cpp -o nla_spike
// Usage:  ./nla_spike ref.f32 test.f32 n_samples max_lag gamma
// Out:    offset_xcorr,peak_xcorr,offset_gcc,peak_gcc,ambiguity_ratio

#include <cmath>
#include <complex>
#include <cstdio>
#include <cstdlib>
#include <cstring>
#include <fstream>
#include <vector>

using cd = std::complex<double>;

// ---------------------------------------------------------------- FFT
static void fft(std::vector<cd>& a, bool invert) {
    const size_t n = a.size();
    if (n <= 1) return;
    for (size_t i = 1, j = 0; i < n; i++) {          // bit reversal
        size_t bit = n >> 1;
        for (; j & bit; bit >>= 1) j ^= bit;
        j ^= bit;
        if (i < j) std::swap(a[i], a[j]);
    }
    for (size_t len = 2; len <= n; len <<= 1) {
        double ang = 2 * M_PI / double(len) * (invert ? 1 : -1);
        cd wl(std::cos(ang), std::sin(ang));
        for (size_t i = 0; i < n; i += len) {
            cd w(1);
            for (size_t j = 0; j < len / 2; j++) {
                cd u = a[i + j], v = a[i + j + len / 2] * w;
                a[i + j] = u + v;
                a[i + j + len / 2] = u - v;
                w *= wl;
            }
        }
    }
    if (invert)
        for (auto& x : a) x /= double(n);
}

static std::vector<cd> rfft(const std::vector<double>& x, size_t nfft) {
    std::vector<cd> a(nfft, cd(0));
    for (size_t i = 0; i < x.size() && i < nfft; i++) a[i] = x[i];
    fft(a, false);
    return a;
}

// ------------------------------------------------------- helpers

static double parabolic(const std::vector<double>& v, int k) {
    if (k <= 0 || k >= (int)v.size() - 1) return 0.0;
    double y0 = v[k - 1], y1 = v[k], y2 = v[k + 1];
    double den = y0 - 2 * y1 + y2;
    if (std::fabs(den) < 1e-12) return 0.0;
    double d = 0.5 * (y0 - y2) / den;
    if (d > 1) d = 1;
    if (d < -1) d = -1;
    return d;
}

struct Result {
    double offset, peak, ambiguity;
};

// plain energy-normalised cross-correlation over |lag| <= max_lag
// convention: positive offset <=> B lags A
static Result xcorr_norm(const std::vector<double>& a,
                         const std::vector<double>& b, int max_lag) {
    const int na = (int)a.size(), nb = (int)b.size();
    // remove DC
    std::vector<double> x(a), y(b);
    auto dc = [](std::vector<double>& v) {
        double m = 0;
        for (double q : v) m += q;
        m /= v.size();
        for (double& q : v) q -= m;
    };
    dc(x);
    dc(y);
    std::vector<double> cx(na + 1, 0.0), cy(nb + 1, 0.0);
    for (int i = 0; i < na; i++) cx[i + 1] = cx[i] + x[i] * x[i];
    for (int i = 0; i < nb; i++) cy[i + 1] = cy[i] + y[i] * y[i];

    int nlag = 2 * max_lag + 1;
    std::vector<double> vals(nlag);
    for (int li = 0; li < nlag; li++) {
        int d = li - max_lag;                       // b advanced by d
        int lo = std::max(0, -d), hi = std::min(na, nb - d);
        if (hi - lo < 16) { vals[li] = 0; continue; }
        double ea = cx[hi] - cx[lo];
        double eb = cy[hi + d] - cy[lo + d];
        if (ea < 1e-18 || eb < 1e-18) { vals[li] = 0; continue; }
        double s = 0;
        for (int n = lo; n < hi; n++) s += x[n] * y[n + d];   // NOTE sign below
        vals[li] = s / std::sqrt(ea * eb);
    }
    int k = 0;
    for (int i = 1; i < nlag; i++)
        if (std::fabs(vals[i]) > std::fabs(vals[k])) k = i;
    double frac = parabolic(vals, k);
    double off = double(k - max_lag) + frac;
    // ambiguity: strongest distinct local maximum outside mainlobe
    double g = std::fabs(vals[k]);
    int left = k, right = k;
    while (left > 0 && std::fabs(vals[left]) > g / std::sqrt(2.0)) left--;
    while (right < nlag - 1 && std::fabs(vals[right]) > g / std::sqrt(2.0))
        right++;
    int minsep = 3 * std::max(right - k, k - left);
    if (minsep < 12) minsep = 12;
    double sec = 0.0;
    for (int i = 1; i < nlag - 1; i++) {
        double av = std::fabs(vals[i]);
        if (av >= std::fabs(vals[i - 1]) && av >= std::fabs(vals[i + 1]) &&
            std::abs((i - max_lag) - (k - max_lag)) >= minsep &&
            av > sec)
            sec = av;
    }
    return {off, vals[k], g > 0 ? sec / g : 0.0};
}

// soft-PHAT generalised cross-correlation via FFT
static Result gcc_soft(const std::vector<double>& a,
                       const std::vector<double>& b, int max_lag,
                       double gamma) {
    const int na = (int)a.size(), nb = (int)b.size();
    size_t nfft = 1;
    while (nfft < (size_t)(na + nb - 1)) nfft <<= 1;
    std::vector<cd> A = rfft(a, nfft), B = rfft(b, nfft);
    std::vector<cd> R(nfft);
    for (size_t i = 0; i < nfft; i++) {
        cd r = A[i] * std::conj(B[i]);
        double m = std::abs(r) + 1e-12;
        R[i] = r * std::pow(m, -gamma);
    }
    fft(R, true);                                    // circular correlation
    int nlag = 2 * max_lag + 1;
    std::vector<double> vals(nlag);
    for (int li = 0; li < nlag; li++) {
        int lag = li - max_lag;                      // positive => B lags A
        // python reference gathers cc[j] with j = -lag (scipy j-axis),
        // wrapping negative j into nfft+j
        long long j = -(long long)lag;
        if (j < 0) j += (long long)nfft;
        vals[li] = R[(size_t)j].real();
    }
    int k = 0;
    for (int i = 1; i < nlag; i++)
        if (std::fabs(vals[i]) > std::fabs(vals[k])) k = i;
    double frac = parabolic(vals, k);
    return {double(k - max_lag) + frac, vals[k],
            0.0};  // ambiguity computed on xcorr profile by caller
}

int main(int argc, char** argv) {
    if (argc < 6) {
        fprintf(stderr,
                "usage: %s ref.f32 test.f32 n max_lag gamma [reps]\n",
                argv[0]);
        return 2;
    }
    int n = atoi(argv[3]);
    int max_lag = atoi(argv[4]);
    double gamma = atof(argv[5]);
    int reps = argc > 6 ? atoi(argv[6]) : 1;

    std::vector<double> a(n), b(n);
    {
        std::ifstream fa(argv[1], std::ios::binary);
        std::ifstream fb(argv[2], std::ios::binary);
        if (!fa || !fb) { fprintf(stderr, "open failed\n"); return 2; }
        float tmp;
        for (int i = 0; i < n && fa.read((char*)&tmp, 4); i++) a[i] = tmp;
        for (int i = 0; i < n && fb.read((char*)&tmp, 4); i++) b[i] = tmp;
    }

    Result rx{}, rg{};
    for (int rep = 0; rep < reps; rep++) {
        rx = xcorr_norm(a, b, max_lag);
        rg = gcc_soft(a, b, max_lag, gamma);
    }

    printf("%.6f,%.8f,%.6f,%.8f,%.6f\n", rx.offset, rx.peak, rg.offset,
           rg.peak, rx.ambiguity);
    return 0;
}
