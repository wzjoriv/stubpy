// SVG filter primitives on premultiplied float32 RGBA arrays (pybind11).
#include <pybind11/numpy.h>
#include <pybind11/pybind11.h>
#include <pybind11/stl.h>

#include <array>
#include <cmath>
#include <limits>
#include <string>
#include <tuple>
#include <vector>

#include "_native/filters_basic.hpp"
#include "_native/filters_color.hpp"
#include "_native/filters_light.hpp"

namespace py = pybind11;
using namespace pybind11::literals;

using ImageArray = py::array_t<float, py::array::c_style | py::array::forcecast>;
using KernelArray = py::array_t<double, py::array::c_style | py::array::forcecast>;
using Color4 = std::array<double, 4>;
using Color3 = std::array<double, 3>;

namespace {

void require_rgba(const ImageArray& img, const char* name) {
    if (img.ndim() != 3 || img.shape(2) != svgr::kChannels)
        throw py::value_error(std::string(name) + " must be an (H, W, 4) array");
}

void require_same(const ImageArray& a, const ImageArray& b) {
    if (a.shape(0) != b.shape(0) || a.shape(1) != b.shape(1)) throw py::value_error("inputs must have the same size");
}

ImageArray empty_like(int h, int w) {
    ImageArray out({static_cast<py::ssize_t>(h), static_cast<py::ssize_t>(w), static_cast<py::ssize_t>(4)});
    std::fill(out.mutable_data(), out.mutable_data() + out.size(), 0.0f);
    return out;
}

svgr::ConstImage view(const ImageArray& img) {
    return {img.data(), static_cast<int>(img.shape(0)), static_cast<int>(img.shape(1))};
}

svgr::Image view(ImageArray& img) {
    return {img.mutable_data(), static_cast<int>(img.shape(0)), static_cast<int>(img.shape(1))};
}

ImageArray gaussian_blur_xy(const ImageArray& img, double std_x, double std_y) {
    require_rgba(img, "img");
    if (std_x < 0 || std_y < 0) throw py::value_error("standard deviation must be non-negative");
    ImageArray out = empty_like(static_cast<int>(img.shape(0)), static_cast<int>(img.shape(1)));
    auto src = view(img);
    auto dst = view(out);
    {
        py::gil_scoped_release release;
        svgr::gaussian_blur(src, dst, std_x, std_y);
    }
    return out;
}

ImageArray offset(const ImageArray& img, double dx, double dy) {
    require_rgba(img, "img");
    ImageArray out = empty_like(static_cast<int>(img.shape(0)), static_cast<int>(img.shape(1)));
    auto src = view(img);
    auto dst = view(out);
    {
        py::gil_scoped_release release;
        svgr::offset(src, dst, dx, dy);
    }
    return out;
}

ImageArray resample(const ImageArray& img, int height, int width, svgr::ResampleFilter filter) {
    require_rgba(img, "img");
    if (height <= 0 || width <= 0) throw py::value_error("size must be positive");
    if (img.shape(0) == 0 || img.shape(1) == 0) throw py::value_error("img must not be empty");
    ImageArray out = empty_like(height, width);
    auto src = view(img);
    auto dst = view(out);
    {
        py::gil_scoped_release release;
        svgr::resample(src, dst, filter);
    }
    return out;
}

ImageArray flood_size(int height, int width, const Color4& color) {
    if (height < 0 || width < 0) throw py::value_error("size must be non-negative");
    ImageArray out = empty_like(height, width);
    svgr::flood(view(out), color.data());
    return out;
}

ImageArray flood_like(const ImageArray& like, const Color4& color) {
    require_rgba(like, "like");
    return flood_size(static_cast<int>(like.shape(0)), static_cast<int>(like.shape(1)), color);
}

ImageArray blend(const ImageArray& src, const ImageArray& backdrop, svgr::BlendMode mode) {
    require_rgba(src, "src");
    require_rgba(backdrop, "backdrop");
    require_same(src, backdrop);
    ImageArray out = empty_like(static_cast<int>(src.shape(0)), static_cast<int>(src.shape(1)));
    auto a = view(src);
    auto b = view(backdrop);
    auto d = view(out);
    {
        py::gil_scoped_release release;
        svgr::blend(a, b, d, mode);
    }
    return out;
}

ImageArray composite(const ImageArray& a, const ImageArray& b, svgr::CompositeOperator op, double k1, double k2,
                     double k3, double k4) {
    require_rgba(a, "a");
    require_rgba(b, "b");
    require_same(a, b);
    ImageArray out = empty_like(static_cast<int>(a.shape(0)), static_cast<int>(a.shape(1)));
    svgr::composite(view(a), view(b), view(out), op, k1, k2, k3, k4);
    return out;
}

ImageArray color_matrix(const ImageArray& img, svgr::ColorMatrixType kind, const std::vector<double>& values) {
    require_rgba(img, "img");
    ImageArray out = empty_like(static_cast<int>(img.shape(0)), static_cast<int>(img.shape(1)));
    svgr::color_matrix(view(img), view(out), svgr::color_matrix_values(kind, values));
    return out;
}

ImageArray component_transfer(const ImageArray& img, const std::vector<svgr::TransferFunction>& funcs) {
    require_rgba(img, "img");
    if (funcs.size() != svgr::kChannels) throw py::value_error("expected four transfer functions (R, G, B, A)");
    const svgr::TransferFunction* ptrs[svgr::kChannels] = {&funcs[0], &funcs[1], &funcs[2], &funcs[3]};
    ImageArray out = empty_like(static_cast<int>(img.shape(0)), static_cast<int>(img.shape(1)));
    svgr::component_transfer(view(img), view(out), ptrs);
    return out;
}

ImageArray morphology(const ImageArray& img, int rx, int ry, svgr::MorphologyOperator op) {
    require_rgba(img, "img");
    ImageArray out = empty_like(static_cast<int>(img.shape(0)), static_cast<int>(img.shape(1)));
    auto src = view(img);
    auto dst = view(out);
    {
        py::gil_scoped_release release;
        svgr::morphology(src, dst, rx, ry, op);
    }
    return out;
}

ImageArray convolve_matrix(const ImageArray& img, const KernelArray& kernel, double divisor, double bias,
                           int target_x, int target_y, svgr::EdgeMode edge_mode, bool preserve_alpha) {
    require_rgba(img, "img");
    if (kernel.ndim() != 2 || kernel.size() == 0) throw py::value_error("kernel must be a non-empty 2-D array");
    int oy = static_cast<int>(kernel.shape(0)), ox = static_cast<int>(kernel.shape(1));
    if (target_x >= ox || target_y >= oy) throw py::value_error("target outside the kernel");
    ImageArray out = empty_like(static_cast<int>(img.shape(0)), static_cast<int>(img.shape(1)));
    auto src = view(img);
    auto dst = view(out);
    const double* k = kernel.data();
    {
        py::gil_scoped_release release;
        svgr::convolve(src, dst, k, ox, oy, divisor, bias, target_x, target_y, edge_mode, preserve_alpha);
    }
    return out;
}

ImageArray tile(const ImageArray& img, int x, int y, int w, int h) {
    require_rgba(img, "img");
    ImageArray out = empty_like(static_cast<int>(img.shape(0)), static_cast<int>(img.shape(1)));
    svgr::tile(view(img), view(out), x, y, w, h);
    return out;
}

ImageArray merge(const std::vector<ImageArray>& layers) {
    if (layers.empty()) throw py::value_error("merge needs at least one layer");
    for (const auto& layer : layers) {
        require_rgba(layer, "layer");
        require_same(layer, layers[0]);
    }
    ImageArray out = empty_like(static_cast<int>(layers[0].shape(0)), static_cast<int>(layers[0].shape(1)));
    for (const auto& layer : layers) svgr::merge_over(view(out), view(layer));
    return out;
}

ImageArray turbulence(int height, int width, const KernelArray& inv, double base_fx, double base_fy, int octaves,
                      long seed, bool stitch, bool fractal, const std::array<double, 4>& tile_rect) {
    if (inv.ndim() != 2 || inv.shape(0) != 2 || inv.shape(1) != 3) throw py::value_error("inv must be a 2x3 matrix");
    ImageArray out = empty_like(height, width);
    auto dst = view(out);
    const double* m = inv.data();
    {
        py::gil_scoped_release release;
        svgr::turbulence(dst, m, base_fx, base_fy, octaves, seed, stitch, fractal, tile_rect.data());
    }
    return out;
}

ImageArray displacement_map(const ImageArray& img, const ImageArray& map, double scale, svgr::Channel x_channel,
                            svgr::Channel y_channel) {
    require_rgba(img, "img");
    require_rgba(map, "map");
    require_same(img, map);
    ImageArray out = empty_like(static_cast<int>(img.shape(0)), static_cast<int>(img.shape(1)));
    auto src = view(img);
    auto disp = view(map);
    auto dst = view(out);
    {
        py::gil_scoped_release release;
        svgr::displacement_map(src, disp, dst, scale, x_channel, y_channel);
    }
    return out;
}

ImageArray light(const ImageArray& img, double surface_scale, double constant, double exponent,
                 const svgr::LightSource& source, const Color3& color, bool specular) {
    require_rgba(img, "img");
    ImageArray out = empty_like(static_cast<int>(img.shape(0)), static_cast<int>(img.shape(1)));
    auto src = view(img);
    auto dst = view(out);
    {
        py::gil_scoped_release release;
        svgr::lighting(src, dst, surface_scale, constant, exponent, source, color.data(), specular);
    }
    return out;
}

std::string transfer_repr(const svgr::TransferFunction& f) {
    static const char* names[] = {"IDENTITY", "TABLE", "DISCRETE", "LINEAR", "GAMMA"};
    return std::string("TransferFunction(") + names[static_cast<int>(f.kind)] + ")";
}

}  // namespace

