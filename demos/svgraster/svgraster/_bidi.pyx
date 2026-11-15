# cython: boundscheck=False, wraparound=False, cdivision=True, embedsignature=True
"""Bidi weak, neutral and implicit resolution over one isolating run sequence (Cython).

Mirrors :mod:`svgraster.shaping.bidi._weak`; the lists are copied into C
arrays, resolved without the GIL and written back in place.
"""
from cpython.mem cimport PyMem_Free, PyMem_Malloc

cdef enum BidiType:
    T_L, T_R, T_AL, T_EN, T_ES, T_ET, T_AN, T_CS, T_NSM, T_BN, T_B, T_S, T_WS, T_ON,
    T_LRE, T_LRO, T_RLE, T_RLO, T_PDF, T_LRI, T_RLI, T_FSI, T_PDI


cdef inline bint _neutral(int t) noexcept nogil:
    return t == T_B or t == T_S or t == T_WS or t == T_ON or t == T_LRI or t == T_RLI or t == T_FSI or t == T_PDI


cdef int* _load(list values, Py_ssize_t n) except NULL:
    cdef int* buf = <int*> PyMem_Malloc((n if n else 1) * sizeof(int))
    if buf == NULL:
        raise MemoryError()
    cdef Py_ssize_t i
    for i in range(n):
        buf[i] = values[i]
    return buf


cdef void _store(int* buf, list values, Py_ssize_t n):
    cdef Py_ssize_t i
    for i in range(n):
        values[i] = buf[i]


cdef void _weak(int* t, Py_ssize_t n, int sos) noexcept nogil:
    cdef Py_ssize_t i, j
    cdef int prev = sos, strong = sos
    for i in range(n):
        if t[i] == T_NSM:
            t[i] = T_ON if (prev == T_LRI or prev == T_RLI or prev == T_FSI or prev == T_PDI) else prev
        prev = t[i]
    for i in range(n):
        if t[i] == T_L or t[i] == T_R or t[i] == T_AL:
            strong = t[i]
        elif t[i] == T_EN and strong == T_AL:
            t[i] = T_AN
    for i in range(n):
        if t[i] == T_AL:
            t[i] = T_R
    for i in range(1, n - 1):
        if t[i] == T_ES and t[i - 1] == T_EN and t[i + 1] == T_EN:
            t[i] = T_EN
        elif t[i] == T_CS and t[i - 1] == t[i + 1] and (t[i - 1] == T_EN or t[i - 1] == T_AN):
            t[i] = t[i - 1]
    i = 0
    while i < n:
        if t[i] != T_ET:
            i += 1
            continue
        j = i
        while j < n and t[j] == T_ET:
            j += 1
        if (i > 0 and t[i - 1] == T_EN) or (j < n and t[j] == T_EN):
            while i < j:
                t[i] = T_EN
                i += 1
        i = j
    for i in range(n):
        if t[i] == T_ES or t[i] == T_ET or t[i] == T_CS:
            t[i] = T_ON
    strong = sos
    for i in range(n):
        if t[i] == T_L or t[i] == T_R:
            strong = t[i]
        elif t[i] == T_EN and strong == T_L:
            t[i] = T_L


cdef void _neutrals(int* t, Py_ssize_t n, int sos, int eos, int embedding) noexcept nogil:
    cdef Py_ssize_t i = 0, j
    cdef int before, after, fill
    while i < n:
        if not _neutral(t[i]):
            i += 1
            continue
        j = i
        while j < n and _neutral(t[j]):
            j += 1
        before = sos if i == 0 else (T_L if t[i - 1] == T_L else T_R)
        after = eos if j == n else (T_L if t[j] == T_L else T_R)
        fill = before if before == after else embedding
        while i < j:
            t[i] = fill
            i += 1


cdef void _implicit(int* t, int* lv, Py_ssize_t n) noexcept nogil:
    cdef Py_ssize_t i
    for i in range(n):
        if lv[i] & 1:
            if t[i] == T_L or t[i] == T_EN or t[i] == T_AN:
                lv[i] += 1
        elif t[i] == T_R:
            lv[i] += 1
        elif t[i] == T_AN or t[i] == T_EN:
            lv[i] += 2


def resolve_weak(list types, int sos):
    """W1-W7 in place on ``types``."""
    cdef Py_ssize_t n = len(types)
    cdef int* buf = _load(types, n)
    with nogil:
        _weak(buf, n, sos)
    _store(buf, types, n)
    PyMem_Free(buf)


def resolve_neutral(list types, int sos, int eos, int embedding):
    """N1-N2 in place on ``types``."""
    cdef Py_ssize_t n = len(types)
    cdef int* buf = _load(types, n)
    with nogil:
        _neutrals(buf, n, sos, eos, embedding)
    _store(buf, types, n)
    PyMem_Free(buf)


def resolve_implicit(list types, list levels):
    """I1-I2 in place on ``levels``."""
    cdef Py_ssize_t n = len(types)
    cdef int* t = _load(types, n)
    cdef int* lv = _load(levels, n)
    with nogil:
        _implicit(t, lv, n)
    _store(lv, levels, n)
    PyMem_Free(t)
    PyMem_Free(lv)
