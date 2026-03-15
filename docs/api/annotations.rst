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
   * - ``isinstance(a, UnionType)``
     - PEP 604 ``str | int`` unions (Python 3.10+)
   * - ``isinstance(a, type)``
     - Plain classes — uses ``__name__``
   * - ``__origin__ is not None``
     - All subscripted typing generics (Union, Optional, Callable, Literal, …)
   * - ``_name is not None``
     - Bare unsubscripted aliases (``List``, ``Dict``, …)
