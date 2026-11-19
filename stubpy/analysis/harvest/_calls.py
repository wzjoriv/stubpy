"""Call-site scanning: where a function body forwards its ``*args`` / ``**kwargs``."""
from __future__ import annotations

import ast
from collections.abc import Iterator
from dataclasses import dataclass, field

from ._replacers import fields_target


@dataclass
class ForwardingTargets:
    """Forwarding call sites found in one function body."""
    kw_targets: list[str] = field(default_factory=list)
    pos_targets: list[str] = field(default_factory=list)
    kw_method_targets: list[str] = field(default_factory=list)
    args_method_targets: list[str] = field(default_factory=list)
    kw_positional_skips: dict[str, int] = field(default_factory=dict)
    kw_explicit_names: dict[str, set] = field(default_factory=dict)
    kw_unknown_starred: set[str] = field(default_factory=set)
    kw_consumed: dict[str, str | None] = field(default_factory=dict)
    kw_injected: set[str] = field(default_factory=set)
    kw_dynamic: bool = False


def call_func_name(call: ast.Call) -> str:
    """Return the target name of a call, or ``""`` when it cannot be named statically.

    ``f(...)`` gives ``f`` and ``mod.sub.f(...)`` gives ``mod.sub.f``;
    ``self.f(...)`` and calls on other expressions give ``f``; ``self.attr.f(...)`` gives ``self.attr.f``;
    ``type(self)(...)`` gives ``cls``; ``Cls(...).m(...)`` gives ``Cls().m``
    and ``Cls.m(self, ...)`` gives ``Cls.m``.
    """
    func = call.func
    if isinstance(func, ast.Name):
        return func.id
    if (
        isinstance(func, ast.Call)
        and isinstance(func.func, ast.Name)
        and func.func.id == "type"
        and len(func.args) == 1
        and isinstance(func.args[0], ast.Name)
        and func.args[0].id in ("self", "cls")
    ):
        return "cls"
    if isinstance(func, ast.Attribute):
        owner = func.value
        if isinstance(owner, ast.Call) and isinstance(owner.func, ast.Name) and owner.func.id[:1].isupper():
            return f"{owner.func.id}().{func.attr}"
        if (
            isinstance(owner, ast.Name)
            and owner.id[:1].isupper()
            and call.args
            and isinstance(call.args[0], ast.Name)
            and call.args[0].id in ("self", "cls")
        ):
            return f"{owner.id}.{func.attr}"
        chain = _name_chain(func)
        if chain is not None and (chain.split(".")[0] not in ("self", "cls") or chain.count(".") == 2):
            return chain
        return func.attr
    return ""


def _name_chain(node: ast.expr) -> str | None:
    """Return ``a.b.c`` for attributes rooted at a name, else ``None``."""
    parts: list[str] = []
    while isinstance(node, ast.Attribute):
        parts.append(node.attr)
        node = node.value
    return ".".join([node.id, *reversed(parts)]) if isinstance(node, ast.Name) else None


def receives_self(call: ast.Call) -> bool:
    """True when the first positional argument is ``self`` / ``cls`` (``Base.m(self, ...)``)."""
    return bool(call.args) and isinstance(call.args[0], ast.Name) and call.args[0].id in ("self", "cls")


def iter_body_calls(fn_node: ast.FunctionDef | ast.AsyncFunctionDef) -> Iterator[ast.Call]:
    """Yield the calls in *fn_node*'s body, skipping nested function and class scopes."""
    def _walk(node: ast.AST) -> Iterator[ast.Call]:
        for child in ast.iter_child_nodes(node):
            if isinstance(child, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef, ast.Lambda)):
                continue
            if isinstance(child, ast.Call):
                yield child
            yield from _walk(child)

    yield from _walk(fn_node)


def _is_self_call(call: ast.Call) -> bool:
    """Return ``True`` for ``self.X(...)`` and ``cls.X(...)`` calls."""
    return (
        isinstance(call.func, ast.Attribute)
        and isinstance(call.func.value, ast.Name)
        and call.func.value.id in ("self", "cls")
    )


