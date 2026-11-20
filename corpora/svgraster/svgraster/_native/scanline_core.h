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
#define BAND_ROWS 8
#define PARALLEL_MIN_BANDS 4

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

/* Coverage for sub-scanlines [k0, k1) using the edges that overlap them; -1 when out of memory. */
static int rasterize_band(float *buf, int width, const Edge *edges, ptrdiff_t count, long long k0, long long k1,
                          int rule, int samples) {
    ptrdiff_t n_cand = 0;
    while (n_cand < count && edges[n_cand].ks < k1) n_cand++;
    if (n_cand == 0) return 0;
    ptrdiff_t *cand = (ptrdiff_t *)malloc((size_t)n_cand * sizeof(ptrdiff_t));
    Crossing *cross = (Crossing *)malloc((size_t)n_cand * sizeof(Crossing));
    if (!cand || !cross) {
        free(cand);
        free(cross);
        return -1;
    }
    ptrdiff_t m = 0;
    for (ptrdiff_t i = 0; i < n_cand; i++) if (edges[i].ke > k0) cand[m++] = i;
    double weight = 1.0 / samples;
    for (long long k = k0; k < k1 && m > 0; k++) {
        ptrdiff_t n_active = 0;
        double y = (k + SAMPLE_OFFSET) / samples;
        for (ptrdiff_t i = 0; i < m; i++) {
            const Edge *e = &edges[cand[i]];
            if (e->ks > k || e->ke <= k) continue;
            cross[n_active].x = e->x0 + (y - e->y0) * e->dxdy;
            cross[n_active].dir = e->dir;
            n_active++;
        }
        if (n_active < 2) continue;
        insertion_sort(cross, n_active);
        float *row = buf + (size_t)(k / samples) * (size_t)width;
        int winding = 0;
        for (ptrdiff_t i = 0; i + 1 < n_active; i++) {
            winding += cross[i].dir;
            int inside = rule == RULE_NONZERO ? winding != 0 : (winding & 1);
            if (inside) add_span(row, width, cross[i].x, cross[i + 1].x, weight);
        }
    }
    free(cand);
    free(cross);
    return 0;
}

/* Accumulate coverage of the edge list into buf, in parallel bands of BAND_ROWS pixel rows. */
static int rasterize_edges(float *buf, int width, int height, EdgeList *list, int rule, int samples) {
    ptrdiff_t count = list->count;
    if (count == 0) return 0;
    Edge *edges = list->items;
    qsort(edges, (size_t)count, sizeof(Edge), edge_cmp);
    long long k_total = (long long)height * samples;
    long long band = (long long)BAND_ROWS * samples;
    int n_bands = (int)((k_total + band - 1) / band);
    int failed = 0, b;
#pragma omp parallel for schedule(dynamic) reduction(|:failed) if (n_bands >= PARALLEL_MIN_BANDS)
    for (b = 0; b < n_bands; b++) {
        long long k0 = (long long)b * band;
        long long k1 = k0 + band < k_total ? k0 + band : k_total;
        if (rasterize_band(buf, width, edges, count, k0, k1, rule, samples) < 0) failed |= 1;
    }
    return failed ? -1 : 0;
}

#endif