PYBIND11_MODULE(_filters, m) {
    m.doc() = "SVG filter primitives on premultiplied float32 RGBA arrays (pybind11).";
    m.attr("HAVE_OPENMP") = py::bool_(SVGR_HAVE_OPENMP);

    py::enum_<svgr::BlendMode>(m, "BlendMode", "feBlend modes.")
        .value("NORMAL", svgr::BlendMode::Normal)
        .value("MULTIPLY", svgr::BlendMode::Multiply)
        .value("SCREEN", svgr::BlendMode::Screen)
        .value("DARKEN", svgr::BlendMode::Darken)
        .value("LIGHTEN", svgr::BlendMode::Lighten)
        .value("OVERLAY", svgr::BlendMode::Overlay)
        .value("COLOR_DODGE", svgr::BlendMode::ColorDodge)
        .value("COLOR_BURN", svgr::BlendMode::ColorBurn)
        .value("HARD_LIGHT", svgr::BlendMode::HardLight)
        .value("SOFT_LIGHT", svgr::BlendMode::SoftLight)
        .value("DIFFERENCE", svgr::BlendMode::Difference)
        .value("EXCLUSION", svgr::BlendMode::Exclusion)
        .value("HUE", svgr::BlendMode::Hue)
        .value("SATURATION", svgr::BlendMode::Saturation)
        .value("COLOR", svgr::BlendMode::Color)
        .value("LUMINOSITY", svgr::BlendMode::Luminosity);

    py::enum_<svgr::CompositeOperator>(m, "CompositeOperator", "feComposite operators.")
        .value("OVER", svgr::CompositeOperator::Over)
        .value("IN", svgr::CompositeOperator::In)
        .value("OUT", svgr::CompositeOperator::Out)
        .value("ATOP", svgr::CompositeOperator::Atop)
        .value("XOR", svgr::CompositeOperator::Xor)
        .value("ARITHMETIC", svgr::CompositeOperator::Arithmetic)
        .value("LIGHTER", svgr::CompositeOperator::Lighter);

    py::enum_<svgr::ColorMatrixType>(m, "ColorMatrixType", "feColorMatrix types.")
        .value("MATRIX", svgr::ColorMatrixType::Matrix)
        .value("SATURATE", svgr::ColorMatrixType::Saturate)
        .value("HUE_ROTATE", svgr::ColorMatrixType::HueRotate)
        .value("LUMINANCE_TO_ALPHA", svgr::ColorMatrixType::LuminanceToAlpha);

    py::enum_<svgr::TransferType>(m, "TransferType", "feComponentTransfer function types.")
        .value("IDENTITY", svgr::TransferType::Identity)
        .value("TABLE", svgr::TransferType::Table)
        .value("DISCRETE", svgr::TransferType::Discrete)
        .value("LINEAR", svgr::TransferType::Linear)
        .value("GAMMA", svgr::TransferType::Gamma);

    py::enum_<svgr::ResampleFilter>(m, "ResampleFilter", "Resampling filters for resolution changes.")
        .value("NEAREST", svgr::ResampleFilter::Nearest)
        .value("BILINEAR", svgr::ResampleFilter::Bilinear);

    py::enum_<svgr::EdgeMode>(m, "EdgeMode", "feConvolveMatrix edge modes.")
        .value("DUPLICATE", svgr::EdgeMode::Duplicate)
        .value("WRAP", svgr::EdgeMode::Wrap)
        .value("NONE", svgr::EdgeMode::None);

    py::enum_<svgr::MorphologyOperator>(m, "MorphologyOperator", "feMorphology operators.")
        .value("ERODE", svgr::MorphologyOperator::Erode)
        .value("DILATE", svgr::MorphologyOperator::Dilate);

    py::enum_<svgr::Channel>(m, "Channel", "Channel selectors for feDisplacementMap.")
        .value("R", svgr::Channel::R)
        .value("G", svgr::Channel::G)
        .value("B", svgr::Channel::B)
        .value("A", svgr::Channel::A);

    py::enum_<svgr::LightType>(m, "LightType", "Light source kinds.")
        .value("DISTANT", svgr::LightType::Distant)
        .value("POINT", svgr::LightType::Point)
        .value("SPOT", svgr::LightType::Spot);

    py::class_<svgr::TransferFunction>(m, "TransferFunction", "One feComponentTransfer channel function.")
        .def(py::init<>(), "Identity.")
        .def(py::init([](svgr::TransferType kind, std::vector<double> values) {
                 svgr::TransferFunction f;
                 f.kind = kind;
                 f.values = std::move(values);
                 return f;
             }),
             "kind"_a, "values"_a, "Table or discrete function over ``values``.")
        .def(py::init([](double slope, double intercept) {
                 svgr::TransferFunction f;
                 f.kind = svgr::TransferType::Linear;
                 f.slope = slope;
                 f.intercept = intercept;
                 return f;
             }),
             "slope"_a, "intercept"_a = 0.0, "Linear function ``slope * c + intercept``.")
        .def(py::init([](double amplitude, double exponent, double offset) {
                 svgr::TransferFunction f;
                 f.kind = svgr::TransferType::Gamma;
                 f.amplitude = amplitude;
                 f.exponent = exponent;
                 f.offset = offset;
                 return f;
             }),
             "amplitude"_a, "exponent"_a, "offset"_a = 0.0, "Gamma function ``amplitude * c**exponent + offset``.")
        .def_property(
            "kind", [](const svgr::TransferFunction& f) { return f.kind; },
            [](svgr::TransferFunction& f, svgr::TransferType k) { f.kind = k; }, "The function type.")
        .def_property_readonly(
            "values", [](const svgr::TransferFunction& f) { return f.values; }, "Table values.")
        .def_readwrite("slope", &svgr::TransferFunction::slope)
        .def_readwrite("intercept", &svgr::TransferFunction::intercept)
        .def_readwrite("amplitude", &svgr::TransferFunction::amplitude)
        .def_readwrite("exponent", &svgr::TransferFunction::exponent)
        .def_readwrite("offset", &svgr::TransferFunction::offset)
        .def("__call__", [](const svgr::TransferFunction& f, double c) { return f(c); }, "c"_a,
             "Apply to one straight channel value.")
        .def("__repr__", &transfer_repr);

    py::class_<svgr::LightSource>(m, "LightSource", "A distant, point or spot light in filter pixel space.")
        .def(py::init([](double azimuth, double elevation) {
                 svgr::LightSource s;
                 s.azimuth = azimuth;
                 s.elevation = elevation;
                 return s;
             }),
             "azimuth"_a, "elevation"_a, "A distant light.")
        .def(py::init([](double x, double y, double z) {
                 svgr::LightSource s;
                 s.kind = svgr::LightType::Point;
                 s.position = {x, y, z};
                 return s;
             }),
             "x"_a, "y"_a, "z"_a, "A point light.")
        .def(py::init([](double x, double y, double z, double px, double py_, double pz, double specular_exponent,
                         double limiting_cone_angle) {
                 svgr::LightSource s;
                 s.kind = svgr::LightType::Spot;
                 s.position = {x, y, z};
                 s.points_at = {px, py_, pz};
                 s.specular_exponent = specular_exponent;
                 s.limiting_cone_angle = limiting_cone_angle;
                 return s;
             }),
             "x"_a, "y"_a, "z"_a, "points_at_x"_a, "points_at_y"_a, "points_at_z"_a, "specular_exponent"_a = 1.0,
             "limiting_cone_angle"_a = std::numeric_limits<double>::quiet_NaN(), "A spot light.")
        .def_property_readonly("kind", [](const svgr::LightSource& s) { return s.kind; }, "The light type.")
        .def_property(
            "position", [](const svgr::LightSource& s) { return s.position; },
            [](svgr::LightSource& s, const std::array<double, 3>& p) { s.position = p; }, "Light position.")
        .def_property(
            "points_at", [](const svgr::LightSource& s) { return s.points_at; },
            [](svgr::LightSource& s, const std::array<double, 3>& p) { s.points_at = p; }, "Spot target.")
        .def_readwrite("azimuth", &svgr::LightSource::azimuth)
        .def_readwrite("elevation", &svgr::LightSource::elevation)
        .def_readwrite("specular_exponent", &svgr::LightSource::specular_exponent)
        .def_readwrite("limiting_cone_angle", &svgr::LightSource::limiting_cone_angle);

    m.def("gaussian_blur", &gaussian_blur_xy, "img"_a, "std_x"_a, "std_y"_a,
          "feGaussianBlur with separate x and y deviations in pixels.");
    m.def("gaussian_blur", [](const ImageArray& img, double std) { return gaussian_blur_xy(img, std, std); },
          "img"_a, "std"_a, "feGaussianBlur with one deviation in pixels.");
    m.def("offset", &offset, "img"_a, "dx"_a, "dy"_a, "feOffset by a sub-pixel amount (bilinear).");
    m.def("offset", [](const ImageArray& img, const std::array<double, 2>& shift) {
              return offset(img, shift[0], shift[1]);
          },
          "img"_a, "shift"_a, "feOffset by a ``(dx, dy)`` pair.");
    m.def("resample", &resample, "img"_a, "height"_a, "width"_a, py::kw_only(),
          "filter"_a = svgr::ResampleFilter::Bilinear, "Resize an image (filterRes and kernelUnitLength).");
    m.def("flood", &flood_size, "height"_a, "width"_a, "color"_a, "feFlood with a premultiplied RGBA color.");
    m.def("flood", &flood_like, "like"_a, "color"_a, "feFlood sized like another image.");
    m.def("blend", &blend, "src"_a, "backdrop"_a, "mode"_a = svgr::BlendMode::Normal, "feBlend of in over in2.");
    m.def("composite", &composite, "a"_a, "b"_a, "op"_a = svgr::CompositeOperator::Over, "k1"_a = 0.0,
          "k2"_a = 0.0, "k3"_a = 0.0, "k4"_a = 0.0, "feComposite of in with in2.");
    m.def("color_matrix", &color_matrix, "img"_a, "kind"_a = svgr::ColorMatrixType::Matrix,
          "values"_a = std::vector<double>{}, "feColorMatrix.");
    m.def("color_matrix_values",
          [](svgr::ColorMatrixType kind, const std::vector<double>& values) {
              return svgr::color_matrix_values(kind, values);
          },
          "kind"_a, "values"_a = std::vector<double>{}, "The 4x5 matrix for a feColorMatrix type.");
    m.def("component_transfer", &component_transfer, "img"_a, "funcs"_a, "feComponentTransfer.");
    m.def("morphology", &morphology, "img"_a, "rx"_a, "ry"_a, "op"_a = svgr::MorphologyOperator::Erode,
          "feMorphology.");
    m.def("convolve_matrix", &convolve_matrix, "img"_a, "kernel"_a, "divisor"_a = 1.0, "bias"_a = 0.0,
          "target_x"_a = -1, "target_y"_a = -1, "edge_mode"_a = svgr::EdgeMode::Duplicate,
          "preserve_alpha"_a = false, "feConvolveMatrix.");
    m.def("tile", &tile, "img"_a, "x"_a, "y"_a, "w"_a, "h"_a, "feTile from a pixel rectangle of the input.");
    m.def("merge", &merge, "layers"_a, "feMerge (source-over, bottom to top).");
    m.def("turbulence", &turbulence, "height"_a, "width"_a, "inv"_a, "base_fx"_a, "base_fy"_a, "octaves"_a = 1,
          "seed"_a = 0, "stitch"_a = false, "fractal"_a = false,
          "tile"_a = std::array<double, 4>{0.0, 0.0, 0.0, 0.0}, "feTurbulence (SVG reference algorithm).");
    m.def("displacement_map", &displacement_map, "img"_a, "map"_a, "scale"_a, "x_channel"_a = svgr::Channel::A,
          "y_channel"_a = svgr::Channel::A, "feDisplacementMap with bilinear sampling.");
    m.def("diffuse_lighting",
          [](const ImageArray& img, double surface_scale, double diffuse_constant, const svgr::LightSource& source,
             const Color3& color) { return light(img, surface_scale, diffuse_constant, 1.0, source, color, false); },
          "img"_a, "surface_scale"_a, "diffuse_constant"_a, "light"_a, "color"_a = Color3{1.0, 1.0, 1.0},
          "feDiffuseLighting.");
    m.def("specular_lighting",
          [](const ImageArray& img, double surface_scale, double specular_constant, double specular_exponent,
             const svgr::LightSource& source, const Color3& color) {
              return light(img, surface_scale, specular_constant, specular_exponent, source, color, true);
          },
          "img"_a, "surface_scale"_a, "specular_constant"_a, "specular_exponent"_a, "light"_a,
          "color"_a = Color3{1.0, 1.0, 1.0}, "feSpecularLighting.");
    m.def("gaussian_kernel", &svgr::gaussian_kernel, "sigma"_a, "Normalized 1-D Gaussian weights.");
    m.def("set_num_threads", &svgr::set_threads, "n"_a, "Set the OpenMP thread count (no-op without OpenMP).");
}
