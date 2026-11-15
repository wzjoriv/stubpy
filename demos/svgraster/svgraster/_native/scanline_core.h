/* Pure C scanline core: edge lists, sub-scanline crossings and exact span coverage. */
#ifndef SVGR_SCANLINE_CORE_H
#define SVGR_SCANLINE_CORE_H

#include <math.h>
#include <stddef.h>
#include <stdlib.h>

#define RULE_NONZERO 0
#define RULE_EVENODD 1
#define SAMPLE_OFFSET 0.5
#define INITIAL_EDGE_CAPACITY 64

typedef struct {
    double x0, y0, dxdy;
    long long ks, ke;
    int dir;
} Edge;

typedef struct {
    double x;
    int dir;
} Crossing;

typedef struct {
    Edge *items;
    ptrdiff_t count;
    ptrdiff_t cap;
} EdgeList;

static int edge_cmp(const void *a, const void *b) {
    long long ka = ((const Edge *)a)->ks, kb = ((const Edge *)b)->ks;
    return (ka > kb) - (ka < kb);
}

static double clamp_index(double v, double hi) { return v < 0 ? 0 : (v > hi ? hi : v); }

/* Append the edges of a closed polygon; returns -1 when out of memory. */
static int edges_append_polygon(EdgeList *list, const double *pts, ptrdiff_t n, long long k_total, int samples) {
    for (ptrdiff_t i = 0; i < n; i++) {
        double x0 = pts[2 * i], y0 = pts[2 * i + 1];
        double x1 = pts[2 * ((i + 1) % n)], y1 = pts[2 * ((i + 1) % n) + 1];
        if (y0 == y1) continue;
        int dir = y1 > y0 ? 1 : -1;
        if (y1 < y0) {
            double t = x0; x0 = x1; x1 = t;
            t = y0; y0 = y1; y1 = t;
        }
        double ks = clamp_index(ceil(y0 * samples - SAMPLE_OFFSET), (double)k_total);
        double ke = clamp_index(ceil(y1 * samples - SAMPLE_OFFSET), (double)k_total);
        if (ke <= ks) continue;
        if (list->count == list->cap) {
            ptrdiff_t ncap = list->cap ? list->cap * 2 : INITIAL_EDGE_CAPACITY;
            Edge *grown = (Edge *)realloc(list->items, (size_t)ncap * sizeof(Edge));
            if (!grown) return -1;
            list->items = grown;
            list->cap = ncap;
        }
        Edge *e = &list->items[list->count++];
        e->x0 = x0; e->y0 = y0; e->dxdy = (x1 - x0) / (y1 - y0);
        e->ks = (long long)ks; e->ke = (long long)ke; e->dir = dir;
    }
    return 0;
}

static void add_span(float *row, int width, double a, double b, double weight) {
    a = clamp_index(a, width);
    b = clamp_index(b, width);
    if (b <= a) return;
    int ia = (int)floor(a), ib = (int)floor(b);
    if (ia == ib) {
        row[ia] += (float)((b - a) * weight);
        return;
    }
    row[ia] += (float)((ia + 1 - a) * weight);
    for (int i = ia + 1; i < ib; i++) row[i] += (float)weight;
    if (ib < width) row[ib] += (float)((b - ib) * weight);
}

static void insertion_sort(Crossing *c, ptrdiff_t n) {
    for (ptrdiff_t i = 1; i < n; i++) {
        Crossing key = c[i];
        ptrdiff_t j = i - 1;
        while (j >= 0 && c[j].x > key.x) {
            c[j + 1] = c[j];
            j--;
        }
        c[j + 1] = key;
    }
}

/* Accumulate coverage of the edge list into buf (rows of width floats); -1 when out of memory. */
static int rasterize_edges(float *buf, int width, EdgeList *list, int rule, int samples) {
    ptrdiff_t count = list->count;
    if (count == 0) return 0;
    Edge *edges = list->items;
    qsort(edges, (size_t)count, sizeof(Edge), edge_cmp);
    ptrdiff_t *active = (ptrdiff_t *)malloc((size_t)count * sizeof(ptrdiff_t));
    Crossing *cross = (Crossing *)malloc((size_t)count * sizeof(Crossing));
    if (!active || !cross) {
        free(active);
        free(cross);
        return -1;
    }
    long long k_end = 0;
    for (ptrdiff_t i = 0; i < count; i++) if (edges[i].ke > k_end) k_end = edges[i].ke;
    double weight = 1.0 / samples;
    ptrdiff_t next = 0, n_active = 0;
    for (long long k = edges[0].ks; k < k_end; k++) {
        while (next < count && edges[next].ks <= k) active[n_active++] = next++;
        ptrdiff_t kept = 0;
        for (ptrdiff_t i = 0; i < n_active; i++) if (edges[active[i]].ke > k) active[kept++] = active[i];
        n_active = kept;
        if (n_active == 0) continue;
        double y = (k + SAMPLE_OFFSET) / samples;
        for (ptrdiff_t i = 0; i < n_active; i++) {
            const Edge *e = &edges[active[i]];
            cross[i].x = e->x0 + (y - e->y0) * e->dxdy;
            cross[i].dir = e->dir;
        }
        insertion_sort(cross, n_active);
        float *row = buf + (size_t)(k / samples) * (size_t)width;
        int winding = 0;
        for (ptrdiff_t i = 0; i + 1 < n_active; i++) {
            winding += cross[i].dir;
            int inside = rule == RULE_NONZERO ? winding != 0 : (winding & 1);
            if (inside) add_span(row, width, cross[i].x, cross[i + 1].x, weight);
        }
    }
    free(active);
    free(cross);
    return 0;
}

#endif
