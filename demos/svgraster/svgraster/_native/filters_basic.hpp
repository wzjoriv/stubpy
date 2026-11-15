// feGaussianBlur, feOffset, feFlood, feTile, feMerge, feMorphology and feConvolveMatrix kernels.
#pragma once

#include <cmath>
#include <limits>
#include <vector>

#include "image.hpp"

namespace svgr {

constexpr double kKernelSigmas = 3.0;

enum class EdgeMode { Duplicate = 0, Wrap = 1, None = 2 };
enum class MorphologyOperator { Erode = 0, Dilate = 1 };

inline std::vector<double> gaussian_kernel(double sigma) {
    int radius = static_cast<int>(std::ceil(kKernelSigmas * sigma));
    std::vector<double> k(2 * radius + 1);
    double sum = 0.0;
    for (int i = -radius; i <= radius; ++i) {
        k[i + radius] = std::exp(-(static_cast<double>(i) * i) / (2.0 * sigma * sigma));
        sum += k[i + radius];
    }
    for (double& v : k) v /= sum;
    return k;
}

inline void blur_axis(std::vector<double>& buf, int h, int w, double sigma, bool horizontal) {
    if (sigma <= 0) return;
    std::vector<double> k = gaussian_kernel(sigma);
    int radius = static_cast<int>(k.size() / 2);
    std::vector<double> out(buf.size(), 0.0);
#pragma omp parallel for schedule(static)
    for (int y = 0; y < h; ++y) {
        for (int x = 0; x < w; ++x) {
            double acc[kChannels] = {0.0, 0.0, 0.0, 0.0};
            for (int i = 0; i < static_cast<int>(k.size()); ++i) {
                int sx = horizontal ? x + i - radius : x;
                int sy = horizontal ? y : y + i - radius;
                if (sx < 0 || sx >= w || sy < 0 || sy >= h) continue;
                const double* s = &buf[(static_cast<std::size_t>(sy) * w + sx) * kChannels];
                for (int c = 0; c < kChannels; ++c) acc[c] += k[i] * s[c];
            }
            double* d = &out[(static_cast<std::size_t>(y) * w + x) * kChannels];
            for (int c = 0; c < kChannels; ++c) d[c] = acc[c];
        }
    }
    buf.swap(out);
}

inline void gaussian_blur(ConstImage src, Image dst, double sx, double sy) {
    std::vector<double> buf(src.data, src.data + static_cast<std::size_t>(src.height) * src.width * kChannels);
    blur_axis(buf, src.height, src.width, sx, true);
    blur_axis(buf, src.height, src.width, sy, false);
    for (std::size_t i = 0; i < buf.size(); ++i) dst.data[i] = static_cast<float>(buf[i]);
}


// Bilinear tap of src at integer (sx, sy) with transparent outside.
inline void add_tap(ConstImage src, int sx, int sy, double weight, double acc[kChannels]) {
    if (weight <= 0 || sx < 0 || sx >= src.width || sy < 0 || sy >= src.height) return;
    const float* s = src.px(sy, sx);
    for (int c = 0; c < kChannels; ++c) acc[c] += weight * s[c];
}

inline void sample_bilinear(ConstImage src, double sx, double sy, double acc[kChannels]) {
    double fx0 = std::floor(sx), fy0 = std::floor(sy);
    double fx = sx - fx0, fy = sy - fy0;
    int x0 = static_cast<int>(fx0), y0 = static_cast<int>(fy0);
    add_tap(src, x0, y0, (1 - fx) * (1 - fy), acc);
    add_tap(src, x0 + 1, y0, fx * (1 - fy), acc);
    add_tap(src, x0, y0 + 1, (1 - fx) * fy, acc);
    add_tap(src, x0 + 1, y0 + 1, fx * fy, acc);
}

inline void offset(ConstImage src, Image dst, double dx, double dy) {
#pragma omp parallel for schedule(static)
    for (int y = 0; y < dst.height; ++y) {
        for (int x = 0; x < dst.width; ++x) {
            double acc[kChannels] = {0.0, 0.0, 0.0, 0.0};
            sample_bilinear(src, x - dx, y - dy, acc);
            float* d = dst.px(y, x);
            for (int c = 0; c < kChannels; ++c) d[c] = static_cast<float>(acc[c]);
        }
    }
}

enum class ResampleFilter { Nearest = 0, Bilinear = 1 };

// Resize src to dst's size; pixel centres map onto each other.
inline void resample(ConstImage src, Image dst, ResampleFilter filter) {
    double kx = static_cast<double>(src.width) / dst.width, ky = static_cast<double>(src.height) / dst.height;
#pragma omp parallel for schedule(static)
    for (int y = 0; y < dst.height; ++y) {
        for (int x = 0; x < dst.width; ++x) {
            double sx = (x + kPixelCenter) * kx, sy = (y + kPixelCenter) * ky;
            float* d = dst.px(y, x);
            if (filter == ResampleFilter::Nearest) {
                int ix = std::min(src.width - 1, static_cast<int>(sx));
                int iy = std::min(src.height - 1, static_cast<int>(sy));
                for (int c = 0; c < kChannels; ++c) d[c] = src.px(iy, ix)[c];
                continue;
            }
            sx = std::min(std::max(sx - kPixelCenter, 0.0), src.width - 1.0);
            sy = std::min(std::max(sy - kPixelCenter, 0.0), src.height - 1.0);
            double acc[kChannels] = {0.0, 0.0, 0.0, 0.0};
            sample_bilinear(src, sx, sy, acc);
            for (int c = 0; c < kChannels; ++c) d[c] = static_cast<float>(acc[c]);
        }
    }
}

inline void flood(Image dst, const double color[kChannels]) {
    for (int y = 0; y < dst.height; ++y)
        for (int x = 0; x < dst.width; ++x)
            for (int c = 0; c < kChannels; ++c) dst.px(y, x)[c] = static_cast<float>(color[c]);
}

inline int positive_mod(int a, int n) { return ((a % n) + n) % n; }

inline void tile(ConstImage src, Image dst, int tx, int ty, int tw, int th) {
#pragma omp parallel for schedule(static)
    for (int y = 0; y < dst.height; ++y) {
        for (int x = 0; x < dst.width; ++x) {
            float* d = dst.px(y, x);
            int sx = tw > 0 ? tx + positive_mod(x - tx, tw) : -1;
            int sy = th > 0 ? ty + positive_mod(y - ty, th) : -1;
            bool inside = sx >= 0 && sx < src.width && sy >= 0 && sy < src.height;
            for (int c = 0; c < kChannels; ++c) d[c] = inside ? src.px(sy, sx)[c] : 0.0f;
        }
    }
}

inline void merge_over(Image dst, ConstImage layer) {
    for (std::size_t i = 0; i < static_cast<std::size_t>(dst.height) * dst.width; ++i) {
        const float* s = layer.data + i * kChannels;
        float* d = dst.data + i * kChannels;
        float inv = 1.0f - s[3];
        for (int c = 0; c < kChannels; ++c) d[c] = s[c] + d[c] * inv;
    }
}

inline void morph_axis(std::vector<float>& buf, int h, int w, int radius, bool horizontal, bool erode) {
    if (radius <= 0) return;
    std::vector<float> out(buf.size());
#pragma omp parallel for schedule(static)
    for (int y = 0; y < h; ++y) {
        for (int x = 0; x < w; ++x) {
            for (int c = 0; c < kChannels; ++c) {
                float best = erode ? std::numeric_limits<float>::infinity() : -std::numeric_limits<float>::infinity();
                for (int i = -radius; i <= radius; ++i) {
                    int sx = horizontal ? x + i : x;
                    int sy = horizontal ? y : y + i;
                    if (sx < 0 || sx >= w || sy < 0 || sy >= h) continue;
                    float v = buf[(static_cast<std::size_t>(sy) * w + sx) * kChannels + c];
                    best = erode ? std::min(best, v) : std::max(best, v);
                }
                out[(static_cast<std::size_t>(y) * w + x) * kChannels + c] = best;
            }
        }
    }
    buf.swap(out);
}

inline void morphology(ConstImage src, Image dst, int rx, int ry, MorphologyOperator op) {
    std::vector<float> buf(src.data, src.data + static_cast<std::size_t>(src.height) * src.width * kChannels);
    bool erode = op == MorphologyOperator::Erode;
    if (rx > 0 || ry > 0) {
        morph_axis(buf, src.height, src.width, rx, true, erode);
        morph_axis(buf, src.height, src.width, ry, false, erode);
    }
    std::copy(buf.begin(), buf.end(), dst.data);
}

inline bool edge_index(int idx, int n, EdgeMode mode, int& out) {
    if (mode == EdgeMode::Wrap) {
        out = positive_mod(idx, n);
        return true;
    }
    out = idx < 0 ? 0 : (idx >= n ? n - 1 : idx);
    return mode == EdgeMode::Duplicate || (idx >= 0 && idx < n);
}

inline void convolve(ConstImage src, Image dst, const double* kernel, int ox, int oy, double divisor, double bias,
                     int tx, int ty, EdgeMode mode, bool preserve_alpha) {
    int h = src.height, w = src.width;
    if (tx < 0) tx = ox / 2;
    if (ty < 0) ty = oy / 2;
    if (divisor == 0) divisor = 1.0;
    std::vector<double> in(static_cast<std::size_t>(h) * w * kChannels);
    for (std::size_t i = 0; i < static_cast<std::size_t>(h) * w; ++i) {
        if (preserve_alpha) {
            straight(src.data + i * kChannels, &in[i * kChannels]);
        } else {
            for (int c = 0; c < kChannels; ++c) in[i * kChannels + c] = src.data[i * kChannels + c];
        }
    }
#pragma omp parallel for schedule(static)
    for (int y = 0; y < h; ++y) {
        for (int x = 0; x < w; ++x) {
            double acc[kChannels] = {0.0, 0.0, 0.0, 0.0};
            for (int i = 0; i < oy; ++i) {
                int sy;
                bool vy = edge_index(y - ty + i, h, mode, sy);
                for (int j = 0; j < ox; ++j) {
                    int sx;
                    bool vx = edge_index(x - tx + j, w, mode, sx);
                    double weight = kernel[(oy - i - 1) * ox + (ox - j - 1)];
                    const double* s = &in[(static_cast<std::size_t>(sy) * w + sx) * kChannels];
                    double valid = (vx && vy) ? 1.0 : 0.0;
                    for (int c = 0; c < kChannels; ++c) acc[c] += weight * (s[c] * valid);
                }
            }
            float* d = dst.px(y, x);
            double out[kChannels];
            for (int c = 0; c < kChannels; ++c) out[c] = clamp01(acc[c] / divisor + bias);
            if (preserve_alpha) {
                out[3] = in[(static_cast<std::size_t>(y) * w + x) * kChannels + 3];
                for (int c = 0; c < 3; ++c) out[c] *= out[3];
            } else {
                for (int c = 0; c < 3; ++c) out[c] = std::min(out[c], out[3]);
            }
            for (int c = 0; c < kChannels; ++c) d[c] = static_cast<float>(out[c]);
        }
    }
}

}  // namespace svgr
