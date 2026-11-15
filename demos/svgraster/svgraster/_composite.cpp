// Porter-Duff compositing, coverage painting, masks, conversions and stroking (nanobind).
#include <nanobind/nanobind.h>
#include <nanobind/ndarray.h>
#include <nanobind/stl/string.h>
#include <nanobind/stl/tuple.h>
#include <nanobind/stl/vector.h>

#include <cstddef>

#include <cmath>
#include <cstring>
#include <stdexcept>
#include <string>
#include <tuple>
#include <vector>

#include "_native/image.hpp"
#include "_native/stroke.hpp"

namespace nb = nanobind;
using namespace nb::literals;

using RGBA = nb::ndarray<float, nb::numpy, nb::shape<-1, -1, 4>, nb::c_contig, nb::device::cpu>;
using RGBA8 = nb::ndarray<uint8_t, nb::numpy, nb::shape<-1, -1, 4>, nb::c_contig, nb::device::cpu>;
using Mask = nb::ndarray<float, nb::numpy, nb::shape<-1, -1>, nb::c_contig, nb::device::cpu>;
using Points = nb::ndarray<const double, nb::shape<-1, 2>, nb::c_contig, nb::device::cpu>;
using PointsOut = nb::ndarray<double, nb::numpy, nb::shape<-1, 2>>;
using Color = std::tuple<float, float, float, float>;

