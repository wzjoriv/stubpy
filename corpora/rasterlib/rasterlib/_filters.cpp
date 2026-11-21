// A few filter primitives on premultiplied float32 RGBA arrays (pybind11).
#include <pybind11/numpy.h>
#include <pybind11/pybind11.h>
#include <pybind11/stl.h>

#include <algorithm>
#include <array>
#include <cmath>
#include <string>
#include <vector>

namespace py = pybind11;
using namespace pybind11::literals;

using ImageArray = py::array_t<float, py::array::c_style | py::array::forcecast>;
using Color4 = std::array<double, 4>;

namespace {

enum class BlendMode { Normal, Multiply, Screen, Darken, Lighten };
enum class ResampleFilter { Nearest, Bilinear };
enum class TransferType { Identity, Table, Linear, Gamma };
enum class LightType { Distant, Point };

struct TransferFunction {
    TransferType kind = TransferType::Identity;
    std::vector<double> values;
    double slope = 1.0, intercept = 0.0, amplitude = 1.0, exponent = 1.0, offset = 0.0;

    double operator()(double c) const {
        switch (kind) {
            case TransferType::Table: {
                if (values.empty()) return c;
                double pos = std::clamp(c, 0.0, 1.0) * (values.size() - 1);
                size_t lo = static_cast<size_t>(pos), hi = std::min(lo + 1, values.size() - 1);
                return values[lo] + (values[hi] - values[lo]) * (pos - lo);
            }
            case TransferType::Linear: return slope * c + intercept;
            case TransferType::Gamma: return amplitude * std::pow(c, exponent) + offset;
            default: return c;
        }
    }
};

struct LightSource {
    LightType kind = LightType::Distant;
    double azimuth = 0.0, elevation = 0.0;
    std::array<double, 3> position{0.0, 0.0, 0.0};
};

void require_rgba(const ImageArray& img) {
    if (img.ndim() != 3 || img.shape(2) != 4) throw py::value_error("img must be an (H, W, 4) array");
}

ImageArray blank(py::ssize_t h, py::ssize_t w) {
    ImageArray out({h, w, static_cast<py::ssize_t>(4)});
    std::fill(out.mutable_data(), out.mutable_data() + out.size(), 0.0f);
    return out;
}

std::vector<double> gaussian_kernel(double sigma) {
    if (sigma <= 0) return {1.0};
    int radius = static_cast<int>(std::ceil(sigma * 3.0));
    std::vector<double> k(2 * radius + 1);
    double sum = 0.0;
    for (int i = -radius; i <= radius; ++i) sum += k[i + radius] = std::exp(-(i * i) / (2.0 * sigma * sigma));
    for (double& v : k) v /= sum;
    return k;
}

void blur_axis(const float* src, float* dst, int h, int w, const std::vector<double>& k, bool horizontal) {
    int radius = static_cast<int>(k.size() / 2);
    for (int y = 0; y < h; ++y)
        for (int x = 0; x < w; ++x)
            for (int c = 0; c < 4; ++c) {
                double acc = 0.0;
                for (int i = -radius; i <= radius; ++i) {
                    int yy = horizontal ? y : std::clamp(y + i, 0, h - 1);
                    int xx = horizontal ? std::clamp(x + i, 0, w - 1) : x;
                    acc += k[i + radius] * src[(static_cast<size_t>(yy) * w + xx) * 4 + c];
                }
                dst[(static_cast<size_t>(y) * w + x) * 4 + c] = static_cast<float>(acc);
            }
}

ImageArray gaussian_blur_xy(const ImageArray& img, double std_x, double std_y) {
    require_rgba(img);
    if (std_x < 0 || std_y < 0) throw py::value_error("standard deviation must be non-negative");
    int h = static_cast<int>(img.shape(0)), w = static_cast<int>(img.shape(1));
    ImageArray tmp = blank(h, w), out = blank(h, w);
    blur_axis(img.data(), tmp.mutable_data(), h, w, gaussian_kernel(std_x), true);
    blur_axis(tmp.data(), out.mutable_data(), h, w, gaussian_kernel(std_y), false);
    return out;
}

ImageArray flood_size(int height, int width, const Color4& color) {
    if (height < 0 || width < 0) throw py::value_error("size must be non-negative");
    ImageArray out = blank(height, width);
    float* d = out.mutable_data();
    for (size_t i = 0; i < out.size() / 4; ++i)
        for (int c = 0; c < 4; ++c) d[4 * i + c] = static_cast<float>(color[c]);
    return out;
}

ImageArray flood_like(const ImageArray& like, const Color4& color) {
    require_rgba(like);
    return flood_size(static_cast<int>(like.shape(0)), static_cast<int>(like.shape(1)), color);
}

ImageArray resample(const ImageArray& img, int height, int width, ResampleFilter filter) {
    require_rgba(img);
    if (height <= 0 || width <= 0) throw py::value_error("size must be positive");
    int h = static_cast<int>(img.shape(0)), w = static_cast<int>(img.shape(1));
    if (h == 0 || w == 0) throw py::value_error("img must not be empty");
    ImageArray out = blank(height, width);
    const float* s = img.data();
    float* d = out.mutable_data();
    for (int y = 0; y < height; ++y)
        for (int x = 0; x < width; ++x) {
            double sy = std::clamp((y + 0.5) * h / height - 0.5, 0.0, h - 1.0);
            double sx = std::clamp((x + 0.5) * w / width - 0.5, 0.0, w - 1.0);
            int y0 = static_cast<int>(sy), x0 = static_cast<int>(sx);
            int y1 = std::min(y0 + 1, h - 1), x1 = std::min(x0 + 1, w - 1);
            double fy = sy - y0, fx = sx - x0;
            if (filter == ResampleFilter::Nearest) {
                y0 = std::min(static_cast<int>(std::round(sy)), h - 1);
                x0 = std::min(static_cast<int>(std::round(sx)), w - 1);
                y1 = y0, x1 = x0, fy = fx = 0.0;
            }
            for (int c = 0; c < 4; ++c) {
                auto at = [&](int yy, int xx) { return s[(static_cast<size_t>(yy) * w + xx) * 4 + c]; };
                double top = at(y0, x0) * (1 - fx) + at(y0, x1) * fx;
                double bottom = at(y1, x0) * (1 - fx) + at(y1, x1) * fx;
                d[(static_cast<size_t>(y) * width + x) * 4 + c] = static_cast<float>(top * (1 - fy) + bottom * fy);
            }
        }
    return out;
}

ImageArray blend(const ImageArray& src, const ImageArray& backdrop, BlendMode mode) {
    require_rgba(src);
    require_rgba(backdrop);
    if (src.shape(0) != backdrop.shape(0) || src.shape(1) != backdrop.shape(1))
        throw py::value_error("inputs must have the same size");
    ImageArray out = blank(src.shape(0), src.shape(1));
    const float *a = src.data(), *b = backdrop.data();
    float* d = out.mutable_data();
    for (size_t i = 0; i < out.size() / 4; ++i) {
        float qa = a[4 * i + 3], qb = b[4 * i + 3];
        for (int c = 0; c < 3; ++c) {
            float ca = a[4 * i + c], cb = b[4 * i + c], v = ca + cb * (1 - qa);
            switch (mode) {
                case BlendMode::Multiply: v = (1 - qa) * cb + (1 - qb) * ca + ca * cb; break;
                case BlendMode::Screen: v = cb + ca - ca * cb; break;
                case BlendMode::Darken: v = std::min((1 - qa) * cb + ca, (1 - qb) * ca + cb); break;
                case BlendMode::Lighten: v = std::max((1 - qa) * cb + ca, (1 - qb) * ca + cb); break;
                default: break;
            }
            d[4 * i + c] = v;
        }
        d[4 * i + 3] = 1 - (1 - qa) * (1 - qb);
    }
    return out;
}

}  // namespace

