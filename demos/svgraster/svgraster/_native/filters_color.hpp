// feBlend, feComposite, feColorMatrix and feComponentTransfer kernels.
#pragma once

#include <array>
#include <cmath>
#include <vector>

#include "image.hpp"

namespace svgr {

enum class BlendMode {
    Normal = 0, Multiply, Screen, Darken, Lighten, Overlay, ColorDodge, ColorBurn,
    HardLight, SoftLight, Difference, Exclusion, Hue, Saturation, Color, Luminosity
};
enum class CompositeOperator { Over = 0, In, Out, Atop, Xor, Arithmetic, Lighter };
enum class ColorMatrixType { Matrix = 0, Saturate, HueRotate, LuminanceToAlpha };
enum class TransferType { Identity = 0, Table, Discrete, Linear, Gamma };

constexpr double kLumR = 0.3, kLumG = 0.59, kLumB = 0.11;
constexpr double kHalf = 0.5, kQuarter = 0.25;
constexpr double kPi = 3.14159265358979323846;
constexpr double kDegrees = 180.0;
constexpr int kMatrixRows = 4, kMatrixCols = 5;
constexpr double kLumCoeffs[3] = {0.213, 0.715, 0.072};
constexpr double kL2ACoeffs[3] = {0.2125, 0.7154, 0.0721};
constexpr double kSatDiag[3] = {0.787, 0.285, 0.928};
constexpr double kHueCos[3][3] = {{0.787, -0.715, -0.072}, {-0.213, 0.285, -0.072}, {-0.213, -0.715, 0.928}};
constexpr double kHueSin[3][3] = {{-0.213, -0.715, 0.928}, {0.143, 0.140, -0.283}, {-0.787, 0.715, 0.072}};

using Rgb = std::array<double, 3>;

inline double lum(const Rgb& c) { return kLumR * c[0] + kLumG * c[1] + kLumB * c[2]; }

inline Rgb clip_color(Rgb c) {
    double l = lum(c);
    double lo = std::min({c[0], c[1], c[2]}), hi = std::max({c[0], c[1], c[2]});
    if (lo < 0) for (double& v : c) v = l + (v - l) * l / (l - lo);
    if (hi > 1) for (double& v : c) v = l + (v - l) * (1 - l) / (hi - l);
    return c;
}

inline Rgb set_lum(Rgb c, double l) {
    double d = l - lum(c);
    for (double& v : c) v += d;
    return clip_color(c);
}

inline double sat(const Rgb& c) { return std::max({c[0], c[1], c[2]}) - std::min({c[0], c[1], c[2]}); }

inline Rgb set_sat(Rgb c, double s) {
    double lo = std::min({c[0], c[1], c[2]}), range = sat(c);
    for (double& v : c) v = range > 0 ? (v - lo) * s / range : 0.0;
    return c;
}

inline double hard_light(double cb, double cs) {
    return cs <= kHalf ? cb * 2 * cs : cb + (2 * cs - 1) - cb * (2 * cs - 1);
}

inline double separable(BlendMode mode, double cb, double cs) {
    switch (mode) {
        case BlendMode::Multiply: return cb * cs;
        case BlendMode::Screen: return cb + cs - cb * cs;
        case BlendMode::Darken: return std::min(cb, cs);
        case BlendMode::Lighten: return std::max(cb, cs);
        case BlendMode::Overlay: return hard_light(cs, cb);
        case BlendMode::ColorDodge: return cb == 0 ? 0.0 : (cs >= 1 ? 1.0 : std::min(1.0, cb / (1 - cs)));
        case BlendMode::ColorBurn: return cb >= 1 ? 1.0 : (cs <= 0 ? 0.0 : 1 - std::min(1.0, (1 - cb) / cs));
        case BlendMode::HardLight: return hard_light(cb, cs);
        case BlendMode::SoftLight: {
            double d = cb <= kQuarter ? ((16 * cb - 12) * cb + 4) * cb : std::sqrt(cb);
            return cs <= kHalf ? cb - (1 - 2 * cs) * cb * (1 - cb) : cb + (2 * cs - 1) * (d - cb);
        }
        case BlendMode::Difference: return std::abs(cb - cs);
        case BlendMode::Exclusion: return cb + cs - 2 * cb * cs;
        default: return cs;
    }
}

inline Rgb blend_function(BlendMode mode, const Rgb& cb, const Rgb& cs) {
    switch (mode) {
        case BlendMode::Hue: return set_lum(set_sat(cs, sat(cb)), lum(cb));
        case BlendMode::Saturation: return set_lum(set_sat(cb, sat(cs)), lum(cb));
        case BlendMode::Color: return set_lum(cs, lum(cb));
        case BlendMode::Luminosity: return set_lum(cb, lum(cs));
        default: return {separable(mode, cb[0], cs[0]), separable(mode, cb[1], cs[1]), separable(mode, cb[2], cs[2])};
    }
}

inline void blend(ConstImage src, ConstImage backdrop, Image dst, BlendMode mode) {
    const int n = src.height * src.width;
#pragma omp parallel for schedule(static)
    for (int i = 0; i < n; ++i) {
        const float* s = src.data + static_cast<std::size_t>(i) * kChannels;
        const float* b = backdrop.data + static_cast<std::size_t>(i) * kChannels;
        double ss[kChannels], bb[kChannels];
        straight(s, ss);
        straight(b, bb);
        Rgb mixed = blend_function(mode, {bb[0], bb[1], bb[2]}, {ss[0], ss[1], ss[2]});
        double as = ss[3], ab = bb[3];
        float* d = dst.data + static_cast<std::size_t>(i) * kChannels;
        for (int c = 0; c < 3; ++c)
            d[c] = static_cast<float>(clamp01((1 - ab) * s[c] + (1 - as) * b[c] + as * ab * mixed[c]));
        d[3] = static_cast<float>(clamp01(as + ab - as * ab));
    }
}

inline void composite(ConstImage a, ConstImage b, Image dst, CompositeOperator op, double k1, double k2, double k3,
                      double k4) {
    const int n = a.height * a.width;
#pragma omp parallel for schedule(static)
    for (int i = 0; i < n; ++i) {
        const float* pa = a.data + static_cast<std::size_t>(i) * kChannels;
        const float* pb = b.data + static_cast<std::size_t>(i) * kChannels;
        float* d = dst.data + static_cast<std::size_t>(i) * kChannels;
        double aa = pa[3], ab = pb[3], out[kChannels];
        for (int c = 0; c < kChannels; ++c) {
            double x = pa[c], y = pb[c];
            switch (op) {
                case CompositeOperator::In: out[c] = x * ab; break;
                case CompositeOperator::Out: out[c] = x * (1 - ab); break;
                case CompositeOperator::Atop: out[c] = x * ab + y * (1 - aa); break;
                case CompositeOperator::Xor: out[c] = x * (1 - ab) + y * (1 - aa); break;
                case CompositeOperator::Lighter: out[c] = std::min(x + y, 1.0); break;
                case CompositeOperator::Arithmetic: out[c] = clamp01(k1 * x * y + k2 * x + k3 * y + k4); break;
                default: out[c] = x + y * (1 - aa); break;
            }
        }
        if (op == CompositeOperator::Arithmetic)
            for (int c = 0; c < 3; ++c) out[c] = std::min(out[c], out[3]);
        for (int c = 0; c < kChannels; ++c) d[c] = static_cast<float>(out[c]);
    }
}

using ColorMatrix = std::array<std::array<double, kMatrixCols>, kMatrixRows>;

inline ColorMatrix color_matrix_values(ColorMatrixType kind, const std::vector<double>& values) {
    ColorMatrix m{};
    for (int i = 0; i < kMatrixRows; ++i) m[i][i] = 1.0;
    if (kind == ColorMatrixType::Matrix) {
        if (values.size() == kMatrixRows * kMatrixCols)
            for (int i = 0; i < kMatrixRows; ++i)
                for (int j = 0; j < kMatrixCols; ++j) m[i][j] = values[i * kMatrixCols + j];
    } else if (kind == ColorMatrixType::Saturate) {
        double s = values.empty() ? 1.0 : values[0];
        for (int i = 0; i < 3; ++i)
            for (int j = 0; j < 3; ++j) m[i][j] = kLumCoeffs[j] + (i == j ? kSatDiag[i] : -kLumCoeffs[j]) * s;
    } else if (kind == ColorMatrixType::HueRotate) {
        double rad = (values.empty() ? 0.0 : values[0]) * kPi / kDegrees;
        double cs = std::cos(rad), sn = std::sin(rad);
        for (int i = 0; i < 3; ++i)
            for (int j = 0; j < 3; ++j) m[i][j] = kLumCoeffs[j] + cs * kHueCos[i][j] + sn * kHueSin[i][j];
    } else {
        m = ColorMatrix{};
        for (int j = 0; j < 3; ++j) m[3][j] = kL2ACoeffs[j];
    }
    return m;
}

inline void color_matrix(ConstImage src, Image dst, const ColorMatrix& m) {
    const int n = src.height * src.width;
#pragma omp parallel for schedule(static)
    for (int i = 0; i < n; ++i) {
        double in[kChannels], out[kChannels];
        straight(src.data + static_cast<std::size_t>(i) * kChannels, in);
        for (int r = 0; r < kMatrixRows; ++r) {
            double acc = 0.0;
            for (int c = 0; c < kChannels; ++c) acc += in[c] * m[r][c];
            out[r] = acc + m[r][kChannels];
        }
        store_premultiplied(dst.data + static_cast<std::size_t>(i) * kChannels, out);
    }
}

struct TransferFunction {
    TransferType kind = TransferType::Identity;
    std::vector<double> values;
    double slope = 1.0, intercept = 0.0;
    double amplitude = 1.0, exponent = 1.0, offset = 0.0;

