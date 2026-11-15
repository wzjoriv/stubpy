// Stroke outlining (segments, joins, caps) and dashing into polygons.
#pragma once

#include <algorithm>
#include <cmath>
#include <vector>

namespace svgr {

enum class LineJoin { Miter = 0, Round = 1, Bevel = 2 };
enum class LineCap { Butt = 0, Round = 1, Square = 2 };

constexpr int kMinRoundSegments = 8;
constexpr int kMaxRoundSegments = 256;
constexpr double kCollinearEps = 1e-12;
constexpr double kRoundJoinMinAngle = 0.25;
constexpr double kTwoPi = 6.283185307179586;

struct Pt {
    double x, y;
};

using Polygon = std::vector<Pt>;

inline Pt operator+(Pt a, Pt b) { return {a.x + b.x, a.y + b.y}; }
inline Pt operator-(Pt a, Pt b) { return {a.x - b.x, a.y - b.y}; }
inline Pt operator*(Pt a, double s) { return {a.x * s, a.y * s}; }

inline Polygon oriented(Polygon poly) {
    double area = 0.0;
    std::size_t n = poly.size();
    double s1 = 0.0, s2 = 0.0;
    for (std::size_t i = 0; i < n; ++i) {
        s1 += poly[i].x * poly[(i + 1) % n].y;
        s2 += poly[(i + 1) % n].x * poly[i].y;
    }
    area = s1 - s2;
    if (area < 0) std::reverse(poly.begin(), poly.end());
    return poly;
}

inline int round_segments(double radius, double tolerance) {
    if (radius <= tolerance) return kMinRoundSegments;
    double step = 2.0 * std::acos(1.0 - tolerance / radius);
    double n = std::ceil(kTwoPi / step);
    return static_cast<int>(std::min<double>(kMaxRoundSegments, std::max<double>(kMinRoundSegments, n)));
}

inline Polygon circle_polygon(Pt c, double r, double tolerance) {
    int n = round_segments(r, tolerance);
    Polygon poly(n);
    for (int i = 0; i < n; ++i) {
        double a = kTwoPi * i / n;
        poly[i] = {c.x + r * std::cos(a), c.y + r * std::sin(a)};
    }
    return poly;
}

inline std::vector<Pt> dedupe(const std::vector<Pt>& pts, bool closed) {
    std::vector<Pt> out;
    for (const Pt& p : pts)
        if (out.empty() || p.x != out.back().x || p.y != out.back().y) out.push_back(p);
    if (closed && out.size() > 1 && out.back().x == out.front().x && out.back().y == out.front().y) out.pop_back();
    return out;
}

inline void add_join(Pt v, Pt d0, Pt d1, double hw, LineJoin join, double miter_limit, double tolerance,
                     std::vector<Polygon>& out) {
    double cross = d0.x * d1.y - d0.y * d1.x;
    double dot = d0.x * d1.x + d0.y * d1.y;
    if (std::abs(cross) <= kCollinearEps && dot > 0) return;
    if (join == LineJoin::Round && dot < std::cos(kRoundJoinMinAngle)) {
        out.push_back(circle_polygon(v, hw, tolerance));
        return;
    }
    double side = cross > 0 ? -1.0 : 1.0;
    Pt n0 = Pt{-d0.y, d0.x} * side, n1 = Pt{-d1.y, d1.x} * side;
    Pt a0 = v + n0 * hw, a1 = v + n1 * hw;
    if (join == LineJoin::Miter && 1.0 + dot > kCollinearEps) {
        double ratio = 1.0 / std::sqrt((1.0 + dot) / 2.0);
        if (ratio <= miter_limit) {
            Pt bis = n0 + n1;
            Pt tip = v + bis * (1.0 / std::hypot(bis.x, bis.y)) * (hw * ratio);
            out.push_back(oriented({v, a0, tip, a1}));
            return;
        }
    }
    out.push_back(oriented({v, a0, a1}));
}

inline void add_cap(Pt p, Pt d, double hw, LineCap cap, double tolerance, bool at_start, std::vector<Polygon>& out) {
    if (cap == LineCap::Round) {
        out.push_back(circle_polygon(p, hw, tolerance));
    } else if (cap == LineCap::Square) {
        Pt nrm = Pt{-d.y, d.x} * hw;
        Pt ext = d * (at_start ? -hw : hw);
        out.push_back(oriented({p + nrm, p - nrm, p - nrm + ext, p + nrm + ext}));
    }
}

inline std::vector<Polygon> stroke_polyline(const std::vector<Pt>& points, bool closed, double width, LineJoin join,
                                            LineCap cap, double miter_limit, double tolerance) {
    double hw = width / 2.0;
    std::vector<Pt> pts = dedupe(points, closed);
    std::vector<Polygon> out;
    if (hw <= 0 || pts.empty()) return out;
    if (pts.size() == 1) {
        Pt p = pts[0];
        if (cap == LineCap::Round) out.push_back(circle_polygon(p, hw, tolerance));
        if (cap == LineCap::Square)
            out.push_back({{p.x - hw, p.y - hw}, {p.x + hw, p.y - hw}, {p.x + hw, p.y + hw}, {p.x - hw, p.y + hw}});
        return out;
    }
    closed = closed && pts.size() > 2;
    std::size_t count = closed ? pts.size() : pts.size() - 1;
    std::vector<Pt> starts(count), dirs(count);
    for (std::size_t i = 0; i < count; ++i) {
        Pt p0 = pts[i], p1 = pts[(i + 1) % pts.size()];
        Pt v = p1 - p0;
        double len = std::hypot(v.x, v.y);
        Pt d = {v.x / len, v.y / len};
        starts[i] = p0;
        dirs[i] = d;
        Pt nrm = Pt{-d.y, d.x} * hw;
        out.push_back(oriented({p0 + nrm, p1 + nrm, p1 - nrm, p0 - nrm}));
    }
    for (std::size_t i = closed ? 0 : 1; i < count; ++i)
        add_join(starts[i], dirs[(i + count - 1) % count], dirs[i], hw, join, miter_limit, tolerance, out);
    if (!closed) {
        add_cap(pts.front(), dirs.front(), hw, cap, tolerance, true, out);
        add_cap(pts.back(), dirs.back(), hw, cap, tolerance, false, out);
    }
    return out;
}

inline std::vector<double> normalize_dashes(const std::vector<double>& dashes) {
    double total = 0.0;
    for (double d : dashes) {
        if (d < 0) return {};
        total += d;
    }
    if (dashes.empty() || total <= 0) return {};
    std::vector<double> out = dashes;
    if (out.size() % 2) out.insert(out.end(), dashes.begin(), dashes.end());
    return out;
}

inline std::vector<std::vector<Pt>> dash_polyline(std::vector<Pt> pts, bool closed, const std::vector<double>& dashes,
                                                  double offset) {
    std::vector<double> pattern = normalize_dashes(dashes);
    if (pattern.empty() || pts.empty()) return {pts};
    if (closed && pts.size() > 1) pts.push_back(pts.front());
    double total = 0.0;
    for (double d : pattern) total += d;
    double pos = std::fmod(offset, total);
    if (pos < 0) pos += total;
    std::size_t idx = 0;
    while (pos >= pattern[idx]) {
        pos -= pattern[idx];
        idx = (idx + 1) % pattern.size();
    }
    double rem = pattern[idx] - pos;
    bool on = idx % 2 == 0;
    std::vector<std::vector<Pt>> out;
    std::vector<Pt> cur;
    if (on) cur.push_back(pts.front());
    for (std::size_t i = 0; i + 1 < pts.size(); ++i) {
        Pt a = pts[i], b = pts[i + 1];
        double seg = std::hypot(b.x - a.x, b.y - a.y);
        if (seg == 0) continue;
        double t = 0.0;
        while (seg - t > rem) {
            t += rem;
            Pt p = a + (b - a) * (t / seg);
            if (on) {
                cur.push_back(p);
                out.push_back(cur);
                cur.clear();
            } else {
                cur = {p};
            }
            idx = (idx + 1) % pattern.size();
            rem = pattern[idx];
            on = !on;
        }
        rem -= seg - t;
        if (on) cur.push_back(b);
    }
    if (on && !cur.empty()) out.push_back(cur);
    return out;
}

}  // namespace svgr
