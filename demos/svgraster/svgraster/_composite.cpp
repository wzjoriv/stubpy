// Compositing and frame packing (nanobind).
#include <nanobind/nanobind.h>
#include <nanobind/ndarray.h>
#include <nanobind/stl/tuple.h>

#include <algorithm>
#include <cmath>
#include <cstdint>
#include <stdexcept>
#include <string>
#include <tuple>
#include <vector>

namespace nb = nanobind;
using namespace nb::literals;

using RGBA = nb::ndarray<float, nb::numpy, nb::shape<-1, -1, 4>, nb::c_contig, nb::device::cpu>;
using Color = std::tuple<float, float, float, float>;

namespace {

enum class LineJoin { Miter, Round, Bevel };
enum class PixelFormat { RGBA = 0, RGB = 1, BGRA = 2 };

void over(RGBA& dst, const RGBA& src, float opacity) {
    if (dst.shape(0) != src.shape(0) || dst.shape(1) != src.shape(1))
        throw std::invalid_argument("dst and src must have the same size");
    float* d = dst.data();
    const float* s = src.data();
    std::size_t n = dst.shape(0) * dst.shape(1);
    for (std::size_t i = 0; i < n; ++i) {
        float inv = 1.0f - s[4 * i + 3] * opacity;
        for (int c = 0; c < 4; ++c) d[4 * i + c] = d[4 * i + c] * inv + s[4 * i + c] * opacity;
    }
}

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
        std::vector<std::uint8_t> buf(frame_bytes());
        const float* s = img.data();
        float bg[3] = {std::get<0>(background_), std::get<1>(background_), std::get<2>(background_)};
        int ch = channels();
        for (std::size_t i = 0; i < static_cast<std::size_t>(width_) * height_; ++i) {
            float a = s[4 * i + 3], px[4];
            for (int c = 0; c < 3; ++c) px[c] = format_ == PixelFormat::RGB ? s[4 * i + c] + bg[c] * (1 - a) : a > 0 ? s[4 * i + c] / a : 0.0f;
            px[3] = a;
            if (format_ == PixelFormat::BGRA) std::swap(px[0], px[2]);
            for (int c = 0; c < ch; ++c)
                buf[i * ch + c] = static_cast<std::uint8_t>(std::floor(std::clamp(px[c], 0.0f, 1.0f) * 255.0f + 0.5f));
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
    m.doc() = "Compositing and frame packing (nanobind).";

    nb::enum_<PixelFormat>(m, "PixelFormat", "Packed 8-bit pixel layouts for video frames.")
        .value("RGBA", PixelFormat::RGBA)
        .value("RGB", PixelFormat::RGB)
        .value("BGRA", PixelFormat::BGRA);

    nb::enum_<LineJoin>(m, "LineJoin", "Stroke join styles.")
        .value("MITER", LineJoin::Miter)
        .value("ROUND", LineJoin::Round)
        .value("BEVEL", LineJoin::Bevel);

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
        .def("pack", &FramePacker::pack, "img"_a, "Pack one premultiplied ``(H, W, 4)`` float32 frame.");

    m.def("over", &over, "dst"_a, "src"_a, nb::kw_only(), "opacity"_a = 1.0f,
          "Composite ``src`` (scaled by ``opacity``) over ``dst`` in place.");
}
