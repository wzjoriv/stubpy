"""Call-site scanning: where a function body forwards its ``*args`` / ``**kwargs``."""
from __future__ import annotations

import ast
from collections.abc import Iterator
from dataclasses import dataclass, field


@dataclass
class ForwardingTargets:
    """Forwarding call sites found in one function body."""
    kw_targets: list[str] = field(default_factory=list)
    pos_targets: list[str] = field(default_factory=list)
    kw_method_targets: list[str] = field(default_factory=list)
    args_method_targets: list[str] = field(default_factory=list)
    kw_positional_skips: dict[str, int] = field(default_factory=dict)
    kw_explicit_names: dict[str, set] = field(default_factory=dict)


def call_func_name(call: ast.Call) -> str:
    """Return the bare function name of a call (``f`` or ``obj.f``), or ``""``."""
    func = call.func
    if isinstance(func, ast.Name):
        return func.id
    if isinstance(func, ast.Attribute):
        return func.attr
    return ""


def iter_body_calls(fn_node: ast.FunctionDef | ast.AsyncFunctionDef) -> Iterator[ast.Call]:
    """Yield the calls in *fn_node*'s body, skipping nested function and class scopes."""
    def _walk(node: ast.AST) -> Iterator[ast.Call]:
        for child in ast.iter_child_nodes(node):
            if isinstance(child, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
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


def scan_forwarding(node: ast.FunctionDef | ast.AsyncFunctionDef) -> ForwardingTargets:
    """Find the calls in *node* that receive its ``**kwargs`` or ``*args``."""
    found = ForwardingTargets()
    kwargs_name = node.args.kwarg.arg if node.args.kwarg else None
    varargs_name = node.args.vararg.arg if node.args.vararg else None
    if not (kwargs_name or varargs_name):
        return found

    for call in iter_body_calls(node):
        fname = call_func_name(call)
        if not fname:
            continue

        if kwargs_name:
            has_kw_fwd = any(
                kw.arg is None
                and isinstance(kw.value, ast.Name)
                and kw.value.id == kwargs_name
                for kw in call.keywords
            )
            if has_kw_fwd:
                target_list = found.kw_method_targets if _is_self_call(call) else found.kw_targets
                if fname not in target_list:
                    target_list.append(fname)
                pos_count = sum(1 for a in call.args if not isinstance(a, ast.Starred))
                found.kw_positional_skips[fname] = max(
                    found.kw_positional_skips.get(fname, 0), pos_count
                )
                explicit = {kw.arg for kw in call.keywords if kw.arg is not None}
                found.kw_explicit_names.setdefault(fname, set()).update(explicit)

        if varargs_name:
            has_pos_fwd = any(
                isinstance(arg, ast.Starred)
                and isinstance(arg.value, ast.Name)
                and arg.value.id == varargs_name
                for arg in call.args
            )
            if has_pos_fwd:
                target_list = found.args_method_targets if _is_self_call(call) else found.pos_targets
                if fname not in target_list:
                    target_list.append(fname)

    return found