    double operator()(double c) const {
        std::size_t n = values.size();
        if (kind == TransferType::Table && n) {
            if (n == 1) return values[0];
            if (c >= 1.0) return values[n - 1];
            long k = static_cast<long>(std::floor(c * (n - 1)));
            k = std::max(0L, std::min(k, static_cast<long>(n) - 2));
            return values[k] + (c * (n - 1) - k) * (values[k + 1] - values[k]);
        }
        if (kind == TransferType::Discrete && n) {
            long k = static_cast<long>(std::floor(c * n));
            k = std::max(0L, std::min(k, static_cast<long>(n) - 1));
            return values[k];
        }
        if (kind == TransferType::Linear) return slope * c + intercept;
        if (kind == TransferType::Gamma) return amplitude * std::pow(c, exponent) + offset;
        return c;
    }
};

inline void component_transfer(ConstImage src, Image dst, const TransferFunction* funcs[kChannels]) {
    const int n = src.height * src.width;
#pragma omp parallel for schedule(static)
    for (int i = 0; i < n; ++i) {
        double in[kChannels], out[kChannels];
        straight(src.data + static_cast<std::size_t>(i) * kChannels, in);
        for (int c = 0; c < kChannels; ++c) out[c] = (*funcs[c])(in[c]);
        store_premultiplied(dst.data + static_cast<std::size_t>(i) * kChannels, out);
    }
}

}  // namespace svgr
