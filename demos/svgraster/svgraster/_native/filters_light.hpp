// feTurbulence (the SVG reference noise), feDisplacementMap and the lighting filters.
#pragma once

#include <array>
#include <cmath>
#include <limits>
#include <vector>

#include "image.hpp"

namespace svgr {

constexpr int kBSize = 0x100;
constexpr int kBMask = 0xff;
constexpr int kPerlinN = 0x1000;
constexpr long kRandM = 2147483647;
constexpr long kRandA = 16807;
constexpr long kRandQ = 127773;
constexpr long kRandR = 2836;
constexpr double kSobelScale = 0.25;
constexpr double kRadians = 3.14159265358979323846 / 180.0;

enum class LightType { Distant = 0, Point = 1, Spot = 2 };
enum class Channel { R = 0, G = 1, B = 2, A = 3 };

struct Lattice {
    int selector[kBSize + kBSize + 2];
    double gradient[kChannels][kBSize + kBSize + 2][2];

    static long setup_seed(long seed) {
        if (seed <= 0) seed = -(seed % (kRandM - 1)) + 1;
        if (seed > kRandM - 1) seed = kRandM - 1;
        return seed;
    }

    static long random(long seed) {
        long result = kRandA * (seed % kRandQ) - kRandR * (seed / kRandQ);
        if (result <= 0) result += kRandM;
        return result;
    }

    explicit Lattice(long seed) {
        seed = setup_seed(seed);
        int i = 0, j, k;
        for (k = 0; k < kChannels; ++k) {
            for (i = 0; i < kBSize; ++i) {
                selector[i] = i;
                for (j = 0; j < 2; ++j) {
                    seed = random(seed);
                    gradient[k][i][j] = static_cast<double>((seed % (kBSize + kBSize)) - kBSize) / kBSize;
                }
                double s = std::sqrt(gradient[k][i][0] * gradient[k][i][0] + gradient[k][i][1] * gradient[k][i][1]);
                gradient[k][i][0] /= s;
                gradient[k][i][1] /= s;
            }
        }
        while (--i) {
            k = selector[i];
            seed = random(seed);
            j = static_cast<int>(seed % kBSize);
            selector[i] = selector[j];
            selector[j] = k;
        }
        for (i = 0; i < kBSize + 2; ++i) {
            selector[kBSize + i] = selector[i];
            for (k = 0; k < kChannels; ++k)
                for (j = 0; j < 2; ++j) gradient[k][kBSize + i][j] = gradient[k][i][j];
        }
    }

