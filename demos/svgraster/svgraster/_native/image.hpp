// Shared helpers for the C++ layers: premultiplied RGBA views and OpenMP shims.
#pragma once

#include <algorithm>
#include <cmath>
#include <cstddef>

#ifdef _OPENMP
#include <omp.h>
#define SVGR_HAVE_OPENMP 1
#else
#define SVGR_HAVE_OPENMP 0
#endif

namespace svgr {

constexpr int kChannels = 4;
constexpr double kPixelCenter = 0.5;

inline void set_threads(int n) {
#ifdef _OPENMP
    if (n > 0) omp_set_num_threads(n);
#else
    (void)n;
#endif
}

struct Image {
    float* data;
    int height;
    int width;

    float* px(int y, int x) const { return data + (static_cast<std::size_t>(y) * width + x) * kChannels; }
    std::size_t size() const { return static_cast<std::size_t>(height) * width * kChannels; }
};

struct ConstImage {
    const float* data;
    int height;
    int width;

    const float* px(int y, int x) const { return data + (static_cast<std::size_t>(y) * width + x) * kChannels; }
};

inline double clamp01(double v) { return v < 0.0 ? 0.0 : (v > 1.0 ? 1.0 : v); }

inline void straight(const float* p, double out[kChannels]) {
    double a = p[3];
    for (int c = 0; c < 3; ++c) out[c] = a > 0 ? p[c] / a : 0.0;
    out[3] = a;
}

inline void store_premultiplied(float* dst, const double rgba[kChannels]) {
    double a = clamp01(rgba[3]);
    for (int c = 0; c < 3; ++c) dst[c] = static_cast<float>(clamp01(rgba[c]) * a);
    dst[3] = static_cast<float>(a);
}

}  // namespace svgr
