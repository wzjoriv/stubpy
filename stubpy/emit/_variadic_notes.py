"""
Diagnostics for variadics a signature keeps: unresolved ``**kwargs`` and overloaded compiled callees.
"""
from __future__ import annotations

from typing import Any

from stubpy._constants import VAR_KW, VAR_POS
from stubpy.compiled.runtime import overload_count
from stubpy.resolve import ParamWithHints, local_target
from stubpy.state.diagnostics import Stage


def warn_dynamic_kwargs(
    name: str, params_with_hints: list[ParamWithHints], ast_info: Any, ctx: Any,
) -> None:
    """Report a ``**kwargs`` that stays in the stub although the function forwards it.

    A callee that cannot be named statically gives a WARNING. Named
    callees that left ``**kwargs`` open (unresolvable, or accepting
    arbitrary keywords themselves) give an INFO, a WARNING under ``verbose``.

    Parameters
    ----------
    name : str
        The qualified function name, used as the diagnostic symbol.
    params_with_hints : list of tuple
        The final ``(inspect.Parameter, hints)`` pairs; nothing is reported without a ``**kwargs``.
    ast_info : object
        The function's AST info, which records where ``**kwargs`` is forwarded.
    ctx : StubContext
        The run context that collects the diagnostics.

    Returns
    -------
    None

    See Also
    --------
    note_compiled_overloads : The equivalent report for overloaded compiled callees.

    Examples
    --------
    >>> import inspect
    >>> from types import SimpleNamespace
    >>> from stubpy.state.context import StubContext
    >>> ctx = StubContext()
    >>> kw = inspect.Parameter("kw", inspect.Parameter.VAR_KEYWORD)
    >>> warn_dynamic_kwargs("f", [(kw, {})], SimpleNamespace(kwargs_dynamic=True), ctx)
    >>> len(ctx.diagnostics.warnings)
    1
    """
    if not any(p.kind == VAR_KW for p, _ in params_with_hints):
        return
    if getattr(ast_info, "kwargs_dynamic", False):
        ctx.diagnostics.warning(
            Stage.RESOLVE, name,
            "**kwargs is passed to a callee that cannot be resolved statically; kept as **kwargs",
        )
        return
    targets = list(getattr(ast_info, "kwargs_forwarded_to", []) or []) + list(
        getattr(ast_info, "kwargs_method_targets", []) or []
    )
    if targets:
        report = ctx.diagnostics.warning if getattr(ctx.config, "verbose", False) else ctx.diagnostics.info
        report(
            Stage.RESOLVE, name,
            f"**kwargs forwarded to {', '.join(targets)} is kept: the callee could not be resolved "
            "or accepts arbitrary keywords itself",
        )


def _first_definition(cls: type, method_name: str) -> Any:
    """The *method_name* of the first class after *cls* in its MRO that defines it."""
    for parent in cls.__mro__[1:]:
        if method_name in vars(parent):
            return vars(parent)[method_name]
    return None


def forwarding_callees(ast_info: Any, namespace: dict[str, Any], cls: type | None = None,
                       method_name: str = "") -> list[tuple[str, Any]]:
    """Return ``(label, callable)`` for each callee a function or method forwards its variadics to.

    A forward to the method's own name resolves to the first definition
    further up the MRO of *cls* (labelled ``super().name``); a forwarded class resolves to its
    ``__init__``.

    Parameters
    ----------
    ast_info : object
        The AST info, which names the forwarded-to callees.
    namespace : dict of str to Any
        The module namespace the names resolve in.
    cls : type, optional
        The class owning the method. Defaults to None.
    method_name : str, optional
        The method's name. Defaults to ``""``.

    Returns
    -------
    list of tuple of (str, Any)
        The resolved callees; names that do not resolve are left out.

    Examples
    --------
    >>> from types import SimpleNamespace
    >>> from stubpy.analysis.harvest import ast_harvest
    >>> info = ast_harvest("def f(**kw):\\n    print(**kw)").functions[0]
    >>> forwarding_callees(info, {"print": print})
    [('print', <built-in function print>)]
    """
    names = list(getattr(ast_info, "kwargs_forwarded_to", []) or []) + list(
        getattr(ast_info, "args_forwarded_to", []) or [])
    found: list[tuple[str, Any]] = []
    for name in dict.fromkeys(names):
        if cls is not None and name == method_name:
            target = _first_definition(cls, method_name)
            if target is not None:
                found.append((f"super().{method_name}", target))
            continue
        target = local_target(ast_info, name, namespace) or namespace.get(name)
        if isinstance(target, type):
            init = vars(target).get("__init__") or _first_definition(target, "__init__")
            found.append((f"{name}.__init__", init))
        elif target is not None:
            found.append((name, target))
    return found


def note_compiled_overloads(name: str, params_with_hints: list[ParamWithHints],
                            callees: list[tuple[str, Any]], ctx: Any) -> None:
    """Record an INFO when variadics stay open because a callee is an overloaded compiled callable.

    Parameters
    ----------
    name : str
        The qualified function name, used as the diagnostic symbol.
    params_with_hints : list of tuple
        The final ``(inspect.Parameter, hints)`` pairs; nothing is recorded without ``*args`` or ``**kwargs``.
    callees : list of tuple of (str, Any)
        ``(label, callable)`` pairs from :func:`forwarding_callees`.
    ctx : StubContext
        The run context that collects the diagnostics.

    Returns
    -------
    None

    See Also
    --------
    warn_dynamic_kwargs : The report for unresolved ``**kwargs``.
    forwarding_callees : Finds the callees.
    """
    if not any(p.kind in (VAR_KW, VAR_POS) for p, _ in params_with_hints):
        return
    for label, target in callees:
        count = overload_count(target)
        if count > 1:
            ctx.diagnostics.info(
                Stage.RESOLVE, name,
                f"{label} is compiled with {count} overloads; *args / **kwargs are kept "
                "(overloads are not expanded into the caller)",
            )