PYBIND11_MODULE(_filters, m) {
    m.doc() = "A few filter primitives on premultiplied float32 RGBA arrays (pybind11).";

    py::enum_<BlendMode>(m, "BlendMode", "feBlend modes.")
        .value("NORMAL", BlendMode::Normal)
        .value("MULTIPLY", BlendMode::Multiply)
        .value("SCREEN", BlendMode::Screen)
        .value("DARKEN", BlendMode::Darken)
        .value("LIGHTEN", BlendMode::Lighten);

    py::enum_<TransferType>(m, "TransferType", "feComponentTransfer function types.")
        .value("IDENTITY", TransferType::Identity)
        .value("TABLE", TransferType::Table)
        .value("LINEAR", TransferType::Linear)
        .value("GAMMA", TransferType::Gamma);

    py::enum_<ResampleFilter>(m, "ResampleFilter", "Resampling filters for resolution changes.")
        .value("NEAREST", ResampleFilter::Nearest)
        .value("BILINEAR", ResampleFilter::Bilinear);

    py::enum_<LightType>(m, "LightType", "Light source kinds.")
        .value("DISTANT", LightType::Distant)
        .value("POINT", LightType::Point);

    py::class_<TransferFunction>(m, "TransferFunction", "One feComponentTransfer channel function.")
        .def(py::init<>(), "Identity.")
        .def(py::init([](TransferType kind, std::vector<double> values) {
                 TransferFunction f;
                 f.kind = kind;
                 f.values = std::move(values);
                 return f;
             }),
             "kind"_a, "values"_a, "Table function over ``values``.")
        .def(py::init([](double slope, double intercept) {
                 TransferFunction f;
                 f.kind = TransferType::Linear;
                 f.slope = slope;
                 f.intercept = intercept;
                 return f;
             }),
             "slope"_a, "intercept"_a = 0.0, "Linear function ``slope * c + intercept``.")
        .def(py::init([](double amplitude, double exponent, double offset) {
                 TransferFunction f;
                 f.kind = TransferType::Gamma;
                 f.amplitude = amplitude;
                 f.exponent = exponent;
                 f.offset = offset;
                 return f;
             }),
             "amplitude"_a, "exponent"_a, "offset"_a = 0.0, "Gamma function ``amplitude * c**exponent + offset``.")
        .def_property(
            "kind", [](const TransferFunction& f) { return f.kind; },
            [](TransferFunction& f, TransferType k) { f.kind = k; }, "The function type.")
        .def_property_readonly("values", [](const TransferFunction& f) { return f.values; }, "Table values.")
        .def("__call__", [](const TransferFunction& f, double c) { return f(c); }, "c"_a,
             "Apply to one straight channel value.");

    py::class_<LightSource>(m, "LightSource", "A distant or point light in filter pixel space.")
        .def(py::init([](double azimuth, double elevation) {
                 LightSource s;
                 s.azimuth = azimuth;
                 s.elevation = elevation;
                 return s;
             }),
             "azimuth"_a, "elevation"_a, "A distant light.")
        .def(py::init([](double x, double y, double z) {
                 LightSource s;
                 s.kind = LightType::Point;
                 s.position = {x, y, z};
                 return s;
             }),
             "x"_a, "y"_a, "z"_a, "A point light.")
        .def_property_readonly("kind", [](const LightSource& s) { return s.kind; }, "The light type.")
        .def_property(
            "position", [](const LightSource& s) { return s.position; },
            [](LightSource& s, const std::array<double, 3>& p) { s.position = p; }, "Light position.")
        .def_readwrite("azimuth", &LightSource::azimuth)
        .def_readwrite("elevation", &LightSource::elevation);

    m.def("gaussian_blur", &gaussian_blur_xy, "img"_a, "std_x"_a, "std_y"_a,
          "feGaussianBlur with separate x and y deviations in pixels.");
    m.def("gaussian_blur", [](const ImageArray& img, double std) { return gaussian_blur_xy(img, std, std); },
          "img"_a, "std"_a, "feGaussianBlur with one deviation in pixels.");
    m.def("resample", &resample, "img"_a, "height"_a, "width"_a, py::kw_only(),
          "filter"_a = ResampleFilter::Bilinear, "Resize an image.");
    m.def("flood", &flood_size, "height"_a, "width"_a, "color"_a, "feFlood with a premultiplied RGBA color.");
    m.def("flood", &flood_like, "like"_a, "color"_a, "feFlood sized like another image.");
    m.def("blend", &blend, "src"_a, "backdrop"_a, "mode"_a = BlendMode::Normal, "feBlend of in over in2.");
    m.def("gaussian_kernel", &gaussian_kernel, "sigma"_a, "Normalized 1-D Gaussian weights.");
}