    double noise2(int channel, double vx, double vy, const long* stitch) const {
        double t = vx + kPerlinN;
        int bx0 = static_cast<int>(t) & kBMask, bx1 = (bx0 + 1) & kBMask;
        double rx0 = t - static_cast<int>(t), rx1 = rx0 - 1.0;
        t = vy + kPerlinN;
        int by0 = static_cast<int>(t) & kBMask, by1 = (by0 + 1) & kBMask;
        double ry0 = t - static_cast<int>(t), ry1 = ry0 - 1.0;
        if (stitch) {
            if (bx0 >= stitch[2]) bx0 -= static_cast<int>(stitch[0]);
            if (bx1 >= stitch[2]) bx1 -= static_cast<int>(stitch[0]);
            if (by0 >= stitch[3]) by0 -= static_cast<int>(stitch[1]);
            if (by1 >= stitch[3]) by1 -= static_cast<int>(stitch[1]);
        }
        bx0 &= kBMask; bx1 &= kBMask; by0 &= kBMask; by1 &= kBMask;
        int i = selector[bx0], j = selector[bx1];
        int b00 = selector[i + by0], b10 = selector[j + by0], b01 = selector[i + by1], b11 = selector[j + by1];
        double sx = rx0 * rx0 * (3.0 - 2.0 * rx0), sy = ry0 * ry0 * (3.0 - 2.0 * ry0);
        const double (*g)[2] = gradient[channel];
        double u = rx0 * g[b00][0] + ry0 * g[b00][1];
        double v = rx1 * g[b10][0] + ry0 * g[b10][1];
        double a = u + sx * (v - u);
        u = rx0 * g[b01][0] + ry1 * g[b01][1];
        v = rx1 * g[b11][0] + ry1 * g[b11][1];
        double b = u + sx * (v - u);
        return a + sy * (b - a);
    }
};

inline double stitch_frequency(double freq, double size) {
    if (freq == 0.0 || size <= 0) return freq;
    double lo = std::floor(size * freq) / size, hi = std::ceil(size * freq) / size;
    return (lo > 0 && freq / lo < hi / freq) ? lo : hi;
}

inline void turbulence(Image dst, const double inv[6], double fx, double fy, int octaves, long seed, bool stitch,
                       bool fractal, const double tile[4]) {
    Lattice lattice(seed);
    long info[4] = {0, 0, 0, 0};
    if (stitch) {
        fx = stitch_frequency(fx, tile[2]);
        fy = stitch_frequency(fy, tile[3]);
        info[0] = static_cast<long>(tile[2] * fx + 0.5);
        info[1] = static_cast<long>(tile[3] * fy + 0.5);
        info[2] = static_cast<long>(tile[0] * fx + kPerlinN + info[0]);
        info[3] = static_cast<long>(tile[1] * fy + kPerlinN + info[1]);
    }
#pragma omp parallel for schedule(static)
    for (int y = 0; y < dst.height; ++y) {
        for (int x = 0; x < dst.width; ++x) {
            double px = x + kPixelCenter, py = y + kPixelCenter;
            double ux = inv[0] * px + inv[1] * py + inv[2];
            double uy = inv[3] * px + inv[4] * py + inv[5];
            double rgba[kChannels];
            for (int ch = 0; ch < kChannels; ++ch) {
                long st[4] = {info[0], info[1], info[2], info[3]};
                double vx = ux * fx, vy = uy * fy, ratio = 1.0, total = 0.0;
                for (int o = 0; o < octaves; ++o) {
                    double n = lattice.noise2(ch, vx, vy, stitch ? st : nullptr);
                    total += (fractal ? n : std::abs(n)) / ratio;
                    vx *= 2;
                    vy *= 2;
                    ratio *= 2;
                    if (stitch) {
                        st[0] *= 2;
                        st[2] = 2 * st[2] - kPerlinN;
                        st[1] *= 2;
                        st[3] = 2 * st[3] - kPerlinN;
                    }
                }
                rgba[ch] = fractal ? (total + 1.0) / 2.0 : total;
            }
            store_premultiplied(dst.px(y, x), rgba);
        }
    }
}

inline void displacement_map(ConstImage src, ConstImage map, Image dst, double scale, Channel xc, Channel yc) {
#pragma omp parallel for schedule(static)
    for (int y = 0; y < dst.height; ++y) {
        for (int x = 0; x < dst.width; ++x) {
            double m[kChannels];
            straight(map.px(y, x), m);
            int sx = static_cast<int>(std::floor(x + scale * (m[static_cast<int>(xc)] - kPixelCenter) + kPixelCenter));
            int sy = static_cast<int>(std::floor(y + scale * (m[static_cast<int>(yc)] - kPixelCenter) + kPixelCenter));
            bool inside = sx >= 0 && sx < src.width && sy >= 0 && sy < src.height;
            float* d = dst.px(y, x);
            for (int c = 0; c < kChannels; ++c) d[c] = inside ? src.px(sy, sx)[c] : 0.0f;
        }
    }
}

struct LightSource {
    LightType kind = LightType::Distant;
    double azimuth = 0.0, elevation = 0.0;
    std::array<double, 3> position{0.0, 0.0, 0.0};
    std::array<double, 3> points_at{0.0, 0.0, 0.0};
    double specular_exponent = 1.0;
    double limiting_cone_angle = std::numeric_limits<double>::quiet_NaN();

