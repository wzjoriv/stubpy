"""
Parsed signature model.
"""
from __future__ import annotations

import inspect
from dataclasses import dataclass

from ..._constants import KW_ONLY, POS_KW, POS_ONLY, VAR_KW, VAR_POS

__all__ = ["Param", "Signature"]


@dataclass(frozen=True)
class Param:
    """One parameter of a parsed signature.

    Attributes
    ----------
    name : str
        The parameter name.
    kind : inspect._ParameterKind
        The parameter kind.  Defaults to positional-or-keyword.
    annotation : str or None
        The annotation text, if any.
    default : str or None
        The default text (``...`` when unknown); ``None`` when there is none.

    Examples
    --------
    >>> Param("n", annotation="int", default="1").annotation
    'int'
    """

    name: str
    kind: inspect._ParameterKind = POS_KW
    annotation: str | None = None
    default: str | None = None


@dataclass(frozen=True)
class Signature:
    """A parsed signature.

    Attributes
    ----------
    params : tuple of Param
        The parameters in order.
    returns : str or None
        The return annotation text, if any.
    """

    params: tuple[Param, ...]
    returns: str | None = None

    @property
    def names(self) -> tuple[str, ...]:
        """The parameter names in order.

        Returns
        -------
        tuple of str
            One name per parameter.

        Examples
        --------
        >>> Signature((Param("a"), Param("b"))).names
        ('a', 'b')
        """
        return tuple(p.name for p in self.params)

    def is_generic(self) -> bool:
        """Report whether this is the uninformative ``(*args, **kwargs)`` placeholder.

        A leading ``self`` or ``cls`` is ignored.

        Returns
        -------
        bool
            ``True`` when the only parameters are ``*args`` and ``**kwargs``.

        Examples
        --------
        >>> Signature((Param("args", VAR_POS), Param("kwargs", VAR_KW))).is_generic()
        True
        >>> Signature((Param("a"),)).is_generic()
        False
        """
        kinds = [p.kind for p in self.params if p.name not in ("self", "cls")]
        return kinds == [VAR_POS, VAR_KW]

    def render(self) -> str:
        """Render the signature as stub text.

        Returns
        -------
        str
            Text such as ``(a: int, /, *, b: str = ...) -> float``.

        Examples
        --------
        >>> sig = Signature((Param("a", POS_ONLY, "int"), Param("b", KW_ONLY, "str", "...")), "float")
        >>> sig.render()
        '(a: int, /, *, b: str = ...) -> float'
        """
        parts: list[str] = []
        prev = None
        star_done = False
        for p in self.params:
            if prev == POS_ONLY and p.kind != POS_ONLY:
                parts.append("/")
            if p.kind == KW_ONLY and not star_done:
                parts.append("*")
                star_done = True
            if p.kind == VAR_POS:
                star_done = True
            prefix = "*" if p.kind == VAR_POS else "**" if p.kind == VAR_KW else ""
            text = prefix + p.name
            if p.annotation:
                text += f": {p.annotation}"
            if p.default is not None:
                text += f" = {p.default}" if p.annotation else f"={p.default}"
            parts.append(text)
            prev = p.kind
        if prev == POS_ONLY:
            parts.append("/")
        ret = f" -> {self.returns}" if self.returns else ""
        return f"({', '.join(parts)}){ret}"
