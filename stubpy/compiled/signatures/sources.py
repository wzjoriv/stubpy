"""
Signatures from nanobind metadata, ``inspect`` and docstrings, best source first.
"""
from __future__ import annotations

import enum
import inspect
import re
from typing import Any

from ._text import default_text, normalize_type
from .models import Param, Signature
from .parse import docstring_signatures, parse_signature

__all__ = ["nanobind_signatures", "from_inspect", "signatures_of", "class_signatures"]

_NB_PLACEHOLDER = re.compile(r"\\(\d+)")


def nanobind_signatures(obj: Any) -> list[Signature]:
    """Read the signatures nanobind records in ``__nb_signature__``.

    Parameters
    ----------
    obj : Any
        The callable.

    Returns
    -------
    list of Signature
        One signature per entry; empty when *obj* has no such attribute.

    Examples
    --------
    >>> nanobind_signatures(len)
    []
    """
    entries = getattr(obj, "__nb_signature__", None)
    if not entries:
        return []
    found: list[Signature] = []
    for entry in entries:
        text = entry[0] if isinstance(entry, tuple) else entry
        defaults = entry[2] if isinstance(entry, tuple) and len(entry) > 2 and entry[2] else ()

        def fill(m: re.Match[str], defaults: tuple = defaults) -> str:
            idx = int(m.group(1))
            if idx < len(defaults):
                return value_text(defaults[idx])
            return "..."

        parsed = parse_signature(_NB_PLACEHOLDER.sub(fill, text))
        if parsed:
            found.append(parsed[1])
    return found


def value_text(value: Any) -> str:
    """Render a live value as default text.

    An enum member is qualified by its module (``pkg._ext.Mode.FAST``).

    Parameters
    ----------
    value : Any
        The default value.

    Returns
    -------
    str
        Source text for the value.

    Examples
    --------
    >>> value_text(3), value_text("a")
    ('3', "'a'")
    """
    if isinstance(value, enum.Enum):
        cls = type(value)
        try:
            exact = cls[value.name] is value
        except (KeyError, TypeError):
            exact = False
        if exact and "<" not in cls.__qualname__:
            return f"{cls.__module__}.{cls.__qualname__}.{value.name}"
    return default_text(repr(value))


def from_inspect(sig: inspect.Signature) -> Signature:
    """Convert an :class:`inspect.Signature` into a :class:`Signature`.

    Annotations are kept only when they are strings.

    Parameters
    ----------
    sig : inspect.Signature
        The signature to convert.

    Returns
    -------
    Signature
        The converted signature.

    Examples
    --------
    >>> import inspect
    >>> def f(a, b=2): ...
    >>> from_inspect(inspect.signature(f)).render()
    '(a, b=2)'
    """
    params = []
    for p in sig.parameters.values():
        ann = p.annotation if isinstance(p.annotation, str) else None
        default = None if p.default is inspect.Parameter.empty else value_text(p.default)
        params.append(Param(p.name, p.kind, normalize_type(ann), default))
    ret = sig.return_annotation if isinstance(sig.return_annotation, str) else None
    return Signature(tuple(params), normalize_type(ret))


def signatures_of(obj: Any, name: str | None = None) -> list[Signature]:
    """Find the best available signatures of a compiled callable.

    Sources are tried in order: nanobind metadata, the docstring, then
    :func:`inspect.signature`.  A generic ``(*args, **kwargs)`` result is
    treated as nothing.

    Parameters
    ----------
    obj : Any
        The callable.
    name : str, optional
        The name docstring signature lines start with.  Defaults to the
        callable's ``__name__``.

    Returns
    -------
    list of Signature
        The signatures found; empty when there is no useful one.

    See Also
    --------
    class_signatures : The same for a class's constructor.

    Examples
    --------
    >>> def f(a, b=2): ...
    >>> [s.render() for s in signatures_of(f)]
    ['(a, b=2)']
    """
    name = name or getattr(obj, "__name__", "")
    found = nanobind_signatures(obj)
    if found:
        return found
    doc_sigs = docstring_signatures(name, getattr(obj, "__doc__", None))
    try:
        insp = from_inspect(inspect.signature(obj))
    except (TypeError, ValueError):
        insp = None
    useful = [s for s in doc_sigs if not s.is_generic()]
    if insp is not None and not insp.is_generic() and insp.returns is None and len(doc_sigs) == 1:
        doc = doc_sigs[0]
        if doc.returns and _untyped(doc) and (doc.is_generic() or _same_names(doc, insp)):
            return [Signature(insp.params, doc.returns)]
    if useful:
        return useful
    if insp is not None and not insp.is_generic():
        return [insp]
    return []


def _untyped(sig: Signature) -> bool:
    """True when no parameter of *sig* is annotated (a C API ``name(a, b) -> R`` line)."""
    return not any(p.annotation for p in sig.params)


def _same_names(a: Signature, b: Signature) -> bool:
    """True when *a* and *b* name the same parameters, receivers ignored."""
    return [n for n in a.names if n not in ("self", "cls")] == [n for n in b.names if n not in ("self", "cls")]


def class_signatures(cls: type) -> list[Signature]:
    """Read constructor signatures written on the class itself.

    Taken from ``__text_signature__`` or from ``Name(...)`` lines in the
    class docstring.

    Parameters
    ----------
    cls : type
        The class.

    Returns
    -------
    list of Signature
        The constructor signatures; empty when none are written.

    See Also
    --------
    signatures_of : The same for a callable.

    Examples
    --------
    >>> class Vec:
    ...     "Vec(x: float, y: float)"
    >>> [s.render() for s in class_signatures(Vec)]
    ['(x: float, y: float)']
    """
    try:
        if getattr(cls, "__text_signature__", None):
            return [from_inspect(inspect.signature(cls))]
    except (TypeError, ValueError):
        pass
    try:
        doc = cls.__doc__
    except Exception:
        doc = None
    return [s for s in docstring_signatures(cls.__name__, doc) if not s.is_generic()]