def _is_name(node: ast.AST, name: str | None) -> bool:
    return name is not None and isinstance(node, ast.Name) and node.id == name


def _const_key(node: ast.AST) -> str | None:
    return node.value if isinstance(node, ast.Constant) and isinstance(node.value, str) else None


def _scan_kwargs_edits(node: ast.FunctionDef | ast.AsyncFunctionDef, kwargs_name: str, found: ForwardingTargets) -> None:
    """Record keys popped from or deleted in ``**kwargs`` (consumed) and keys assigned into it (injected).

    ``kwargs.setdefault(key, v)`` is neither: the caller may still pass *key*.
    """
    for sub in ast.walk(node):
        if (
            isinstance(sub, ast.Call)
            and isinstance(sub.func, ast.Attribute)
            and _is_name(sub.func.value, kwargs_name)
            and sub.args
        ):
            key = _const_key(sub.args[0])
            if key is None:
                continue
            if sub.func.attr == "pop":
                default = ast.unparse(sub.args[1]) if len(sub.args) > 1 else None
                found.kw_consumed.setdefault(key, default)
        elif isinstance(sub, ast.Delete):
            for target in sub.targets:
                if isinstance(target, ast.Subscript) and _is_name(target.value, kwargs_name):
                    key = _const_key(target.slice)
                    if key is not None:
                        found.kw_consumed.setdefault(key, "...")
        elif isinstance(sub, (ast.Assign, ast.AugAssign)):
            targets = sub.targets if isinstance(sub, ast.Assign) else [sub.target]
            for target in targets:
                if isinstance(target, ast.Subscript) and _is_name(target.value, kwargs_name):
                    key = _const_key(target.slice)
                    if key is not None:
                        found.kw_injected.add(key)


def merged_keys(node: ast.expr, kwargs_name: str) -> set[str] | None:
    """Return the keys a ``{**defaults, **kwargs, "key": v}`` merge fixes after ``**kwargs``; ``None`` for other values.

    Keys set before ``**kwargs`` (by literal or by another ``**x``) can still be passed by the caller.
    """
    if not isinstance(node, ast.Dict):
        return None
    pairs = list(zip(node.keys, node.values, strict=True))
    at = next((i for i, (k, v) in enumerate(pairs) if k is None and _is_name(v, kwargs_name)), None)
    if at is None:
        return None
    later = pairs[at + 1:]
    if any(k is None or _const_key(k) is None for k, _ in later):
        return None
    return {_const_key(k) for k, _ in later}


def _record_kw_call(call: ast.Call, fname: str, varargs_name: str | None, found: ForwardingTargets,
                    kwargs_name: str | None = None) -> None:
    """Record a call that receives ``**kwargs``: positional args bound, unknown ``*x`` and explicit keywords."""
    target_list = found.kw_method_targets if _is_self_call(call) else found.kw_targets
    if fname not in target_list:
        target_list.append(fname)
    args = list(call.args)
    if "." in fname and not fname.split(".")[0].endswith(")") and receives_self(call):
        args = args[1:]
    pos_count = sum(1 for a in args if not isinstance(a, ast.Starred))
    found.kw_positional_skips[fname] = max(found.kw_positional_skips.get(fname, 0), pos_count)
    if any(isinstance(a, ast.Starred) and not _is_name(a.value, varargs_name) for a in args):
        found.kw_unknown_starred.add(fname)
    explicit = {kw.arg for kw in call.keywords if kw.arg is not None}
    for kw in call.keywords:
        if kw.arg is None and kwargs_name is not None:
            explicit |= merged_keys(kw.value, kwargs_name) or set()
    found.kw_explicit_names.setdefault(fname, set()).update(explicit)