namespace {

constexpr float kLumaR = 0.2125f, kLumaG = 0.7154f, kLumaB = 0.0721f;
constexpr float kByteMax = 255.0f;
constexpr float kHalf = 0.5f;
constexpr std::ptrdiff_t kParallelMin = 1 << 14;

enum class PorterDuff { Clear, Src, Dst, SrcOver, DstOver, SrcIn, DstIn, SrcOut, DstOut, SrcAtop, DstAtop, Xor, Plus };
enum class MaskMode { Luminance = 0, Alpha = 1 };

PorterDuff parse_op(const std::string& name) {
    static const char* names[] = {"clear", "src", "dst", "src_over", "dst_over", "src_in", "dst_in",
                                  "src_out", "dst_out", "src_atop", "dst_atop", "xor", "plus"};
    for (int i = 0; i < 13; ++i)
        if (name == names[i]) return static_cast<PorterDuff>(i);
    throw std::invalid_argument("unknown Porter-Duff operator '" + name + "'");
}

void factors(PorterDuff op, float sa, float da, float& fa, float& fb) {
    switch (op) {
        case PorterDuff::Clear: fa = 0; fb = 0; break;
        case PorterDuff::Src: fa = 1; fb = 0; break;
        case PorterDuff::Dst: fa = 0; fb = 1; break;
        case PorterDuff::SrcOver: fa = 1; fb = 1 - sa; break;
        case PorterDuff::DstOver: fa = 1 - da; fb = 1; break;
        case PorterDuff::SrcIn: fa = da; fb = 0; break;
        case PorterDuff::DstIn: fa = 0; fb = sa; break;
        case PorterDuff::SrcOut: fa = 1 - da; fb = 0; break;
        case PorterDuff::DstOut: fa = 0; fb = 1 - sa; break;
        case PorterDuff::SrcAtop: fa = da; fb = 1 - sa; break;
        case PorterDuff::DstAtop: fa = 1 - da; fb = sa; break;
        case PorterDuff::Xor: fa = 1 - da; fb = 1 - sa; break;
        case PorterDuff::Plus: fa = 1; fb = 1; break;
    }
}

void same_size(std::size_t h1, std::size_t w1, std::size_t h2, std::size_t w2) {
    if (h1 != h2 || w1 != w2) throw std::invalid_argument("array sizes differ");
}

RGBA new_rgba(std::size_t h, std::size_t w) {
    float* data = new float[h * w * 4]();
    nb::capsule owner(data, [](void* p) noexcept { delete[] static_cast<float*>(p); });
    return RGBA(data, {h, w, 4}, owner);
}

PointsOut to_points(const std::vector<svgr::Pt>& poly) {
    double* data = new double[poly.size() * 2];
    for (std::size_t i = 0; i < poly.size(); ++i) {
        data[2 * i] = poly[i].x;
        data[2 * i + 1] = poly[i].y;
    }
    nb::capsule owner(data, [](void* p) noexcept { delete[] static_cast<double*>(p); });
    return PointsOut(data, {poly.size(), 2}, owner);
}

std::vector<svgr::Pt> from_points(const Points& pts) {
    std::vector<svgr::Pt> out(pts.shape(0));
    for (std::size_t i = 0; i < out.size(); ++i) out[i] = {pts(i, 0), pts(i, 1)};
    return out;
}

RGBA porter_duff(const RGBA& dst, const RGBA& src, const std::string& op_name) {
    same_size(dst.shape(0), dst.shape(1), src.shape(0), src.shape(1));
    PorterDuff op = parse_op(op_name);
    RGBA out = new_rgba(dst.shape(0), dst.shape(1));
    const float* d = dst.data();
    const float* s = src.data();
    float* o = out.data();
    for (std::size_t i = 0; i < dst.shape(0) * dst.shape(1); ++i) {
        float fa, fb;
        factors(op, s[4 * i + 3], d[4 * i + 3], fa, fb);
        for (int c = 0; c < 4; ++c) o[4 * i + c] = std::min(s[4 * i + c] * fa + d[4 * i + c] * fb, 1.0f);
    }
    return out;
}

void paint_color(RGBA& dst, const Mask& coverage, const Color& color) {
    same_size(dst.shape(0), dst.shape(1), coverage.shape(0), coverage.shape(1));
    float col[4] = {std::get<0>(color), std::get<1>(color), std::get<2>(color), std::get<3>(color)};
    float* d = dst.data();
    const float* cov = coverage.data();
    std::ptrdiff_t n = static_cast<std::ptrdiff_t>(dst.shape(0) * dst.shape(1));
    nb::gil_scoped_release release;
#pragma omp parallel for schedule(static) if (n > kParallelMin)
    for (std::ptrdiff_t i = 0; i < n; ++i) {
        float s[4];
        for (int c = 0; c < 4; ++c) s[c] = col[c] * cov[i];
        float inv = 1.0f - s[3];
        for (int c = 0; c < 4; ++c) d[4 * i + c] = d[4 * i + c] * inv + s[c];
    }
}

void paint_image(RGBA& dst, const Mask& coverage, const RGBA& paint) {
    same_size(dst.shape(0), dst.shape(1), coverage.shape(0), coverage.shape(1));
    same_size(dst.shape(0), dst.shape(1), paint.shape(0), paint.shape(1));
    float* d = dst.data();
    const float* cov = coverage.data();
    const float* p = paint.data();
    std::ptrdiff_t n = static_cast<std::ptrdiff_t>(dst.shape(0) * dst.shape(1));
    nb::gil_scoped_release release;
#pragma omp parallel for schedule(static) if (n > kParallelMin)
    for (std::ptrdiff_t i = 0; i < n; ++i) {
        float s[4];
        for (int c = 0; c < 4; ++c) s[c] = p[4 * i + c] * cov[i];
        float inv = 1.0f - s[3];
        for (int c = 0; c < 4; ++c) d[4 * i + c] = d[4 * i + c] * inv + s[c];
    }
}

void over(RGBA& dst, const RGBA& src, float opacity) {
    same_size(dst.shape(0), dst.shape(1), src.shape(0), src.shape(1));
    float* d = dst.data();
    const float* s = src.data();
    std::ptrdiff_t n = static_cast<std::ptrdiff_t>(dst.shape(0) * dst.shape(1));
    nb::gil_scoped_release release;
#pragma omp parallel for schedule(static) if (n > kParallelMin)
    for (std::ptrdiff_t i = 0; i < n; ++i) {
        float inv = 1.0f - s[4 * i + 3] * opacity;
        for (int c = 0; c < 4; ++c) d[4 * i + c] = d[4 * i + c] * inv + s[4 * i + c] * opacity;
    }
}

Mask mask_values(const RGBA& mask, int mode) {
    std::size_t n = mask.shape(0) * mask.shape(1);
    float* data = new float[n];
    nb::capsule owner(data, [](void* p) noexcept { delete[] static_cast<float*>(p); });
    const float* m = mask.data();
#pragma omp parallel for schedule(static) if (static_cast<std::ptrdiff_t>(n) > kParallelMin)
    for (std::ptrdiff_t i = 0; i < static_cast<std::ptrdiff_t>(n); ++i) {
        if (static_cast<MaskMode>(mode) == MaskMode::Alpha) {
            data[i] = m[4 * i + 3];
        } else {
            float lum = kLumaR * m[4 * i] + kLumaG * m[4 * i + 1] + kLumaB * m[4 * i + 2];
            data[i] = lum < 0 ? 0.0f : (lum > 1 ? 1.0f : lum);
        }
    }
    return Mask(data, {mask.shape(0), mask.shape(1)}, owner);
}

void apply_mask(RGBA& img, const Mask& factors) {
    same_size(img.shape(0), img.shape(1), factors.shape(0), factors.shape(1));
    float* d = img.data();
    const float* f = factors.data();
    std::ptrdiff_t n = static_cast<std::ptrdiff_t>(img.shape(0) * img.shape(1));
    nb::gil_scoped_release release;
#pragma omp parallel for schedule(static) if (n > kParallelMin)
    for (std::ptrdiff_t i = 0; i < n; ++i)
        for (int c = 0; c < 4; ++c) d[4 * i + c] *= f[i];
}

RGBA8 to_uint8(const RGBA& img, bool unpremultiply) {
    std::size_t n = img.shape(0) * img.shape(1);
    uint8_t* data = new uint8_t[n * 4];
    nb::capsule owner(data, [](void* p) noexcept { delete[] static_cast<uint8_t*>(p); });
    const float* s = img.data();
    {
        nb::gil_scoped_release release;
#pragma omp parallel for schedule(static) if (static_cast<std::ptrdiff_t>(n) > kParallelMin)
    for (std::ptrdiff_t i = 0; i < static_cast<std::ptrdiff_t>(n); ++i) {
        float a = s[4 * i + 3];
        for (int c = 0; c < 4; ++c) {
            float v = s[4 * i + c];
            if (unpremultiply && c < 3) v = a > 0 ? v / a : 0.0f;
            v = v < 0 ? 0.0f : (v > 1 ? 1.0f : v);
            data[4 * i + c] = static_cast<uint8_t>(std::floor(v * kByteMax + kHalf));
        }
    }
    }
    return RGBA8(data, {img.shape(0), img.shape(1), 4}, owner);
}

RGBA to_float32(const RGBA8& img, bool premultiply) {
    RGBA out = new_rgba(img.shape(0), img.shape(1));
    const uint8_t* s = img.data();
    float* d = out.data();
    std::ptrdiff_t n = static_cast<std::ptrdiff_t>(img.shape(0) * img.shape(1));
    nb::gil_scoped_release release;
#pragma omp parallel for schedule(static) if (n > kParallelMin)
    for (std::ptrdiff_t i = 0; i < n; ++i) {
        float a = s[4 * i + 3] / kByteMax;
        for (int c = 0; c < 3; ++c) d[4 * i + c] = premultiply ? (s[4 * i + c] / kByteMax) * a : s[4 * i + c] / kByteMax;
        d[4 * i + 3] = a;
    }
    return out;
}

std::vector<PointsOut> stroke(const Points& points, bool closed, double width, int join, int cap, double miter_limit,
                              double tolerance) {
    if (tolerance <= 0) throw std::invalid_argument("tolerance must be positive");
    auto polys = svgr::stroke_polyline(from_points(points), closed, width, static_cast<svgr::LineJoin>(join),
                                       static_cast<svgr::LineCap>(cap), miter_limit, tolerance);
    std::vector<PointsOut> out;
    out.reserve(polys.size());
    for (const auto& p : polys) out.push_back(to_points(p));
    return out;
}

std::vector<PointsOut> dash(const Points& points, bool closed, const std::vector<double>& dashes, double offset) {
    std::vector<PointsOut> out;
    for (const auto& piece : svgr::dash_polyline(from_points(points), closed, dashes, offset))
        out.push_back(to_points(piece));
    return out;
}

enum class PixelFormat { RGBA = 0, RGB = 1, BGRA = 2 };

// Converts premultiplied float32 frames into packed 8-bit pixels for video encoders.
class FramePacker {
public:
    FramePacker(int width, int height, PixelFormat format, Color background)
        : width_(width), height_(height), format_(format), background_(background) {
        if (width <= 0 || height <= 0) throw std::invalid_argument("frame size must be positive");
    }

