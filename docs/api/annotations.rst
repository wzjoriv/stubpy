.. _api_annotations:

stubpy.annotations
==================

.. automodule:: stubpy.annotations
   :no-members:

.. rubric:: Core functions

.. autofunction:: stubpy.annotations.annotation_to_str
.. autofunction:: stubpy.annotations.format_param
.. autofunction:: stubpy.annotations.get_hints_for_method
.. autofunction:: stubpy.annotations.default_to_str

.. rubric:: Extending the dispatch table

New annotation kinds can be supported by registering a handler with the
internal ``_register`` decorator::

    from stubpy.annotations import _register
    from stubpy.context import StubContext

    @_register(lambda a: isinstance(a, MyAnnotationType))
    def _handle_my_annotation(annotation, ctx: StubContext) -> str:
        return f"MyAlias[{annotation.inner}]"

Built-in handlers (in dispatch order):

.. list-table::
   :widths: 35 65
   :header-rows: 1

   * - Predicate
     - Handles
   * - ``isinstance(a, str)``
     - String forward references, e.g. ``"Element"``
   * - ``isinstance(a, ForwardRef)``
     - :class:`typing.ForwardRef` objects
   * - ``a is type(None)``
     - ``NoneType`` → emits ``"None"``
   * - ``a is ...``
     - The ``Ellipsis`` singleton → emits ``"..."`` (used in ``Tuple[X, ...]``)
   * - ``isinstance(a, UnionType)``
     - PEP 604 ``str | int`` unions (Python 3.10+)
   * - ``isinstance(a, (TypeVar, ParamSpec, TypeVarTuple))``
     - TypeVar-like objects — uses ``__name__`` (avoids ``~T`` in Python 3.12+)
   * - ``isinstance(a, type)``
     - Plain classes — uses ``__name__``
   * - ``__origin__ is not None``
     - All subscripted typing generics (Union, Optional, Callable, Literal, …)
   * - ``_name is not None``
     - Bare unsubscripted aliases (``List``, ``Dict``, …)

.. rubric:: Alias preservation with Optional / union forms

When a registered alias (e.g. ``types.Color = Union[str, Tuple[...]]``) is
used as ``Optional[types.Color]`` or ``types.Color | None``, Python
constructs a new ``Union`` whose args include ``NoneType`` — losing the
``Color`` boundary.  Both ``_handle_pep604_union`` and the
``typing.Union`` branch of ``_handle_generic`` detect this case by
reconstructing the non-``None`` sub-union and checking the alias registry
on it before falling back to per-argument expansion.

When an alias appears inside a container generic such as
``Tuple[types.Color, types.Length]`` or ``List[types.Color]``, the
recursive call to :func:`annotation_to_str` on each argument handles
preservation naturally because Python does not flatten the args of
``tuple``/``list``/``Tuple``/``List`` subscriptions.

.. rubric:: AST raw-annotation override in ``format_param``

:func:`format_param` accepts an optional ``raw_ann_override`` string —
the annotation as written in source code, captured by the AST pre-pass
before Python evaluates it.  When the string contains a registered alias
module prefix (e.g. ``"types."``), it takes priority over the runtime
annotation.  This recovers alias names destroyed by ``typing.Union``
flattening (e.g. ``Union[types.Color, int]`` remains as-is instead of
expanding to ``Union[str, Tuple[...], int]``).