def _star_unpacks(node: ast.FunctionDef | ast.AsyncFunctionDef, varargs_name: str | None) -> dict[str, list[str]]:
    """``{rest: [first, ...]}`` for each ``first, ..., *rest = args`` statement in the function body."""
    found: dict[str, list[str]] = {}
    for stmt in node.body if varargs_name else []:
        if not (isinstance(stmt, ast.Assign) and len(stmt.targets) == 1 and _is_name(stmt.value, varargs_name)):
            continue
        target = stmt.targets[0]
        if not isinstance(target, (ast.Tuple, ast.List)):
            continue
        elts = target.elts
        stars = [i for i, e in enumerate(elts) if isinstance(e, ast.Starred)]
        if stars != [len(elts) - 1] or not isinstance(elts[-1].value, ast.Name):
            continue
        if all(isinstance(e, ast.Name) for e in elts[:-1]):
            found[elts[-1].value.id] = [e.id for e in elts[:-1]]
    return found


def _rejoined(call: ast.Call, varargs_name: str | None, unpacks: dict[str, list[str]]) -> ast.Call:
    """*call* with ``first, *rest`` (split from ``*args`` by :func:`_star_unpacks`) written back as ``*args``."""
    args = list(call.args)
    for i, arg in enumerate(args):
        if not (isinstance(arg, ast.Starred) and isinstance(arg.value, ast.Name) and arg.value.id in unpacks):
            continue
        head = unpacks[arg.value.id]
        start = i - len(head)
        if start >= 0 and all(isinstance(a, ast.Name) and a.id == n for a, n in zip(args[start:i], head, strict=True)):
            star = ast.Starred(value=ast.Name(id=varargs_name, ctx=ast.Load()), ctx=ast.Load())
            new = ast.Call(func=call.func, args=[*args[:start], star, *args[i + 1:]], keywords=call.keywords)
            return ast.copy_location(new, call)
    return call


def scan_forwarding(node: ast.FunctionDef | ast.AsyncFunctionDef) -> ForwardingTargets:
    """Find the calls in *node* that receive its ``**kwargs`` or ``*args``, and edits to ``**kwargs``."""
    found = ForwardingTargets()
    kwargs_name = node.args.kwarg.arg if node.args.kwarg else None
    varargs_name = node.args.vararg.arg if node.args.vararg else None
    if not (kwargs_name or varargs_name):
        return found
    if kwargs_name:
        _scan_kwargs_edits(node, kwargs_name, found)

    unpacks = _star_unpacks(node, varargs_name)
    for call in iter_body_calls(node):
        call = _rejoined(call, varargs_name, unpacks)
        fname = call_func_name(call)
        kw_forwarded = kwargs_name is not None and any(
            kw.arg is None and (_is_name(kw.value, kwargs_name) or merged_keys(kw.value, kwargs_name) is not None)
            for kw in call.keywords
        )
        kw_in_expression = kwargs_name is not None and any(
            kw.arg is None and not _is_name(kw.value, kwargs_name) and merged_keys(kw.value, kwargs_name) is None
            and any(_is_name(n, kwargs_name) for n in ast.walk(kw.value))
            for kw in call.keywords
        )
        if kw_in_expression or (kw_forwarded and not fname):
            found.kw_dynamic = True
        if not fname:
            continue
        copied = fields_target(call, fname, node) if kw_forwarded else None
        if copied is not None:
            if copied not in found.kw_targets:
                found.kw_targets.append(copied)
            found.kw_explicit_names.setdefault(copied, set()).update(
                kw.arg for kw in call.keywords if kw.arg is not None)
            continue
        if kw_forwarded:
            _record_kw_call(call, fname, varargs_name, found, kwargs_name)

        if varargs_name and any(
            isinstance(arg, ast.Starred) and _is_name(arg.value, varargs_name) for arg in call.args
        ):
            target_list = found.args_method_targets if _is_self_call(call) else found.pos_targets
            if fname not in target_list:
                target_list.append(fname)
            if not kw_forwarded:
                args = call.args[1:] if "." in fname and receives_self(call) else call.args
                before = next(i for i, a in enumerate(args) if isinstance(a, ast.Starred))
                found.kw_positional_skips[fname] = max(found.kw_positional_skips.get(fname, 0), before)

    return found