    int width() const { return width_; }
    int height() const { return height_; }
    std::size_t frames() const { return frames_; }
    PixelFormat format() const { return format_; }
    void set_format(PixelFormat f) { format_ = f; }
    Color background() const { return background_; }
    void set_background(const Color& c) { background_ = c; }
    int channels() const { return format_ == PixelFormat::RGB ? 3 : 4; }
    std::size_t frame_bytes() const { return static_cast<std::size_t>(width_) * height_ * channels(); }

    nb::bytes pack(const RGBA& img) {
        if (static_cast<int>(img.shape(0)) != height_ || static_cast<int>(img.shape(1)) != width_)
            throw std::invalid_argument("frame size does not match the packer");
        std::vector<uint8_t> buf(frame_bytes());
        const float* s = img.data();
        uint8_t* d = buf.data();
        int ch = channels();
        float bg[4] = {std::get<0>(background_), std::get<1>(background_), std::get<2>(background_),
                       std::get<3>(background_)};
        bool bgra = format_ == PixelFormat::BGRA, rgb = format_ == PixelFormat::RGB;
        std::ptrdiff_t n = static_cast<std::ptrdiff_t>(width_) * height_;
        {
            nb::gil_scoped_release release;
#pragma omp parallel for schedule(static) if (n > kParallelMin)
            for (std::ptrdiff_t i = 0; i < n; ++i) {
                float px[4];
                float a = s[4 * i + 3];
                if (rgb) {
                    for (int c = 0; c < 3; ++c) px[c] = s[4 * i + c] + bg[c] * bg[3] * (1.0f - a);
                    px[3] = 1.0f;
                } else {
                    for (int c = 0; c < 3; ++c) px[c] = a > 0 ? s[4 * i + c] / a : 0.0f;
                    px[3] = a;
                }
                if (bgra) std::swap(px[0], px[2]);
                for (int c = 0; c < ch; ++c) {
                    float v = px[c] < 0 ? 0.0f : (px[c] > 1 ? 1.0f : px[c]);
                    d[ch * i + c] = static_cast<uint8_t>(std::floor(v * kByteMax + kHalf));
                }
            }
        }
        ++frames_;
        return nb::bytes(reinterpret_cast<const char*>(buf.data()), buf.size());
    }

private:
    int width_, height_;
    PixelFormat format_;
    Color background_;
    std::size_t frames_ = 0;
};

}  // namespace