    void vector_at(double x, double y, double z, const double color[3], double l[3], double lc[3]) const {
        if (kind == LightType::Distant) {
            double az = azimuth * kRadians, el = elevation * kRadians;
            l[0] = std::cos(az) * std::cos(el);
            l[1] = std::sin(az) * std::cos(el);
            l[2] = std::sin(el);
            for (int c = 0; c < 3; ++c) lc[c] = color[c];
            return;
        }
        l[0] = position[0] - (x + kPixelCenter);
        l[1] = position[1] - (y + kPixelCenter);
        l[2] = position[2] - z;
        double norm = std::sqrt(l[0] * l[0] + l[1] * l[1] + l[2] * l[2]);
        if (norm <= 0) norm = 1.0;
        for (int c = 0; c < 3; ++c) l[c] /= norm;
        if (kind == LightType::Point) {
            for (int c = 0; c < 3; ++c) lc[c] = color[c];
            return;
        }
        double s[3] = {points_at[0] - position[0], points_at[1] - position[1], points_at[2] - position[2]};
        double sn = std::sqrt(s[0] * s[0] + s[1] * s[1] + s[2] * s[2]);
        if (sn == 0) sn = 1.0;
        double minus_ls = -(l[0] * s[0] / sn + l[1] * s[1] / sn + l[2] * s[2] / sn);
        double factor = std::pow(std::max(minus_ls, 0.0), specular_exponent);
        if (!std::isnan(limiting_cone_angle) && minus_ls < std::cos(std::abs(limiting_cone_angle) * kRadians))
            factor = 0.0;
        for (int c = 0; c < 3; ++c) lc[c] = color[c] * factor;
    }
};

inline void surface_normal(ConstImage src, int x, int y, double surface_scale, double n[3]) {
    auto a = [&](int dx, int dy) {
        int sx = std::min(std::max(x + dx, 0), src.width - 1);
        int sy = std::min(std::max(y + dy, 0), src.height - 1);
        return static_cast<double>(src.px(sy, sx)[3]);
    };
    double nx = -surface_scale * kSobelScale *
                ((a(1, -1) + 2 * a(1, 0) + a(1, 1)) - (a(-1, -1) + 2 * a(-1, 0) + a(-1, 1)));
    double ny = -surface_scale * kSobelScale *
                ((a(-1, 1) + 2 * a(0, 1) + a(1, 1)) - (a(-1, -1) + 2 * a(0, -1) + a(1, -1)));
    double norm = std::sqrt(nx * nx + ny * ny + 1.0);
    n[0] = nx / norm;
    n[1] = ny / norm;
    n[2] = 1.0 / norm;
}

inline void lighting(ConstImage src, Image dst, double surface_scale, double constant, double exponent,
                     const LightSource& light, const double color[3], bool specular) {
#pragma omp parallel for schedule(static)
    for (int y = 0; y < dst.height; ++y) {
        for (int x = 0; x < dst.width; ++x) {
            double n[3], l[3], lc[3];
            surface_normal(src, x, y, surface_scale, n);
            light.vector_at(x, y, surface_scale * src.px(y, x)[3], color, l, lc);
            float* d = dst.px(y, x);
            if (!specular) {
                double ndotl = std::max(n[0] * l[0] + n[1] * l[1] + n[2] * l[2], 0.0);
                for (int c = 0; c < 3; ++c) d[c] = static_cast<float>(clamp01(constant * ndotl * lc[c]));
                d[3] = 1.0f;
                continue;
            }
            double h[3] = {l[0], l[1], l[2] + 1.0};
            double hn = std::sqrt(h[0] * h[0] + h[1] * h[1] + h[2] * h[2]);
            if (hn <= 0) hn = 1.0;
            double ndoth = std::max((n[0] * h[0] + n[1] * h[1] + n[2] * h[2]) / hn, 0.0);
            double p = std::pow(ndoth, exponent), hi = 0.0;
            for (int c = 0; c < 3; ++c) {
                double v = clamp01(constant * p * lc[c]);
                d[c] = static_cast<float>(v);
                hi = std::max(hi, v);
            }
            d[3] = static_cast<float>(hi);
        }
    }
}

}  // namespace svgr
