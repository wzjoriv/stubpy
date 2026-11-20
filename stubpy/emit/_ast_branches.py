"""
Version-branch grouping of a class known only from source.
"""
from __future__ import annotations

import dataclasses
import textwrap

from stubpy.analysis.harvest.models import ClassInfo

from .branches import Unit, join_sections, weave


def branch_groups(ci: ClassInfo) -> list[tuple[tuple, ClassInfo]]:
    """Group a class's version-branched members by branch.

    Parameters
    ----------
    ci : ClassInfo
        The class.

    Returns
    -------
    list of tuple
        ``(branch, members)`` per version branch of the class body, in source
        order, where *members* is a copy of *ci* holding only that branch's members.

    See Also
    --------
    unbranched : The members outside any branch.

    Examples
    --------
    >>> from stubpy.analysis.harvest import ast_harvest
    >>> branch_groups(ast_harvest("class A:\\n    x: int").classes[0])
    []
    """
    groups: dict[tuple, ClassInfo] = {}
    for kind in ("attributes", "methods", "classes"):
        for item in getattr(ci, kind):
            if item.branch:
                group = groups.setdefault(item.branch, dataclasses.replace(ci, attributes=[], methods=[], classes=[]))
                getattr(group, kind).append(item)
    first = {path: min(i.lineno for k in ("attributes", "methods", "classes") for i in getattr(g, k))
             for path, g in groups.items()}
    return sorted(groups.items(), key=lambda item: first[item[0]])


def unbranched(ci: ClassInfo) -> ClassInfo:
    """Return a class without the members that sit in version branches.

    Parameters
    ----------
    ci : ClassInfo
        The class.

    Returns
    -------
    ClassInfo
        A copy holding only the unconditional attributes, methods and nested classes.

    See Also
    --------
    branch_groups : The members inside branches.
    """
    return dataclasses.replace(
        ci, attributes=[a for a in ci.attributes if not a.branch], methods=[m for m in ci.methods if not m.branch],
        classes=[c for c in ci.classes if not c.branch],
    )


def branch_lines(units: list[Unit], indent: str) -> list[str]:
    """Return the version blocks of *units*, indented.

    Parameters
    ----------
    units : list of Unit
        The branch members' stubs, in source order.
    indent : str
        The indentation applied to every line.

    Returns
    -------
    list of str
        The lines; empty when there are no units.

    See Also
    --------
    stubpy.emit.branches.weave : Builds the ``if`` chains.

    Examples
    --------
    >>> branch_lines([Unit("x: int", True), Unit("y: str", True)], "  ")
    ['  x: int', '  y: str']
    """
    text = join_sections(weave(units))
    return textwrap.indent(text, indent).split("\n") if text else []