NB_MODULE(_composite, m) {
    m.doc() = "Compositing, masks, pixel conversion and stroke outlining (nanobind).";
    m.attr("HAVE_OPENMP") = static_cast<bool>(SVGR_HAVE_OPENMP);
    m.attr("PORTER_DUFF") = nb::make_tuple("clear", "src", "dst", "src_over", "dst_over", "src_in", "dst_in",
                                           "src_out", "dst_out", "src_atop", "dst_atop", "xor", "plus");

    nb::enum_<PixelFormat>(m, "PixelFormat", "Packed 8-bit pixel layouts for video frames.")
        .value("RGBA", PixelFormat::RGBA)
        .value("RGB", PixelFormat::RGB)
        .value("BGRA", PixelFormat::BGRA);

    nb::class_<FramePacker>(m, "FramePacker", "Packs premultiplied float32 frames into 8-bit bytes for encoders.")
        .def(nb::init<int, int, PixelFormat, Color>(), "width"_a, "height"_a, nb::kw_only(),
             "format"_a = PixelFormat::RGBA, "background"_a = Color{1.0f, 1.0f, 1.0f, 1.0f},
             "A packer for ``width`` x ``height`` frames.")
        .def_prop_ro("width", &FramePacker::width, "Frame width in pixels.")
        .def_prop_ro("height", &FramePacker::height, "Frame height in pixels.")
        .def_prop_ro("frames", &FramePacker::frames, "Frames packed so far.")
        .def_prop_ro("frame_bytes", &FramePacker::frame_bytes, "Bytes per packed frame.")
        .def_prop_rw("format", &FramePacker::format, &FramePacker::set_format, "The output pixel layout.")
        .def_prop_rw("background", &FramePacker::background, &FramePacker::set_background,
                     "Straight RGBA color composited under frames for ``PixelFormat.RGB``.")
        .def("pack", &FramePacker::pack, "img"_a, "Pack one premultiplied ``(H, W, 4)`` float32 frame.")
        .def("__repr__", [](const FramePacker& p) {
            return "FramePacker(" + std::to_string(p.width()) + "x" + std::to_string(p.height()) +
                   ", frames=" + std::to_string(p.frames()) + ")";
        });

    m.def("set_num_threads", &svgr::set_threads, "n"_a, "Set the OpenMP thread count (no-op without OpenMP).");

    nb::enum_<svgr::LineJoin>(m, "LineJoin", "Stroke join styles.")
        .value("MITER", svgr::LineJoin::Miter)
        .value("ROUND", svgr::LineJoin::Round)
        .value("BEVEL", svgr::LineJoin::Bevel);
    nb::enum_<svgr::LineCap>(m, "LineCap", "Stroke cap styles.")
        .value("BUTT", svgr::LineCap::Butt)
        .value("ROUND", svgr::LineCap::Round)
        .value("SQUARE", svgr::LineCap::Square);

    m.def("porter_duff", &porter_duff, "dst"_a, "src"_a, "op"_a = "src_over",
          "``src op dst`` on premultiplied RGBA, returned as a new array.");
    m.def("paint_coverage", &paint_color, "dst"_a, "coverage"_a, "color"_a,
          nb::sig("def paint_coverage(dst: numpy.ndarray, coverage: numpy.ndarray, "
                  "color: tuple[float, float, float, float]) -> None"),
          "Composite a premultiplied solid color through ``coverage`` into ``dst``.");
    m.def("paint_coverage", &paint_image, "dst"_a, "coverage"_a, "paint"_a,
          "Composite a premultiplied paint image through ``coverage`` into ``dst``.");
    m.def("over", &over, "dst"_a, "src"_a, nb::kw_only(), "opacity"_a = 1.0f,
          "Composite ``src`` (scaled by ``opacity``) over ``dst`` in place.");
    m.def("mask_values", &mask_values, "mask"_a, "mode"_a = 0,
          "Per-pixel factors from a mask layer (0 luminance, 1 alpha).");
    m.def("apply_mask", &apply_mask, "img"_a, "factors"_a, "Multiply every channel by per-pixel factors.");
    m.def("to_uint8", &to_uint8, "img"_a, nb::kw_only(), "unpremultiply"_a = true,
          "Premultiplied float32 RGBA to 8-bit RGBA.");
    m.def("to_float32", &to_float32, "img"_a, nb::kw_only(), "premultiply"_a = true,
          "8-bit RGBA to premultiplied float32 RGBA.");
    m.def("stroke", &stroke, "points"_a, "closed"_a, "width"_a, nb::kw_only(), "join"_a = 0, "cap"_a = 0,
          "miter_limit"_a = 4.0, "tolerance"_a = 0.1,
          nb::sig("def stroke(points: numpy.ndarray, closed: bool, width: float, *, join: int = 0, cap: int = 0, "
                  "miter_limit: float = 4.0, tolerance: float = 0.1) -> list[numpy.ndarray]"),
          "Outline a polyline into positively oriented polygons.");
    m.def("dash", &dash, "points"_a, "closed"_a, "dashes"_a, "offset"_a = 0.0,
          "Split a polyline into dash polylines.");
    m.def("circle_polygon",
          [](double cx, double cy, double radius, double tolerance) {
              return to_points(svgr::circle_polygon({cx, cy}, radius, tolerance));
          },
          "cx"_a, "cy"_a, "radius"_a, "tolerance"_a = 0.1, "A polygon approximating a circle.");
}
